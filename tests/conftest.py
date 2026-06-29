# -*- coding: utf-8 -*-
"""Pytest configuration for Agent Reach tests.

Adds the repo-root ``scripts/`` directory to ``sys.path`` so standalone helper
scripts (e.g. ``x_board.py``) are importable from the test suite. ``scripts/`` is
not an installable package, so this is the lightweight, stdlib-only way to test
it without touching ``pyproject.toml`` or ``agent_reach``.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
