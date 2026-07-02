# -*- coding: utf-8 -*-
"""Regression tests for removed channel documentation."""

from __future__ import annotations

import importlib.resources
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Channels removed in #347; must not be documented as supported platforms.
REMOVED_CHANNEL_PATTERNS = [
    re.compile(r"\bweibo\b", re.IGNORECASE),
    re.compile(r"\bdouyin\b", re.IGNORECASE),
    re.compile(r"wechat[_ -]?articles?", re.IGNORECASE),
    re.compile(r"wechat\.py\b", re.IGNORECASE),
    re.compile(r"mcp-server-weibo", re.IGNORECASE),
    re.compile(r"douyin-mcp-server", re.IGNORECASE),
    re.compile(r"setup-wechat", re.IGNORECASE),
]


def _find_removed_channel_references(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in REMOVED_CHANNEL_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


@pytest.mark.parametrize(
    "relative_path",
    [
        "agent_reach/skill/SKILL.md",
    "agent_reach/skill/SKILL_en.md",
        "docs/README_ko.md",
        "docs/README_ja.md",
    ],
)
def test_removed_channels_are_not_documented(relative_path: str) -> None:
    path = REPO_ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    hits = _find_removed_channel_references(text)
    assert hits == [], f"{relative_path} still documents removed channels: {hits}"


def test_packaged_skill_matches_repo_skill() -> None:
    repo_skill = (REPO_ROOT / "agent_reach/skill/SKILL.md").read_text(encoding="utf-8")
    packaged_skill = (
        importlib.resources.files("agent_reach")
        .joinpath("skill/SKILL.md")
        .read_text(encoding="utf-8")
    )
    assert repo_skill == packaged_skill
