# -*- coding: utf-8 -*-
"""Generic web reading through Jina Reader."""

from __future__ import annotations

import urllib.request

from .base import Channel

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class WebChannel(Channel):
    name = "web"
    description = "Any web page"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True

    def check(self, config=None):
        return "ok", "Reads arbitrary pages via https://r.jina.ai/"

    def read(self, url: str) -> str:
        """Read a URL as markdown through Jina Reader."""

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        req = urllib.request.Request(
            f"https://r.jina.ai/{url}",
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
