# -*- coding: utf-8
"""Load daily_run_settings.json with optional user override."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "daily_run_settings.json"
_USER_PATH = Path.home() / ".agent-reach" / "daily_run_settings.json"

_settings_cache: dict[str, Any] = {"path": None, "mtime": None, "data": None}


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load settings; user override at ~/.agent-reach/daily_run_settings.json wins."""
    if path is not None:
        data = _read_json(path)
        validate_settings(data)
        return data

    active = _USER_PATH if _USER_PATH.exists() else _DEFAULT_PATH
    if not active.exists():
        raise FileNotFoundError(
            f"daily_run settings not found. Expected {_DEFAULT_PATH} or {_USER_PATH}"
        )

    mtime = active.stat().st_mtime
    if (
        _settings_cache["path"] == active
        and _settings_cache["mtime"] == mtime
        and _settings_cache["data"] is not None
    ):
        return deepcopy(_settings_cache["data"])

    data = _read_json(active)
    data = _merge_repo_defaults(data, active)
    validate_settings(data)
    _settings_cache["path"] = active
    _settings_cache["mtime"] = mtime
    _settings_cache["data"] = data
    return deepcopy(data)


def clear_settings_cache() -> None:
    """Invalidate cached settings (tests)."""
    _settings_cache["path"] = None
    _settings_cache["mtime"] = None
    _settings_cache["data"] = None


def validate_settings(data: dict[str, Any]) -> None:
    """Lightweight schema checks for daily_run_settings.json."""
    if not isinstance(data.get("mss_weights"), dict):
        raise ValueError("settings.mss_weights must be an object")
    thresholds = data.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("settings.thresholds must be an object")
    for key in ("macro_veto", "aggressive_entry", "max_snapshot_age_hours"):
        if key not in thresholds:
            raise ValueError(f"settings.thresholds missing {key}")

    audit = data.get("data_audit")
    if audit is not None and not isinstance(audit, dict):
        raise ValueError("settings.data_audit must be an object")

    report = data.get("report")
    if report is not None:
        if not isinstance(report, dict):
            raise ValueError("settings.report must be an object")
        interval = report.get("split_push_interval_seconds")
        if interval is not None and float(interval) < 0:
            raise ValueError("settings.report.split_push_interval_seconds must be >= 0")


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid settings file: {path}")
    return deepcopy(data)


def _merge_repo_defaults(data: dict[str, Any], active: Path) -> dict[str, Any]:
    """Fill missing top-level blocks from repo defaults (user file wins on overlap)."""
    if active == _DEFAULT_PATH or not _DEFAULT_PATH.exists():
        return data
    defaults = _read_json(_DEFAULT_PATH)
    merged = deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            block = deepcopy(merged[key])
            block.update(value)
            merged[key] = block
        else:
            merged[key] = deepcopy(value)
    return merged


def save_user_settings(data: dict[str, Any], *, path: Path | None = None) -> Path:
    """Persist daily-run settings to ~/.agent-reach/daily_run_settings.json."""
    target = path or _USER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    validate_settings(data)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    clear_settings_cache()
    return target


def user_settings_path() -> Path:
    return _USER_PATH
