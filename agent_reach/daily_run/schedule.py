# -*- coding: utf-8
"""Cron/schedule helpers for daily-run morning, intraday, and close jobs."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from agent_reach.daily_run.run_manifest import StepTimer, save_run_manifest

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.schedule")


MARKER_BEGIN = "# agent-reach daily-run schedule BEGIN"
MARKER_END = "# agent-reach daily-run schedule END"
BOOT_CATCHUP_SLEEP_SECONDS = 60
_SH_TZ = ZoneInfo("Asia/Shanghai")

# 13 scans/day: S1 07:00 + S2 08:00 + midday 12:30 + S3–S12 session (A-share aligned)
# Morning T slots: S4 09:45 / S5 10:15 / S6 10:45 / S7 11:20 (inside 09:30–11:30)
# Afternoon T slots: S8 13:05 / S9 13:35 / S10 14:10 / S11 14:40 (inside 13:00–14:57)
INTRADAY_SCAN_TIMES: list[tuple[str, str]] = [
    ("0", "9"),    # 09:00 S3 — pre-open / lookback only
    ("45", "9"),   # 09:45 S4 — post-open confirmation
    ("15", "10"),  # 10:15 S5 — mid-morning
    ("45", "10"),  # 10:45 S6 — late morning
    ("20", "11"),  # 11:20 S7 — last morning eval before lunch
    ("5", "13"),   # 13:05 S8 — afternoon open confirmation
    ("35", "13"),  # 13:35 S9 — early afternoon
    ("10", "14"),  # 14:10 S10 — mid-afternoon
    ("40", "14"),  # 14:40 S11 — pre-close (before 14:57 auction)
    ("0", "15"),   # 15:00 S12 — post-close archive, no trade eval
]
# S1 + S2 + midday + len(INTRADAY_SCAN_TIMES)
INTRADAY_MAX_SCANS = 1 + 1 + 1 + len(INTRADAY_SCAN_TIMES)


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


def boot_catchup_script() -> Path:
    """Absolute path to scripts/daily-run-boot-catchup.sh (repo root)."""
    return Path(__file__).resolve().parents[2] / "scripts" / "daily-run-boot-catchup.sh"


def has_premarket_s1_today() -> bool:
    """True when today's intraday state already contains scan S1."""
    from agent_reach.daily_run.intraday import load_state
    from agent_reach.daily_run.trade_calendar import today_shanghai

    st = load_state()
    if st.date != today_shanghai().isoformat():
        return False
    return any(str(s.get("scan_id") or "") == "S1" for s in st.scans)


def needs_premarket_catchup(
    *,
    now: Optional[datetime] = None,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    """Return (should_run, reason) for late-boot S1 catch-up (07:00–07:59 Shanghai)."""
    sh_now = now or datetime.now(_SH_TZ)
    if sh_now.tzinfo is None:
        sh_now = sh_now.replace(tzinfo=_SH_TZ)
    else:
        sh_now = sh_now.astimezone(_SH_TZ)

    if sh_now.hour != 7:
        return False, f"outside catchup window (hour={sh_now.hour})"

    from agent_reach.daily_run.settings import load_settings
    from agent_reach.daily_run.trade_calendar import is_trading_day

    cfg = settings or load_settings()
    trading_ok, trading_reason = is_trading_day(settings=cfg)
    if not trading_ok:
        return False, trading_reason

    if has_premarket_s1_today():
        return False, "S1 already recorded"

    return True, "late boot before 08:00 morning"


def run_boot_catchup(*, push: bool = True, config=None) -> dict[str, Any]:
    """Run intraday S1 when cron 07:00 was missed due to late boot."""
    should_run, reason = needs_premarket_catchup()
    if not should_run:
        logger.info("daily-run boot catchup skipped: {}", reason)
        return {"catchup": False, "reason": reason}
    logger.info("daily-run boot catchup running intraday: {}", reason)
    result = run_scheduled("intraday", push=push, config=config)
    return {"catchup": True, "reason": reason, "result": result}


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
        CronEntry("30", "12", "1-5", _cron_run_cmd("midday"), "daily-run 午盘分析 12:30"),
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
    catchup = boot_catchup_script()
    if catchup.is_file():
        lines.append(f"# boot catchup log: ~/.agent-reach/daily_run/logs/boot-catchup-YYYY-MM-DD.log")
        lines.append(
            f"@reboot sleep {BOOT_CATCHUP_SLEEP_SECONDS} && {catchup}  "
            f"# daily-run S1 catchup after late boot"
        )
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
    catchup = boot_catchup_script()
    if catchup.is_file():
        catchup.chmod(catchup.stat().st_mode | 0o111)

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
    from agent_reach.daily_run.settings import effective_settings, load_settings

    cfg_obj = config or Config()
    settings = effective_settings(load_settings())
    t0 = time.perf_counter()

    from agent_reach.daily_run.trade_calendar import is_trading_day

    if job not in ("weekly", "forecast"):
        trading_ok, trading_reason = is_trading_day(settings=settings)
        if not trading_ok and not force:
            result = {"job": job, "skipped": True, "reason": trading_reason}
            save_run_manifest(job, result, duration_ms=0)
            return result
        if not trading_ok and force:
            logger.warning("schedule {}: --force 绕过交易日检查（{}）", job, trading_reason)

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
    """Post-schedule harness for intraday/midday only; morning is handled inside run_morning()."""
    if job == "morning":
        return
    try:
        if job == "intraday":
            from agent_reach.daily_run.intraday_harness import apply_intraday_harness_refinement

            if result.get("skipped"):
                harness_ref = apply_intraday_harness_refinement(result, settings=settings)
            else:
                run_result = result.get("result") or {}
                if not run_result and result.get("symbol_results"):
                    run_result = result
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
        elif job == "midday":
            from agent_reach.daily_run.midday_harness import apply_midday_harness_refinement

            if result.get("skipped"):
                run_result = result
            else:
                run_result = result.get("result") or {}
                if not run_result and result.get("symbol_results"):
                    run_result = result
            harness_ref = (
                apply_midday_harness_refinement(run_result, settings=settings)
                if run_result
                else {"skipped": True, "reason": "empty midday result"}
            )
            if harness_ref:
                result["harness_midday"] = harness_ref
                if push and config is not None:
                    from agent_reach.daily_run.workflows import push_scheduled_harness_card

                    steps = push_scheduled_harness_card(
                        job="midday",
                        harness_result={"midday": harness_ref},
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

    per_symbol = job in ("morning", "midday", "intraday", "close") and _uses_per_symbol_jobs(settings)

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

    if per_symbol and job == "midday":
        from agent_reach.daily_run.symbol_runner import run_midday_for_symbols

        with StepTimer("schedule.midday"):
            result = run_midday_for_symbols(
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

    elif job == "midday":
        from agent_reach.daily_run.midday import midday_cfg, run_midday

        with StepTimer("schedule.midday"):
            if not midday_cfg(settings)["enabled"]:
                result = {"job": job, "skipped": True, "reason": "midday disabled"}
                feishu = None
            else:
                from agent_reach.daily_run.intraday import load_state

                state = load_state()
                if len(state.scans) >= INTRADAY_MAX_SCANS:
                    result = {
                        "job": job,
                        "skipped": True,
                        "reason": f"今日扫描已达 {INTRADAY_MAX_SCANS} 次上限",
                    }
                    feishu = None
                else:
                    snap, path = build_and_save(
                        report_type="midday",
                        config=config,
                        settings=settings,
                        enrich_level="quotes",
                    )
                    run_result = run_midday(
                        snap,
                        settings=settings,
                        doctor_channels=doctor,
                        push=push,
                        config=config,
                    )
                    result = {
                        "job": job,
                        "snapshot_path": str(path),
                        "result": run_result,
                        "scan": run_result.get("scan"),
                    }
                    feishu = run_result.get("feishu")
                    if run_result.get("push_error"):
                        result["push_error"] = run_result["push_error"]

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
        raise ValueError(f"未知定时任务：{job}，可选 morning | midday | intraday | close | weekly | forecast")

    return result, feishu


def _intraday_scan_payload(run: dict[str, Any]) -> dict[str, Any]:
    """Extract scan entry from run_intraday / record_scan result."""
    inner = run.get("scan") or {}
    return inner.get("scan") or inner


def format_scheduled_run_summary(result: dict[str, Any], job: str) -> dict[str, Any]:
    """Normalize cron/CLI one-line summaries for legacy and per-symbol schedule results."""
    symbol_results = result.get("symbol_results") or []
    job_result = result.get("result") or {}

    snapshot_path = result.get("snapshot_path")
    if not snapshot_path and symbol_results:
        snapshot_path = symbol_results[-1].get("snapshot_path")

    out: dict[str, Any] = {
        "snapshot_path": snapshot_path,
        "symbol_count": len(symbol_results) if symbol_results else None,
    }

    def _last_symbol_run() -> dict[str, Any]:
        if not symbol_results:
            return {}
        return symbol_results[-1].get("result") or {}

    if job == "morning":
        if symbol_results:
            report = (_last_symbol_run().get("evaluation") or {}).get("report") or {}
        else:
            report = (job_result.get("evaluation") or {}).get("report") or {}
        out["verdict"] = report.get("verdict")
        out["mss_final"] = report.get("mss_final")
    elif job == "midday":
        if symbol_results:
            scan = _intraday_scan_payload(_last_symbol_run())
            if not scan.get("scan_id"):
                scan = symbol_results[-1].get("scan") or scan
        else:
            scan = result.get("scan") or _intraday_scan_payload(job_result)
        out["scan_id"] = scan.get("scan_id")
        out["mss_final"] = scan.get("mss_final")
        out["verdict"] = scan.get("verdict")
    elif job == "intraday":
        if symbol_results:
            from agent_reach.daily_run.intraday import pick_batch_scan_id

            scan_ids: list[str] = []
            mss_vals: list[float] = []
            verdict = None
            for row in symbol_results:
                scan = _intraday_scan_payload(row.get("result") or {})
                sid = scan.get("scan_id")
                if sid:
                    scan_ids.append(str(sid))
                mss = scan.get("mss_final")
                if mss is not None:
                    mss_vals.append(float(mss))
                if verdict is None and scan.get("verdict"):
                    verdict = scan.get("verdict")
            out["scan_id"] = pick_batch_scan_id(scan_ids) if scan_ids else None
            out["mss_final"] = mss_vals[-1] if mss_vals else None
            out["verdict"] = verdict
        else:
            scan = _intraday_scan_payload(job_result)
            out["scan_id"] = scan.get("scan_id")
            out["mss_final"] = scan.get("mss_final")
            out["verdict"] = scan.get("verdict")
    elif job == "close":
        if symbol_results:
            verify = _last_symbol_run().get("verify") or {}
        else:
            verify = job_result.get("verify") or {}
        out["close_summary"] = str(verify.get("summary") or "")[:80]
    elif job == "weekly":
        wr = job_result.get("report") or {}
        out["weekly_pnl"] = wr.get("weekly_pnl")
        out["weekly_holdings"] = len(wr.get("holdings") or [])
    elif job == "forecast":
        fc = job_result.get("forecast") or {}
        out["forecast_range"] = f"{fc.get('week_start')}–{fc.get('week_end')}"
        out["forecast_symbols"] = len(fc.get("symbols") or {})
        out["forecast_path"] = result.get("forecast_path") or job_result.get("forecast_path")
    return out
