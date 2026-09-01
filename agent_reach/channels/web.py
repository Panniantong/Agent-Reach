# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import urllib.request
from urllib.error import HTTPError, URLError

from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096


def _reader_error_message(error: HTTPError) -> str:
    """Turn Jina's HTTP failures into safe, actionable user guidance."""
    status = error.code
    if status in {401, 403}:
        return (
            f"Jina Reader 拒绝访问（HTTP {status}）；目标页面可能需要登录、"
            "访问权限或浏览器验证，请确认链接可公开访问，或改用已登录的浏览器读取"
        )
    if status == 429:
        return "Jina Reader 请求过于频繁（HTTP 429）；请稍后重试"
    if 500 <= status < 600:
        return f"Jina Reader 暂时不可用（HTTP {status}）；请稍后重试"
    return f"Jina Reader 读取失败（HTTP {status}）"


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
        # 恒可用兜底渠道：无本地命令、不做网络探测（doctor 已有多个渠道触网），保持零开销
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
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            # Avoid exposing Jina's response body: it may contain upstream
            # challenge details or other untrusted content.
            raise RuntimeError(_reader_error_message(error)) from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(
                "无法连接 Jina Reader；请检查网络连接后重试"
            ) from error
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
