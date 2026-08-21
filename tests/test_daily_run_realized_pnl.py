# -*- coding: utf-8
"""Tests for FIFO realized P&L and overview."""

from datetime import date
from pathlib import Path

from agent_reach.daily_run.realized_pnl import (
    backfill_ledger_realized_pnl,
    build_pnl_overview,
    compute_day_realized_pnl,
    compute_realized_pnl,
    compute_trade_cash_flow,
    enrich_sell_actions,
    format_buy_trade_line,
    format_sell_trade_line,
    replay_realized_sells,
    sum_stored_realized_pnl,
    render_pnl_overview_markdown,
)


def test_compute_trade_cash_flow():
    trades = [
        {
            "actions": [
                {"side": "buy", "amount": 10000, "commission": 15},
                {"side": "sell", "amount": 10500, "commission": 16},
            ]
        }
    ]
    assert compute_trade_cash_flow(trades) == 469.0


def test_orphan_sell_uses_holding_cost():
    trades = [
        {
            "at": "2026-08-21T01:01:41+00:00",
            "actions": [
                {
                    "side": "sell",
                    "code": "002273",
                    "name": "水晶光电",
                    "shares": 100,
                    "price": 27.13,
                    "amount": 2713.0,
                    "commission": 4.07,
                    "holding_cost": 33.81,
                }
            ],
        }
    ]
    rows = replay_realized_sells(trades)
    assert len(rows) == 1
    assert rows[0].cost_basis == 3381.0
    assert rows[0].realized_pnl == -672.07
    assert rows[0].avg_buy_price == 33.81


def test_orphan_sell_uses_portfolio_opening_costs():
    trades = [
        {
            "at": "2026-08-21T01:01:41+00:00",
            "actions": [
                {
                    "side": "sell",
                    "code": "002273",
                    "name": "水晶光电",
                    "shares": 100,
                    "price": 27.13,
                    "amount": 2713.0,
                    "commission": 4.07,
                }
            ],
        }
    ]
    rows = replay_realized_sells(trades, opening_costs={"002273": 33.81})
    assert rows[0].realized_pnl == -672.07


def test_compute_realized_pnl_fifo():
    trades = [
        {
            "at": "2026-08-01T00:00:00+00:00",
            "actions": [
                {
                    "side": "buy",
                    "code": "688008",
                    "shares": 100,
                    "amount": 25587.0,
                    "commission": 38.38,
                }
            ],
        },
        {
            "at": "2026-08-17T00:00:00+00:00",
            "actions": [
                {
                    "side": "sell",
                    "code": "688008",
                    "shares": 100,
                    "price": 255.87,
                    "amount": 25587.0,
                    "commission": 38.38,
                }
            ],
        },
    ]
    rows = replay_realized_sells(trades)
    assert len(rows) == 1
    assert rows[0].realized_pnl == -76.76
    assert rows[0].at == "2026-08-17T00:00:00+00:00"
    assert rows[0].avg_buy_price == 256.2538
    assert compute_realized_pnl(trades) == -76.76


def test_enrich_sell_actions(tmp_path: Path):
    ledger = tmp_path / "trade_ledger.jsonl"
    prior = [
        {
            "at": "2026-08-01T00:00:00+00:00",
            "actions": [
                {
                    "side": "buy",
                    "code": "688008",
                    "shares": 100,
                    "amount": 25587.0,
                    "commission": 38.38,
                }
            ],
        }
    ]
    new_actions = [
        {
            "side": "sell",
            "code": "688008",
            "name": "澜起科技",
            "shares": 100,
            "price": 255.87,
            "amount": 25587.0,
            "commission": 38.38,
        }
    ]
    enriched = enrich_sell_actions(
        prior,
        new_actions,
        entry_at="2026-08-17T12:00:00+00:00",
    )
    assert enriched[0]["realized_pnl"] == -76.76
    assert enriched[0]["cost_basis"] == 25625.38


def test_build_pnl_overview(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            [
                '{"at":"2026-08-01T09:30:00+08:00","actions":[{"side":"buy","code":"688008","name":"澜起科技","shares":100,"price":255.87,"amount":25587,"commission":38.38}]}',
                '{"at":"2026-08-17T14:00:00+08:00","actions":[{"side":"sell","code":"688008","name":"澜起科技","shares":100,"price":255.87,"amount":25587,"commission":38.38,"realized_pnl":-76.76}]}',
                '{"at":"2026-08-17T09:54:00+08:00","actions":[{"side":"buy","code":"600584","name":"长电","shares":800,"price":80.8,"amount":64640,"commission":9.69}]}',
            ]
        ),
        encoding="utf-8",
    )
    portfolio = {
        "holdings": [
            {"code": "600584", "name": "长电", "shares": 800, "cost": 80.8, "price": 81.0},
        ]
    }
    overview = build_pnl_overview(
        portfolio,
        start=date(1970, 1, 1),
        end=date(2026, 8, 17),
        ledger_path=ledger,
    )
    assert overview.realized_pnl == -76.76
    assert overview.unrealized_pnl == 160.0
    assert overview.total_pnl == 83.24
    assert len(overview.buys) == 2
    assert overview.holdings[0]["buy_at"] == "2026-08-17T09:54:00+08:00"
    assert overview.holdings[0]["buy_price"] == 80.8
    assert overview.holdings[0]["buy_shares"] == 800
    md = render_pnl_overview_markdown(overview)
    assert "盈亏总览" in md
    assert "总收益" in md
    assert "历史已实现" in md
    assert "当前持股" in md
    assert "买入记录" in md
    assert "800股" in md
    assert "80.80" in md
    assert format_buy_trade_line(overview.buys[-1]).startswith("买入")
    assert "688008" in format_sell_trade_line(overview.realized_sells[0])


def test_backfill_ledger(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        '{"at":"2026-08-01T00:00:00+00:00","actions":[{"side":"buy","code":"688008","shares":100,"amount":25587,"commission":38.38}]}\n'
        '{"at":"2026-08-17T00:00:00+00:00","actions":[{"side":"sell","code":"688008","shares":100,"price":255.87,"amount":25587,"commission":38.38}]}\n',
        encoding="utf-8",
    )
    result = backfill_ledger_realized_pnl(path=ledger)
    assert result["updated"] == 1
    import json

    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    sell = rows[1]["actions"][0]
    assert sell["realized_pnl"] == -76.76


def test_compute_day_realized_pnl_prefers_stored_sell_fields():
    prior = [
        {
            "at": "2026-08-17T01:54:08+00:00",
            "actions": [
                {
                    "side": "buy",
                    "code": "600584",
                    "shares": 800,
                    "amount": 64640.0,
                    "commission": 96.96,
                }
            ],
        }
    ]
    day_trades = [
        {
            "at": "2026-08-19T01:02:56+00:00",
            "actions": [
                {
                    "side": "sell",
                    "code": "600584",
                    "shares": 800,
                    "price": 85.42,
                    "amount": 68336.0,
                    "commission": 102.5,
                    "cost_basis": 64736.96,
                    "realized_pnl": 3496.54,
                },
                {
                    "side": "sell",
                    "code": "000725",
                    "shares": 1400,
                    "price": 6.47,
                    "amount": 9058.0,
                    "commission": 13.59,
                    "cost_basis": 10515.75,
                    "realized_pnl": -1471.34,
                },
            ],
        }
    ]
    assert sum_stored_realized_pnl(day_trades) == 2025.2
    assert compute_day_realized_pnl(day_trades, prior_trades=prior) == 2025.2
    # Day-only FIFO replay without stored fields would miss buy history.
    assert compute_realized_pnl(day_trades) != 2025.2
