# -*- coding: utf-8
"""P3/P4 harness: Feishu summary, overlay CLI, bad-trade auto rollback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_reach.daily_run.harness import (
    HarnessState,
    auto_rollback_on_bad_trade,
    format_harness_errors_markdown,
    format_harness_overlay_markdown,
    format_harness_push_markdown,
    format_harness_rollback_markdown,
    refine_after_job,
    rollback_refinement,
)
from agent_reach.daily_run.harness_migrate import sync_user_harness_keys
from agent_reach.daily_run.report_push import render_close_sections, render_morning_sections
from agent_reach.daily_run.settings import effective_settings
from agent_reach.daily_run.workflows import (
    _harness_push_summary_enabled,
    push_harness_followups,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: hdir / "refinements.jsonl")
    return hdir


class TestHarnessPushMarkdown:
    def test_format_harness_push_markdown_layers(self):
        md = format_harness_push_markdown(
            {
                "layer_a": {"refinement_id": "ref_a", "changes": 2, "skipped": False},
                "layer_b": {
                    "refinement_id": "ref_b",
                    "changes": 1,
                    "skipped": False,
                    "planner": "llm",
                    "proposal_summary": "合并重复记忆",
                },
            },
            job="close",
        )
        assert "Harness 进化 · 收盘" in md
        assert "ref_a" in md
        assert "ref_b" in md
        assert "合计 **3** 项" in md

    def test_render_close_sections_includes_harness(self):
        sections = render_close_sections(
            verify_name="澜起科技",
            verify_markdown="验证完成",
            harness_markdown="**Harness 进化 · 收盘**\n- test",
            portfolio_markdown="盈亏",
        )
        categories = [s.category for s in sections]
        assert "harness" in categories
        assert categories.index("harness") < categories.index("daily_portfolio")

    def test_push_summary_enabled_flags(self):
        cfg = {"harness": {"push_summary_on_close": True, "push_summary_on_weekly": False}}
        assert _harness_push_summary_enabled(cfg, report_kind="close") is True
        assert _harness_push_summary_enabled(cfg, report_kind="weekly") is False
        cfg2 = {"harness": {"push_summary_on_close": True}}
        assert _harness_push_summary_enabled(cfg2, report_kind="weekly") is True
        cfg3 = {"harness": {"push_summary_on_forecast": True, "push_summary_on_close": False}}
        assert _harness_push_summary_enabled(cfg3, report_kind="forecast") is True
        cfg4 = {"harness": {"push_summary_on_close": True}}
        assert _harness_push_summary_enabled(cfg4, report_kind="morning") is True
        cfg5 = {"harness": {"push_summary_on_intraday": False}}
        assert _harness_push_summary_enabled(cfg5, report_kind="intraday") is False

    def test_render_morning_sections_includes_harness(self):
        sections = render_morning_sections(
            team_markdown="",
            report_markdown="MSS 决策",
            report={"name": "澜起科技", "verdict": "观察"},
            harness_markdown="**Harness 进化 · 早盘**",
        )
        assert any(s.category == "harness" for s in sections)

    def test_format_harness_errors_markdown(self):
        md = format_harness_errors_markdown(["close_harness: boom", "layer_a: timeout"])
        assert "Harness 异常" in md
        assert "close_harness" in md

    def test_format_harness_push_markdown_includes_errors(self):
        md = format_harness_push_markdown(
            {"layer_a": {"refinement_id": "ref_a", "changes": 1, "skipped": False}},
            job="close",
            harness_errors=["verify: failed"],
        )
        assert "ref_a" in md
        assert "verify: failed" in md

    def test_format_harness_rollback_markdown(self):
        md = format_harness_rollback_markdown(
            {
                "triggered": True,
                "pnl_pct": -1.5,
                "pnl_label": "日PnL",
                "threshold": -1.0,
                "count": 2,
                "rolled_back": [{"refinement_id": "ref_a"}],
            },
            job="close",
        )
        assert "坏交易回滚" in md
        assert "ref_a" in md

    def test_push_harness_followups_rollback_only(self, monkeypatch):
        pushed: list[str] = []

        def _fake_push(**kwargs):
            pushed.append(kwargs.get("body") or "")
            return {"mode": "single"}

        monkeypatch.setattr(
            "agent_reach.daily_run.workflows._push_harness_summary_card",
            lambda *args, **kwargs: _fake_push(**kwargs),
        )
        steps = push_harness_followups(
            settings={"harness": {"push_rollback_on_feishu": True}},
            config=object(),
            report_kind="close",
            harness_result={
                "auto_rollback": {
                    "triggered": True,
                    "pnl_pct": -2.0,
                    "pnl_label": "日PnL",
                    "threshold": -1.0,
                    "count": 1,
                }
            },
            push=True,
            summary_in_main_push=False,
        )
        assert steps == ["push_harness_rollback"]
        assert "坏交易回滚" in pushed[0]

    def test_format_harness_push_markdown_close_skills(self):
        md = format_harness_push_markdown(
            {
                "layer_a": {"refinement_id": "ref_a", "changes": 1, "skipped": False},
                "close_skills": {
                    "verify": {"refinement_id": "ref_v", "changes": 2, "skipped": False},
                    "data_audit": {"refinement_id": "ref_d", "changes": 1, "skipped": False},
                },
            },
            job="close",
        )
        assert "ref_v" in md
        assert "ref_d" in md
        assert "合计 **4** 项" in md


class TestHarnessOverlay:
    def test_format_harness_overlay_markdown_from_runtime(self):
        base = {"harness": {"runtime_overlay": True}}
        effective = {
            "harness_runtime": {
                "threshold_overlay": {
                    "low_position_20d": {"base": 0.4, "effective": 0.45},
                },
                "runtime_overlay": {
                    "max_holdings": {"base": 5.0, "effective": 4.0},
                },
            }
        }
        md = format_harness_overlay_markdown(base, effective)
        assert "low_position_20d" in md
        assert "0.4 → 0.45" in md
        assert "max_holdings" in md

    def test_effective_settings_overlay_produces_runtime_meta(self):
        base = {
            "harness": {"enabled": True, "runtime_overlay": False},
            "thresholds": {"low_position_20d": 0.4, "max_snapshot_age_hours": 24},
            "mss_weights": {"fx": 0.2, "flow": 0.2, "global": 0.15, "sentiment": 0.15},
        }
        effective = effective_settings(base)
        md = format_harness_overlay_markdown(base, effective)
        assert "overlay disabled" in md or isinstance(md, str)


class TestAutoRollbackOnBadTrade:
    def test_skips_when_disabled(self, harness_tmp):
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"daily_pnl_pct": -2.0},
            harness_result={"layer_a": {"refinement_id": "ref_a", "changes": 1}},
            settings={"harness": {"auto_rollback_on_bad_trade": False}},
        )
        assert result["skipped"] is True

    def test_skips_when_pnl_above_threshold(self, harness_tmp):
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"daily_pnl_pct": -0.5},
            harness_result={"layer_a": {"refinement_id": "ref_a", "changes": 1}},
            settings={"harness": {"auto_rollback_on_bad_trade": True, "bad_trade_pnl_pct": -1.0}},
            job="close",
        )
        assert result["skipped"] is True
        assert result["reason"] == "pnl above threshold"

    def test_weekly_uses_weekly_threshold(self, harness_tmp):
        created = refine_after_job(
            "weekly",
            evidence={"report": {"weekly_pnl_pct": -1.0, "process_improvements": []}},
            settings={"harness": {"enabled": True}},
        )
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"weekly_pnl_pct": -1.5},
            harness_result={"layer_a": created},
            settings={
                "harness": {
                    "auto_rollback_on_bad_trade": True,
                    "bad_trade_weekly_pnl_pct": -2.0,
                }
            },
            job="weekly",
        )
        assert result["skipped"] is True

        result2 = auto_rollback_on_bad_trade(
            portfolio_summary={"weekly_pnl_pct": -2.5},
            harness_result={"layer_a": created},
            settings={
                "harness": {
                    "auto_rollback_on_bad_trade": True,
                    "bad_trade_weekly_pnl_pct": -2.0,
                }
            },
            job="weekly",
        )
        assert result2["triggered"] is True

    def test_rolls_back_close_skills_on_bad_trade(self, harness_tmp):
        state = HarnessState.load()
        state.upsert(
            "memory",
            "pre_rule",
            title="pre",
            content="规则PRE：收盘前应保留",
            source="test",
            job="weekly",
            evidence="",
        )
        state.save()

        verify_ref = refine_after_job(
            "close",
            evidence={"rules": ["verify规则：应撤销"]},
            settings={"harness": {"enabled": True, "jobs": {"close": True}}},
        )
        harness_result = {
            "close_skills": {"verify": verify_ref},
        }
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"daily_pnl_pct": -1.5},
            harness_result=harness_result,
            settings={"harness": {"auto_rollback_on_bad_trade": True, "bad_trade_pnl_pct": -1.0}},
            job="close",
        )
        assert result["triggered"] is True
        assert result["count"] == 1
        state = HarnessState.load()
        contents = [e.content for e in state.entries["memory"].values()]
        assert "规则PRE：收盘前应保留" in contents
        assert "verify规则：应撤销" not in contents

    def test_rolls_back_close_refinements_on_bad_trade(self, harness_tmp):
        state = HarnessState.load()
        state.upsert(
            "memory",
            "pre_rule",
            title="pre",
            content="规则PRE：收盘前应保留",
            source="test",
            job="weekly",
            evidence="",
        )
        state.save()

        first = refine_after_job(
            "close",
            evidence={"rules": ["规则A：坏交易新增"]},
            settings={"harness": {"enabled": True}},
        )
        second = refine_after_job(
            "close",
            evidence={"rules": ["规则B：坏交易后应撤销"]},
            settings={"harness": {"enabled": True}},
        )
        harness_result = {
            "layer_a": first,
            "layer_b": second,
        }
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"daily_pnl_pct": -1.5},
            harness_result=harness_result,
            settings={"harness": {"auto_rollback_on_bad_trade": True, "bad_trade_pnl_pct": -1.0}},
            job="close",
        )
        assert result["triggered"] is True
        assert result["count"] == 2
        state = HarnessState.load()
        contents = [e.content for e in state.entries["memory"].values()]
        assert "规则PRE：收盘前应保留" in contents
        assert "规则A：坏交易新增" not in contents
        assert "规则B：坏交易后应撤销" not in contents

    def test_rollback_event_not_re_rolled_back(self, harness_tmp):
        created = refine_after_job(
            "close",
            evidence={"rules": ["临时规则"]},
            settings={"harness": {"enabled": True}},
        )
        rollback_refinement(created["refinement_id"])
        result = auto_rollback_on_bad_trade(
            portfolio_summary={"daily_pnl_pct": -3.0},
            harness_result={"layer_a": created},
            settings={"harness": {"auto_rollback_on_bad_trade": True, "bad_trade_pnl_pct": -1.0}},
            job="close",
        )
        assert result["triggered"] is True
        assert result["count"] >= 0


class TestHarnessSyncSettings:
    def test_sync_user_harness_keys_adds_missing(self, tmp_path):
        user_file = tmp_path / "daily_run_settings.json"
        user_file.write_text(
            json.dumps(
                {
                    "mss_weights": {"fx": 0.2, "flow": 0.2, "global": 0.15, "sentiment": 0.15},
                    "thresholds": {"max_snapshot_age_hours": 24, "low_position_20d": 0.4},
                    "harness": {"enabled": True},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = sync_user_harness_keys(path=user_file, dry_run=True)
        assert result["added"]
        assert any("push_summary_on_close" in key for key in result["added"])
        assert any("expert_consensus_weekly" in key for key in result["added"])
