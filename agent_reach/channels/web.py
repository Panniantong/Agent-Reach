# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.request
from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Cloudflare / anti-bot block detection patterns
_CF_BLOCK_PATTERNS = [
    "Just a moment...",
    "Checking your browser",
    "security verification",
    "DDoS protection",
    "cf-browser-verify",
    "Please turn JavaScript on",
    "Attention Required! | Cloudflare",
]


def _is_blocked(text: str) -> bool:
    """Check whether a response looks like a Cloudflare / anti-bot block page."""
    t = text[:2000]
    for pat in _CF_BLOCK_PATTERNS:
        if pat.lower() in t.lower():
            return True
    return False


def _direct_fetch(url: str) -> str | None:
    """Attempt a direct HTTP fetch with browser-like headers as fallback."""
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


class WebChannel(Channel):
    name = "web"
    description = "任意网页"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        # 恒可用兜底渠道：无本地命令、不做网络探测（doctor 已有多个渠道触网），保持零开销
        self.active_backend = self.backends[0]
        return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"

    def read(self, url: str) -> str:
        """通过 Jina Reader 读取网页，返回 Markdown 全文。

        Falls back to direct HTTP fetch when Jina Reader is blocked
        by Cloudflare or similar anti-bot protection.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")

        # Detect Cloudflare / anti-bot blocks and fall back to a direct fetch.
        # If the direct fetch also fails (returns None/empty), keep the
        # original Jina response instead of dropping the data.
        if _is_blocked(text):
            direct = _direct_fetch(url)
            return direct or text

        return text
