# -*- coding: utf-8 -*-
"""XiaoHongShu — multi-backend: OpenCLI / xiaohongshu-mcp / xhs-cli.

Backend order encodes the recommendation, and probing order makes the
environment split automatic: OpenCLI needs a desktop Chrome so it simply
never probes alive on a server, where xiaohongshu-mcp (self-contained
headless browser) takes over. xhs-cli (upstream unmaintained since
2026-03) keeps working for existing installs as the last candidate.
"""

import urllib.error
import urllib.request

from agent_reach.probe import probe_command

from .base import Channel

_MCP_ENDPOINT = "http://localhost:18060/mcp"
_MCP_INSTALL_URL = "https://github.com/xpzouying/xiaohongshu-mcp"


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
    description = "XiaoHongShu (Little Red Book) posts"
    backends = ["OpenCLI", "xiaohongshu-mcp", "xhs-cli (xiaohongshu-cli)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "xiaohongshu.com" in d or "xhslink.com" in d

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
                    self.active_backend = backend
                    return status, message

        if findings:  # only broken candidates left
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "No XiaoHongShu backend installed. Recommend:\n"
            "  Desktop: agent-reach install --channels opencli\n"
            "       (reuses Chrome login session, zero-config if you've browsed XHS)\n"
            f"  Server: xiaohongshu-mcp (includes headless browser + QR login): {_MCP_INSTALL_URL}"
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
            return "ok", (
                "OpenCLI available (reuses browser login session). Usage: "
                "opencli xiaohongshu search/note/comments/feed -f yaml"
            )
        return "warn", st.hint

    def _check_mcp(self):
        """xiaohongshu-mcp candidate. None = service not running."""
        if not _mcp_service_reachable():
            return None
        mcporter = probe_command(
            "mcporter", ["config", "list"], timeout=10, package="mcporter"
        )
        if mcporter.ok and "xiaohongshu" in mcporter.output:
            return "ok", (
                "xiaohongshu-mcp service running "
                "(mcporter call 'xiaohongshu.search_feeds(keyword: \"...\")'). "
                "If not logged in, have agent call get_login_qrcode to scan"
            )
        return "warn", (
            "xiaohongshu-mcp service running but mcporter not connected. Run:\n"
            f"  mcporter config add xiaohongshu {_MCP_ENDPOINT}"
        )

    def _check_xhs_cli(self):
        """Legacy xhs-cli candidate. None = not installed."""
        probe = probe_command(
            "xhs", ["status"], timeout=10, package="xiaohongshu-cli"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "xhs command exists but can't execute\n" + probe.hint
        if probe.status == "timeout":
            return "warn", "xhs-cli installed but status check timed out\n" + probe.hint

        # Process is alive (executed successfully or non-zero exit) — categorize by output
        if probe.ok and "ok: true" in probe.output:
            return "ok", (
                "xhs-cli available (search, read, comments, hot; upstream stopped updating 2026-03, "
                "desktop users should migrate to OpenCLI)"
            )
        if "not_authenticated" in probe.output or "expired" in probe.output:
            return "warn", (
                "xhs-cli installed but not logged in. Run:\n"
                "  xhs login\n"
                "(auto-extracts cookies from browser, or QR code login)"
            )
        return "warn", (
            "xhs-cli installed but status abnormal. Run:\n"
            "  xhs -v status for details"
        )
