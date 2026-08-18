# -*- coding: utf-8
"""Tests for continual harness self-learning."""

from pathlib import Path

import pytest

from agent_reach.daily_run.harness import (
    HarnessState,
    build_manifest_harness_summary,
    close_open_plans,
    format_harness_for_briefing,
    refine_after_job,
    refine_after_job_llm,
    refine_after_job_llm_summarize,
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


class TestHarnessLlmSummarize:
    def test_summarize_blocks_high_freq_jobs(self, harness_tmp):
        layer_a = {"skipped": False, "refinement_id": "ref_a", "changes": 1}
        for job in ("morning", "intraday"):
            result = refine_after_job_llm_summarize(
                job,
                evidence={"memory": ["test"], "summary": job},
                settings={
                    "harness": {
                        "enabled": True,
                        "llm_refine": {"enabled": True, "summarize_enabled": True},
                    }
                },
                layer_a_result=layer_a,
            )
            assert result["skipped"] is True
            assert "not allowed" in result.get("reason", "")

    def test_summarize_skips_without_provider(self, harness_tmp, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.llm_chat.resolve_chat_provider",
            lambda provider: None,
        )
        result = refine_after_job_llm_summarize(
            "skill_closure",
            evidence={"memory": ["layer a fact"], "summary": "skill_closure"},
            settings={
                "harness": {
                    "enabled": True,
                    "llm_refine": {"enabled": True, "summarize_enabled": True, "cooldown_hours": 0},
                }
            },
            layer_a_result={"skipped": False, "changes": 1},
        )
        assert result["skipped"] is True
        assert result.get("reason") == "no llm provider"

    def test_summarize_after_skill_closure_with_mock_llm(self, harness_tmp, monkeypatch):
        from agent_reach.daily_run.harness_skill_base import apply_skill_refinement

        monkeypatch.setattr(
            "agent_reach.daily_run.llm_chat.resolve_chat_provider",
            lambda provider: "deepseek",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.harness.plan_harness_refinement",
            lambda job, evidence, state, settings=None, instructions="": {
                "summary": "summarize skill_closure",
                "rationale": "mock",
                "planner": "llm",
                "edits": [
                    {
                        "action": "create",
                        "kind": "playbook",
                        "entry_id": "closure_synth",
                        "title": "周六综合",
                        "content": "综合：收紧 MSS 偏离时的观察池",
                    }
                ],
            },
        )
        result = apply_skill_refinement(
            "skill_closure",
            {
                "memory": ["MSS 预测偏离：下日调低进攻阈值"],
                "playbook": ["mss/high：MSS miss — detail"],
                "summary": "skill_closure improvements=1",
            },
            settings={
                "harness": {
                    "enabled": True,
                    "jobs": {"skill_closure": True},
                    "llm_refine": {
                        "enabled": True,
                        "summarize_enabled": True,
                        "summarize_cooldown_hours": 0,
                    },
                }
            },
        )
        assert result.get("skipped") is False
        summarize = result.get("llm_summarize") or {}
        assert summarize.get("skipped") is False
        assert summarize.get("layer") == "summarize"
        state = HarnessState.load()
        playbook = " ".join(e.content for e in state.entries["playbook"].values())
        assert "综合" in playbook or "MSS" in playbook

    def test_use_llm_review_gate(self, harness_tmp, monkeypatch):
        from agent_reach.daily_run.harness import review_harness_refine

        monkeypatch.setattr(
            "agent_reach.daily_run.llm_chat.resolve_chat_provider",
            lambda provider: "deepseek",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.llm_chat.chat_json",
            lambda **kwargs: {
                "should_refine": True,
                "rationale": "mock llm review",
                "instructions": "合并重复项",
            },
        )
        state = HarnessState.load()
        review = review_harness_refine(
            "close",
            {
                "verify": {"deviations": [{"field": "mss"}]},
                "portfolio_summary": {"daily_pnl_pct": 0.6},
            },
            state,
            settings={
                "harness": {
                    "llm_refine": {
                        "enabled": True,
                        "use_llm_review": True,
                        "cooldown_hours": 0,
                    }
                }
            },
        )
        assert review["should_refine"] is True
        assert review["rationale"] == "mock llm review"


class TestManifestHarnessSummary:
    def test_build_manifest_harness_summary_nested(self):
        payload = {
            "job": "close",
            "result": {
                "harness": {
                    "layer_a": {"refinement_id": "ref_a", "changes": 2, "skipped": False, "job": "close"},
                    "layer_b": {
                        "refinement_id": "ref_b",
                        "changes": 1,
                        "skipped": False,
                        "job": "close",
                        "planner": "llm",
                    },
                }
            },
            "harness_errors": ["run_guard:dedupe: boom"],
        }
        summary = build_manifest_harness_summary(payload)
        assert summary["total_changes"] == 3
        assert len(summary["refinements"]) == 2
        assert summary["errors"] == ["run_guard:dedupe: boom"]
        assert any(r.get("planner") == "llm" for r in summary["refinements"])


class TestHarnessLlmCompact:
    def test_compact_llm_user_payload_caps_size(self):
        from agent_reach.daily_run.harness import _compact_llm_user_payload, _llm_refine_limits

        limits = _llm_refine_limits({"max_context_chars": 400})
        payload = _compact_llm_user_payload(
            {
                "job": "close",
                "signals": ["x" * 200],
                "layer_a": {"memory": ["a" * 300], "policy": [], "playbook": [], "plan": []},
                "harness_overview": "o" * 900,
                "recent_refinements": [{"summary": "s" * 200, "changes": ["c" * 200]}],
            },
            limits,
        )
        assert len(__import__("json").dumps(payload, ensure_ascii=False)) <= 500

    def test_build_merged_close_harness_evidence(self):
        from agent_reach.daily_run.harness import build_merged_close_harness_evidence

        evidence = build_merged_close_harness_evidence(
            [
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "result": {"verify": {"summary": "宏观否决", "recommendations": ["维持高现金"]}},
                },
                {
                    "code": "002273",
                    "name": "水晶光电",
                    "result": {"verify": {"summary": "观察", "recommendations": []}},
                },
            ],
            primary_snapshot={"code": "688008", "name": "澜起科技"},
            portfolio_summary={"daily_pnl": -90, "daily_pnl_pct": -0.1},
        )
        assert evidence["portfolio_scope"] == "merged"
        assert evidence["symbol_count"] == 2
        assert evidence["portfolio_summary"]["daily_pnl"] == -90

    def test_merged_close_signals(self):
        from agent_reach.daily_run.harness import _collect_refine_signals

        signals = _collect_refine_signals(
            "close",
            {
                "portfolio_scope": "merged",
                "symbol_count": 2,
                "portfolio_summary": {"daily_pnl_pct": 0.6},
                "verify": {"recommendations": ["维持"]},
            },
        )
        assert any("全持仓" in s for s in signals)
