# -*- coding: utf-8 -*-
"""URL safety helpers — scheme allowlisting and SSRF guarding.

Used wherever a user- or agent-supplied URL is handed to a fetcher or an
external downloader (yt-dlp, ffmpeg, Jina Reader). The threat model: the URL
may originate from an LLM or from scraped content, so it must not be trusted to
point at the public web. These checks block

  * non-http(s) schemes (``file:``, ``data:``, ``gopher:`` …),
  * argument injection (a value like ``--exec=...`` has no scheme → rejected),
  * SSRF against loopback / private / link-local hosts and the cloud metadata
    endpoint ``169.254.169.254``,
  * CRLF / whitespace injection when the URL is concatenated into a request.

Note: ``assert_safe_public_url`` validates the *initial* host only. It does not
constrain HTTP redirects, and resolving-then-fetching leaves a small
DNS-rebinding window. These are pragmatic mitigations for a developer CLI, not a
hardened SSRF proxy.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")


class UnsafeURLError(ValueError):
    """Raised when a URL is not a safe public http(s) target."""


def is_http_url(value: object) -> bool:
    """True if ``value`` already carries an ``http://`` or ``https://`` scheme."""
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_safe_public_url(url: str, *, resolve: bool = True) -> str:
    """Validate that ``url`` is a public http(s) URL; return it unchanged.

    Raises :class:`UnsafeURLError` if the scheme is not http/https, the host is
    missing, the URL contains control/whitespace characters, or (when
    ``resolve`` is True) the host resolves to a private/loopback/link-local/
    reserved/metadata address.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("empty URL")
    # Reject control chars and whitespace early — these enable request-line /
    # header (CRLF) injection when the URL is embedded into another request.
    if any(ord(c) < 0x21 for c in url):
        raise UnsafeURLError("URL contains whitespace or control characters")

    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"unsupported URL scheme: {parts.scheme!r} (only http/https allowed)"
        )
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    if not resolve:
        return url

    # Literal IP host — check directly, no DNS lookup. Determine literal-ness
    # first; do NOT let UnsafeURLError (a ValueError subclass) be swallowed by
    # the ip_address() parse guard.
    try:
        ipaddress.ip_address(host)
        is_literal = True
    except ValueError:
        is_literal = False  # not a literal IP — resolve the name below
    if is_literal:
        if not _is_public_ip(host):
            raise UnsafeURLError(f"URL host {host} is not a public address")
        return url

    try:
        infos = socket.getaddrinfo(host, parts.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURLError(f"could not resolve host {host}: {e}") from e
    addrs = {str(info[4][0]) for info in infos}
    if not addrs:
        raise UnsafeURLError(f"host {host} resolved to no addresses")
    for ip in addrs:
        if not _is_public_ip(ip):
            raise UnsafeURLError(
                f"URL host {host} resolves to non-public address {ip}"
            )
    return url
