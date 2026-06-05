"""
Locale detection — shared across CLI, doctor, and channels.

Checks the same env vars the skill installer already uses (AGENT_REACH_LANG,
LC_ALL, LC_MESSAGES, LANG) so all user-facing strings switch together.
"""

import os


def use_english() -> bool:
    """Return True when the user prefers English over Chinese."""
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