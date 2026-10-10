"""UTF-8-safe text helpers for cross-platform file operations."""

from __future__ import annotations

import re

_URL_CREDENTIALS_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9+.\-]{0,19}://)[^/\s@]+@"
)
_BARE_USERINFO_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[^:/\s@]+:[^/\s@]+@(?=[A-Za-z0-9.\-\[])"
)
_URL_QUERY_SECRET_RE = re.compile(
    r"([?&#](?:"
    r"access[_-]?token|auth[_-]?token|token|bearer|"
    r"api[_-]?key|key|password|passwd|secret|"
    r"signature|sig|session(?:id)?|cookie|credential"
    r")=)[^&#\s]*",
    re.IGNORECASE,
)


def scrub_url_credentials(text: object) -> str:
    """Redact URL userinfo and sensitive query/fragment values from text."""
    scrubbed = _URL_CREDENTIALS_RE.sub(r"\1***@", str(text))
    scrubbed = _BARE_USERINFO_RE.sub("***@", scrubbed)
    return _URL_QUERY_SECRET_RE.sub(r"\1***", scrubbed)
