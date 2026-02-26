# -*- coding: utf-8 -*-
"""XiaoHongShu (小红书) — via mcporter + xiaohongshu MCP server.

Backend: xiaohongshu-mcp server (internal API, reliable)
Requires: mcporter CLI + xiaohongshu MCP server running
"""

import json
import shutil
import subprocess
from urllib.parse import urlparse, parse_qs, urlencode
from .base import Channel, ReadResult, SearchResult
from typing import List, Optional


class XiaoHongShuChannel(Channel):
    name = "xiaohongshu"
    description = "小红书笔记"
    backends = ["xiaohongshu-mcp"]
    tier = 2

    def _mcporter_ok(self) -> bool:
        """Check if mcporter + xiaohongshu MCP is available."""
        if not shutil.which("mcporter"):
            return False
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            return "xiaohongshu" in r.stdout
        except Exception:
            return False

    def _call(self, expr: str, timeout: int = 30) -> str:
        r = subprocess.run(
            ["mcporter", "call", expr],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr or r.stdout)
        return r.stdout

    # ── Channel interface ──

    def can_handle(self, url: str) -> bool:
        d = urlparse(url).netloc.lower()
        return "xiaohongshu.com" in d or "xhslink.com" in d

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + xiaohongshu-mcp。安装步骤：\n"
                "  1. npm install -g mcporter\n"
                "  2. docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp\n"
                "  3. mcporter config add xiaohongshu http://localhost:18060/mcp\n"
                "  详见 https://github.com/xpzouying/xiaohongshu-mcp"
            )
        if not self._mcporter_ok():
            return "off", (
                "mcporter 已装但小红书 MCP 未配置。运行：\n"
                "  docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp\n"
                "  mcporter config add xiaohongshu http://localhost:18060/mcp"
            )
        try:
            out = self._call("xiaohongshu.check_login_status()", timeout=10)
            if "已登录" in out or "logged" in out.lower():
                return "ok", "完整可用（阅读、搜索、发帖、评论、点赞）"
            return "warn", "MCP 已连接但未登录，需扫码登录"
        except Exception:
            return "warn", "MCP 连接异常，检查 xiaohongshu-mcp 服务是否在运行"

    async def read(self, url: str, config=None) -> ReadResult:
        if not self._mcporter_ok():
            return ReadResult(
                title="XiaoHongShu",
                content=(
                    "⚠️ 小红书需要 mcporter + xiaohongshu-mcp 才能使用。\n\n"
                    "安装步骤：\n"
                    "1. npm install -g mcporter\n"
                    "2. docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp\n"
                    "3. mcporter config add xiaohongshu http://localhost:18060/mcp\n"
                    "4. 运行 agent-reach doctor 检查状态\n\n"
                    "详见 https://github.com/xpzouying/xiaohongshu-mcp"
                ),
                url=url, platform="xiaohongshu",
            )

        note_id = self._extract_note_id(url)
        if not note_id:
            return ReadResult(
                title="XiaoHongShu",
                content=f"⚠️ 无法从 URL 提取笔记 ID: {url}",
                url=url, platform="xiaohongshu",
            )

        # Step 1: try xsec_token from URL query param (e.g. from search results)
        xsec_token = self._extract_token_from_url(url)

        # Step 2: try homepage feeds
        if not xsec_token:
            xsec_token = self._find_token_in_feeds(note_id)

        # Step 3: search for the note to get a fresh token
        if not xsec_token:
            xsec_token = self._find_token_by_search(note_id)

        # If no token found, fallback to Jina Reader
        if not xsec_token:
            return await self._read_jina(url)

        # Get detail via MCP
        out = self._call(
            f'xiaohongshu.get_feed_detail(feed_id: "{note_id}", xsec_token: "{xsec_token}")',
            timeout=15,
        )

        return ReadResult(
            title=self._extract_title(out) or f"XHS {note_id}",
            content=out.strip(),
            url=url, platform="xiaohongshu",
        )

    async def search(self, query: str, config=None, **kwargs) -> List[SearchResult]:
        if not self._mcporter_ok():
            raise ValueError(
                "小红书搜索需要 mcporter + xiaohongshu-mcp。\n"
                "安装: npm install -g mcporter && mcporter config add xiaohongshu http://localhost:18060/mcp"
            )
        limit = kwargs.get("limit", 10)
        safe_q = query.replace('"', '\\"')
        out = self._call(f'xiaohongshu.search_feeds(keyword: "{safe_q}")', timeout=30)

        results = []
        try:
            data = json.loads(out)
            for item in data.get("feeds", [])[:limit]:
                card = item.get("noteCard", {})
                user = card.get("user", {})
                interact = card.get("interactInfo", {})
                note_id = item.get("id", "")
                xsec_token = item.get("xsecToken", "")
                note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                if xsec_token:
                    note_url += f"?xsec_token={xsec_token}"
                results.append(SearchResult(
                    title=card.get("displayTitle", ""),
                    url=note_url,
                    snippet=f"👤 {user.get('nickname', '')} · ❤ {interact.get('likedCount', '0')}",
                    score=0,
                ))
        except (json.JSONDecodeError, KeyError):
            pass
        return results

    # ── Helpers ──

    def _extract_note_id(self, url: str) -> str:
        """Extract note ID from URL path, ignoring query params."""
        path = urlparse(url).path.strip("/").split("/")
        return path[-1] if path else ""

    def _extract_token_from_url(self, url: str) -> Optional[str]:
        """Extract xsec_token from URL query parameter if present."""
        qs = parse_qs(urlparse(url).query)
        tokens = qs.get("xsec_token", [])
        return tokens[0] if tokens else None

    def _find_token_in_feeds(self, note_id: str) -> Optional[str]:
        """Try to find xsec_token for a note from homepage feeds."""
        try:
            out = self._call("xiaohongshu.list_feeds()", timeout=15)
            data = json.loads(out)
            for feed in data.get("feeds", []):
                if feed.get("id") == note_id:
                    return feed.get("xsecToken") or None
        except Exception:
            pass
        return None

    def _find_token_by_search(self, note_id: str) -> Optional[str]:
        """Search for the note ID to get a fresh xsec_token."""
        try:
            out = self._call(
                f'xiaohongshu.search_feeds(keyword: "{note_id}")', timeout=20
            )
            data = json.loads(out)
            for feed in data.get("feeds", []):
                if feed.get("id") == note_id:
                    return feed.get("xsecToken") or None
            # If exact match not found but results exist, try the first one
            # (search by note_id sometimes returns the note with a different key)
        except Exception:
            pass
        return None

    def _extract_title(self, text: str) -> str:
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith(("{", "[", "#", "http")):
                return line[:80]
        return ""

    async def _read_jina(self, url: str) -> ReadResult:
        """Fallback: read XHS note via Jina Reader when xsec_token unavailable."""
        import requests
        try:
            resp = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"Accept": "text/markdown"},
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text
            if len(text.strip()) < 50 or "登录" in text[:200]:
                return ReadResult(
                    title="XiaoHongShu",
                    content=(
                        f"⚠️ 无法获取笔记详情: {url}\n\n"
                        "小红书需要 xsec_token 才能通过 MCP 读取笔记。\n"
                        "请尝试先搜索相关关键词，再从结果中读取。"
                    ),
                    url=url, platform="xiaohongshu",
                )
            title = ""
            for line in text.split("\n"):
                line = line.strip()
                if line and not line.startswith(("#", "http", "![", "[")):
                    title = line[:80]
                    break
            return ReadResult(
                title=title or "XiaoHongShu",
                content=text.strip(),
                url=url, platform="xiaohongshu",
            )
        except Exception:
            return ReadResult(
                title="XiaoHongShu",
                content=(
                    f"⚠️ 无法获取笔记详情: {url}\n\n"
                    "小红书需要 xsec_token 才能通过 MCP 读取笔记。\n"
                    "请尝试先搜索相关关键词，再从结果中读取。"
                ),
                url=url, platform="xiaohongshu",
            )
