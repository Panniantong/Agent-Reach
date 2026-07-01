# -*- coding: utf-8 -*-
"""URL host-matching helper shared by channel can_handle() methods.

Channels must route on the *host* of a URL, never on a substring of the raw
URL or netloc. Substring checks such as ``"x.com" in url`` match lookalike
and spoofed hosts — ``notx.com``, ``x.com.evil.test``, ``x.com@evil.test`` —
which would make a credentialed channel attach the user's auth cookies to an
attacker-controlled request. host_matches() accepts only an exact host or a
real subdomain of one of the allowed hosts.
"""

from urllib.parse import urlparse


def domain_covers(host: str, *allowed_hosts: str) -> bool:
    """Return True if bare *host* is exactly, or a subdomain of, an allowed host.

    Operates on already-extracted host strings (e.g. a cookie's ``domain``,
    which may carry a leading dot like ``.xueqiu.com``). Leading/trailing dots
    are stripped on both sides and matching is exact-or-dot-boundary, so
    lookalikes such as ``notxueqiu.com`` or ``xueqiu.com.evil.test`` are
    rejected while real subdomains (``stock.xueqiu.com``) are accepted.
    """
    if not host:
        return False
    h = host.lower().strip(".")
    if not h:
        return False
    for allowed in allowed_hosts:
        a = allowed.lower().strip(".")
        if a and (h == a or h.endswith("." + a)):
            return True
    return False


def host_matches(url: str, *allowed_hosts: str) -> bool:
    """Return True if *url*'s host is one of *allowed_hosts* or a subdomain.

    Uses urlparse().hostname, which lowercases the host and strips any
    userinfo (``user@``) and ``:port`` — so spoofing tricks that fool a
    substring or netloc check are rejected. Host comparison is delegated to
    domain_covers (exact-or-dot-boundary).
    """
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    return domain_covers(host or "", *allowed_hosts)
