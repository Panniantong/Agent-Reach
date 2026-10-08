"""Protect the two backend-specific sorting command contracts."""

import json
import shlex
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "agent_reach/skill"


@pytest.mark.parametrize("locale", ["SKILL.md", "SKILL_en.md"])
def test_skill_entry_point_exposes_newest_sort(locale):
    content = (SKILL / locale).read_text(encoding="utf-8")
    commands = [
        shlex.split(line)
        for line in content.splitlines()
        if line.startswith("opencli xiaohongshu search ") and "--sort" in line
    ]
    assert any(args[args.index("--sort") + 1] == "latest" for args in commands)


def test_mcp_latest_example_passes_a_nested_json_filter():
    social = (SKILL / "references/social.md").read_text(encoding="utf-8")
    commands = [
        shlex.split(line)
        for line in social.splitlines()
        if line.startswith("mcporter call xiaohongshu.search_feeds ")
    ]
    filtered = [args for args in commands if any(arg.startswith("filters=") for arg in args)]
    assert filtered
    for args in filtered:
        value = next(arg.split("=", 1)[1] for arg in args if arg.startswith("filters="))
        # Legacy PowerShell spelling has additional native-argument escaping;
        # its actual wire payload is checked by the separate MCP fixture replay.
        filters = json.loads(value.replace('\\"', '"'))
        assert filters == {"sort_by": "最新"}
        assert not any(arg.startswith("sort_by=") for arg in args)
        assert args[args.index("--timeout") + 1] == "120000"


def test_sort_guidance_keeps_enum_and_acceptance_boundaries():
    social = (SKILL / "references/social.md").read_text(encoding="utf-8")
    for english, chinese in (
        ("comprehensive", "综合"),
        ("latest", "最新"),
        ("most-liked", "最多点赞"),
        ("most-commented", "最多评论"),
        ("most-collected", "最多收藏"),
    ):
        assert f"| `{english}` | {chinese}" in social
    assert "published_at" in social and "由笔记 ID 推算" in social
    assert "两次结果不同不自动证明排序正确" in social
    assert "真实验收仍需用户控制的登录环境" in social
    assert "Windows PowerShell 5.1" in social and "Legacy" in social
