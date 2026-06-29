# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.parse
import urllib.request

from ..utils.urlsafe import assert_safe_public_url, is_http_url
from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# Cap the Jina Reader response so a hostile/huge page can't exhaust memory or
# flood the agent's context (and token budget).
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


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
        """通过 Jina Reader 读取网页，返回 Markdown 全文。"""
        if not is_http_url(url):
            url = "https://" + url
        # `url` is user/agent supplied — reject non-http(s) schemes and internal
        # SSRF targets, and percent-encode before embedding it in the Jina path
        # so it cannot inject extra path/query segments or CRLF.
        assert_safe_public_url(url)
        jina_url = "https://r.jina.ai/" + urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=~-._")
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            data = data[:_MAX_BYTES]
        return data.decode("utf-8", errors="replace")
