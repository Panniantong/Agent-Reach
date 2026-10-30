"""Run every declared channel action through the real `agent-reach` CLI and write the
release acceptance record that `check_release_acceptance.py` (and the release workflow) require.

Run on the maintainer's machine after the needed logins/keys are in place:

    python scripts/record_release_acceptance.py                 # all channels
    python scripts/record_release_acceptance.py --only reddit   # recheck some, keep the rest
    python scripts/record_release_acceptance.py --episode <xiaoyuzhou episode URL>

Only codes, counts and backends are written; no queries' results, cookies or paths.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_release_acceptance import source_digest  # noqa: E402

DEFAULT_OUT = ROOT / ".github" / "release-acceptance.json"

#: Actions without a fixed live_test take their target from an earlier result in the same run.
FROM_SEARCH = {
    ("twitter", "tweets"): ("profile", None, {"username": "OpenAI", "limit": 2}),
    ("twitter", "thread"): ("search", "target", None),
    ("youtube", "transcribe"): (None, None, {"target": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}),
    ("reddit", "read"): ("search", "target", None),
    ("xiaohongshu", "read"): ("search", "target", None),
    ("xiaohongshu", "comments"): ("search", "target", None),
    ("linkedin", "read"): ("jobs", "target", None),
    ("boss", "read"): ("search", "target", None),
}


def _argv(channel, action, params) -> list:
    args = [channel.name, action.name]
    for p in action.params:
        value = params.get(p.name)
        if value is None:
            continue
        args += [str(value)] if p.required else [f"--{p.name}", str(value)]
    return args + ["--timeout", str(max(action.timeout or 60, 60))]


def _run(args) -> dict:
    env = {**os.environ, "AGENT_REACH_NO_UPDATE_CHECK": "1", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-m", "agent_reach.cli", *args], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env=env, timeout=900, cwd=str(ROOT))
    try:
        # split("\n"), not splitlines(): post text may hold U+2028 and similar separators
        return json.loads(out.stdout.strip().split("\n")[-1])
    except (ValueError, IndexError):
        return {"ok": False, "items": [], "error": {"code": "UNREADABLE"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", default=None, help="channels to (re)check; others keep their rows")
    parser.add_argument("--episode", default="", help="a public Xiaoyuzhou episode URL for transcribe")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    ns = parser.parse_args()

    from agent_reach.runtime import manage, state
    from agent_reach.runtime.cli import unified_channels

    digest, osname = source_digest(), platform.system()
    out_path = Path(ns.out)
    try:
        old = json.loads(out_path.read_text("utf-8"))
    except (OSError, ValueError):
        old = {}
    kept = [r for r in old.get("results", []) if r.get("source_sha256") == digest]
    channels = [c for c in unified_channels() if ns.only is None or c.name in ns.only]
    names = {c.name for c in channels}
    rows = [r for r in kept if r.get("channel") not in names]
    pending = [p for p in old.get("pending", []) if p.get("channel") not in names
               and old.get("source_sha256") == digest]
    data = state.load()
    for ch in channels:
        if not manage.is_added(ch, data):
            pending += [{"channel": ch.name, "action": a.name, "reason": f"not added: run `agent-reach add {ch.name}`"}
                        for a in ch.actions]
            print(f"{ch.name}: not added, skipped")
            continue
        first_url = {}
        for action in ch.actions:
            params = dict(action.live_test or {})
            if not action.live_test:
                source, key, fixed = FROM_SEARCH.get((ch.name, action.name), (None, None, None))
                if (ch.name, action.name) == ("xiaoyuzhou", "transcribe"):
                    fixed = {"target": ns.episode} if ns.episode else None
                if fixed:
                    params = dict(fixed)
                elif source and first_url.get(source):
                    params = {key: first_url[source]}
                else:
                    reason = "needs --episode" if ch.name == "xiaoyuzhou" else f"no {source} result to read"
                    pending.append({"channel": ch.name, "action": action.name, "reason": reason})
                    print(f"{ch.name}/{action.name}: skipped ({reason})")
                    continue
            result = _run(_argv(ch, action, params))
            items = result.get("items") or []
            if items and items[0].get("url"):
                first_url[action.name] = items[0]["url"]
            passed = bool(result.get("ok") and items and result.get("backend"))
            code = None if passed else (result.get("error") or {}).get("code") or "EMPTY"
            rows.append({"channel": ch.name, "action": action.name, "method": "real-cli",
                         "backend": result.get("backend"), "item_count": len(items),
                         "at": datetime.now(timezone.utc).isoformat(), "os": osname,
                         "source_sha256": digest, "passed": passed, "error": code})
            if not passed:
                pending.append({"channel": ch.name, "action": action.name, "reason": code})
            print(f"{ch.name}/{action.name}: {'ok' if passed else code} ({len(items)} items)")
    required = {(c.name, a.name) for c in unified_channels() for a in c.actions}
    passed_keys = {(r["channel"], r["action"]) for r in rows if r.get("passed")}
    waived = old.get("waived") or []  # maintainer decisions survive re-recording
    waived_keys = {(w.get("channel"), w.get("action")) for w in waived}
    pending = [p for p in pending if (p["channel"], p["action"]) not in passed_keys | waived_keys]
    record = {"source_sha256": digest, "release_ready": not pending and required <= passed_keys | waived_keys,
              "pending": pending, "waived": waived,
              "results": sorted(rows, key=lambda r: (r["channel"], r["action"]))}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"\nrelease_ready: {record['release_ready']}  passed {len(passed_keys & required)}/{len(required)}  "
          f"pending {len(pending)}  -> {out_path}")
    return 0 if record["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
