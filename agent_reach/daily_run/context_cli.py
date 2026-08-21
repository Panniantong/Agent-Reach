# -*- coding: utf-8
"""CLI handlers for agent-reach context ls/read/find."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_reach.daily_run.context_store import find_context, list_context, read_layer


def add_context_subparser(sub: argparse._SubParsersAction) -> None:
    p_ctx = sub.add_parser("context", help="Browse agentreach:// context (cases, harness, skill)")
    p_ctx_sub = p_ctx.add_subparsers(dest="context_action", required=True)

    p_ls = p_ctx_sub.add_parser("ls", help="List entries under a URI")
    p_ls.add_argument(
        "uri",
        nargs="?",
        default="agentreach://daily_run/memory/cases",
        help="agentreach:// URI (default: daily_run/memory/cases)",
    )

    p_read = p_ctx_sub.add_parser("read", help="Read one context layer")
    p_read.add_argument("uri", help="agentreach:// URI or path")
    p_read.add_argument(
        "--layer",
        default="abstract",
        choices=["abstract", "overview", "detail", "l0", "l1", "l2"],
        help="Layer to read (default: abstract / L0)",
    )
    p_read.add_argument("--json", action="store_true", help="Wrap output as JSON")

    p_find = p_ctx_sub.add_parser("find", help="Search cases/harness/skill by keyword")
    p_find.add_argument("query", nargs="?", default="", help="Search text")
    p_find.add_argument("--kind", default="", help="cases | harness | skill")
    p_find.add_argument("--code", default="", help="Filter cases by stock code")
    p_find.add_argument("--limit", type=int, default=8)
    p_find.add_argument("--json", action="store_true", help="JSON output")


def cmd_context(args: argparse.Namespace) -> None:
    action = args.context_action
    if action == "ls":
        rows = list_context(args.uri)
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        if not rows:
            print(f"(empty) {args.uri}")
            return
        for row in rows:
            abstract = row.get("abstract") or ""
            print(f"{row.get('uri')}\t{abstract}")
        return

    if action == "read":
        text = read_layer(args.uri, layer=args.layer)
        if args.json:
            print(json.dumps({"uri": args.uri, "layer": args.layer, "text": text}, ensure_ascii=False))
        else:
            print(text.rstrip())
        return

    if action == "find":
        rows = find_context(
            args.query,
            kind=args.kind,
            code=args.code,
            limit=max(1, int(args.limit)),
        )
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        if not rows:
            print("(no matches)")
            return
        for row in rows:
            print(f"{row.get('uri')}\t[{row.get('kind')}] {row.get('abstract')}")
        return

    print(f"Unknown context action: {action}", file=sys.stderr)
    sys.exit(1)
