# -*- coding: utf-8
"""Deep-loss cover exemptions for defensive trim / plan trim."""

from agent_reach.daily_run.deep_loss_cover_policy import cover_exempt_for_sell
from agent_reach.daily_run.portfolio_manager import deep_loss_sell_analysis


def test_cover_exempt_defensive_trim():
    assert cover_exempt_for_sell(
        "002583",
        settings={"pnl_overview": {"defensive_trim_exempt_cover": True}},
        sell_kind="defensive_trim",
    )


def test_deep_loss_analysis_allows_trim_without_cover(monkeypatch):
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.is_deep_loss_holding",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager._holding_unrealized_pnl",
        lambda *a, **k: (-10000.0, -34.0),
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.portfolio_coverable_gains",
        lambda *a, **k: 0.0,
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.holding_sellable_shares",
        lambda h: int(h.get("shares") or 0),
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.resolve_deep_loss_sell_shares",
        lambda total, code, settings, **kw: max(100, int(total * 0.25)),
    )
    monkeypatch.setattr(
        "agent_reach.daily_run.portfolio_manager.deep_loss_policy",
        lambda settings: {
            "cover_ratio": 1.0,
            "sell_ratio": 0.35,
            "non_deep_loss_sell_ratio": 0.5,
        },
    )

    pf = {"holdings": [{"code": "002583", "name": "海能达", "shares": 2500}]}
    holding = pf["holdings"][0]
    enriched = {"002583": {"price": 8.5}}
    analysis = deep_loss_sell_analysis(
        pf,
        holding,
        enriched,
        {"pnl_overview": {"defensive_trim_exempt_cover": True}},
        sell_kind="defensive_trim",
    )
    assert analysis["allowed"] is True
    assert analysis["required_cover"] == 0.0
