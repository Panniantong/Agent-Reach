#!/usr/bin/env python3
# -*- coding: utf-8
"""Run pnl_overview harness refinement from current portfolio + ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description="PnL overview harness skill runner")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--portfolio", "-p", default="",
        help="Portfolio JSON (default ~/.agent-reach/daily_run/portfolio.json)",
    )
    args = parser.parse_args()

    from agent_reach.daily_run.pnl_overview_harness import (
        apply_pnl_overview_harness_refinement,
        build_close_pnl_overview,
        pnl_overview_to_harness_evidence,
    )
    from agent_reach.daily_run.realized_pnl import render_pnl_overview_markdown
    from agent_reach.daily_run.settings import effective_settings, load_settings
    from agent_reach.daily_run.snapshot_builder import load_portfolio

    cfg = effective_settings(load_settings())
    pf_path = Path(args.portfolio).expanduser() if args.portfolio else None
    portfolio = load_portfolio(pf_path)

    from agent_reach.daily_run.close_portfolio_summary import build_close_portfolio_summary
    from pathlib import Path as _Path

    baseline = {}
    mb = _Path.home() / ".agent-reach" / "daily_run" / "last_morning.json"
    if mb.is_file():
        baseline = json.loads(mb.read_text(encoding="utf-8"))

    snap = {"portfolio": portfolio, "code": portfolio.get("code"), "watchlist": portfolio.get("watchlist") or []}
    summary = build_close_portfolio_summary(snap, baseline, settings=cfg)
    pf_summary = summary.to_dict()
    overview = build_close_pnl_overview(pf_summary, settings=cfg)

    result = apply_pnl_overview_harness_refinement(pf_summary, overview=overview, settings=cfg)
    payload = {
        "harness": result,
        "evidence_preview": pnl_overview_to_harness_evidence(
            overview, portfolio_summary=pf_summary, settings=cfg
        ),
        "overview": overview.to_dict(),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_pnl_overview_markdown(overview))
        print("\n--- harness ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
