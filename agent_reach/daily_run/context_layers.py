# -*- coding: utf-8
"""OpenViking-inspired context layers (L0/L1), overlay diff audit, and narrative traces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

L0_MAX_CHARS = 256
L1_MAX_CHARS = 4000

_OVERLAY_KEYS = (
    "threshold_overlay",
    "runtime_overlay",
    "forecast_overlay",
    "calibration_overlay",
    "lookback_overlay",
    "mss_weights_overlay",
    "position_overlay",
    "deep_loss_overlay",
    "pnl_target_overlay",
    "trend_overlay",
    "expected_return_overlay",
    "intraday_audit_overlay",
    "min_deploy_overlay",
    "friction_model_overlay",
    "defensive_trim_overlay",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def layer0(text: Any, *, max_chars: int = L0_MAX_CHARS) -> str:
    raw = str(text or "").strip().replace("\n", " ")
    if len(raw) <= max_chars:
        return raw
    return raw[: max(0, max_chars - 1)].rstrip() + "…"


def layer1(text: Any, *, max_chars: int = L1_MAX_CHARS) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max(0, max_chars - 1)].rstrip() + "……"


def agentreach_uri(*parts: str) -> str:
    cleaned = [str(p).strip("/") for p in parts if str(p).strip()]
    return "agentreach://" + "/".join(cleaned)


def _harness_root() -> Path:
    from agent_reach.daily_run.harness import harness_dir

    return harness_dir()


def _overlay_snapshot(meta: dict[str, Any]) -> dict[str, Any]:
    return {key: meta[key] for key in _OVERLAY_KEYS if key in meta}


def _last_overlay_path() -> Path:
    return _harness_root() / "last_runtime_overlay.json"


def load_last_runtime_overlay() -> dict[str, Any]:
    path = _last_overlay_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_last_runtime_overlay(meta: dict[str, Any]) -> None:
    path = _last_overlay_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_overlay_snapshot(meta), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _overlay_block_diff(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    adds: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    deletes: list[dict[str, Any]] = []

    all_keys = set(before.keys()) | set(after.keys())
    for block_key in sorted(all_keys):
        old_block = before.get(block_key) if isinstance(before.get(block_key), dict) else {}
        new_block = after.get(block_key) if isinstance(after.get(block_key), dict) else {}
        if not old_block and new_block:
            adds.append({"overlay": block_key, "after": new_block})
            continue
        if old_block and not new_block:
            deletes.append({"overlay": block_key, "before": old_block})
            continue
        item_keys = set(old_block.keys()) | set(new_block.keys())
        for item_key in sorted(item_keys):
            old_item = old_block.get(item_key)
            new_item = new_block.get(item_key)
            if old_item == new_item:
                continue
            uri = agentreach_uri("daily_run", "harness", "runtime", block_key, item_key)
            if old_item is None and new_item is not None:
                adds.append({"uri": uri, "overlay": block_key, "key": item_key, "after": new_item})
            elif old_item is not None and new_item is None:
                deletes.append({"uri": uri, "overlay": block_key, "key": item_key, "before": old_item})
            else:
                updates.append(
                    {
                        "uri": uri,
                        "overlay": block_key,
                        "key": item_key,
                        "before": old_item,
                        "after": new_item,
                    }
                )
    return {"adds": adds, "updates": updates, "deletes": deletes}


def build_memory_diff(
    operations: dict[str, list[dict[str, Any]]],
    *,
    job: str = "",
    trigger: str = "",
    refinement_id: str = "",
) -> dict[str, Any]:
    adds = list(operations.get("adds") or [])
    updates = list(operations.get("updates") or [])
    deletes = list(operations.get("deletes") or [])
    return {
        "at": _now_iso(),
        "job": job,
        "trigger": trigger,
        "refinement_id": refinement_id or None,
        "operations": {
            "adds": adds,
            "updates": updates,
            "deletes": deletes,
        },
        "summary": {
            "total_adds": len(adds),
            "total_updates": len(updates),
            "total_deletes": len(deletes),
        },
    }


def record_runtime_overlay_diff(
    before_meta: dict[str, Any],
    after_meta: dict[str, Any],
    *,
    job: str = "runtime",
    trigger: str = "apply_overlay",
) -> Optional[dict[str, Any]]:
    ops = _overlay_block_diff(_overlay_snapshot(before_meta), _overlay_snapshot(after_meta))
    if not any(ops[k] for k in ("adds", "updates", "deletes")):
        return None
    diff = build_memory_diff(ops, job=job, trigger=trigger)
    path = _harness_root() / "overlay_diff.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(diff, ensure_ascii=False) + "\n")
    return diff


def record_harness_entry_diff(
    job: str,
    edits: list[Any],
    *,
    refinement_id: str = "",
    trigger: str = "",
) -> Optional[dict[str, Any]]:
    adds: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    deletes: list[dict[str, Any]] = []
    for raw in edits or []:
        edit = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw or {})
        action = str(edit.get("action") or "")
        kind = str(edit.get("kind") or "")
        entry_id = str(edit.get("entry_id") or "")
        uri = agentreach_uri("daily_run", "harness", kind, entry_id)
        before = edit.get("before")
        after = edit.get("after")
        if action == "create":
            adds.append({"uri": uri, "kind": kind, "entry_id": entry_id, "after": after})
        elif action == "update":
            updates.append({"uri": uri, "kind": kind, "entry_id": entry_id, "before": before, "after": after})
        elif action == "delete":
            deletes.append({"uri": uri, "kind": kind, "entry_id": entry_id, "before": before})
    if not adds and not updates and not deletes:
        return None
    diff = build_memory_diff(
        {"adds": adds, "updates": updates, "deletes": deletes},
        job=job,
        trigger=trigger or f"job:{job}",
        refinement_id=refinement_id,
    )
    path = _harness_root() / "memory_diff.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(diff, ensure_ascii=False) + "\n")
    return diff


def load_recent_overlay_diff(*, limit: int = 1) -> list[dict[str, Any]]:
    path = _harness_root() / "overlay_diff.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def write_text_sidecars(target: Path, content: str) -> dict[str, str]:
    """Write L0/L1 sidecars next to a markdown fragment (OpenViking-style)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    abstract_path = target.with_name(f"{target.stem}.abstract.md")
    overview_path = target.with_name(f"{target.stem}.overview.md")
    abstract_path.write_text(layer0(content) + "\n", encoding="utf-8")
    overview_path.write_text(layer1(content) + "\n", encoding="utf-8")
    return {
        "abstract": str(abstract_path),
        "overview": str(overview_path),
        "uri": agentreach_uri("daily_run", "skill", target.name),
    }


def _format_overlay_item(key: str, change: dict[str, Any]) -> str:
    base = change.get("base")
    eff = change.get("effective")
    if base is None or eff is None:
        return f"{key}={eff}"
    if isinstance(base, (int, float)) and isinstance(eff, (int, float)):
        if abs(float(eff) - float(base)) < 0.0001:
            return ""
        if 0 <= float(base) <= 1 and 0 <= float(eff) <= 1:
            return f"{key} {float(base):.0%}→{float(eff):.0%}"
        return f"{key} {base}→{eff}"
    return f"{key} {base}→{eff}"


def build_context_trace(
    settings: dict[str, Any],
    *,
    job: str = "",
    ctx: Optional[dict[str, Any]] = None,
    max_items: int = 5,
) -> list[str]:
    """L0 retrieval trace lines for 规则解读 cards."""
    lines: list[str] = []
    runtime = dict(settings.get("harness_runtime") or {})

    threshold = runtime.get("threshold_overlay") or {}
    for key, change in threshold.items():
        if not isinstance(change, dict):
            continue
        bit = _format_overlay_item(str(key), change)
        if bit:
            lines.append(layer0(f"阈值 {bit}"))
        if len(lines) >= max_items:
            return lines[:max_items]

    position = runtime.get("position_overlay") or {}
    for key, change in position.items():
        if not isinstance(change, dict):
            continue
        bit = _format_overlay_item(str(key), change)
        if bit:
            lines.append(layer0(f"仓位 {bit}"))
        if len(lines) >= max_items:
            return lines[:max_items]

    injection = runtime.get("injection_gate") or {}
    for text in injection.get("adopted_preview") or []:
        lines.append(layer0(f"采纳 {text}"))
        if len(lines) >= max_items:
            return lines[:max_items]

    ctx = ctx or {}
    if ctx.get("cash_limit_bypass"):
        streak = ctx.get("consecutive_buy_streak")
        suffix = f"（连续 {streak} 次买入）" if streak else ""
        lines.append(layer0(f"临时突破现金/deploy 限制{suffix}"))
    msg = str(ctx.get("portfolio_message") or ctx.get("trade_reasoning") or "").strip()
    if msg and ctx.get("trade_action") in ("buy", "sell"):
        applied = ctx.get("portfolio_applied")
        status = "已落账" if applied else "未落账"
        lines.append(layer0(f"调仓{status}：{msg}"))

    recent = load_recent_overlay_diff(limit=1)
    if recent and len(lines) < max_items:
        summary = recent[0].get("summary") or {}
        total = int(summary.get("total_updates") or 0)
        if total:
            lines.append(layer0(f"近期 harness overlay 更新 {total} 项"))

    return lines[:max_items]
