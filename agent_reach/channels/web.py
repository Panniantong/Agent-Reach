# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.request

from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096


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


class WebChannel(Channel):
    name = "web"
    description = "Any web page"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        # Always available back-end channels: no local commands, no network detection (doctor has access to the network through multiple channels), and zero overhead
        self.active_backend = self.backends[0]
        return "ok", "Read any web page through Jina Reader (curl https://r.jina.ai/URL)"

    def read(self, url: str) -> str:
        """Read web pages through Jina Reader and return the full text of Markdown."""
        url = normalize_public_http_url(url)
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Jina Reader response exceeds {_MAX_RESPONSE_BYTES} byte limit"
            )
        if _is_antibot_page(body):
            raise RuntimeError(
                "Jina Reader returned the anti-bot verification page and failed to obtain the target content; "
                "Please use site-specific tools or browsers to read it instead."
            )
        return body.decode("utf-8")
