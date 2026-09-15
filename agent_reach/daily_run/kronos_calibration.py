# -*- coding: utf-8
"""Kronos close-review error ledger (Layer A) for weekly inference calibration."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.context_store import daily_run_root
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.week_forecast_tracker import ForecastDayReview


def kronos_data_dir() -> Path:
    return daily_run_root() / "kronos"


def error_ledger_path() -> Path:
    return kronos_data_dir() / "error_ledger.jsonl"


def _direction_from_change(chg: float) -> str:
    if chg > 0.3:
        return "up"
    if chg < -0.3:
        return "down"
    return "flat"


def build_kronos_ledger_entries(
    review: ForecastDayReview,
    forecast: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build per-symbol ledger rows from a close-day forecast review."""
    ds = review.date
    paths = forecast.get("kronos_paths") or {}
    rows: list[dict[str, Any]] = []

    for ev in review.symbol_evals:
        block = paths.get(ev.code) or {}
        if not block.get("available"):
            continue
        k_day = (block.get("days") or {}).get(ds)
        if not k_day or ev.actual_change_pct is None:
            continue
        k_chg = float(k_day.get("change_pct") or 0)
        actual = float(ev.actual_change_pct)
        k_dir = str(k_day.get("direction") or _direction_from_change(k_chg))
        act_dir = _actual_direction(actual)
        rows.append(
            {
                "date": ds,
                "code": _normalize_code(ev.code),
                "name": ev.name,
                "role": ev.role,
                "actual_change_pct": round(actual, 2),
                "kronos_change_pct": round(k_chg, 2),
                "error_pct": round(actual - k_chg, 2),
                "direction_hit": k_dir == act_dir,
                "mc_direction": ev.predicted_direction,
                "kronos_direction": k_dir,
                "actual_direction": act_dir,
                "mc_hit": ev.hit,
            }
        )
    return rows


def _actual_direction(chg: float) -> str:
    if chg > 0.3:
        return "up"
    if chg < -0.3:
        return "down"
    return "flat"


def append_kronos_error_ledger(
    review: ForecastDayReview,
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Append close-day Kronos errors to ~/.agent-reach/daily_run/kronos/error_ledger.jsonl."""
    from agent_reach.daily_run.kronos_predictor import is_kronos_enabled

    if not is_kronos_enabled(settings):
        return {"skipped": True, "reason": "kronos disabled"}

    rows = build_kronos_ledger_entries(review, forecast)
    if not rows:
        return {"skipped": True, "reason": "no kronos rows for review day"}

    path = error_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    errors = [float(r["error_pct"]) for r in rows]
    divergences = sum(1 for r in rows if not r["direction_hit"])
    return {
        "skipped": False,
        "path": str(path),
        "rows": len(rows),
        "mean_error_pct": round(sum(errors) / len(errors), 2) if errors else None,
        "divergence_count": divergences,
        "date": review.date,
    }


def load_kronos_error_ledger(
    *,
    since: Optional[date] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    path = error_ledger_path()
    if not path.exists():
        return []
    since_s = since.isoformat() if since else None
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_s and str(row.get("date") or "") < since_s:
            continue
        rows.append(row)
    return rows[-limit:]


def summarize_kronos_ledger(
    rows: list[dict[str, Any]],
    *,
    lookback_days: int = 14,
) -> dict[str, Any]:
    if not rows:
        return {"rows": 0}

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    recent = [r for r in rows if str(r.get("date") or "") >= cutoff]
    if not recent:
        recent = rows

    errors = [abs(float(r.get("error_pct") or 0)) for r in recent]
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in recent:
        code = _normalize_code(str(row.get("code") or ""))
        if code:
            by_code.setdefault(code, []).append(row)

    symbol_stats: dict[str, dict[str, Any]] = {}
    for code, items in by_code.items():
        dir_hits = sum(1 for r in items if r.get("direction_hit"))
        mean_err = sum(abs(float(r.get("error_pct") or 0)) for r in items) / len(items)
        symbol_stats[code] = {
            "name": items[-1].get("name") or code,
            "rows": len(items),
            "direction_hit_rate": round(dir_hits / len(items), 3) if items else None,
            "mean_abs_error_pct": round(mean_err, 2),
        }

    divergence_codes = [
        code
        for code, stat in symbol_stats.items()
        if stat.get("rows", 0) >= 2
        and float(stat.get("direction_hit_rate") if stat.get("direction_hit_rate") is not None else 1)
        < 0.5
        and float(stat.get("mean_abs_error_pct") or 0) >= 1.0
    ]

    return {
        "rows": len(recent),
        "mean_abs_error_pct": round(sum(errors) / len(errors), 2) if errors else None,
        "direction_miss_rate": round(
            sum(1 for r in recent if not r.get("direction_hit")) / len(recent),
            3,
        )
        if recent
        else None,
        "symbol_stats": symbol_stats,
        "divergence_heavy_codes": divergence_codes,
    }


def kronos_ledger_to_harness_evidence(summary: dict[str, Any]) -> dict[str, Any]:
    memory: list[str] = []
    playbook: list[str] = []
    if summary.get("rows", 0) <= 0:
        return {"memory": memory, "policy": [], "playbook": playbook, "plan": [], "summary": "kronos_ledger empty"}

    rows = int(summary["rows"])
    mae = summary.get("mean_abs_error_pct")
    miss = summary.get("direction_miss_rate")
    memory.append(
        f"Kronos 台账 {rows} 条 · MAE {float(mae):.2f}%" if mae is not None else f"Kronos 台账 {rows} 条"
    )
    if miss is not None and float(miss) >= 0.4:
        memory.append(f"Kronos 方向失准 {float(miss):.0%} → 周六 hold-out 调 inference_T / blend")
        playbook.append("Kronos 收盘偏差偏高 → 运行 kronos_calibrate hold-out grid")

    heavy = summary.get("divergence_heavy_codes") or []
    if heavy:
        codes = ", ".join(str(c) for c in heavy[:5])
        memory.append(f"Kronos 分歧重标 {codes}")
        playbook.append(f"分歧重标 {codes} → 可下调 symbol_blend")

    return {
        "memory": memory,
        "policy": [],
        "playbook": playbook,
        "plan": [],
        "summary": f"kronos_ledger rows={rows} mae={mae}",
    }
