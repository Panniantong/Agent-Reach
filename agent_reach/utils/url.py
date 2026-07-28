"""Security helpers for untrusted URLs."""

from __future__ import annotations

from urllib.parse import urlsplit


def domain_matches(host: str, *domains: str) -> bool:
    """Match a hostname/cookie domain exactly or as a real subdomain."""
    normalized_host = str(host or "").lower().lstrip(".").rstrip(".")
    if not normalized_host:
        return False
    for domain in domains:
        allowed = domain.lower().lstrip(".").rstrip(".")
        if normalized_host == allowed or normalized_host.endswith("." + allowed):
            return True
    return False


def host_matches(url: str, *domains: str) -> bool:
    """Return whether *url* has an exact allowed host or a real subdomain.

    Only HTTP(S) URLs without userinfo are accepted. Using ``hostname`` rather
    than substring matching prevents lookalikes such as ``x.com.evil.test`` and
    userinfo disguises such as ``x.com@evil.test``.
    """
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        # ``hostname`` is permissive: malformed or out-of-range ports only
        # raise when ``port`` is accessed. Force that validation here so
        # hostile authorities fail closed.
        _ = parsed.port
    except (TypeError, ValueError):
        return False

    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if not host or parsed.username is not None or parsed.password is not None:
        return False

    return domain_matches(host, *domains)
