# -*- coding: utf-8
"""Tests for intraday scan/trade workflow and lookback MSS."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from agent_reach.daily_run.intraday import (
    IntradayState,
    evaluate_trade,
    load_state,
    record_scan,
    reset_state,
    run_intraday,
)
from agent_reach.daily_run.lookback import compute_lookback_mss, detect_mss_trend
from agent_reach.daily_run.settings import load_settings


@pytest.fixture
def intraday_snapshot():
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "code": "688008",
        "name": "澜起科技",
        "price": 255.87,
        "ma20": 260.0,
        "position_20d": 0.55,
        "volume_ratio": 1.2,
        "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
        "sources": {
            "quote": {"summary": "q"},
            "flow": {"summary": "f"},
            "sentiment": {"summary": "s"},
        },
        "structured_review_complete": True,
        "portfolio": {"cash_ratio": 0.61, "total": 91938},
    }


class TestLookback:
    def test_compute_lookback_mss_three_scans(self):
        settings = load_settings()
        scans = [
            {"scan_id": "S1", "mss_final": 40.0},
            {"scan_id": "S2", "mss_final": 45.0},
            {"scan_id": "S3", "mss_final": 50.0},
        ]
        mss, detail = compute_lookback_mss(scans, settings)
        assert mss == pytest.approx(46.5, abs=0.1)
        assert len(detail) == 3
        assert detail[0]["scan_id"] == "S3"

    def test_compute_lookback_single_scan(self):
        settings = load_settings()
        mss, detail = compute_lookback_mss([{"scan_id": "S1", "mss_final": 42.0}], settings)
        assert mss == 42.0
        assert len(detail) == 1

    def test_detect_trend_rising(self):
        scans = [{"mss_final": 40}, {"mss_final": 45}, {"mss_final": 52}]
        assert detect_mss_trend(scans) == "turning_up"


class TestIntradayWorkflow:
    def test_load_state_rolls_over_on_beijing_date(self, tmp_path):
        state_path = tmp_path / "intraday.json"
        state_path.write_text(
            '{"date": "1999-01-01", "scans": [{"scan_id": "S1"}], "trades": []}',
            encoding="utf-8",
        )
        with patch("agent_reach.daily_run.intraday.today_shanghai", return_value=date(2026, 7, 9)):
            state = load_state(state_path)
        assert state.date == "2026-07-09"
        assert state.scans == []

    def test_record_scan(self, intraday_snapshot, tmp_path):
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        result = record_scan(
            intraday_snapshot,
            settings=load_settings(),
            state_path=state_path,
        )
        assert result["scan"]["scan_id"] == "S1"
        assert result["lookback_mss"] == result["scan"]["mss_final"]
        state = IntradayState.from_dict(result["state"])
        assert len(state.scans) == 1

    def test_evaluate_trade_hold(self, intraday_snapshot, tmp_path):
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        settings = load_settings()
        for _ in range(3):
            record_scan(intraday_snapshot, settings=settings, state_path=state_path)
        result = evaluate_trade(
            intraday_snapshot,
            settings=settings,
            state_path=state_path,
            expected_return_pct=0.005,
        )
        assert result["decision"]["trade_id"] == "T1"
        assert result["decision"]["action"] in ("hold", "buy", "sell", "skip")
        assert "portfolio_apply" in result
        assert result["portfolio_apply"]["applied"] is False

    def test_apply_paper_trade_buy(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.intraday import TradeDecision, apply_paper_trade

        portfolio_path = tmp_path / "portfolio.json"
        portfolio_path.write_text(
            '{"total":100000,"cash":80000,"cash_ratio":0.8,'
            '"holdings":[{"code":"688008","name":"澜起科技","shares":100,"cost":255.87,"days_held":5}],'
            '"watchlist":[{"code":"000725","name":"京东方A"}]}',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_builder.default_portfolio_path",
            lambda: portfolio_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.daily_trade_state_path",
            lambda: tmp_path / "daily_trade_state.json",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.default_ledger_path",
            lambda: tmp_path / "trade_ledger.jsonl",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager._today_str",
            lambda: "2026-07-24",
        )

        snapshot = {
            "code": "688008",
            "name": "澜起科技",
            "price": 260.0,
            "change_pct": 1.5,
            "portfolio": {
                "total": 100000,
                "cash": 80000,
                "cash_ratio": 0.8,
                "holdings": [
                    {"code": "688008", "name": "澜起科技", "shares": 100, "cost": 255.87, "price": 260.0},
                ],
            },
            "watchlist": [
                {"code": "000725", "name": "京东方A", "price": 7.5, "change_pct": 2.0},
            ],
        }
        settings = load_settings()
        settings.setdefault("portfolio", {})["auto_adjust_enabled"] = True
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )

        result = apply_paper_trade(decision, snapshot, settings=settings)
        assert result.applied is True
        saved = __import__("json").loads(portfolio_path.read_text(encoding="utf-8"))
        assert any(h["code"] == "000725" for h in saved["holdings"])

    def test_apply_paper_trade_blocks_duplicate(self, tmp_path, monkeypatch):
        from agent_reach.daily_run.intraday import TradeDecision, apply_paper_trade
        from agent_reach.daily_run.portfolio_manager import ApplyResult, TradeAction

        portfolio_path = tmp_path / "portfolio.json"
        portfolio_path.write_text(
            '{"total":100000,"cash":80000,"cash_ratio":0.8,'
            '"holdings":[{"code":"688008","name":"澜起科技","shares":100,"cost":255.87,"days_held":5}],'
            '"watchlist":[{"code":"000725","name":"京东方A"}]}',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.snapshot_builder.default_portfolio_path",
            lambda: portfolio_path,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.daily_trade_state_path",
            lambda: tmp_path / "daily_trade_state.json",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager.default_ledger_path",
            lambda: tmp_path / "trade_ledger.jsonl",
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.portfolio_manager._today_str",
            lambda: "2026-07-31",
        )

        trade = TradeAction(
            side="buy",
            code="000725",
            name="京东方A",
            shares=5300,
            price=7.5,
            amount=39750.0,
            commission=59.62,
            reasoning="test",
        )
        pf = __import__("json").loads(portfolio_path.read_text(encoding="utf-8"))

        def _fake_apply(*_args, **_kwargs):
            return ApplyResult(applied=True, portfolio=pf, actions=[trade], message="ok")

        monkeypatch.setattr("agent_reach.daily_run.portfolio_manager.apply_auto_adjust", _fake_apply)

        snapshot = {"code": "688008", "portfolio": pf, "watchlist": pf["watchlist"]}
        settings = load_settings()
        settings.setdefault("portfolio", {})["auto_adjust_enabled"] = True
        decision = TradeDecision(
            action="buy",
            trade_id="T1",
            lookback_mss=55.0,
            lookback_detail=[],
            trend="rising",
            reasoning="MSS 达阈值",
        )

        first = apply_paper_trade(decision, snapshot, settings=settings)
        second = apply_paper_trade(decision, snapshot, settings=settings)
        assert first.applied is True
        assert second.applied is False
        assert "重复成交" in second.message

    def test_max_scans_limit(self, intraday_snapshot, tmp_path):
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        settings = load_settings()
        from agent_reach.daily_run.intraday import MAX_SCANS

        for _ in range(MAX_SCANS):
            record_scan(intraday_snapshot, settings=settings, state_path=state_path)
        with pytest.raises(RuntimeError, match="扫描已达上限"):
            record_scan(intraday_snapshot, settings=settings, state_path=state_path)

    @patch("agent_reach.daily_run.intraday.send_card", create=True)
    def test_run_intraday_scan_and_trade(self, mock_send, intraday_snapshot, tmp_path):
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        with patch("agent_reach.daily_run.intraday.send_card") as mock_card:
            mock_card.return_value = {"code": 0, "data": {}}
            # Need 3 scans before trade makes sense; run_intraday does 1 scan + trade
            # Pre-seed 2 scans
            settings = load_settings()
            for _ in range(2):
                record_scan(intraday_snapshot, settings=settings, state_path=state_path)
            result = run_intraday(
                intraday_snapshot,
                settings=settings,
                push=False,
                trade=True,
                state_path=state_path,
            )
        assert "scan" in result["steps"]
        assert "trade" in result["steps"]
        assert "push" not in result["steps"]

    @patch("agent_reach.integrations.feishu.send_card")
    def test_run_intraday_survives_feishu_error(self, mock_card, intraday_snapshot, tmp_path):
        from agent_reach.integrations.feishu import FeishuError

        mock_card.side_effect = FeishuError("飞书未配置")
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        result = run_intraday(
            intraday_snapshot,
            settings=load_settings(),
            push=True,
            trade=False,
            state_path=state_path,
        )
        assert result["scan_count"] == 1
        assert result.get("push_error")
        assert "push" not in result["steps"]
        state = IntradayState.from_dict(result["scan"]["state"])
        assert len(state.scans) == 1

    def test_run_intraday_pushes_separate_intraday_narrative_card(
        self, intraday_snapshot, tmp_path, monkeypatch
    ):
        state_path = tmp_path / "intraday.json"
        reset_state(state_path)
        sends: list[tuple[str, str]] = []

        def _fake_send(_cfg, title, body, template="blue"):
            sends.append((title, body))
            return {"code": 0}

        monkeypatch.setattr("agent_reach.integrations.feishu.send_card", _fake_send)
        result = run_intraday(
            intraday_snapshot,
            settings=load_settings(),
            push=True,
            trade=False,
            state_path=state_path,
        )
        assert len(sends) >= 2
        assert "S1 数据收集完成" in sends[0][1] or "数据收集完成" in sends[0][1]
        assert any("盘中 AI 解读" in t for t, _ in sends)
        assert any("盘中小结" in body for _, body in sends)
        assert not any("早盘全持仓" in body for _, body in sends)
        assert result.get("narrative_feishu") is not None
