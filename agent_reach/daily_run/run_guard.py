# -*- coding: utf-8
"""DSH-style busy guards: lockfiles, duplicate job detection, harness cooldown."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional


class JobBusyError(RuntimeError):
    """Raised when a scheduled job is already running or deduplicated."""


class HarnessCooldownError(RuntimeError):
    """Raised when manual harness refine is blocked by cooldown."""


_LOCK_DIR = Path.home() / ".agent-reach" / "daily_run" / "locks"
_DEDUP_JOBS = frozenset({"morning", "close", "weekly", "forecast"})


def lock_dir() -> Path:
    return _LOCK_DIR


def _guard_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict(((settings or {}).get("schedule") or {}).get("guard") or {})


def guard_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    cfg = _guard_cfg(settings)
    return cfg.get("enabled", True) is not False


@contextmanager
def job_run_lock(job: str, *, force: bool = False, settings: Optional[dict[str, Any]] = None) -> Iterator[None]:
    """Exclusive per-job lock; skip when force=True or guard disabled."""
    if force or not guard_enabled(settings):
        yield
        return

    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = _LOCK_DIR / f"{job}.lock"
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise JobBusyError(
            f"任务 {job} 正在运行（lockfile: {path}）。"
            " 若确需并行，请加 --force。"
        ) from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def check_duplicate_job(
    job: str,
    *,
    force: bool = False,
    require_feishu: bool = True,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Return skip reason if today's successful run already exists."""
    if force or not guard_enabled(settings):
        return None
    if job not in _DEDUP_JOBS:
        return None

    cfg = _guard_cfg(settings)
    if cfg.get("dedupe_jobs", True) is False:
        return None

    from agent_reach.daily_run.run_manifest import has_job_manifest_today

    if not has_job_manifest_today(job, require_feishu=require_feishu):
        return None

    labels = {
        "morning": "早盘",
        "close": "收盘复盘",
        "weekly": "周报",
        "forecast": "下周预测",
    }
    label = labels.get(job, job)
    return f"今日{label}已成功执行（manifest 去重）。补跑请加 --force"


def assert_harness_refine_allowed(
    *,
    force_review: bool = False,
    ignore_cooldown: bool = False,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    """Block manual Layer B refine during cooldown unless ignore_cooldown."""
    if ignore_cooldown:
        return
    cfg = _harness_cfg(settings)
    llm_cfg = dict(cfg.get("llm_refine") or {})
    if llm_cfg.get("enabled") is False:
        return

    from agent_reach.daily_run.harness import _within_llm_cooldown, load_harness

    state = load_harness()
    if _within_llm_cooldown(state, llm_cfg):
        hours = float(llm_cfg.get("cooldown_hours") or 24)
        msg = f"Harness LLM refine cooldown 生效（{hours:g}h 内已 refine）。"
        if force_review:
            msg += " 跳过 review 仍需等待 cooldown，或加 --ignore-cooldown。"
        raise HarnessCooldownError(msg)


def _harness_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    if settings is None:
        try:
            from agent_reach.daily_run.settings import load_settings

            settings = load_settings()
        except Exception:
            settings = {}
    return dict((settings or {}).get("harness") or {})
