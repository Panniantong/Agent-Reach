# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader."""

import urllib.error
import urllib.request

from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096
_JINA_READER_ROOT = "https://r.jina.ai/"
# Doctor probe: short enough for poisoned-DNS timeouts, long enough for TLS.
_PROBE_TIMEOUT = 5


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
    description = "任意网页"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    def check(self, config=None):
        # GET + 1 byte, not HEAD: Cloudflare holds HEAD open until timeout.
        self.active_backend = None
        req = urllib.request.Request(
            _JINA_READER_ROOT,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
                resp.read(1)
        except urllib.error.HTTPError:
            # Host answered (4xx/5xx). Unreachable is connect/DNS/timeout.
            pass
        except Exception as e:
            return (
                "warn",
                f"Jina Reader 不可达（{_JINA_READER_ROOT.rstrip('/')}）：{e}。"
                "网页读取可改用 Exa（exa_search）作为 fallback。",
            )
        self.active_backend = self.backends[0]
        return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"

    def read(self, url: str) -> str:
        """通过 Jina Reader 读取网页，返回 Markdown 全文。"""
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
                "Jina Reader 返回了反爬验证页，未获取到目标内容；"
                "请改用站点专用工具或浏览器读取"
            )
        return body.decode("utf-8")
