# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

from .base import Channel


class WebChannel(Channel):
    name = "web"
    description = "任意网页"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"
