# -*- coding: utf-8 -*-
"""Version parity across pyproject.toml, package __init__, and CLI tests.

Project convention (CLAUDE.md): the version must match in three places —
pyproject.toml, agent_reach/__init__.py, and the version literals referenced
by tests/test_cli.py (update-check fixtures and assertions).
"""

import re
from pathlib import Path

from agent_reach import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    """Return the [project] version from pyproject.toml (stdlib-only parse)."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match, "pyproject.toml has no top-level [project] version"
    return match.group(1)


def _test_cli_version_references() -> set:
    """Return every bare dotted version literal quoted in tests/test_cli.py."""
    text = (REPO_ROOT / "tests" / "test_cli.py").read_text(encoding="utf-8")
    return set(re.findall(r'"v?(\d+\.\d+(?:\.\d+)?)"', text))


class TestVersionConsistency:
    def test_pyproject_matches_package(self):
        assert _pyproject_version() == __version__

    def test_cli_tests_reference_package_version(self):
        references = _test_cli_version_references()
        assert __version__ in references, (
            f"tests/test_cli.py no longer references v{__version__}; "
            "update its update-check fixtures/assertions to the new version"
        )
