"""
Locale detection — shared across CLI, doctor, and channels.

The effective language is determined by (highest priority first):
1. A programmatic override set via `set_english()` (used by --lang flag)
2. The AGENT_REACH_LANG env var
3. The LC_ALL, LC_MESSAGES, or LANG env vars
"""

import os

_OVERRIDE_ENGLISH: bool | None = None


def set_english(enabled: bool) -> None:
    """Override the language choice programmatically (e.g. from --lang flag)."""
    global _OVERRIDE_ENGLISH
    _OVERRIDE_ENGLISH = enabled


def reset_override() -> None:
    """Clear the programmatic override (for testing)."""
    global _OVERRIDE_ENGLISH
    _OVERRIDE_ENGLISH = None


def use_english() -> bool:
    """Return True when the user prefers English over Chinese."""
    # 1. Programmatic override (set by --lang flag or config)
    if _OVERRIDE_ENGLISH is not None:
        return _OVERRIDE_ENGLISH

    # 2. Environment variables
    candidates = (
        os.environ.get("AGENT_REACH_LANG", ""),
        os.environ.get("LC_ALL", ""),
        os.environ.get("LC_MESSAGES", ""),
        os.environ.get("LANG", ""),
    )
    for val in candidates:
        val = val.strip().lower()
        if val.startswith("en") or val == "english":
            return True
    return False
