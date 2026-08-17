# -*- coding: utf-8
"""Tests for FIFO realized P&L and overview."""

from datetime import date
from pathlib import Path

from agent_reach.daily_run.realized_pnl import (
    backfill_ledger_realized_pnl,
    build_pnl_overview,
    compute_realized_pnl,
    compute_trade_cash_flow,
    enrich_sell_actions,
    replay_realized_sells,
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
                '{"at":"2026-08-01T00:00:00+00:00","actions":[{"side":"buy","code":"688008","shares":100,"amount":25587,"commission":38.38}]}',
                '{"at":"2026-08-17T00:00:00+00:00","actions":[{"side":"sell","code":"688008","shares":100,"price":255.87,"amount":25587,"commission":38.38,"realized_pnl":-76.76}]}',
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
    md = render_pnl_overview_markdown(overview)
    assert "盈亏总览" in md
    assert "澜起" not in md or "688008" in md


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
