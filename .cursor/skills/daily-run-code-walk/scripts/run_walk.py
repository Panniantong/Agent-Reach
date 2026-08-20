#!/usr/bin/env python3
# -*- coding: utf-8
"""Daily-run code walk + harness self-evolution (skill entrypoint)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily-run code walk with harness self-evolution")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--no-source-walk", action="store_true", help="Skip AST module walk")
    parser.add_argument("--no-evolve", action="store_true", help="Skip harness refine")
    parser.add_argument(
        "--review-diff",
        action="store_true",
        help="Run Phase R deterministic git-diff checks on agent_reach/daily_run/",
    )
    parser.add_argument("--diff-base", default="main", help="Base branch for --review-diff (default: main)")
    parser.add_argument(
        "--diff-scope",
        choices=["branch", "uncommitted"],
        default="branch",
        help="Diff scope for --review-diff (default: branch)",
    )
    args = parser.parse_args()

    from agent_reach.daily_run.code_walk_harness import render_code_walk_markdown, run_agent_code_walk

    report = run_agent_code_walk(
        walk_source=not args.no_source_walk,
        evolve_harness=not args.no_evolve,
        review_diff=args.review_diff,
        diff_base=args.diff_base,
        diff_scope=args.diff_scope,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_code_walk_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
