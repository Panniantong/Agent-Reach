# -*- coding: utf-8
"""Next-day total P&L targets with harness reward/penalty cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.harness_policy import pnl_target_policy_default
from agent_reach.daily_run.trade_calendar import next_trading_day, today_shanghai


@dataclass
class PnlTarget:
    target_date: str
    set_on: str
    baseline_nav: float
    target_pnl_cny: float
    target_pnl_pct: Optional[float] = None
    status: str = "pending"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date,
            "set_on": self.set_on,
            "baseline_nav": round(float(self.baseline_nav), 2),
            "target_pnl_cny": round(float(self.target_pnl_cny), 2),
            "target_pnl_pct": self.target_pnl_pct,
            "status": self.status,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> PnlTarget:
        return cls(
            target_date=str(row.get("target_date") or ""),
            set_on=str(row.get("set_on") or ""),
            baseline_nav=float(row.get("baseline_nav") or 0),
            target_pnl_cny=float(row.get("target_pnl_cny") or 0),
            target_pnl_pct=(
                float(row["target_pnl_pct"]) if row.get("target_pnl_pct") is not None else None
            ),
            status=str(row.get("status") or "pending"),
            note=str(row.get("note") or ""),
        )


@dataclass
class PnlTargetResult:
    target_date: str
    evaluated_on: str
    target_pnl_cny: float
    actual_pnl_cny: float
    actual_pnl_pct: Optional[float] = None
    hit: bool = False
    delta_cny: float = 0.0
    reward: bool = False
    penalty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_date": self.target_date,
            "evaluated_on": self.evaluated_on,
            "target_pnl_cny": round(float(self.target_pnl_cny), 2),
            "actual_pnl_cny": round(float(self.actual_pnl_cny), 2),
            "actual_pnl_pct": self.actual_pnl_pct,
            "hit": self.hit,
            "delta_cny": round(float(self.delta_cny), 2),
            "reward": self.reward,
            "penalty": self.penalty,
        }


def default_pnl_target_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "pnl_target.json"


def _pnl_target_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("pnl_target") or {})


def load_pnl_target_state(*, path: Optional[Path] = None) -> dict[str, Any]:
    p = path or default_pnl_target_path()
    if not p.is_file():
        return {"pending": None, "last_result": None, "history": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"pending": None, "last_result": None, "history": []}
    if not isinstance(data, dict):
        return {"pending": None, "last_result": None, "history": []}
    return data


def save_pnl_target_state(state: dict[str, Any], *, path: Optional[Path] = None) -> Path:
    p = path or default_pnl_target_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def load_pending_target(*, path: Optional[Path] = None) -> Optional[PnlTarget]:
    raw = load_pnl_target_state(path=path).get("pending")
    if not isinstance(raw, dict) or not raw.get("target_date"):
        return None
    return PnlTarget.from_dict(raw)


def compute_next_day_target(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    prev_result: Optional[PnlTargetResult | dict[str, Any]] = None,
) -> PnlTarget:
    cfg = _pnl_target_cfg(settings)
    policy = {key: pnl_target_policy_default(settings or {}, key) for key in (
        "base_target_pct",
        "base_target_cny",
        "min_target_cny",
        "streak_bonus_pct",
        "miss_recovery_factor",
    )}
    as_of = str(portfolio_summary.get("as_of") or today_shanghai().isoformat())[:10]
    day = date.fromisoformat(as_of)
    next_day = next_trading_day(day, settings=settings or {})

    end_total = portfolio_summary.get("end_total")
    if end_total is None:
        end_total = portfolio_summary.get("start_total")
    baseline = float(end_total or 0)

    base_pct = float(policy["base_target_pct"])
    base_cny = float(policy["base_target_cny"])
    min_cny = float(policy["min_target_cny"])

    if base_cny > 0:
        target_cny = base_cny
    else:
        target_cny = round(baseline * base_pct / 100, 2) if baseline > 0 else 0.0

    if min_cny > 0:
        target_cny = max(target_cny, min_cny)

    prev_hit = False
    prev_miss = False
    if prev_result is not None:
        data = prev_result.to_dict() if isinstance(prev_result, PnlTargetResult) else prev_result
        prev_hit = bool(data.get("hit"))
        prev_miss = not prev_hit

    if prev_hit and policy["streak_bonus_pct"] > 0:
        target_cny = round(target_cny * (1 + float(policy["streak_bonus_pct"]) / 100), 2)

    if prev_miss and policy["miss_recovery_factor"] > 0:
        target_cny = round(target_cny * float(policy["miss_recovery_factor"]), 2)

    target_pct = round(target_cny / baseline * 100, 2) if baseline > 0 else None
    return PnlTarget(
        target_date=next_day.isoformat(),
        set_on=as_of,
        baseline_nav=baseline,
        target_pnl_cny=target_cny,
        target_pnl_pct=target_pct,
        status="pending",
    )


def evaluate_pending_target(
    portfolio_summary: dict[str, Any],
    pending: PnlTarget,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> PnlTargetResult:
    cfg = _pnl_target_cfg(settings)
    as_of = str(portfolio_summary.get("as_of") or "")[:10]
    actual = portfolio_summary.get("daily_pnl")
    actual_cny = float(actual if actual is not None else 0.0)
    actual_pct = portfolio_summary.get("daily_pnl_pct")
    actual_pct_f = float(actual_pct) if actual_pct is not None else None

    use_pct = bool(cfg.get("evaluate_by_pct"))
    if use_pct and pending.target_pnl_pct is not None and actual_pct_f is not None:
        hit = actual_pct_f >= float(pending.target_pnl_pct)
    else:
        hit = actual_cny >= float(pending.target_pnl_cny)

    delta = round(actual_cny - float(pending.target_pnl_cny), 2)
    return PnlTargetResult(
        target_date=pending.target_date,
        evaluated_on=as_of,
        target_pnl_cny=float(pending.target_pnl_cny),
        actual_pnl_cny=actual_cny,
        actual_pnl_pct=actual_pct_f,
        hit=hit,
        delta_cny=delta,
        reward=hit,
        penalty=not hit,
    )


def run_pnl_target_close_cycle(
    portfolio_summary: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> dict[str, Any]:
    """Evaluate today's target (if any), then set next trading day's target."""
    cfg = _pnl_target_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "pnl_target disabled"}

    as_of = str(portfolio_summary.get("as_of") or "")[:10]
    state = load_pnl_target_state(path=path)
    evaluation: Optional[PnlTargetResult] = None

    pending = load_pending_target(path=path)
    if pending and pending.target_date == as_of and pending.status == "pending":
        evaluation = evaluate_pending_target(portfolio_summary, pending, settings=settings)
        pending.status = "hit" if evaluation.hit else "miss"
        state["last_result"] = evaluation.to_dict()
        history = list(state.get("history") or [])
        history.append({**evaluation.to_dict(), "baseline_nav": pending.baseline_nav})
        state["history"] = history[-int(cfg.get("history_limit", 120)) :]

    next_target = compute_next_day_target(
        portfolio_summary,
        settings=settings,
        prev_result=evaluation or state.get("last_result"),
    )
    state["pending"] = next_target.to_dict()
    save_pnl_target_state(state, path=path)

    return {
        "skipped": False,
        "evaluated": evaluation.to_dict() if evaluation else None,
        "next_target": next_target.to_dict(),
        "path": str(path or default_pnl_target_path()),
    }


def render_pnl_target_markdown(
    *,
    pending: Optional[PnlTarget | dict[str, Any]] = None,
    last_result: Optional[PnlTargetResult | dict[str, Any]] = None,
    next_target: Optional[PnlTarget | dict[str, Any]] = None,
) -> str:
    lines = ["### 🎯 盈亏目标"]

    if last_result:
        data = last_result.to_dict() if isinstance(last_result, PnlTargetResult) else last_result
        label = "达成" if data.get("hit") else "未达"
        emoji = "✅" if data.get("hit") else "⚠️"
        lines.append(
            f"- {emoji} 今日目标 {label}：目标 **{float(data['target_pnl_cny']):+,.0f}** "
            f"实际 **{float(data['actual_pnl_cny']):+,.0f}**（差 {float(data['delta_cny']):+,.0f}）"
        )

    target = next_target or pending
    if target:
        row = target.to_dict() if isinstance(target, PnlTarget) else target
        pct_s = f"（{float(row['target_pnl_pct']):+.2f}%）" if row.get("target_pnl_pct") is not None else ""
        lines.append(
            f"- 下一交易日 **{row.get('target_date')}** 总盈亏目标 "
            f"**+{float(row['target_pnl_cny']):,.0f}**{pct_s}"
        )
    else:
        lines.append("- 尚未设定下一交易日目标")

    return "\n".join(lines)
