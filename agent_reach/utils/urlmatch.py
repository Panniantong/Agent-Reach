# -*- coding: utf-8 -*-
"""Host matching for channel routing.

Channels decide whether they own a URL via ``can_handle``. A naive substring
test like ``"github.com" in urlparse(url).netloc`` also matches look-alike hosts
(``github.com.evil.com``, ``evil-github.com``) and userinfo tricks
(``github.com@evil.com`` — the netloc contains "github.com" but the real host is
``evil.com``). Routing an attacker-controlled URL to a *credentialed* channel
(e.g. one that attaches cookies or a logged-in CLI) lets it exercise that
channel's session against a host the user never intended.

``host_matches`` extracts the real hostname (``urlsplit`` excludes userinfo and
port) and requires an exact or proper-subdomain match.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def host_matches(url: str, *domains: str) -> bool:
    """True if the URL's host equals one of ``domains`` or is a subdomain of it.

    Uses the parsed hostname (not netloc), so embedded credentials and ports
    cannot smuggle a look-alike host past the check.
    """
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower()
    for domain in domains:
        d = domain.lower().strip(".")
        if host == d or host.endswith("." + d):
            return True
    return False
