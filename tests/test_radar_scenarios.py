# -*- coding: utf-8 -*-
"""Scenario registry tests — offline: LLM calls, collectors, and network mocked."""

import json
from types import SimpleNamespace

import agent_reach.radar_scenarios as rs
from agent_reach.config import Config
from agent_reach.radar import Item
from agent_reach.radar_scenarios import (
    SCENARIOS,
    fetch_github_trending,
    run_scenario,
    scenarios_manifest,
)

BILINGUAL = "## 繁中版\n\n貼文內容 #AI\n\n觀點僅供參考，非投資建議\n\n## English\n\nPost body #AI\n\nNot financial advice."


def _empty_config(tmp_path) -> Config:
    return Config(config_path=tmp_path / "config.yaml")


def _paper(aid, score, topic="ee"):
    return Item(source="arxiv", kind="paper", title=f"Paper {aid}",
                url=f"https://arxiv.org/abs/{aid}", text="abstract", score=score,
                extra={"arxiv_id": aid, "topic": topic, "topics": [topic], "why": []})


# ── registry shape ─────────────────────────────────────────────────────────


def test_registry_ids_and_manifest_serializable():
    assert set(SCENARIOS) == {
        "arxiv_expert_report", "x_guru_summary", "github_trending_post", "market_signal_post",
    }
    status = {"ollama": {"ok": True}, "twitter": {"ok": False}, "nvidia": {"ok": True},
              "anthropic": {"ok": True}}
    manifest = scenarios_manifest(status)
    json.dumps(manifest)  # must be JSON-serializable for the UI
    by_id = {m["id"]: m for m in manifest}
    assert by_id["arxiv_expert_report"]["ready"] is True
    assert by_id["x_guru_summary"]["ready"] is False
    assert by_id["x_guru_summary"]["missing"] == ["twitter"]


def test_unknown_scenario_and_never_raises(monkeypatch, tmp_path):
    assert run_scenario("nope")["ok"] is False

    def boom(params, config):
        raise RuntimeError("explode")

    monkeypatch.setitem(
        SCENARIOS, "arxiv_expert_report",
        SimpleNamespace(id="arxiv_expert_report", run=boom),
    )
    result = run_scenario("arxiv_expert_report", {}, _empty_config(tmp_path))
    assert result == {"ok": False, "error": "explode"}


# ── arxiv expert report ────────────────────────────────────────────────────


def test_arxiv_expert_writes_report(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(rs, "load_sources", lambda: {"scenario_models": {"arxiv_expert": ["ollama:qwen3:4b"]}})
    import agent_reach.radar_wiki as rw
    monkeypatch.setattr(rw, "_load_all_papers", lambda s, c, w: [_paper("2607.1", 9), _paper("2607.2", 5, "ai")])
    import agent_reach.radar_arxiv as ra
    monkeypatch.setattr(ra, "fetch_paper_text", lambda aid, max_chars=30000: "full text")
    monkeypatch.setattr(rs, "llm_chat_first", lambda specs, sys, usr, cfg=None, timeout=600: ("# 專家報告\n內容", specs[0]))

    result = run_scenario("arxiv_expert_report", {"topic": "ee", "top_n": "1"}, _empty_config(tmp_path))
    assert result["ok"] and len(result["outputs"]) == 1
    body = (tmp_path / "reports").glob("*.md")
    text = next(body).read_text(encoding="utf-8")
    assert "model: ollama:qwen3:4b" in text and "# 專家報告" in text


def test_arxiv_expert_no_papers(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "load_sources", lambda: {})
    import agent_reach.radar_wiki as rw
    monkeypatch.setattr(rw, "_load_all_papers", lambda s, c, w: [])
    result = run_scenario("arxiv_expert_report", {}, _empty_config(tmp_path))
    assert result["ok"] is False


# ── github trending post ───────────────────────────────────────────────────


def test_fetch_github_trending_parses_and_never_raises(monkeypatch):
    payload = {"items": [{"full_name": "a/b", "stargazers_count": 1200,
                          "description": "desc", "language": "Python",
                          "html_url": "https://github.com/a/b"}]}
    monkeypatch.setattr(rs.requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload))
    repos = fetch_github_trending(days=7)
    assert repos == [{"name": "a/b", "stars": 1200, "desc": "desc",
                      "lang": "Python", "url": "https://github.com/a/b"}]

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(rs.requests, "get", boom)
    assert fetch_github_trending() == []


def test_github_post_bilingual_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SOCIAL_DIR", tmp_path / "social")
    monkeypatch.setattr(rs, "load_sources", lambda: {"scenario_models": {"social_post": ["anthropic:claude-fable-5"]}})
    monkeypatch.setattr(rs, "fetch_github_trending", lambda days=7, keyword="", top_n=10, timeout=30: [
        {"name": "a/b", "stars": 1200, "desc": "d", "lang": "Py", "url": "u"}])
    monkeypatch.setattr(rs, "llm_chat_first", lambda specs, sys, usr, cfg=None, timeout=600: (BILINGUAL, specs[0]))
    result = run_scenario("github_trending_post", {}, _empty_config(tmp_path))
    assert result["ok"]
    text = next((tmp_path / "social").glob("*-github.md")).read_text(encoding="utf-8")
    assert "## 繁中版" in text and "## English" in text
    assert "非投資建議" in text and "Not financial advice" in text


# ── market signal post ─────────────────────────────────────────────────────


def test_market_signal_needs_material(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "RADAR_DIR", tmp_path)
    monkeypatch.setattr(rs, "load_sources", lambda: {})
    result = run_scenario("market_signal_post", {}, _empty_config(tmp_path))
    assert result["ok"] is False and "radar" in result["error"]


def test_market_signal_uses_digest_and_market_items(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "RADAR_DIR", tmp_path)
    monkeypatch.setattr(rs, "SOCIAL_DIR", tmp_path / "social")
    monkeypatch.setattr(rs, "load_sources", lambda: {"scenario_models": {"social_post": ["anthropic:claude-fable-5"]}})
    (tmp_path / "latest.md").write_text("# digest 內容", encoding="utf-8")
    (tmp_path / "latest-items.json").write_text(json.dumps({
        "date": "2026-07-11",
        "items": {"market": [{"title": "▲ Technology +2.34%", "source": "finviz:sector"}]},
    }), encoding="utf-8")
    captured = {}

    def fake_llm(specs, system, user, cfg=None, timeout=600):
        captured["user"] = user
        return BILINGUAL, specs[0]

    monkeypatch.setattr(rs, "llm_chat_first", fake_llm)
    result = run_scenario("market_signal_post", {}, _empty_config(tmp_path))
    assert result["ok"]
    assert "digest 內容" in captured["user"] and "Technology" in captured["user"]


# ── model spec resolution ──────────────────────────────────────────────────


def test_model_param_overrides_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SOCIAL_DIR", tmp_path / "social")
    monkeypatch.setattr(rs, "load_sources", lambda: {"scenario_models": {"social_post": ["anthropic:x"]}})
    monkeypatch.setattr(rs, "fetch_github_trending", lambda **k: [
        {"name": "a/b", "stars": 1, "desc": "", "lang": "", "url": ""}])
    seen = {}

    def fake_llm(specs, system, user, cfg=None, timeout=600):
        seen["specs"] = specs
        return BILINGUAL, specs[0]

    monkeypatch.setattr(rs, "llm_chat_first", fake_llm)
    run_scenario("github_trending_post", {"model": "ollama:qwen3:4b"}, _empty_config(tmp_path))
    assert seen["specs"] == ["ollama:qwen3:4b"]
