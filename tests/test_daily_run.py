# -*- coding: utf-8 -*-
"""Tests for daily_run skill pipeline."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_reach.daily_run.auditor import run_data_audit
from agent_reach.daily_run.pipeline import evaluate_snapshot, render_markdown
from agent_reach.daily_run.quality_gate import validate_report
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.verdict import compute_mss, compute_verdict


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def base_snapshot():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "as_of": now,
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "reference_price": 256.0,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {
            "quote": {"summary": "sina"},
            "flow": {"summary": "northbound"},
            "sentiment": {"summary": "xueqiu"},
        },
        "structured_review_complete": True,
    }


class TestSettings:
    def test_load_settings(self, settings):
        assert settings["version"] == "1.0.0"
        assert "macro_veto" not in settings["thresholds"]

    def test_effective_settings_evolve_thresholds(self):
        cfg = effective_settings()
        assert cfg["thresholds"]["macro_veto"] >= 25
        assert cfg["thresholds"]["aggressive_entry"] >= 40
        assert "max_price_deviation_pct" in cfg["thresholds"]


class TestAuditor:
    def test_audit_passes_fresh_snapshot(self, settings, base_snapshot):
        result = run_data_audit(base_snapshot, settings)
        assert result.passed is True

    def test_audit_fails_stale_snapshot(self, settings, base_snapshot):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        base_snapshot["as_of"] = old
        result = run_data_audit(base_snapshot, settings)
        assert result.passed is False
        assert any("过期" in i for i in result.issues)

    def test_audit_fails_missing_sources(self, settings, base_snapshot):
        base_snapshot["sources"] = {"quote": "ok"}
        result = run_data_audit(base_snapshot, settings)
        assert result.passed is False

    def test_audit_price_deviation(self, settings, base_snapshot):
        base_snapshot["reference_price"] = 200.0
        result = run_data_audit(base_snapshot, settings)
        assert result.passed is False


class TestVerdict:
    def test_compute_mss(self, settings, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState

        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        settings = dict(settings)
        settings.setdefault("harness", {})["runtime_overlay"] = False
        macro_weights = {"fx": 0.25, "flow": 0.25, "global": 0.25, "sentiment": 0.25}
        cfg = {**settings, "mss_weights": macro_weights}
        score = compute_mss({"fx": 40, "flow": 40, "global": 40, "sentiment": 40}, cfg)
        assert score == 40.0

    def test_compute_mss_with_expert_dims(self, settings, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState

        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        settings = dict(settings)
        settings.setdefault("harness", {})["runtime_overlay"] = False
        breakdown = {
            "fx": 35,
            "flow": 48,
            "global": 38,
            "sentiment": 50,
            "technical": 52,
            "quant": 49,
            "risk": 55,
        }
        score = compute_mss(breakdown, settings)
        assert score != 42.5

    def test_compute_mss_uses_harness_effective_weights(self, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState, HarnessEntry

        state = HarnessState()
        state.entries["memory"]["dev"] = HarnessEntry(
            id="dev",
            kind="memory",
            title="偏差",
            content="偏差：价格变动 23.7% 超过锚点阈值 8.0%",
            source="deterministic",
            job="forecast",
            evidence="forecast",
            created_at="2026-08-17T00:00:00+00:00",
            updated_at="2026-08-17T00:00:00+00:00",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: state,
        )
        settings = load_settings()
        settings.setdefault("harness", {})["runtime_overlay_sources"] = ["memory"]
        breakdown = {
            "fx": 40,
            "flow": 40,
            "global": 40,
            "sentiment": 40,
            "technical": 80,
            "quant": 80,
            "risk": 40,
        }
        neutral = compute_mss(
            breakdown,
            {**settings, "harness": {**settings.get("harness", {}), "runtime_overlay": False}},
        )
        evolved = compute_mss(breakdown, settings)
        assert evolved != neutral

    def test_macro_veto_avoid(self, settings, base_snapshot, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState

        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        settings = dict(settings)
        settings.setdefault("harness", {})["runtime_overlay"] = False
        base_snapshot["mss_breakdown"] = {"fx": 30, "flow": 30, "global": 30, "sentiment": 30}
        base_snapshot["mss_final"] = 30.0
        v = compute_verdict(base_snapshot, settings)
        assert v.verdict == "回避"
        assert v.blocked is True

    def test_aggressive_buy(self, settings, base_snapshot, monkeypatch):
        from agent_reach.daily_run.harness import HarnessState

        monkeypatch.setattr(
            "agent_reach.daily_run.harness.load_harness",
            lambda: HarnessState(),
        )
        settings = dict(settings)
        settings.setdefault("harness", {})["runtime_overlay"] = False
        base_snapshot["mss_breakdown"] = {"fx": 55, "flow": 55, "global": 55, "sentiment": 55}
        base_snapshot["mss_final"] = 55.0
        v = compute_verdict(base_snapshot, settings)
        assert v.verdict == "可做"

    def test_missing_technical_watch(self, settings, base_snapshot):
        base_snapshot["mss_breakdown"] = {"fx": 55, "flow": 55, "global": 55, "sentiment": 55}
        base_snapshot["mss_final"] = 55.0
        base_snapshot.pop("ma20")
        v = compute_verdict(base_snapshot, settings)
        assert v.verdict == "观察"


class TestQualityGate:
    def test_gate_passes_complete_report(self, settings, base_snapshot):
        ev = evaluate_snapshot(base_snapshot, settings)
        gate = ev["gate"]
        assert gate.passed is True

    def test_render_markdown_contains_verdict(self, settings, base_snapshot):
        ev = evaluate_snapshot(base_snapshot, settings)
        md = render_markdown(ev["report"])
        assert "结论" in md
        assert "MSS" in md


class TestPipeline:
    def test_evaluate_snapshot_json_serializable(self, settings, base_snapshot):
        ev = evaluate_snapshot(base_snapshot, settings)
        json.dumps(ev["report"], ensure_ascii=False)

    def test_cli_sample_file_roundtrip(self, settings, base_snapshot, tmp_path):
        p = tmp_path / "snap.json"
        p.write_text(json.dumps(base_snapshot, ensure_ascii=False), encoding="utf-8")
        loaded = json.loads(Path(p).read_text(encoding="utf-8"))
        ev = evaluate_snapshot(loaded, settings)
        assert ev["audit"].passed
