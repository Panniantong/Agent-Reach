# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.error
import urllib.request

from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096
_PROBE_TIMEOUT = 3


def _probe_jina() -> bool:
    """Check that Jina Reader is actually reachable right now.

    Any HTTP response — 4xx included — proves DNS, TCP and TLS all work,
    which is the only thing this check needs to establish.

    Must stay a GET: a HEAD to the root is held open by Cloudflare until the
    socket times out, which would report a working reader as unreachable.
    Only one byte is read before the connection is closed.
    """
    req = urllib.request.Request(
        "https://r.jina.ai/",
        headers={"User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            resp.read(1)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


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
        # Jina Reader 是外部后端，并不恒可用：被墙或无代理时该渠道读不了任何网页，
        # 此时报 ok 就是假阳性。base.py 要求外部后端必须真实探测后再声明 active。
        if _probe_jina():
            self.active_backend = self.backends[0]
            return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"
        self.active_backend = None
        return "warn", (
            "Jina Reader 不可达（网络受限，可能需要代理）。"
            "替代方案：改用 Exa 后端读全文，mcporter call exa.web_fetch_exa"
        )

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
