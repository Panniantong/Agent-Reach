# -*- coding: utf-8 -*-
"""Web — any URL via a configurable backend (Firecrawl preferred, Jina fallback).

Firecrawl is a self-hostable reader. Its base URL comes from the env var
``FIRECRAWL_URL`` or the config key ``firecrawl_url`` (default
``http://localhost:13002``) so a user's own install is honored. Jina Reader
remains the always-available public fallback.

Backend routing follows ``base.py``: ``backends`` is an ordered candidate
list (``backends[0]`` preferred); ``ordered_backends(config)`` honors a user
override via ``web_backend`` / ``WEB_BACKEND``.

Fallback semantics: a *transport* failure (network error, timeout, HTTP
error status) on Firecrawl falls back to Jina. A *content* failure (oversize
response, antibot page, Firecrawl scrape error) propagates as an error and
does NOT trigger the fallback — the caller sees the real failure.
"""

import json
import os
import urllib.request

from loguru import logger

from agent_reach.utils.url import normalize_public_http_url

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_ANTIBOT_SCAN_BYTES = 4096
_DEFAULT_FIRECRAWL_URL = "http://localhost:13002"
_PROBE_TIMEOUT = 5
_READ_TIMEOUT = 30

# Transport failures meaning "this backend is unreachable, try the next".
# Content-level errors (ValueError oversize, RuntimeError antibot/scrape
# failure) are deliberately NOT here — they propagate per the fallback policy.
# OSError is the common base of URLError / socket.timeout / ConnectionError /
# TimeoutError, so the probe can never raise out of a health check.
_NETWORK_ERRORS = (OSError,)


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
    backends = ["Firecrawl", "Jina Reader"]  # Firecrawl preferred, Jina fallback
    tier = 0

    def can_handle(self, url: str) -> bool:
        return True  # Fallback — handles any URL

    # ------------------------------------------------------------------ #
    # Config helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _firecrawl_base_url(config=None) -> str:
        if config:
            url = config.get("firecrawl_url")
            if url:
                return str(url).rstrip("/")
        env_url = os.environ.get("FIRECRAWL_URL")
        if env_url:
            return env_url.rstrip("/")
        return _DEFAULT_FIRECRAWL_URL

    @staticmethod
    def _firecrawl_api_key(config=None) -> str | None:
        if config:
            key = config.get("firecrawl_api_key")
            if key:
                return str(key)
        return os.environ.get("FIRECRAWL_API_KEY")

    @staticmethod
    def _firecrawl_request(target_url: str, base: str, api_key):
        body = json.dumps(
            {"url": target_url, "formats": ["markdown"]}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/v1/scrape",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": _UA},
            method="POST",
        )
        if api_key:
            # Bearer token only on the wire; never logged.
            req.add_header("Authorization", f"Bearer {api_key}")
        return req

    # ------------------------------------------------------------------ #
    # check
    # ------------------------------------------------------------------ #

    def check(self, config=None):
        """Probe Firecrawl; set active_backend and report ok/warn.

        Firecrawl reachable → ok (active=Firecrawl). Firecrawl down → warn
        (active=Jina Reader, unverified). A user override to Jina Reader
        skips the probe and stays ok (zero-overhead, as before).
        """
        self.active_backend = None
        ordered = self.ordered_backends(config)
        if ordered and ordered[0] == "Firecrawl":
            if self._firecrawl_reachable(config):
                self.active_backend = "Firecrawl"
                return "ok", (
                    f"Firecrawl 可用（{self._firecrawl_base_url(config)}），"
                    "Jina Reader 作为兜底"
                )
            self.active_backend = "Jina Reader"
            return "warn", (
                "Firecrawl 不可用，已回退到 Jina Reader（未实时验证）；"
                f"配置 FIRECRAWL_URL 指向你的 Firecrawl（默认 {_DEFAULT_FIRECRAWL_URL}）"
            )
        # User override to Jina Reader (or Firecrawl not preferred): no probe.
        self.active_backend = "Jina Reader"
        return "ok", "通过 Jina Reader 读取任意网页（curl https://r.jina.ai/URL）"

    def _firecrawl_reachable(self, config) -> bool:
        base = self._firecrawl_base_url(config)
        api_key = self._firecrawl_api_key(config)
        req = self._firecrawl_request("https://example.com", base, api_key)
        try:
            with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
                return getattr(resp, "status", 200) == 200
        except _NETWORK_ERRORS as exc:
            logger.debug(f"Firecrawl probe failed: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # read
    # ------------------------------------------------------------------ #

    def read(self, url: str, config=None) -> str:
        """读取网页全文 (Markdown)。Firecrawl 优先，Jina Reader 兜底。

        Transport failures fall back to the next backend; content failures
        (oversize / antibot / scrape error) propagate immediately.
        """
        url = normalize_public_http_url(url)
        last_network_error = None
        for backend in self.ordered_backends(config):
            try:
                if backend == "Firecrawl":
                    return self._read_firecrawl(url, config)
                if backend == "Jina Reader":
                    return self._read_jina(url)
            except _NETWORK_ERRORS as exc:
                logger.warning(f"web 后端 {backend} 不可用：{exc}；尝试下一个后端")
                last_network_error = exc
                continue
        if last_network_error is not None:
            raise last_network_error
        raise RuntimeError("没有可用的 web 后端")

    def _read_firecrawl(self, url: str, config) -> str:
        base = self._firecrawl_base_url(config)
        api_key = self._firecrawl_api_key(config)
        req = self._firecrawl_request(url, base, api_key)
        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT) as resp:
            payload = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Firecrawl response exceeds {_MAX_RESPONSE_BYTES} byte limit"
            )
        try:
            data = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Firecrawl 响应不是有效 JSON：{exc}") from exc
        if not isinstance(data, dict) or data.get("success") is False:
            detail = (
                data.get("error", "未知错误")
                if isinstance(data, dict)
                else "响应格式错误"
            )
            raise RuntimeError(f"Firecrawl 抓取失败：{detail}")
        markdown = (data.get("data") or {}).get("markdown", "")
        if not isinstance(markdown, str):
            raise RuntimeError("Firecrawl 响应缺少 data.markdown")
        return markdown

    def _read_jina(self, url: str) -> str:
        """通过 Jina Reader 读取网页，返回 Markdown 全文。"""
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT) as resp:
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