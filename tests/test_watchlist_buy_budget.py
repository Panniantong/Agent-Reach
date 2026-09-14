# -*- coding: utf-8
"""Watchlist vs holding buy budget precheck labeling."""

from agent_reach.daily_run.portfolio_manager import (
    ApplyResult,
    buy_budget_precheck_reason,
    render_apply_markdown,
)


def test_watchlist_budget_reason_tagged(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.simulate_buy_analysis",
        lambda *a, **k: {
            "allowed": False,
            "block_reason": "688981 可部署买入预算 ¥11,753 不足一手",
        },
    )
    pf = {"holdings": [{"code": "688008", "shares": 100}]}
    reason = buy_budget_precheck_reason(
        pf,
        {},
        {"deploy_signal": {"watchlist_buy_precheck_only": True}},
        prefer_code="688981",
    )
    assert "观察池买入预算不足" in reason


def test_render_apply_markdown_watchlist_label():
    md = render_apply_markdown(
        ApplyResult(applied=False, portfolio={}, message="x"),
        decision={"block_kind": "buy_budget", "reasoning": "【观察池买入预算不足】688981"},
    )
    assert "观察池" in md
    assert "非现金不足" in md
