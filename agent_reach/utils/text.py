"""UTF-8-safe text helpers for cross-platform file operations."""

from __future__ import annotations

import re
from pathlib import Path

# Matches `scheme://user:pass@` (or `scheme://user@`) so proxy / URL
# credentials can be stripped before an error string reaches a log or the agent.
# The scheme length is bounded and the userinfo is a single char class (it
# already includes ":"), so there is no unbounded/nested quantifier and matching
# stays linear — no quadratic backtracking on long credential-free strings.
_URL_CREDENTIALS_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]{0,19}://)[^/\s@]+@")


def scrub_url_credentials(text: object) -> str:
    """Redact `user:pass@` credentials embedded in any URL within ``text``.

    Network exceptions (e.g. a urllib proxy error) frequently include the full
    proxy URL, which may carry `user:pass`. Run untrusted/error text through
    this before surfacing it to the user, the agent, or a log.
    """
    return _URL_CREDENTIALS_RE.sub(r"\1***@", str(text))


def read_utf8_text(path: str | Path, default: str = "") -> str:
    """Read text as UTF-8 with replacement semantics."""

    target = Path(path)
    if not target.exists():
        return default
    return target.read_text(encoding="utf-8", errors="replace")
