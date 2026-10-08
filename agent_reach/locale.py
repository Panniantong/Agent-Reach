"""Locale helpers shared by user-facing Agent Reach output."""

import os

_ENGLISH_PREFIXES = ("en", "english")


def is_english_locale(value: str | None = None) -> bool:
    """Return whether a locale value or the process environment requests English."""
    candidates = (
        (value,)
        if value is not None
        else (
            os.environ.get("AGENT_REACH_LANG", ""),
            os.environ.get("LC_ALL", ""),
            os.environ.get("LC_MESSAGES", ""),
            os.environ.get("LANG", ""),
        )
    )
    return any(
        candidate.strip().lower().startswith(_ENGLISH_PREFIXES)
        for candidate in candidates
        if candidate
    )
