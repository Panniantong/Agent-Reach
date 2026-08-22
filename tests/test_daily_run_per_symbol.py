# -*- coding: utf-8
"""Tests for per-symbol daily-run orchestration."""

from unittest.mock import patch

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.snapshot_builder import build_snapshot
from agent_reach.daily_run.symbols import list_target_symbols, resolve_target_symbols
from agent_reach.daily_run.report_push import ReportSection, merge_sections_by_category
from agent_reach.daily_run.symbol_runner import run_morning_for_symbols
from agent_reach.daily_run.workflows import load_morning_baseline, save_morning_baseline


PORTFOLIO = {
    "primary_code": "688008",
    "holdings": [
        {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87},
        {"code": "002273", "name": "水晶光电", "shares": 300, "cost": 33.81},
    ],
    "watchlist": [
        {"code": "603986", "name": "兆易创新"},
        {"code": "000725", "name": "京东方A"},
    ],
    "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
}


class TestTargetSymbols:
    def test_list_target_symbols_all(self):
        codes = list_target_symbols(PORTFOLIO, mode="all")
        assert codes == ["688008", "002273", "603986", "000725"]

    def test_resolve_primary_mode(self):
        cfg = load_settings()
        cfg = {**cfg, "schedule": {**(cfg.get("schedule") or {}), "symbols_mode": "primary"}}
        assert resolve_target_symbols(PORTFOLIO, cfg) == ["688008"]

    def test_resolve_all_mode(self):
        cfg = load_settings()
        cfg = {**cfg, "schedule": {**(cfg.get("schedule") or {}), "symbols_mode": "all"}}
        assert len(resolve_target_symbols(PORTFOLIO, cfg)) == 4

    def test_resolve_intraday_symbols_mode_override(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "symbols_mode": "all",
                "intraday_symbols_mode": "holdings",
            },
        }
        assert resolve_target_symbols(PORTFOLIO, cfg, workflow="intraday") == ["688008", "002273"]
        assert len(resolve_target_symbols(PORTFOLIO, cfg)) == 4

    def test_resolve_intraday_all_includes_watchlist(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "intraday_symbols_mode": "all",
            },
        }
        assert resolve_target_symbols(PORTFOLIO, cfg, workflow="intraday") == [
            "688008",
            "002273",
            "603986",
            "000725",
        ]

    def test_resolve_intraday_holdings_watchlist_alias(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "intraday_symbols_mode": "holdings+watchlist",
            },
        }
        assert resolve_target_symbols(PORTFOLIO, cfg, workflow="intraday") == [
            "688008",
            "002273",
            "603986",
            "000725",
        ]

    def test_resolve_close_symbols_mode_holdings(self):
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "symbols_mode": "all",
                "close_symbols_mode": "holdings",
            },
        }
        assert resolve_target_symbols(PORTFOLIO, cfg, workflow="close") == ["688008", "002273"]
        assert len(resolve_target_symbols(PORTFOLIO, cfg)) == 4


class TestPerSymbolSnapshot:
    def test_build_snapshot_uses_symbol_name_for_premarket(self):
        snap = build_snapshot(PORTFOLIO, report_type="premarket", primary_code="002273", enrich=False)
        assert snap["code"] == "002273"
        assert snap["name"] == "水晶光电"


class TestMergeSections:
    def test_merge_sections_by_category_experts_off(self):
        """Experts disabled: per-symbol expert bodies are skipped; decision merges by ## blocks."""
        g1 = [
            ReportSection("experts", "", "expert A"),
            ReportSection("decision", "", "decision A"),
        ]
        g2 = [
            ReportSection("experts", "", "expert B"),
            ReportSection("decision", "", "decision B"),
        ]
        merged = merge_sections_by_category(
            [("澜起科技", g1), ("水晶光电", g2)],
            report_kind="morning",
        )
        assert len(merged) == 1
        assert merged[0].category == "decision"
        assert "澜起科技" in merged[0].body and "水晶光电" in merged[0].body
        assert "2只" in merged[0].title
        assert "expert A" not in merged[0].body

    def test_merge_decision_unified_body(self):
        reports = [
            ("澜起科技", "688008", {"verdict": "观察", "confidence": "中", "mss_final": 42.5, "reasoning": "a"}),
            ("水晶光电", "002273", {"verdict": "观察", "confidence": "低", "mss_final": 40.0, "reasoning": "b"}),
        ]
        from agent_reach.daily_run.report_push import render_merged_decision_markdown

        md = render_merged_decision_markdown(reports, report_kind="morning")
        assert "组合" not in md
        assert "MSS 决策 · 2 只标的" in md
        assert "| 澜起科技 | 688008 |" in md
        assert "### 水晶光电" in md

        g1 = [ReportSection("decision", "", "x")]
        g2 = [ReportSection("decision", "", "y")]
        merged = merge_sections_by_category(
            [("澜起科技", g1), ("水晶光电", g2)],
            report_kind="morning",
            decision_entries=reports,
        )
        assert len(merged) == 1
        assert merged[0].category == "decision"
        assert "MSS 决策 · 2 只标的" in merged[0].body

    def test_merge_experts_unified_body(self):
        snap_a = {
            "team_review": {"consensus_score": 42, "consensus_label": "观察", "conflicts": []},
            "expert_results": [
                {"name": "technical", "score": 45, "summary": "tech A", "success": True},
            ],
        }
        snap_b = {
            "team_review": {"consensus_score": 40, "consensus_label": "观察", "conflicts": []},
            "expert_results": [
                {"name": "technical", "score": 38, "summary": "tech B", "success": True},
            ],
        }
        from agent_reach.daily_run.team import render_merged_experts_markdown

        md = render_merged_experts_markdown([("澜起科技", "688008", snap_a), ("水晶光电", "002273", snap_b)])
        assert "组合共识概览" in md
        assert "各专家评分矩阵" in md
        assert "澜起科技" in md and "水晶光电" in md
        assert "## 澜起科技" not in md

        g1 = [ReportSection("experts", "", "old")]
        g2 = [ReportSection("experts", "", "old2")]
        merged = merge_sections_by_category(
            [("澜起科技", g1), ("水晶光电", g2)],
            report_kind="morning",
            expert_snapshots=[("澜起科技", "688008", snap_a), ("水晶光电", "002273", snap_b)],
        )
        assert len(merged) == 1
        assert "组合共识概览" in merged[0].body


class TestPerSymbolBaselines:
    def test_save_and_load_per_code_baseline(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.workflows.morning_baseline_path",
            lambda code: tmp_path / f"{code}.json",
        )
        snap = {"code": "688008", "name": "澜起科技", "price": 100}
        save_morning_baseline(snap, code="688008")
        loaded = load_morning_baseline(code="688008")
        assert loaded["code"] == "688008"


class TestSymbolRunner:
    @patch("agent_reach.daily_run.intraday.record_morning_scan", return_value={"scan": {"scan_id": "S1"}})
    @patch("agent_reach.daily_run.workflows.run_morning")
    @patch("agent_reach.daily_run.symbol_runner.build_and_save")
    @patch("agent_reach.daily_run.symbol_runner.load_portfolio")
    def test_run_morning_for_symbols(self, mock_pf, mock_build, mock_run, mock_morning_scan, tmp_path):
        mock_pf.return_value = PORTFOLIO
        mock_build.side_effect = [
            ({"code": "688008", "name": "澜起科技"}, tmp_path / "a.json"),
            ({"code": "002273", "name": "水晶光电"}, tmp_path / "b.json"),
        ]
        mock_run.side_effect = [
            {"snapshot": {"code": "688008"}, "evaluation": {"report": {}}, "feishu": {"ok": 1}},
            {"snapshot": {"code": "002273"}, "evaluation": {"report": {}}, "feishu": {"ok": 2}},
        ]
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {**(cfg.get("schedule") or {}), "symbols_mode": "holdings"},
        }
        result = run_morning_for_symbols(settings=cfg, push=False, symbols=["688008", "002273"])
        assert len(result["symbol_results"]) == 2
        assert mock_run.call_count == 2

    @patch("agent_reach.daily_run.report_narrative.generate_merged_morning_narrative")
    @patch("agent_reach.daily_run.report_push.push_report_sections", return_value={"mode": "split"})
    @patch("agent_reach.daily_run.intraday.record_morning_scan", return_value={"scan": {"scan_id": "S1"}})
    @patch("agent_reach.daily_run.workflows.run_morning")
    @patch("agent_reach.daily_run.symbol_runner.build_and_save")
    @patch("agent_reach.daily_run.symbol_runner.load_portfolio")
    def test_merge_mode_single_merged_narrative(
        self,
        mock_pf,
        mock_build,
        mock_run,
        mock_morning_scan,
        mock_push,
        mock_merged_narrative,
        tmp_path,
    ):
        mock_pf.return_value = PORTFOLIO
        mock_build.side_effect = [
            ({"code": "688008", "name": "澜起科技", "portfolio": {"cash_ratio": 0.5}}, tmp_path / "a.json"),
            ({"code": "002273", "name": "水晶光电"}, tmp_path / "b.json"),
        ]
        mock_run.side_effect = [
            {
                "snapshot": {"code": "688008", "portfolio": {"cash_ratio": 0.5}},
                "evaluation": {"report": {"verdict": "观察", "mss_final": 42}},
                "team_markdown": "",
                "report_markdown": "r1",
                "llm_narrative": {"skipped": True, "reason": "deferred"},
            },
            {
                "snapshot": {"code": "002273"},
                "evaluation": {"report": {"verdict": "观察", "mss_final": 40}},
                "team_markdown": "",
                "report_markdown": "r2",
                "llm_narrative": {"skipped": True, "reason": "deferred"},
            },
        ]
        mock_merged_narrative.return_value = {
            "summary": "组合早报",
            "focus_points": ["A"],
            "job": "morning",
            "planner": "llm",
        }
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "symbols_mode": "holdings",
                "symbol_push_mode": "merge_by_category",
            },
            "llm_narrative": {**(cfg.get("llm_narrative") or {}), "merge_single_call": True},
        }
        run_morning_for_symbols(settings=cfg, push=True, symbols=["688008", "002273"])
        assert mock_merged_narrative.call_count == 1
        for call in mock_run.call_args_list:
            assert call.kwargs.get("skip_narrative") is True
        pushed_sections = mock_push.call_args[0][0]
        assert any(sec.category == "ai_narrative" for sec in pushed_sections)
        assert sum(1 for sec in pushed_sections if sec.category == "ai_narrative") == 1

    @patch("agent_reach.daily_run.workflows.run_merged_close_harness_layer_b")
    @patch("agent_reach.daily_run.report_push.push_report_sections", return_value={"mode": "split"})
    @patch("agent_reach.daily_run.symbol_runner.build_and_save")
    @patch("agent_reach.daily_run.symbol_runner.load_portfolio")
    @patch("agent_reach.daily_run.workflows.run_close")
    @patch("agent_reach.daily_run.intraday.load_state")
    @patch("agent_reach.daily_run.workflows.load_morning_baseline")
    def test_merge_mode_single_merged_harness_layer_b(
        self,
        mock_baseline,
        mock_load_state,
        mock_run_close,
        mock_pf,
        mock_build,
        mock_push,
        mock_merged_harness,
        tmp_path,
    ):
        from agent_reach.daily_run.intraday import IntradayState

        mock_pf.return_value = PORTFOLIO
        mock_baseline.return_value = {"code": "688008"}
        mock_load_state.return_value = IntradayState(date="2026-08-18")
        mock_build.side_effect = [
            ({"code": "688008", "name": "澜起科技"}, tmp_path / "a.json"),
            ({"code": "002273", "name": "水晶光电"}, tmp_path / "b.json"),
        ]
        mock_run_close.side_effect = [
            {
                "snapshot": {"code": "688008", "portfolio": {"holdings": PORTFOLIO["holdings"]}},
                "verify": {"summary": "a"},
                "harness": {"layer_a": {"changes": 1}, "layer_b": {"skipped": True, "reason": "deferred"}},
            },
            {
                "snapshot": {"code": "002273"},
                "verify": {"summary": "b"},
                "harness": {"layer_a": {"changes": 1}, "layer_b": {"skipped": True, "reason": "deferred"}},
            },
        ]
        mock_merged_harness.return_value = {
            "layer_a": {"merged": True, "symbol_count": 2},
            "layer_b": {"changes": 1, "planner": "llm"},
        }
        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "symbols_mode": "holdings",
                "symbol_push_mode": "merge_by_category",
            },
            "harness": {
                **(cfg.get("harness") or {}),
                "push_summary_on_close": True,
                "llm_refine": {
                    **((cfg.get("harness") or {}).get("llm_refine") or {}),
                    "merge_single_call": True,
                },
            },
        }
        from agent_reach.daily_run.symbol_runner import run_close_for_symbols

        run_close_for_symbols(settings=cfg, push=True, symbols=["688008", "002273"])
        assert mock_merged_harness.call_count == 1
        for call in mock_run_close.call_args_list:
            assert call.kwargs.get("skip_harness_layer_b") is True


class TestIntradayParallel:
    def test_intraday_parallel_workers_caps_at_symbol_count(self):
        from agent_reach.daily_run.symbol_runner import intraday_parallel_workers

        cfg = {"schedule": {"intraday_parallel": True, "intraday_parallel_workers": 10}}
        assert intraday_parallel_workers(cfg, 4) == 4
        assert intraday_parallel_workers(cfg, 10) == 10

    def test_intraday_parallel_disabled(self):
        from agent_reach.daily_run.symbol_runner import intraday_parallel_workers

        cfg = {"schedule": {"intraday_parallel": False, "intraday_parallel_workers": 10}}
        assert intraday_parallel_workers(cfg, 10) == 1

    @patch("agent_reach.daily_run.symbol_runner.ThreadPoolExecutor")
    @patch("agent_reach.daily_run.symbol_runner.build_and_save")
    @patch("agent_reach.daily_run.symbol_runner.load_portfolio")
    @patch("agent_reach.daily_run.intraday.run_intraday")
    @patch("agent_reach.daily_run.intraday.load_state")
    @patch("agent_reach.daily_run.intraday.should_evaluate_trade")
    def test_run_intraday_for_symbols_uses_parallel_executor(
        self,
        mock_should_trade,
        mock_load_state,
        mock_run_intraday,
        mock_load_portfolio,
        mock_build,
        mock_executor,
    ):
        from agent_reach.daily_run.intraday import IntradayState
        from agent_reach.daily_run.symbol_runner import run_intraday_for_symbols

        mock_load_portfolio.return_value = PORTFOLIO
        mock_load_state.return_value = IntradayState(date="2026-08-22", scans=[], trades=[])
        mock_should_trade.return_value = False
        mock_build.return_value = ({"code": "688008", "portfolio": PORTFOLIO}, "/tmp/snap.json")
        mock_run_intraday.return_value = {
            "scan": {"scan": {"scan_id": "S2"}, "markdown": "scan md"},
            "feishu": None,
        }

        class _ImmediateExecutor:
            def __init__(self, max_workers=None):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, fn, idx, code):
                from concurrent.futures import Future

                fut = Future()
                fut.set_result(fn(idx, code))
                return fut

        mock_executor.side_effect = _ImmediateExecutor

        cfg = load_settings()
        cfg = {
            **cfg,
            "schedule": {
                **(cfg.get("schedule") or {}),
                "symbols_mode": "all",
                "intraday_parallel": True,
                "intraday_parallel_workers": 10,
                "symbol_push_mode": "merge_by_category",
            },
        }
        result = run_intraday_for_symbols(settings=cfg, push=False, symbols=["688008", "002273"])
        mock_executor.assert_called_once()
        assert mock_executor.call_args.kwargs["max_workers"] == 2
        assert result["intraday_parallel"] is True
        assert len(result["symbol_results"]) == 2
        assert mock_run_intraday.call_count == 2
