"""Unified entry: `agent-reach <channel> <action>`, `read <url>`, `channels`, `check`.

Everything here prints JSON to stdout (one object per invocation) so agents
never parse prose. Logs and warnings go to stderr. Exit code 0 = ok, 1 = error.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional, Sequence

from agent_reach.channels import get_all_channels
from agent_reach.channels.base import Action, Channel

from .dispatch import DEFAULT_TIMEOUT, find_action, run_action
from .result import BAD_INPUT, SCHEMA_VERSION, ReachError, envelope

_TOP_LEVEL = ("channels", "check", "read")


def unified_channels() -> List[Channel]:
    """Channels already moved to the unified entry."""
    return [ch for ch in get_all_channels() if ch.level]


def _channel(name: str) -> Optional[Channel]:
    return next((ch for ch in unified_channels() if ch.name == name), None)


def handles(argv: Sequence[str]) -> bool:
    """Whether this argv belongs to the unified entry (vs. legacy commands)."""
    if not argv:
        return False
    head = argv[0]
    return head in _TOP_LEVEL or _channel(head) is not None


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse that raises instead of printing usage and exiting."""

    def error(self, message: str):  # type: ignore[override]
        raise _ArgError(message)


def _emit(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if payload.get("ok") else 1


def _usage(channel: Channel, action: Action) -> str:
    parts = ["agent-reach", channel.name, action.name]
    for p in action.params:
        parts.append(f"<{p.name}>" if p.required else f"[--{p.name} {p.name.upper()}]")
    return " ".join(parts)


def _bad_input(channel: Optional[str], action: Optional[str], message: str) -> int:
    return _emit(envelope(channel=channel, action=action, error=ReachError(BAD_INPUT, message)))


def _parse_action_args(action: Action, args: Sequence[str]) -> Dict[str, object]:
    parser = _Parser(prog=action.name, add_help=False)
    for p in action.params:
        if p.required:
            # Join extra words so an unquoted multi-word query still works.
            parser.add_argument(p.name, nargs="+" if p.type is str else None)
        else:
            parser.add_argument(f"--{p.name}", dest=p.name, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ns = vars(parser.parse_args(list(args)))
    for p in action.params:
        if p.required and p.type is str and isinstance(ns.get(p.name), list):
            ns[p.name] = " ".join(ns[p.name])
    return ns


def _cmd_action(channel: Channel, args: Sequence[str]) -> int:
    if not args or args[0].startswith("-"):
        valid = ", ".join(a.name for a in channel.actions)
        return _bad_input(channel.name, None, f"missing action for {channel.name}; valid: {valid}")
    action = find_action(channel, args[0])
    if action is None:
        # Let run_action produce the standard unknown-action envelope.
        return _emit(run_action(channel, args[0], {}))
    try:
        ns = _parse_action_args(action, args[1:])
    except _ArgError as exc:
        return _bad_input(channel.name, action.name, f"{exc}; usage: {_usage(channel, action)}")
    timeout = ns.pop("timeout")
    return _emit(run_action(channel, action.name, ns, timeout=timeout))


def _cmd_read(args: Sequence[str]) -> int:
    parser = _Parser(prog="read", add_help=False)
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, "read", f"{exc}; usage: agent-reach read <url>")
    readers = [ch for ch in unified_channels() if find_action(ch, "read")]
    specific = [ch for ch in readers if ch.name != "web"]
    target = next((ch for ch in specific if ch.can_handle(ns.url)), None)
    target = target or next((ch for ch in readers if ch.name == "web"), None)
    if target is None:
        return _bad_input(None, "read", "no channel can read this URL")
    return _emit(run_action(target, "read", {"target": ns.url}, timeout=ns.timeout))


def _cmd_channels(_args: Sequence[str]) -> int:
    channels = []
    for ch in unified_channels():
        channels.append(
            {
                "name": ch.name,
                "description": ch.description,
                "level": ch.level,
                "actions": [
                    {
                        "name": a.name,
                        "help": a.help,
                        "usage": _usage(ch, a),
                        "params": [
                            {
                                "name": p.name,
                                "help": p.help,
                                "required": p.required,
                                "type": p.type.__name__,
                                "default": p.default,
                            }
                            for p in a.params
                        ],
                        "backends": [label for label, _ in a.backends],
                    }
                    for a in ch.actions
                ],
            }
        )
    return _emit(
        {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "commands": {
                "read": "agent-reach read <url>  (picks the channel from the URL)",
                "action": "agent-reach <channel> <action> [args] [--timeout SECONDS]",
            },
            "channels": channels,
        }
    )


def _cmd_check(args: Sequence[str]) -> int:
    parser = _Parser(prog="check", add_help=False)
    parser.add_argument("channels", nargs="*")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, "check", str(exc))
    selected = unified_channels()
    if ns.channels:
        unknown = set(ns.channels) - {ch.name for ch in selected}
        if unknown:
            return _bad_input(None, "check", f"unknown channel(s): {', '.join(sorted(unknown))}")
        selected = [ch for ch in selected if ch.name in ns.channels]

    results = []
    for ch in selected:
        for action in ch.actions:
            if action.live_test is None:
                continue
            for label, _ in action.backends:
                out = run_action(ch, action.name, dict(action.live_test), timeout=ns.timeout, only_backend=label)
                passed = bool(out["ok"] and out["items"])
                err = out["error"] or ({"code": "EMPTY", "message": "succeeded but returned no items"} if not passed else None)
                results.append(
                    {
                        "channel": ch.name,
                        "action": action.name,
                        "backend": label,
                        "passed": passed,
                        "elapsed_ms": out["meta"]["elapsed_ms"],
                        "error": err and {"code": err["code"], "message": err["message"]},
                    }
                )

    # An action passes when at least one of its backends works.
    by_action: Dict[tuple, bool] = {}
    for r in results:
        key = (r["channel"], r["action"])
        by_action[key] = by_action.get(key, False) or r["passed"]
    ok = bool(results) and all(by_action.values())

    if ns.text:
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            why = "" if r["passed"] else f"  {r['error']['code']}: {r['error']['message']}"
            sys.stdout.write(f"{mark}  {r['channel']} {r['action']} [{r['backend']}] {r['elapsed_ms']}ms{why}\n")
        sys.stdout.write(f"\n{sum(by_action.values())}/{len(by_action)} actions working\n")
        return 0 if ok else 1
    return _emit({"schema_version": SCHEMA_VERSION, "ok": ok, "results": results})


def main(argv: Sequence[str]) -> int:
    head, rest = argv[0], argv[1:]
    if head == "channels":
        return _cmd_channels(rest)
    if head == "check":
        return _cmd_check(rest)
    if head == "read":
        return _cmd_read(rest)
    channel = _channel(head)
    assert channel is not None  # guaranteed by handles()
    return _cmd_action(channel, rest)
