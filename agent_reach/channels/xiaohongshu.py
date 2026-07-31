# -*- coding: utf-8 -*-
"""XiaoHongShu — multi-backend: OpenCLI / xiaohongshu-mcp / xhs-cli.

Backend order encodes the recommendation, and probing order makes the
environment split automatic: OpenCLI needs a desktop Chrome so it simply
never probes alive on a server, where xiaohongshu-mcp (self-contained
headless browser) takes over after an explicit Cookie-Editor import.
xhs-cli (upstream unmaintained since
2026-03) keeps working for existing installs as the last candidate.
"""

import json
import shutil
import time
import urllib.error
import urllib.request

from agent_reach.utils.paths import (
    PrivatePathError,
    read_small_text_no_follow,
    user_home,
)

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config

_MCP_ENDPOINT = "http://localhost:18060/mcp"
_MCP_INSTALL_URL = "https://github.com/xpzouying/xiaohongshu-mcp"
_XHS_COOKIE_TTL_SECONDS = 7 * 86400
_MAX_XHS_COOKIE_BYTES = 1024 * 1024


def _mcp_service_reachable(timeout: int = 3) -> bool:
    """True if the xiaohongshu-mcp HTTP service answers on localhost.

    Any HTTP response counts (the MCP endpoint replies 405 to GET) —
    we only care that the service is up. Proxies are bypassed explicitly:
    localhost must never be routed through HTTP_PROXY.
    """
    req = urllib.request.Request(_MCP_ENDPOINT, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        opener.open(req, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True  # 405/404 etc. — service is alive
    except Exception:
        return False


def format_xhs_result(data):
    """Clean XHS API response, keeping only useful fields.

    Handles both single note objects and lists of notes (search results).
    Drastically reduces token usage by stripping structural redundancy (#134).
    """
    if isinstance(data, list):
        return [_clean_note(item) for item in data]
    if isinstance(data, dict):
        # Handle search_feeds wrapper: {"items": [...]} or {"data": {"items": [...]}}
        items = None
        if "items" in data:
            items = data["items"]
        elif "data" in data and isinstance(data.get("data"), dict):
            items = data["data"].get("items") or data["data"].get("notes")
        if items and isinstance(items, list):
            return [_clean_note(item) for item in items]
        # Single note
        return _clean_note(data)
    return data


def _clean_note(note):
    """Extract useful fields from a single XHS note/feed item."""
    if not isinstance(note, dict):
        return note

    # Some responses nest the note under "note_card" or "note"
    inner = note.get("note_card") or note.get("note") or note

    result = {}

    # Basic info
    for key in ("id", "note_id", "xsec_token", "title", "desc", "type", "time"):
        if key in inner:
            result[key] = inner[key]

    # Content (may be in desc or content)
    if "content" in inner and "desc" not in result:
        result["content"] = inner["content"]

    # Author
    user = inner.get("user") or inner.get("author")
    if isinstance(user, dict):
        result["user"] = {
            k: user[k] for k in ("nickname", "user_id", "nick_name") if k in user
        }

    # Engagement metrics
    interact = inner.get("interact_info") or inner.get("note_interact_info") or {}
    if isinstance(interact, dict):
        for key in ("liked_count", "collected_count", "comment_count", "share_count"):
            if key in interact:
                result[key] = interact[key]
    # Also check top-level (some API formats)
    for key in ("liked_count", "collected_count", "comment_count", "share_count"):
        if key in inner and key not in result:
            result[key] = inner[key]

    # Images — just URLs
    images = inner.get("image_list") or inner.get("images_list") or []
    if isinstance(images, list):
        urls = []
        for img in images:
            if isinstance(img, dict):
                url = img.get("url") or img.get("url_default") or img.get("original")
                if url:
                    urls.append(url)
            elif isinstance(img, str):
                urls.append(img)
        if urls:
            result["images"] = urls

    # Tags
    tags = inner.get("tag_list") or inner.get("tags") or []
    if isinstance(tags, list):
        tag_names = []
        for t in tags:
            if isinstance(t, dict) and "name" in t:
                tag_names.append(t["name"])
            elif isinstance(t, str):
                tag_names.append(t)
        if tag_names:
            result["tags"] = tag_names

    # Comments (if present, e.g. from get_feed_detail with comments)
    comments = inner.get("comments") or []
    if isinstance(comments, list) and comments:
        result["comments"] = [_clean_comment(c) for c in comments]

    return result


def _clean_comment(comment):
    """Extract useful fields from a comment."""
    if not isinstance(comment, dict):
        return comment
    result = {}
    if "content" in comment:
        result["content"] = comment["content"]
    user = comment.get("user_info") or comment.get("user")
    if isinstance(user, dict):
        result["user"] = user.get("nickname") or user.get("nick_name", "")
    for key in ("like_count", "sub_comment_count"):
        if key in comment:
            result[key] = comment[key]
    return result


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记"
    backends = ["OpenCLI", "xiaohongshu-mcp", "xhs-cli (xiaohongshu-cli)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaohongshu.com", "xhslink.com")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        If none is fully usable, the first fixable candidate (warn) is
        reported, so the user gets one actionable prescription instead
        of three half-relevant ones.
        """
        self.active_backend = None
        findings = []  # (backend, status, message)

        for backend in self.ordered_backends(config):
            if backend == "OpenCLI":
                result = self._check_opencli()
            elif backend == "xiaohongshu-mcp":
                result = self._check_mcp()
            else:
                result = self._check_xhs_cli()
            if result is None:
                continue  # not installed — not a candidate right now
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:  # only broken candidates left
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "未安装任何小红书后端。推荐：\n"
            "  桌面：agent-reach install --channels opencli\n"
            "       （复用 Chrome 登录态，刷过小红书即零配置可用）\n"
            f"  服务器：xiaohongshu-mcp：{_MCP_INSTALL_URL}\n"
            "       登录只使用 Cookie-Editor 明确导出：\n"
            "       agent-reach configure xhs-cookies '<Cookie-Editor export>'"
        )

    def _check_opencli(self):
        """OpenCLI candidate. None = not installed."""
        from agent_reach.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "warn", (
                "OpenCLI 桥接已连接，但小红书登录态和实际命令未实时验证；"
                "Doctor 不执行平台命令，因此当前不标记为可用。"
            )
        return "warn", st.hint

    def _check_mcp(self):
        """xiaohongshu-mcp candidate. None = service not running."""
        if not _mcp_service_reachable():
            return None
        if not shutil.which("mcporter"):
            return "warn", (
                "xiaohongshu-mcp 服务可达，但 mcporter 未安装，Doctor 未接入"
                "该服务。先安装：npm install -g mcporter"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter 配置检查失败：{exc}"
        if "xiaohongshu" in inspection.server_names:
            return "warn", (
                "xiaohongshu-mcp 服务可达且已接入 mcporter，但 Doctor "
                "未验证登录态，不能据此宣称笔记功能可用。若未登录，用 "
                "Cookie-Editor 导出后运行 agent-reach configure xhs-cookies"
            )
        if inspection.imports_unchecked:
            return "warn", (
                "xiaohongshu-mcp 服务可达；mcporter 本地配置未发现"
                " xiaohongshu，且 editor imports 未展开，Doctor 当前未验证接入。"
            )
        return "warn", (
            "xiaohongshu-mcp 服务在跑但 mcporter 未接入。运行：\n"
            f"  mcporter config add xiaohongshu {_MCP_ENDPOINT} --scope home"
        )

    def _check_xhs_cli(self):
        """Inspect saved xhs-cli cookies without invoking browser extraction."""
        if not shutil.which("xhs"):
            return None
        cookie_path = user_home() / ".xiaohongshu-cli" / "cookies.json"
        try:
            payload = read_small_text_no_follow(
                cookie_path,
                max_bytes=_MAX_XHS_COOKIE_BYTES,
            )
        except PrivatePathError as exc:
            return "warn", (
                f"xhs-cli 已安装，但 cookies.json 无法安全读取：{exc}。"
            )
        except OSError:
            return "warn", (
                "xhs-cli 已安装，但 cookies.json 无法安全读取；"
                "Doctor 未执行会自动提取浏览器 Cookie 的 `xhs status`。"
            )
        if payload is None:
            return self._xhs_cookie_hint()
        try:
            data = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            return "warn", (
                "xhs-cli 已安装，但保存的 cookies.json 无法安全解析；"
                "Doctor 未执行会自动提取浏览器 Cookie 的 `xhs status`。"
            )
        if not isinstance(data, dict) or not data.get("a1"):
            return self._xhs_cookie_hint()
        saved_at = data.get("saved_at")
        if isinstance(saved_at, (int, float)) and (
            time.time() - saved_at > _XHS_COOKIE_TTL_SECONDS
        ):
            return "warn", (
                "xhs-cli 已安装，保存的 Cookie 已超过 7 天；Doctor 不会让"
                "上游自动读取浏览器或刷新文件，请用 Cookie-Editor 明确更新。"
            )
        return "warn", (
            "xhs-cli 已安装并检测到显式保存的 Cookie；Doctor 为避免上游"
            "自动读取浏览器或改写 Cookie，不执行 `xhs status`，未实时验证。"
        )

    @staticmethod
    def _xhs_cookie_hint():
        return "warn", (
            "xhs-cli 已安装但没有可用的显式 Cookie。不要运行会自动读取"
            "浏览器的 `xhs login/status`；请迁移到 xiaohongshu-mcp，"
            "再用 Cookie-Editor 导出并运行 "
            "agent-reach configure xhs-cookies。"
        )
