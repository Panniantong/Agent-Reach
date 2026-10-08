# -*- coding: utf-8 -*-
"""Web — search (Exa) and read any page (Jina Reader, Exa fallback).

This channel is a fallback: agents that already have working built-in web
search / fetch should use those first.
"""

import json
import re
import urllib.request

from agent_reach.runtime.result import (
    BAD_INPUT,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import http_request
from agent_reach.utils.url import normalize_public_http_url

from .base import Action, Channel, Param

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096
_EXA_MCP = "https://mcp.exa.ai/mcp"
_EXA_HEADER_RE = re.compile(r"^(Title|URL|Published|Author):\s*(.*)$")


def _is_antibot_page(body: bytes) -> bool:
    """Recognize high-confidence Jina/Cloudflare challenge responses."""
    sample = body[:_ANTIBOT_SCAN_BYTES].decode("utf-8", errors="ignore").casefold()

    jina_captcha_warning = "warning:" in sample and "requiring captcha" in sample
    challenge_structure = any(
        marker in sample
        for marker in (
            "title: just a moment...",
            "## performing security verification",
            "title: attention required! | cloudflare",
        )
    )
    cloudflare_block = "title: attention required! | cloudflare" in sample and (
        "ray id" in sample or "/cdn-cgi/challenge-platform/" in sample
    )
    return (jina_captcha_warning and challenge_structure) or cloudflare_block


def _public_url(target: str) -> str:
    try:
        return normalize_public_http_url(target)
    except ValueError:
        raise ReachError(BAD_INPUT, "target must be a public http(s) URL") from None


def _exa_call(tool: str, arguments: dict, timeout: float) -> str:
    """Call one tool on Exa's free hosted MCP (no key) and return its text."""
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    ).encode("utf-8")
    raw = http_request(
        _EXA_MCP,
        timeout=timeout,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    ).decode("utf-8", errors="replace")
    payloads = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")] or [raw]
    msg = json.loads(payloads[-1])
    if "error" in msg:
        text = str(msg["error"].get("message", msg["error"]))
        code = RATE_LIMITED if "rate" in text.lower() or "limit" in text.lower() else UPSTREAM_BROKEN
        raise ReachError(code, f"Exa: {text}")
    result = msg.get("result") or {}
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if result.get("isError"):
        code = RATE_LIMITED if "rate" in text.lower() else UPSTREAM_BROKEN
        raise ReachError(code, f"Exa: {text[:300]}")
    return text


def _parse_exa_text(text: str) -> list:
    """Split Exa's `Title: / URL: / Published: / Author:` blocks into items."""
    items = []
    for block in re.split(r"\n(?=Title: )", "\n" + text.strip()):
        block = block.strip()
        if not block.startswith("Title:"):
            continue
        fields, body = {}, []
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            m = _EXA_HEADER_RE.match(lines[i])
            if not m:
                break
            fields[m.group(1).lower()] = m.group(2).strip()
            i += 1
        for line in lines[i:]:
            if line.strip() in ("Highlights:", "Text:"):
                continue
            body.append(line)
        na = lambda v: None if v in (None, "", "N/A") else v  # noqa: E731
        items.append(
            make_item(
                title=na(fields.get("title")),
                url=na(fields.get("url")),
                author=na(fields.get("author")),
                published_at=na(fields.get("published")),
                text="\n".join(body).strip(),
                raw=fields,
            )
        )
    return items


def _parse_jina(url: str, body: str) -> dict:
    title = re.search(r"^Title:\s*(.*)$", body, re.M)
    published = re.search(r"^Published Time:\s*(.*)$", body, re.M)
    content = body.split("Markdown Content:", 1)[1] if "Markdown Content:" in body else body
    return make_item(
        title=title.group(1).strip() if title else None,
        url=url,
        published_at=published.group(1).strip() if published else None,
        text=content.strip(),
    )


class WebChannel(Channel):
    name = "web"
    description = "网页搜索与阅读（Agent 自带工具不可用时的保底）"
    backends = ["Jina Reader"]
    tier = 0

    level = "default"
    actions = (
        Action(
            "search",
            "Search the web (Exa semantic search)",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("exa", "_exa_search"),),
            live_test={"query": "yt-dlp github repository", "limit": 2},
        ),
        Action(
            "read",
            "Read a web page as clean text",
            (Param("target", "page URL"),),
            (("jina", "_jina_read"), ("exa", "_exa_read")),
            live_test={"target": "https://example.com"},
        ),
    )

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        # 恒可用兜底渠道：无本地命令、不做网络探测（doctor 已有多个渠道触网），保持零开销
        self.active_backend = self.backends[0]
        return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"

    def read(self, url: str, timeout: float = 30) -> str:
        """通过 Jina Reader 读取网页，返回 Markdown 全文。"""
        url = normalize_public_http_url(url)
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Jina Reader response exceeds {_MAX_RESPONSE_BYTES} byte limit"
            )
        if _is_antibot_page(body):
            raise RuntimeError(
                "Jina Reader 返回了反爬验证页，未获取到目标内容；"
                "请改用站点专用工具或浏览器读取"
            )
        return body.decode("utf-8")

    # ── unified entry backends ──

    def _exa_search(self, *, query: str, limit: int, timeout: float) -> list:
        text = _exa_call("web_search_exa", {"query": query, "objective": query, "numResults": limit}, timeout)
        return _parse_exa_text(text)[:limit]

    def _exa_read(self, *, target: str, timeout: float) -> list:
        url = _public_url(target)
        text = _exa_call("web_fetch_exa", {"urls": [url], "maxCharacters": 20000}, timeout)
        items = _parse_exa_text(text)
        if items:
            items[0]["url"] = items[0]["url"] or url
            return items[:1]
        if not text.strip():
            raise ReachError(UPSTREAM_BROKEN, "Exa returned no content")
        return [make_item(url=url, text=text.strip())]

    def _jina_read(self, *, target: str, timeout: float) -> list:
        url = _public_url(target)
        try:
            body = self.read(url, timeout=timeout)
        except RuntimeError as exc:
            raise ReachError(UPSTREAM_BROKEN, str(exc)) from None
        return [_parse_jina(url, body)]
