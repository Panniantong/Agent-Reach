# -*- coding: utf-8 -*-
"""Tests that lock in repository cleanup decisions."""

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_legacy_files_are_removed():
    repo_root = _repo_root()

    assert not (repo_root / "scripts" / "sync-upstream.sh").exists()
    assert not (repo_root / "test.sh").exists()
    assert not (repo_root / "CLAUDE.md").exists()
    assert not (repo_root / ".claude" / "settings.local.json").exists()
    assert not (repo_root / "docs" / "cookie-export.md").exists()
    assert not (repo_root / "docs" / "dependency-locking.md").exists()
    assert not (repo_root / "docs" / "update.md").exists()
    assert not (repo_root / "docs" / "README_en.md").exists()
    assert not (repo_root / "docs" / "README_ja.md").exists()
    assert not (repo_root / "docs" / "usage_ja.md").exists()
    assert not (repo_root / "docs" / "assets").exists()
    assert not (repo_root / "docs" / "wechat-group-qr.jpg").exists()
    assert not (repo_root / "docs" / "assets" / "logo-1.png").exists()
    assert not (repo_root / "docs" / "assets" / "logo-1.svg").exists()
    assert not (repo_root / "docs" / "assets" / "logo-2.png").exists()
    assert not (repo_root / "docs" / "assets" / "logo-2.svg").exists()
    assert not (repo_root / "docs" / "assets" / "logo-3.png").exists()
    assert not (repo_root / "docs" / "assets" / "logo-3.svg").exists()


def test_readme_does_not_reference_untracked_usage_doc():
    readme = (_repo_root() / "README.md").read_text(encoding="utf-8")

    assert "docs/usage_ja.md" not in readme


def test_docs_folder_only_contains_supported_docs():
    docs_dir = _repo_root() / "docs"
    names = {path.name for path in docs_dir.iterdir()}

    expected_docs = {
        "codex-integration.md",
        "downstream-usage.md",
        "install.md",
        "python-sdk.md",
        "troubleshooting.md",
    }

    assert names == expected_docs


def test_llms_txt_points_at_current_fork_docs():
    llms = (_repo_root() / "llms.txt").read_text(encoding="utf-8")

    assert "github.com/iwachacha/Agent-Reach/blob/main/docs/install.md" in llms
    assert "github.com/Panniantong/Agent-Reach/blob/main/" not in llms
    assert "hacker_news" in llms
    assert "mcp_registry" in llms
    assert "reddit" in llms


def test_caller_control_policy_is_documented_consistently():
    repo_root = _repo_root()
    files = {
        "readme": repo_root / "README.md",
        "downstream": repo_root / "docs" / "downstream-usage.md",
        "skill": repo_root / "agent_reach" / "skills" / "agent-reach" / "SKILL.md",
        "agent_prompt": repo_root / "agent_reach" / "skills" / "agent-reach" / "agents" / "openai.yaml",
    }

    texts = {name: path.read_text(encoding="utf-8") for name, path in files.items()}

    assert "Agent Reach does not choose" in texts["readme"]
    assert "auto-escalate" in texts["readme"]
    assert "explicit opt-in" in texts["readme"]
    assert "--limit 20" in texts["readme"]

    assert "The caller chooses scope" in texts["downstream"]
    assert "auto-escalate" in texts["downstream"]
    assert "explicit opt-in" in texts["downstream"]
    assert "--limit 20" in texts["downstream"]

    assert "The caller chooses" in texts["skill"]
    assert "auto-escalate" in texts["skill"]
    assert "explicit opt-in" in texts["skill"]
    assert "--limit 20" in texts["skill"]

    assert "does not choose scope" in texts["agent_prompt"]
    assert "explicit opt-in" in texts["agent_prompt"]


def test_skill_suite_files_exist():
    repo_root = _repo_root()
    suite_root = repo_root / "agent_reach" / "skills"
    expected = [
        "agent-reach",
        "agent-reach-shape-brief",
        "agent-reach-orchestrate",
        "agent-reach-maintain-proposals",
        "agent-reach-maintain-release",
    ]

    for skill_name in expected:
        skill_dir = suite_root / skill_name
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "agents" / "openai.yaml").exists()
