# -*- coding: utf-8
"""Schedule guard events and manifest gaps → harness self-evolution."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from agent_reach.daily_run.harness_skill_base import apply_skill_refinement, merge_harness_evidence


def _guard_harness_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = settings or {}
    guard = (cfg.get("schedule") or {}).get("guard") or {}
    if guard.get("harness_evolve", True) is False:
        return False
    harness = cfg.get("harness") or {}
    return harness.get("enabled") is not False


def guard_event_to_harness_evidence(
    job: str,
    *,
    reason: str,
    guard: str,
    consecutive_failures: Optional[int] = None,
) -> dict[str, Any]:
    memory: list[str] = []
    policy: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    labels = {
        "morning": "早盘",
        "close": "收盘",
        "intraday": "盘中",
        "weekly": "周报",
        "forecast": "预测",
    }
    label = labels.get(job, job)
    memory.append(f"run_guard {guard}：{label} — {reason[:200]}")

    if guard == "dedupe":
        playbook.append(f"今日{label}已执行 manifest 去重；补跑需 --force")
    elif guard == "lock":
        plan.append(f"run_guard：检查 {job}.lock 僵尸进程，必要时 rm lock 后 --force")
    elif guard == "failure":
        memory.append(f"定时任务 {label} 连续失败 {consecutive_failures or '?'} 次")
        plan.append(f"run_guard：排查 {label} cron 日志与 doctor 通道")

    if "cooldown" in reason.lower():
        playbook.append("Harness LLM refine cooldown 生效；勿重复手动 refine")

    summary = f"run_guard {job} {guard}"
    return {
        "memory": memory,
        "policy": policy,
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def schedule_gaps_to_harness_evidence(
    *,
    week_start: date,
    manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    memory: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []

    trading_days = {(week_start + timedelta(days=i)).isoformat() for i in range(5)}
    days_with_morning = {m.get("_run_date") for m in manifests if m.get("job") == "morning"}
    days_with_close = {m.get("_run_date") for m in manifests if m.get("job") == "close"}
    days_with_intraday = {m.get("_run_date") for m in manifests if m.get("job") == "intraday"}

    missing_morning = sorted(trading_days - days_with_morning)
    missing_close = sorted(trading_days - days_with_close)
    if missing_morning:
        memory.append(f"缺失 {len(missing_morning)} 天早盘 manifest：{', '.join(missing_morning)}")
        plan.append("run_guard：检查 cron 0 8 * * 1-5 与 daily-run schedule run morning")
    if missing_close:
        memory.append(f"缺失 {len(missing_close)} 天收盘 manifest：{', '.join(missing_close)}")
        plan.append("run_guard：检查 cron 30 15 * * 1-5 或手动补跑 close")

    intraday_by_day: dict[str, int] = {}
    for m in manifests:
        if m.get("job") != "intraday":
            continue
        day = str(m.get("_run_date") or "")
        intraday_by_day[day] = intraday_by_day.get(day, 0) + 1

    low_scan_days = [d for d, n in intraday_by_day.items() if n < 5]
    if low_scan_days:
        memory.append(f"{len(low_scan_days)} 天盘中扫描偏少：{', '.join(low_scan_days[:3])}")
        playbook.append("盘中扫描偏少：intraday 次数不足，下日 trade_min_scans 可降至 2")
        plan.append("run_guard：确认 09:30–15:00 intraday cron 与 intraday_state 累积")

    if not days_with_intraday and not intraday_by_day:
        memory.append("本周无 intraday manifest：S4–S15 未落盘")
        plan.append("run_guard：排查 intraday cron 与 resolve-job.sh 窗口")

    summary = f"schedule_gaps morning_miss={len(missing_morning)} close_miss={len(missing_close)}"
    return {
        "memory": memory,
        "policy": [],
        "playbook": playbook,
        "plan": plan,
        "summary": summary,
    }


def apply_run_guard_harness_refinement(
    job: str,
    *,
    reason: str,
    guard: str,
    consecutive_failures: Optional[int] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not _guard_harness_enabled(settings):
        return {"skipped": True, "reason": "run_guard harness disabled", "job": "run_guard"}
    evidence = guard_event_to_harness_evidence(
        job,
        reason=reason,
        guard=guard,
        consecutive_failures=consecutive_failures,
    )
    return apply_skill_refinement("run_guard", evidence, settings=settings)


def apply_schedule_gaps_harness_refinement(
    *,
    week_start: date,
    manifests: list[dict[str, Any]],
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not _guard_harness_enabled(settings):
        return {"skipped": True, "reason": "run_guard harness disabled", "job": "run_guard"}
    evidence = schedule_gaps_to_harness_evidence(week_start=week_start, manifests=manifests)
    if not any(evidence.get(k) for k in ("memory", "playbook", "plan")):
        return {"skipped": True, "reason": "no schedule gaps", "job": "run_guard"}
    return apply_skill_refinement("run_guard", evidence, settings=settings)


def apply_process_improvements_guard_harness(
    process_improvements: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Map weekly schedule/workflow improvements to run_guard harness."""
    if not _guard_harness_enabled(settings):
        return {"skipped": True, "reason": "run_guard harness disabled", "job": "run_guard"}

    memory: list[str] = []
    playbook: list[str] = []
    plan: list[str] = []
    for item in process_improvements:
        cat = str(item.get("category") or "")
        if cat not in ("schedule", "workflow"):
            continue
        title = str(item.get("title") or "")
        detail = str(item.get("detail") or "")
        action = str(item.get("action") or "")
        line = f"{title} — {detail}"
        memory.append(line)
        if action:
            plan.append(f"run_guard：{action[:160]}")
        if "扫描" in title or "intraday" in detail.lower():
            playbook.append(line[:200])
        if item.get("priority") == "high":
            plan.append(f"run_guard high：{title}")

    if not memory:
        return {"skipped": True, "reason": "no schedule improvements", "job": "run_guard"}

    evidence = merge_harness_evidence(
        {
            "memory": memory,
            "playbook": playbook,
            "plan": plan,
            "summary": f"weekly schedule items={len(memory)}",
        }
    )
    return apply_skill_refinement("run_guard", evidence, settings=settings)
