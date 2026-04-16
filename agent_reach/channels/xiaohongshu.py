# -*- coding: utf-8 -*-
"""XiaoHongShu — check if xhs-cli (xiaohongshu-cli) is available."""

import shutil
from pathlib import Path
from .base import Channel


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
    backends = ["xhs-cli (xiaohongshu-cli)"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "xiaohongshu.com" in d or "xhslink.com" in d

    def check(self, config=None):
        xhs = shutil.which("xhs")
        if not xhs:
            return "off", (
                "需要安装 xhs-cli：\n"
                "  pipx install xiaohongshu-cli\n"
                "或：\n"
                "  uv tool install xiaohongshu-cli\n"
                "安装后运行 `xhs login` 登录"
            )

        # Keep doctor/status fully non-interactive.
        #
        # xhs-cli status may scan multiple browsers for cookies, which can
        # trigger repeated macOS Keychain prompts. A passive health check should
        # never open browser-cookie access or login flows.
        if config:
            try:
                cookie_str = (config.get("xhs_cookie") or "").strip()
                if cookie_str:
                    n_cookies = len([p for p in cookie_str.split(";") if "=" in p])
                    return "ok", (
                        f"检测到本地 Cookie 配置（{n_cookies} 项）。"
                        "doctor 跳过在线校验，保持非交互"
                    )
            except Exception:
                pass

        cookie_files = [
            Path.home() / ".xiaohongshu-cli" / "cookies.json",
            Path.home() / ".agent-reach" / "xhs-cookies.json",
        ]
        for path in cookie_files:
            try:
                if path.exists() and path.stat().st_size > 10:
                    return "ok", (
                        f"检测到本地登录状态：{path}。"
                        "doctor 跳过在线校验，保持非交互"
                    )
            except OSError:
                pass

        return "warn", (
            "xhs-cli 已安装，但当前未检测到本地 Cookie。"
            "需要时手动配置：\n"
            "  xhs login\n"
            "或：\n"
            "  agent-reach configure xhs-cookies '<cookie header 或 JSON>'"
        )
