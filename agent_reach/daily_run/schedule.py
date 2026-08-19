# -*- coding: utf-8
"""Cron/schedule helpers for daily-run morning, intraday, and close jobs."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.run_manifest import StepTimer, save_run_manifest

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.schedule")


MARKER_BEGIN = "# agent-reach daily-run schedule BEGIN"
MARKER_END = "# agent-reach daily-run schedule END"

# 15 scans/day: S1 premarket 07:00 + S2 morning 08:00 + S3 09:00 + S4–S15 session (no 08:30 slot)
INTRADAY_SCAN_TIMES: list[tuple[str, str]] = [
    ("0", "9"),    # 09:00 S3
    ("30", "9"),   # 09:30 S4
    ("54", "9"),   # 09:54 S5
    ("18", "10"),  # 10:18 S6
    ("42", "10"),  # 10:42 S7
    ("6", "11"),   # 11:06 S8
    ("30", "11"),  # 11:30 S9
    ("0", "13"),   # 13:00 S10
    ("24", "13"),  # 13:24 S11
    ("48", "13"),  # 13:48 S12
    ("12", "14"),  # 14:12 S13
    ("36", "14"),  # 14:36 S14
    ("0", "15"),   # 15:00 S15
]
# S1 = 07:00 premarket intraday; S2 = 08:00 morning job; S3–S15 = intraday cron slots above
INTRADAY_MAX_SCANS = 1 + 1 + len(INTRADAY_SCAN_TIMES)


@dataclass
class CronEntry:
    minute: str
    hour: str
    weekday: str
    job: str
    label: str

    def line(self) -> str:
        return f"{self.minute} {self.hour} * * {self.weekday} {self.job}  # {self.label}"


def _agent_reach_cmd() -> str:
    exe = shutil_which("agent-reach")
    if exe:
        return exe
    return f"{sys.executable} -m agent_reach.cli"


def shutil_which(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def local_cron_script() -> Path:
    """Absolute path to scripts/daily-run-local-cron.sh (repo root)."""
    return Path(__file__).resolve().parents[2] / "scripts" / "daily-run-local-cron.sh"


def _cron_run_cmd(job: str) -> str:
    """Cron-safe command: prefer local wrapper script over bare CLI name."""
    script = local_cron_script()
    if script.is_file():
        return f"{script} {job}"
    return f"{_agent_reach_cmd()} daily-run schedule run {job}"


def default_entries() -> list[CronEntry]:
    """Default Asia/Shanghai trading schedule (CRON_TZ=Asia/Shanghai)."""
    entries = [
        CronEntry("0", "7", "1-5", _cron_run_cmd("intraday"), "daily-run 盘前 S1 7:00"),
        CronEntry("0", "8", "1-5", _cron_run_cmd("morning"), "daily-run 早盘 8:00"),
    ]
    for i, (minute, hour) in enumerate(INTRADAY_SCAN_TIMES, start=3):
        entries.append(
            CronEntry(
                minute,
                hour,
                "1-5",
                _cron_run_cmd("intraday"),
                f"daily-run 盘中 S{i}/{INTRADAY_MAX_SCANS}",
            )
        )
    entries.append(
        CronEntry("0", "18", "1-5", _cron_run_cmd("close"), "daily-run 收盘 18:00")
    )
    entries.append(
        CronEntry("30", "8", "6", _cron_run_cmd("weekly"), "daily-run 周报 周六 8:30")
    )
    entries.append(
        CronEntry("30", "8", "0", _cron_run_cmd("forecast"), "daily-run 下周预测 周日 8:30")
    )
    return entries


def render_crontab_block(entries: Optional[list[CronEntry]] = None) -> str:
    entries = entries or default_entries()
    script = local_cron_script()
    lines = [
        MARKER_BEGIN,
        "SHELL=/bin/bash",
        "CRON_TZ=Asia/Shanghai",
        "# logs: ~/.agent-reach/daily_run/logs/cron-YYYY-MM-DD.log",
    ]
    if script.is_file():
        lines.append(f"# wrapper: {script}")
    for e in entries:
        lines.append(e.line())
    lines.append(MARKER_END)
    return "\n".join(lines) + "\n"


def install_crontab(entries: Optional[list[CronEntry]] = None, *, dry_run: bool = False) -> str:
    block = render_crontab_block(entries)
    if dry_run:
        return block

    script = local_cron_script()
    if script.is_file():
        script.chmod(script.stat().st_mode | 0o111)

    crontab_bin = shutil_which("crontab")
    if not crontab_bin:
        fallback = Path.home() / ".agent-reach" / "daily_run" / "crontab.txt"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(block, encoding="utf-8")
        raise RuntimeError(
            f"系统未安装 crontab。已将推荐配置写入 {fallback}，"
            "请手动复制到本地 crontab 或任务计划程序"
        )

    existing = ""
    try:
        existing = subprocess.check_output([crontab_bin, "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        existing = ""

    if MARKER_BEGIN in existing:
        before = existing.split(MARKER_BEGIN)[0].rstrip()
        after_parts = existing.split(MARKER_END)
        after = after_parts[1].lstrip("\n") if len(after_parts) > 1 else ""
        new_crontab = before
        if new_crontab:
            new_crontab += "\n"
        new_crontab += block
        if after.strip():
            new_crontab += after
    else:
        new_crontab = existing.rstrip() + "\n\n" + block if existing.strip() else block

    proc = subprocess.run(
        [crontab_bin, "-"],
        input=new_crontab.encode(),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode() or "crontab install failed")
    return new_crontab


def _doctor_for_job(config, settings: dict, job: str) -> dict:
    if job in ("weekly", "forecast"):
        return {}
    from agent_reach.daily_run.doctor_cache import doctor_channels_cached

    return doctor_channels_cached(config, settings)


def run_scheduled(
    job: str,
    *,
    push: bool = True,
    config=None,
    force: bool = False,
) -> dict:
    """Execute morning | intraday | close with auto snapshot + doctor + manifest."""
    from agent_reach.config import Config
    from agent_reach.daily_run.settings import load_settings

    cfg_obj = config or Config()
    settings = load_settings()
    t0 = time.perf_counter()

    from agent_reach.daily_run.trade_calendar import is_trading_day

    if job not in ("weekly", "forecast"):
        trading_ok, trading_reason = is_trading_day(settings=settings)
        if not trading_ok:
            result = {"job": job, "skipped": True, "reason": trading_reason}
            save_run_manifest(job, result, duration_ms=0)
            return result

    from agent_reach.daily_run.run_guard import (
        JobBusyError,
        check_duplicate_job,
        job_run_lock,
    )

    dup_reason = check_duplicate_job(job, force=force, settings=settings)
    if dup_reason:
        result = {"job": job, "skipped": True, "reason": dup_reason, "guard": "dedupe"}
        _apply_scheduled_guard_harness(job, dup_reason, "dedupe", settings, result=result)
        _attach_manifest_harness_summary(result)
        save_run_manifest(job, result, duration_ms=0)
        return result

    try:
        with job_run_lock(job, force=force, settings=settings):
            return _run_scheduled_inner(
                job,
                push=push,
                config=cfg_obj,
                settings=settings,
                t0=t0,
            )
    except JobBusyError as exc:
        result = {"job": job, "skipped": True, "reason": str(exc), "guard": "lock"}
        _apply_scheduled_guard_harness(job, str(exc), "lock", settings, result=result)
        _attach_manifest_harness_summary(result)
        save_run_manifest(job, result, duration_ms=0)
        return result


def _attach_manifest_harness_summary(payload: dict[str, Any]) -> None:
    from agent_reach.daily_run.harness import build_manifest_harness_summary

    payload["harness_summary"] = build_manifest_harness_summary(payload)


def _append_harness_error(target: dict[str, Any], context: str, exc: BaseException) -> None:
    msg = f"{context}: {exc}"
    target.setdefault("harness_errors", []).append(msg)
    logger.warning("daily-run harness error: {}", msg)


def _apply_scheduled_guard_harness(
    job: str,
    reason: str,
    guard: str,
    settings: dict,
    *,
    consecutive_failures: int | None = None,
    result: Optional[dict[str, Any]] = None,
) -> None:
    try:
        from agent_reach.daily_run.run_guard_harness import apply_run_guard_harness_refinement

        apply_run_guard_harness_refinement(
            job,
            reason=reason,
            guard=guard,
            consecutive_failures=consecutive_failures,
            settings=settings,
        )
    except Exception as exc:
        if result is not None:
            _append_harness_error(result, f"run_guard:{guard}", exc)
        else:
            logger.warning("daily-run run_guard harness failed ({}): {}", job, exc)


def _apply_scheduled_job_harness(
    job: str,
    result: dict,
    settings: dict,
    *,
    push: bool = False,
    config=None,
) -> None:
    """Post-schedule harness for intraday only; morning is handled inside run_morning()."""
    if job == "morning":
        return
    try:
        if job == "intraday":
            from agent_reach.daily_run.intraday_harness import apply_intraday_harness_refinement

            if result.get("skipped"):
                harness_ref = apply_intraday_harness_refinement(result, settings=settings)
            else:
                run_result = result.get("result") or {}
                harness_ref = (
                    apply_intraday_harness_refinement(run_result, settings=settings)
                    if run_result
                    else {"skipped": True, "reason": "empty intraday result"}
                )
            if harness_ref:
                result["harness_intraday"] = harness_ref
                if push and config is not None:
                    from agent_reach.daily_run.workflows import push_scheduled_harness_card

                    steps = push_scheduled_harness_card(
                        job="intraday",
                        harness_result={"intraday": harness_ref},
                        settings=settings,
                        config=config,
                        push=push,
                        harness_errors=result.get("harness_errors"),
                    )
                    if steps:
                        result.setdefault("harness_followup_steps", []).extend(steps)
    except Exception as exc:
        _append_harness_error(result, f"scheduled_job_harness:{job}", exc)


def _run_scheduled_inner(
    job: str,
    *,
    push: bool,
    config,
    settings: dict,
    t0: float,
) -> dict:
    from agent_reach.daily_run.job_health import (
        maybe_alert_consecutive_failures,
        record_job_outcome,
    )

    doctor = _doctor_for_job(config, settings, job)

    try:
        result, feishu = _run_job_body(
            job,
            push=push,
            config=config,
            settings=settings,
            doctor=doctor,
            t0=t0,
        )
        record_job_outcome(job, success=True)
    except Exception as exc:
        job_error = str(exc)
        streak = record_job_outcome(job, success=False, error=job_error)
        maybe_alert_consecutive_failures(job, settings=settings, config=config)
        duration_ms = (time.perf_counter() - t0) * 1000
        fail_payload = {"job": job, "error": job_error, "consecutive_failures": streak}
        _apply_scheduled_guard_harness(
            job, job_error, "failure", settings, consecutive_failures=streak, result=fail_payload
        )
        _attach_manifest_harness_summary(fail_payload)
        save_run_manifest(job, fail_payload, duration_ms=duration_ms)
        raise

    duration_ms = (time.perf_counter() - t0) * 1000
    _apply_scheduled_job_harness(job, result, settings, push=push, config=config)
    _attach_manifest_harness_summary(result)
    manifest_path = save_run_manifest(job, result, feishu=feishu, duration_ms=duration_ms)
    result["manifest_path"] = str(manifest_path)
    return result


def _uses_per_symbol_jobs(settings: dict) -> bool:
    mode = str((settings.get("schedule") or {}).get("symbols_mode", "primary")).lower()
    return mode != "primary"


def _maybe_send_scheduled_start_notification(
    job: str,
    *,
    push: bool,
    config,
    settings: dict,
) -> None:
    from agent_reach.daily_run.workflows import (
        scheduled_start_context,
        scheduled_start_notify_enabled,
        send_scheduled_job_start_notification,
    )

    if not push or not scheduled_start_notify_enabled(settings):
        return
    ctx = scheduled_start_context(job, settings)
    if ctx.get("skip"):
        return
    send_scheduled_job_start_notification(
        job,
        config,
        settings,
        symbol_count=int(ctx.get("symbol_count") or 1),
        scan_id=ctx.get("scan_id"),
    )


def _run_job_body(
    job: str,
    *,
    push: bool,
    config,
    settings: dict,
    doctor: dict,
    t0: float,
) -> tuple[dict, Any]:
    """Execute morning/intraday/close; returns (result, feishu)."""
    from agent_reach.daily_run.snapshot_builder import example_portfolio_path, load_portfolio, save_portfolio

    try:
        load_portfolio()
    except FileNotFoundError:
        save_portfolio(
            __import__("json").loads(example_portfolio_path().read_text(encoding="utf-8"))
        )

    _maybe_send_scheduled_start_notification(job, push=push, config=config, settings=settings)

    per_symbol = job in ("morning", "intraday", "close") and _uses_per_symbol_jobs(settings)

    if per_symbol and job == "morning":
        from agent_reach.daily_run.symbol_runner import run_morning_for_symbols

        with StepTimer("schedule.morning"):
            result = run_morning_for_symbols(
                settings=settings,
                push=push,
                config=config,
                doctor_channels=doctor,
            )
            feishu = result.get("feishu")
        return result, feishu

    if per_symbol and job == "intraday":
        from agent_reach.daily_run.symbol_runner import run_intraday_for_symbols

        with StepTimer("schedule.intraday"):
            result = run_intraday_for_symbols(
                settings=settings,
                push=push,
                config=config,
                doctor_channels=doctor,
            )
            feishu = result.get("feishu")
        return result, feishu

    if per_symbol and job == "close":
        from agent_reach.daily_run.symbol_runner import run_close_for_symbols

        with StepTimer("schedule.close"):
            result = run_close_for_symbols(
                settings=settings,
                push=push,
                config=config,
            )
            feishu = result.get("feishu")
        return result, feishu

    from agent_reach.daily_run.snapshot_builder import build_and_save
    from agent_reach.daily_run.workflows import load_morning_baseline, run_close, run_morning

    result: dict
    feishu = None

    if job == "morning":
        with StepTimer("schedule.morning"):
            snap, path = build_and_save(report_type="premarket", config=config)
            run_result = run_morning(
                snap,
                settings=settings,
                doctor_channels=doctor,
                push=push,
                start_notify=False,
                config=config,
            )
            from agent_reach.daily_run.workflows import save_morning_baseline

            save_morning_baseline(run_result["snapshot"])
            from agent_reach.daily_run.intraday import record_morning_scan

            scan_result = record_morning_scan(run_result, settings=settings)
            from agent_reach.daily_run.report_narrative import persist_morning_narrative

            morning_narrative = run_result.get("llm_narrative")
            if morning_narrative and not morning_narrative.get("skipped"):
                persist_morning_narrative(morning_narrative)
            result = {
                "job": job,
                "snapshot_path": str(path),
                "result": run_result,
                "morning_scan": scan_result.get("scan"),
            }
            feishu = run_result.get("feishu")

    elif job == "intraday":
        from agent_reach.daily_run.intraday import load_state, run_intraday, should_evaluate_trade

        with StepTimer("schedule.intraday"):
            state = load_state()
            if len(state.scans) >= INTRADAY_MAX_SCANS:
                result = {
                    "job": job,
                    "skipped": True,
                    "reason": f"今日扫描已达 {INTRADAY_MAX_SCANS} 次上限",
                }
                feishu = None
            else:
                snap, path = build_and_save(report_type="intraday", config=config)
                do_trade = should_evaluate_trade(state, settings)
                run_result = run_intraday(
                    snap,
                    settings=settings,
                    doctor_channels=doctor,
                    push=push,
                    trade=do_trade,
                    config=config,
                )
                result = {
                    "job": job,
                    "snapshot_path": str(path),
                    "trade_evaluated": do_trade,
                    "result": run_result,
                    "scan_count": (run_result.get("scan_count")
                                   or len((run_result.get("scan") or {}).get("state", {}).get("scans") or [])),
                }
                feishu = run_result.get("feishu")
                if run_result.get("push_error"):
                    result["push_error"] = run_result["push_error"]

    elif job == "weekly":
        from agent_reach.daily_run.workflows import run_weekly

        with StepTimer("schedule.weekly"):
            pf = load_portfolio()
            snap, path = build_and_save(
                report_type="close",
                config=config,
                settings=settings,
                portfolio=pf,
                enrich_level="lite",
            )
            run_result = run_weekly(
                snap,
                settings=settings,
                push=push,
                config=config,
                portfolio=pf,
            )
            result = {"job": job, "snapshot_path": str(path), "result": run_result}
            feishu = run_result.get("feishu")

    elif job == "forecast":
        from agent_reach.daily_run.workflows import run_forecast

        with StepTimer("schedule.forecast"):
            pf = load_portfolio()
            snap, path = build_and_save(
                report_type="close",
                config=config,
                settings=settings,
                portfolio=pf,
                enrich_level="lite",
            )
            run_result = run_forecast(
                snap,
                settings=settings,
                push=push,
                config=config,
                portfolio=pf,
            )
            result = {
                "job": job,
                "snapshot_path": str(path),
                "forecast_path": run_result.get("forecast_path"),
                "result": run_result,
            }
            feishu = run_result.get("feishu")

    elif job == "close":
        from agent_reach.daily_run.intraday import load_state

        with StepTimer("schedule.close"):
            pf = load_portfolio()
            snap, path = build_and_save(report_type="close", config=config, portfolio=pf)
            state = load_state()
            if state.scans:
                snap["intraday_scans"] = state.scans
                snap["mss_intraday_actual"] = [s.get("mss_final") for s in state.scans]

            from agent_reach.daily_run.baseline_fallback import load_close_baseline

            baseline_source = "last_morning.json"
            baseline_note = None
            try:
                baseline = load_morning_baseline()
            except FileNotFoundError as exc:
                try:
                    baseline, baseline_source = load_close_baseline(scans=state.scans)
                    baseline_note = f"降级基线：{baseline_source}（原错误：{exc}）"
                    if push:
                        from agent_reach.integrations.feishu import send_card

                        send_card(
                            config,
                            "⚠️ 收盘复盘使用降级基线",
                            f"{baseline_note}\n\n建议补跑 `daily-run schedule run morning`",
                            template="orange",
                        )
                except FileNotFoundError:
                    if push:
                        from agent_reach.integrations.feishu import send_card

                        send_card(
                            config,
                            "⚠️ 收盘复盘缺少早盘基线",
                            f"未找到 `last_morning.json`：{exc}\n\n请先运行 `daily-run morning --save-baseline`",
                            template="red",
                        )
                    raise

            from agent_reach.daily_run.workflows import prepare_close_run

            prepared = prepare_close_run(
                snap,
                baseline,
                pf,
                settings=settings,
                scans=state.scans,
                trades=state.trades,
                attach_intraday=False,
            )
            snap = prepared["snapshot"]
            wl_result_dict = prepared.get("watchlist_adjust")
            code_review_dict = prepared.get("code_review")

            run_result = run_close(
                snap,
                baseline,
                settings=settings,
                push=push,
                config=config,
                intraday_scans=state.scans,
                intraday_trades=state.trades,
                watchlist_adjust=wl_result_dict,
                code_review=code_review_dict,
                verify_dict=prepared.get("verify"),
                experts_already_ran=any(
                    s in (prepared.get("steps") or []) for s in ("team_first", "mss_experts")
                ),
            )
            run_result["baseline_source"] = baseline_source
            if baseline_note:
                run_result["baseline_note"] = baseline_note
            if code_review_dict is not None:
                run_result["code_review"] = code_review_dict
            run_result["prepare_steps"] = prepared.get("steps") or []
            if wl_result_dict is not None:
                run_result["watchlist_adjust"] = wl_result_dict

            result = {"job": job, "snapshot_path": str(path), "result": run_result}
            feishu = run_result.get("feishu")

    else:
        raise ValueError(f"未知定时任务：{job}，可选 morning | intraday | close | weekly | forecast")

    return result, feishu
