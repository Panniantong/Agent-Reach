# -*- coding: utf-8 -*-
"""Tests for the bundled Agent Reach skill suite."""

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _skill_dir(name: str) -> Path:
    return _repo_root() / "agent_reach" / "skills" / name


def test_shape_brief_contract_is_fixed_and_complete():
    contract = (_skill_dir("agent-reach-shape-brief") / "references" / "brief-contract.md").read_text(
        encoding="utf-8"
    )
    defaults = (_skill_dir("agent-reach-shape-brief") / "references" / "defaults.md").read_text(
        encoding="utf-8"
    )
    skill = (_skill_dir("agent-reach-shape-brief") / "SKILL.md").read_text(encoding="utf-8")

    required_fields = [
        "調査ブリーフ",
        "目的",
        "対象",
        "期待成果物",
        "鮮度要件",
        "含める範囲",
        "除外範囲",
        "地域・言語",
        "重視ソース",
        "禁止ソース",
        "証拠厳密度",
        "調査スケール",
        "前提と仮定",
    ]

    for field in required_fields:
        assert field in contract

    assert "Ask Only When" in defaults
    assert "前提と仮定" in defaults
    assert "Do not generate an external prompt or start collection here." in skill


def test_orchestrate_references_cover_subagent_policy_and_run_rules():
    skill = (_skill_dir("agent-reach-orchestrate") / "SKILL.md").read_text(encoding="utf-8")
    intake = (_skill_dir("agent-reach-orchestrate") / "references" / "intake-and-handoff.md").read_text(
        encoding="utf-8"
    )
    flow = (_skill_dir("agent-reach-orchestrate") / "references" / "orchestration-flow.md").read_text(
        encoding="utf-8"
    )
    policy = (_skill_dir("agent-reach-orchestrate") / "references" / "subagent-policy.md").read_text(
        encoding="utf-8"
    )
    routing = (_skill_dir("agent-reach-orchestrate") / "references" / "routing-guides.md").read_text(
        encoding="utf-8"
    )
    examples = (_skill_dir("agent-reach-orchestrate") / "references" / "examples.md").read_text(
        encoding="utf-8"
    )

    assert "Start actual Agent Reach checks and collection in-session." in skill
    assert "Use at most one intake-only subagent per user request" in skill
    assert "調査ブリーフ" in intake
    assert "run `agent-reach channels --json`" in flow
    assert "run `agent-reach doctor --json`" in flow
    assert "agent-reach collect --json" in flow
    assert "Use one intake-only subagent" in policy
    assert "do not delegate channel checks, collection start, or final synthesis" in policy

    expected_sections = [
        "Latest-Info Research",
        "OSS Or Repository Research",
        "Company Or Product Comparison",
        "Community Reaction Collection",
        "Documentation Research",
        "Japanese And English Cross-Market Research",
        "Broad Research",
    ]

    for section in expected_sections:
        assert section in routing

    assert "agent-reach collect --json --save .agent-reach/evidence.jsonl" in examples
    assert "agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json" in examples
    assert "agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json" in examples


def test_maintainer_review_skill_has_policy_and_output_contract():
    skill = (_skill_dir("agent-reach-maintain-proposals") / "SKILL.md").read_text(encoding="utf-8")
    policy = (_skill_dir("agent-reach-maintain-proposals") / "references" / "policy-tests.md").read_text(
        encoding="utf-8"
    )
    output = (_skill_dir("agent-reach-maintain-proposals") / "references" / "review-output.md").read_text(
        encoding="utf-8"
    )

    assert "adopt_now" in skill
    assert "Keep Agent Reach thin" in skill
    assert "Fast Reject Signals" in policy
    assert "Split-When-Possible Rule" in policy
    assert "Implementation Handoff" in output


def test_maintainer_release_skill_has_shipping_guardrails():
    skill = (_skill_dir("agent-reach-maintain-release") / "SKILL.md").read_text(encoding="utf-8")
    boundaries = (_skill_dir("agent-reach-maintain-release") / "references" / "change-boundaries.md").read_text(
        encoding="utf-8"
    )
    flow = (_skill_dir("agent-reach-maintain-release") / "references" / "release-flow.md").read_text(
        encoding="utf-8"
    )

    assert "commit, push, or reinstall" in skill
    assert "Never push unrelated dirty-tree changes" in skill
    assert "Must-Stay-True Rules" in boundaries
    assert "Reinstall After Push" in flow
    assert "skip test execution and say so" in flow
