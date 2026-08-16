# -*- coding: utf-8
"""Tests for continual harness self-learning."""

from pathlib import Path

import pytest

from agent_reach.daily_run.harness import (
    HarnessState,
    close_open_plans,
    format_harness_for_briefing,
    refine_after_job,
    refine_after_job_llm,
    render_harness_content,
    rollback_refinement,
)


@pytest.fixture
def harness_tmp(monkeypatch, tmp_path):
    hdir = tmp_path / "harness"
    monkeypatch.setattr("agent_reach.daily_run.harness.harness_dir", lambda: hdir)
    monkeypatch.setattr("agent_reach.daily_run.harness._state_path", lambda: hdir / "harness_state.json")
    monkeypatch.setattr("agent_reach.daily_run.harness._refinements_path", lambda: hdir / "refinements.jsonl")
    return hdir


class TestHarnessRefine:
    def test_close_refine_writes_memory(self, harness_tmp):
        result = refine_after_job(
            "close",
            evidence={
                "rules": ["宏观一票否决生效：维持高现金，禁止接飞刀"],
                "verify": {"summary": "澜起科技 验证完成", "recommendations": ["维持高现金"]},
                "name": "澜起科技",
                "portfolio_summary": {"daily_pnl": 100.0, "daily_pnl_pct": 0.12},
            },
            settings={"harness": {"enabled": True}},
        )
        assert result["skipped"] is False
        assert result["changes"] >= 1
        state = HarnessState.load()
        assert len(state.entries["memory"]) >= 1
        assert len(state.entries["playbook"]) >= 1

    def test_weekly_refine_playbook(self, harness_tmp):
        result = refine_after_job(
            "weekly",
            evidence={
                "report": {
                    "week_start": "2026-08-10",
                    "week_end": "2026-08-14",
                    "weekly_pnl": -500.0,
                    "weekly_pnl_pct": -0.58,
                    "process_improvements": [
                        {
                            "title": "收紧观察池",
                            "detail": "宏观回避时减少新增",
                            "action": "close 时仅 sector_pool 补位",
                            "priority": "high",
                        }
                    ],
                }
            },
            settings={"harness": {"enabled": True}},
        )
        assert result["skipped"] is False
        state = HarnessState.load()
        assert any("观察池" in e.content for e in state.entries["playbook"].values())
        assert any("观察池" in e.content for e in state.entries["plan"].values())

    def test_forecast_refine_kronos_playbook(self, harness_tmp):
        result = refine_after_job(
            "forecast",
            evidence={
                "forecast": {
                    "week_start": "2026-08-17",
                    "week_end": "2026-08-21",
                    "notes": ["复用周六周报 digest"],
                    "symbols": {
                        "300308": {
                            "code": "300308",
                            "name": "中际旭创",
                            "kronos": {"available": True, "cum_change_pct": 2.0},
                        },
                        "600584": {
                            "code": "600584",
                            "name": "长电科技",
                            "kronos": {"available": True, "cum_change_pct": -5.0},
                        },
                    },
                }
            },
            settings={"harness": {"enabled": True}},
        )
        assert result["skipped"] is False
        state = HarnessState.load()
        playbook_text = " ".join(e.content for e in state.entries["playbook"].values())
        assert "中际旭创" in playbook_text or "长电科技" in playbook_text

    def test_rollback_restores_prior_entry(self, harness_tmp):
        refine_after_job(
            "close",
            evidence={"rules": ["规则A：测试"]},
            settings={"harness": {"enabled": True}},
        )
        second = refine_after_job(
            "close",
            evidence={"rules": ["规则B：覆盖"]},
            settings={"harness": {"enabled": True}},
        )
        rollback_refinement(second["refinement_id"])
        state = HarnessState.load()
        contents = [e.content for e in state.entries["memory"].values()]
        assert "规则A：测试" in contents
        assert "规则B：覆盖" not in contents

    def test_format_briefing(self, harness_tmp):
        refine_after_job(
            "close",
            evidence={"rules": ["测试规则注入简报"]},
            settings={"harness": {"enabled": True}},
        )
        md = format_harness_for_briefing(limit=2)
        assert "测试规则注入简报" in md

    def test_render_harness_content_xml(self, harness_tmp):
        refine_after_job(
            "weekly",
            evidence={
                "report": {
                    "week_start": "2026-08-10",
                    "week_end": "2026-08-14",
                    "process_improvements": [
                        {"title": "测试计划", "detail": "d", "action": "a", "priority": "high"}
                    ],
                }
            },
            settings={"harness": {"enabled": True}},
        )
        xml = render_harness_content(limit=3)
        assert xml.startswith("<harness>")
        assert "<plan" in xml
        assert 'status="open"' in xml
        assert "测试计划" in xml or "下周" in xml

    def test_close_open_plans_on_monday(self, harness_tmp):
        refine_after_job(
            "weekly",
            evidence={
                "report": {
                    "week_start": "2026-08-10",
                    "week_end": "2026-08-14",
                    "process_improvements": [
                        {"title": "待关闭计划", "detail": "d", "action": "a", "priority": "medium"}
                    ],
                }
            },
            settings={"harness": {"enabled": True}},
        )
        state = HarnessState.load()
        assert any((e.status or "open") == "open" for e in state.entries["plan"].values())

        result = close_open_plans(settings={"harness": {"close_plans_on_morning": True}})
        assert result["count"] >= 1
        state = HarnessState.load()
        assert all((e.status or "") == "done" for e in state.entries["plan"].values())

        xml = render_harness_content(limit=5)
        assert not xml or "<plan" not in xml

    def test_disabled_skips(self, harness_tmp):
        result = refine_after_job(
            "close",
            evidence={"rules": ["不应写入"]},
            settings={"harness": {"enabled": False}},
        )
        assert result["skipped"] is True
        assert not (harness_tmp / "harness_state.json").exists()


class TestHarnessLayerB:
    def test_review_rejects_when_no_signals(self, harness_tmp):
        from agent_reach.daily_run.harness import review_harness_refine

        state = HarnessState.load()
        review = review_harness_refine(
            "close",
            evidence={"verify": {}, "portfolio_summary": {}},
            state=state,
            settings={"harness": {"llm_refine": {"enabled": True, "cooldown_hours": 0}}},
        )
        assert review["should_refine"] is False

    def test_llm_refine_weekly_deterministic(self, harness_tmp, monkeypatch):
        from agent_reach.daily_run.harness import refine_after_job_llm

        monkeypatch.setattr(
            "agent_reach.daily_run.llm_chat.resolve_chat_provider",
            lambda provider: None,
        )
        result = refine_after_job_llm(
            "weekly",
            evidence={
                "report": {
                    "week_start": "2026-08-10",
                    "week_end": "2026-08-14",
                    "weekly_pnl_pct": -0.9,
                    "process_improvements": [
                        {"title": "收紧观察池", "detail": "宏观回避时减少新增", "action": "close 补位"}
                    ],
                },
                "applied_config": ["macro_veto=40"],
            },
            settings={"harness": {"enabled": True, "llm_refine": {"enabled": True, "cooldown_hours": 0}}},
        )
        assert result["skipped"] is False
        assert result["planner"] == "deterministic"
        state = HarnessState.load()
        playbook = " ".join(e.content for e in state.entries["playbook"].values())
        assert "收紧观察池" in playbook

    def test_llm_refine_respects_cooldown(self, harness_tmp):
        from agent_reach.daily_run.harness import refine_after_job_llm

        settings = {"harness": {"enabled": True, "llm_refine": {"enabled": True, "cooldown_hours": 24}}}
        evidence = {
            "report": {
                "week_start": "2026-08-10",
                "week_end": "2026-08-14",
                "weekly_pnl_pct": -1.0,
                "process_improvements": [{"title": "A", "detail": "d"}],
            }
        }
        first = refine_after_job_llm("weekly", evidence=evidence, settings=settings)
        assert first["skipped"] is False
        second = refine_after_job_llm("weekly", evidence=evidence, settings=settings)
        assert second["skipped"] is True
        assert "cooldown" in str(second.get("reason", "")).lower()

    def test_manual_refine_skips_review_gate(self, harness_tmp):
        from agent_reach.daily_run.harness import refine_after_job_llm

        result = refine_after_job_llm(
            "forecast",
            evidence={
                "forecast": {
                    "week_start": "2026-08-17",
                    "week_end": "2026-08-21",
                    "symbols": {
                        "300308": {
                            "code": "300308",
                            "name": "中际旭创",
                            "kronos": {"available": True, "cum_change_pct": 2.5},
                        }
                    },
                }
            },
            settings={"harness": {"enabled": True, "llm_refine": {"enabled": True, "cooldown_hours": 0}}},
            skip_review=True,
        )
        assert result["skipped"] is False
        assert result["review"]["rationale"] == "manual refine"
