# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.request
from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class WebChannel(Channel):
    name = "web"
    description = "Any web page"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        # Always-available fallback: no local commands, no network probes (doctor already has many network-touching channels), keep zero overhead
        self.active_backend = self.backends[0]
        return "ok", "Read any web page via Jina Reader (curl https://r.jina.ai/URL)"

    def read(self, url: str) -> str:
        """Read web pages via Jina Reader, returns full Markdown text."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
