# -*- coding: utf-8 -*-
"""Web — any URL via Jina Reader. Always available."""

import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

from .base import Channel

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

#: Hostnames that are always blocked — resolved before any DNS query.
_SSRF_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "metadata.google.internal", "metadata.goog",
})

#: Cloud metadata IPs — the #1 SSRF target in cloud environments.
_SSRF_METADATA_IPS = frozenset({
    "169.254.169.254", "169.254.170.2", "169.254.169.253",
    "100.100.100.200", "fd00:ec2::254",
})


def _validate_url(url: str) -> None:
    """Validate *url* does not target a private or internal host.

    Raises ``ValueError`` with a descriptive message when the URL is unsafe.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL has no hostname")

    # 1. Static hostname blocklist (fast, no DNS)
    if host in _SSRF_BLOCKED_HOSTNAMES:
        raise ValueError(f"URL target '{host}' is not allowed")

    # 2. Cloud metadata IP blocklist
    if host in _SSRF_METADATA_IPS:
        raise ValueError(f"URL target '{host}' is a cloud metadata endpoint")

    # 3. Scheme validation
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"URL scheme '{scheme}' is not supported")

    # 4. IP-based check for literal addresses
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass  # not an IP literal — continue to DNS check below
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"URL target '{host}' is a private or reserved IP")
        if host in _SSRF_METADATA_IPS:
            raise ValueError(f"URL target '{host}' is a cloud metadata endpoint")
        return  # IP literal passed validation

    # 5. DNS resolution check for hostnames
    try:
        addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError(
                    f"URL target '{host}' resolves to private IP '{ip_str}'"
                )
            if ip_str in _SSRF_METADATA_IPS:
                raise ValueError(
                    f"URL target '{host}' resolves to metadata IP '{ip_str}'"
                )
    except OSError:
        # DNS failure — let the caller handle transient errors
        pass


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

        Validates the target URL to block SSRF to private/internal hosts.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # SSRF protection: reject private/internal targets before proxying.
        try:
            _validate_url(url)
        except ValueError as e:
            raise RuntimeError(f"URL validation failed: {e}") from e

        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": _UA, "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
