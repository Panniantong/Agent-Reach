# -*- coding: utf-8 -*-
"""Tests for the guru backfill + knowledge base (pure, offline logic only)."""

from agent_reach.knowledge import knowledge_rules, load_knowledge
from agent_reach.radar import Item
from agent_reach.radar_backfill import assemble_distill_material, backfill_github_repo
import agent_reach.radar_backfill as rb


def _tweet(text, ts="2026-01-01"):
    return Item(source="twitter:@karpathy", kind="tweet", title=text[:50], url="", text=text, ts=ts)


def test_assemble_material_structure():
    repos = [{
        "repo": "karpathy/autoresearch",
        "meta": {"description": "overnight agent research", "stargazerCount": 90500},
        "files": {"README.md": "readme body", "train.py": "print('train')"},
    }]
    tweets = [_tweet("fixed eval or it did not happen")]
    material = assemble_distill_material(tweets, repos)
    assert "## Repo: karpathy/autoresearch" in material
    assert "### README.md" in material and "readme body" in material
    assert "### train.py" in material
    assert "## 歷史 X posts" in material
    assert "fixed eval or it did not happen" in material


def test_assemble_material_truncates():
    repos = [{"repo": "r", "meta": {}, "files": {"big.md": "x" * 100000}}]
    material = assemble_distill_material([], repos, max_chars=5000)
    assert len(material) <= 5000


def test_assemble_material_empty_inputs():
    assert assemble_distill_material([], []) == ""


def test_backfill_github_repo_never_raises_without_gh(monkeypatch):
    monkeypatch.setattr(rb, "_gh", lambda args, timeout=60: "")
    monkeypatch.setattr(rb, "_fetch_raw_fallback", lambda repo, path: "")
    result = backfill_github_repo("nobody/nothing", key_files=["x.py"])
    assert result == {"repo": "nobody/nothing", "meta": {}, "files": {}}


def test_backfill_github_repo_uses_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(rb, "BACKFILL_DIR", tmp_path)
    monkeypatch.setattr(rb, "_gh", lambda args, timeout=60: "")
    monkeypatch.setattr(rb, "_fetch_raw_fallback", lambda repo, path: f"content of {path}")
    result = backfill_github_repo("karpathy/nanochat", key_files=["speedrun.sh"])
    assert result["files"]["README.md"] == "content of README.md"
    assert result["files"]["speedrun.sh"] == "content of speedrun.sh"
    assert (tmp_path / "karpathy__nanochat.json").exists()


def test_load_knowledge_karpathy_seed_present():
    kb = load_knowledge("karpathy")
    assert "核心原則" in kb
    assert "autoresearch" in kb


def test_load_knowledge_missing_returns_empty():
    assert load_knowledge("nonexistent-guru") == ""


def test_knowledge_rules_extracts_only_rules_section():
    rules = knowledge_rules("karpathy")
    assert rules  # section exists in the seed KB
    assert "固定" in rules or "指標" in rules
    # Section boundaries respected: no other headings bleed in.
    assert "## " not in rules
    assert "原始出處索引" not in rules


def test_knowledge_rules_missing_returns_empty():
    assert knowledge_rules("nonexistent-guru") == ""
