"""Subprocess helpers for consistent cross-platform text handling."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

UTF8_ENV = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}


def utf8_subprocess_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment that forces Python child processes into UTF-8 mode."""
    env = dict(base or os.environ)
    env.update(UTF8_ENV)
    return env


def windows_hidden_kwargs() -> dict[str, Any]:
    """Return Windows creation flags that keep child consoles from appearing.

    Use ``CREATE_NO_WINDOW`` without ``DETACHED_PROCESS``: a detached child has
    no console to inherit, so a venv launcher that re-execs the real interpreter
    can cause Windows to allocate a brand-new visible console window.
    """
    if sys.platform == "win32":
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return {"creationflags": create_no_window | create_new_process_group}
    return {}
