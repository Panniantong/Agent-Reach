# -*- coding: utf-8 -*-
"""Docs/contract greps so CLAUDE.md, install recipes, and skill copy cannot drift."""

import re
from pathlib import Path

import agent_reach

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_version_matches_pyproject():
    text = _read("pyproject.toml")
    match = re.search(r'(?m)^version = "([^"]+)"', text)
    assert match is not None
    assert agent_reach.__version__ == match.group(1)
    assert agent_reach.__version__ == "1.5.0"


def test_claude_md_channel_count_and_contract():
    text = _read("CLAUDE.md")
    assert "13 internet platforms" not in text
    assert "13 platforms" not in text
    assert "15 internet platforms" in text
    assert "read/search routing" not in text.lower()
    assert "`can_handle(url)` and `check()`" in text
    assert "must implement `can_handle(url)`, `read(url)`, `search(query)`, `check()`" not in text
    assert "tests/test_docs_contract.py" in text


def test_pyproject_description_not_entire_internet():
    text = _read("pyproject.toml")
    desc_match = re.search(r'(?m)^description = "([^"]+)"', text)
    assert desc_match is not None
    description = desc_match.group(1)
    assert "entire internet" not in description
    assert "10+" not in description


def test_package_strings_not_entire_internet():
    for relative in (
        "agent_reach/__init__.py",
        "agent_reach/core.py",
        "agent_reach/cli.py",
    ):
        text = _read(relative)
        assert "entire internet" not in text, relative


def test_readme_en_tagline_not_entire_internet():
    assert "entire internet" not in _read("docs/README_en.md")


def test_install_md_uses_config_yaml():
    text = _read("docs/install.md")
    assert "~/.agent-reach/config.json" not in text
    assert "~/.agent-reach/config.yaml" in text


def test_docs_and_guides_no_agent_reach_config_json():
    hits = []
    for path in list((ROOT / "docs").rglob("*")) + list((ROOT / "agent_reach" / "guides").rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "~/.agent-reach/config.json" in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_contributing_does_not_register_channels_in_doctor():
    text = _read("CONTRIBUTING.md")
    assert "Update `agent_reach/doctor.py` to include the new channel" not in text
    assert "更新 doctor 检测" not in text
    assert "get_all_channels()" in text


def test_skill_no_cookie_paste_one_liners():
    zh = _read("agent_reach/skill/SKILL.md")
    en = _read("agent_reach/skill/SKILL_en.md")
    assert "用户只需提供 cookies" not in zh
    assert "The user only provides cookies" not in en
    assert "Zero config for 6" not in zh
    assert "Zero config for 6" not in en


def test_skill_no_post_task_check_update_nudge():
    zh = _read("agent_reach/skill/SKILL.md")
    en = _read("agent_reach/skill/SKILL_en.md")
    assert "完成一次较大的调研" not in zh
    assert "after finishing a substantial" not in en
    standing_zh = zh.split("## 路由表", 1)[0]
    standing_en = en.split("## Routing table", 1)[0]
    assert "check-update" not in standing_zh
    assert "check-update" not in standing_en


def test_mcp_server_does_not_advertise_missing_extra():
    text = _read("agent_reach/integrations/mcp_server.py")
    assert "agent-reach[mcp]" not in text
    assert ".[all]" in text
    assert "mcp[cli]" in text


def test_readme_points_to_product_and_github_row_is_read_only():
    text = _read("README.md")
    assert "product/README.md" in text
    github_rows = [line for line in text.splitlines() if "**GitHub**" in line]
    assert github_rows, "expected a GitHub platform row in README.md"
    for line in github_rows:
        assert "Fork" not in line
        assert "Issue" not in line
        assert "PR" not in line
        assert "gh issue create" not in line


def test_install_md_constraints_and_check_only_first():
    text = _read("docs/install.md")
    assert "-c constraints.txt" in text
    assert "pipx cannot take `-c`" in text
    for root in (
        "~/.claude/skills",
        "~/.openclaw/skills",
        "~/.config/opencode/skills",
        "~/.agents/skills",
    ):
        assert root in text

    first_install = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "agent-reach install --env=auto" in stripped:
            first_install = stripped
            break
    assert first_install is not None
    assert "--system" not in first_install
    assert "pip install https://github.com/Panniantong/agent-reach/archive/main.zip" not in text


def test_update_md_constraints_or_pipx_exception():
    text = _read("docs/update.md")
    assert "-c constraints.txt" in text or "-c /tmp/agent-reach-constraints.txt" in text
    assert "pipx cannot take `-c`" in text


def test_translation_readmes_use_constraints_not_bare_zip():
    for relative in (
        "docs/README_en.md",
        "docs/README_ja.md",
        "docs/README_ko.md",
    ):
        text = _read(relative)
        assert (
            "pip install https://github.com/Panniantong/agent-reach/archive/main.zip"
            not in text
        ), relative
        assert "constraints.txt" in text, relative


def test_commercial_github_row_before_twitter():
    for relative in (
        "README.md",
        "docs/README_en.md",
        "docs/README_ja.md",
        "docs/README_ko.md",
    ):
        text = _read(relative)
        github = text.find("**GitHub**")
        twitter = text.find("**Twitter")
        assert github != -1 and twitter != -1, relative
        assert github < twitter, relative
