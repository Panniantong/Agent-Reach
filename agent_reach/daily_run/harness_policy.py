# -*- coding: utf-8
"""Apply harness memory/policy/playbook entries to runtime trading settings."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code

_EVOLVED_THRESHOLD_KEYS: tuple[str, ...] = (
    "macro_veto",
    "aggressive_entry",
    "min_cash_ratio",
    "max_price_deviation_pct",
    "high_position_20d",
    "min_volume_ratio",
    "max_vwap_deviation_pct",
)

_EVOLVED_RUNTIME_KEYS: tuple[str, ...] = (
    "trade_min_scans",
    "trade_every_n_scans",
    "max_applied_trades_per_day",
    "max_trade_evaluations_per_symbol",
    "max_holdings",
    "max_total_symbols",
    "holding_lock_days",
    "stop_loss_ma20_pct",
    "friction_min_return_pct",
)

_EVOLVED_FORECAST_KEYS: tuple[str, ...] = (
    "base_spread",
    "vol_multiplier",
)

_EVOLVED_FLAT_KEYS: tuple[str, ...] = (
    _EVOLVED_THRESHOLD_KEYS + _EVOLVED_RUNTIME_KEYS + _EVOLVED_FORECAST_KEYS
)

_HARNESS_NEUTRAL: dict[str, float] = {
    "macro_veto": 40.0,
    "aggressive_entry": 50.0,
    "min_cash_ratio": 0.0,
    "max_price_deviation_pct": 0.08,
    "high_position_20d": 0.7,
    "min_volume_ratio": 1.0,
    "max_vwap_deviation_pct": 0.04,
}

_FIXED_FALLBACKS: dict[str, float] = {
    "macro_veto": 40.0,
    "aggressive_entry": 50.0,
    "min_cash_ratio": 0.4,
    "max_price_deviation_pct": 0.08,
    "high_position_20d": 0.7,
    "min_volume_ratio": 1.0,
    "max_vwap_deviation_pct": 0.04,
}

_RUNTIME_NEUTRAL: dict[str, float] = {
    "trade_min_scans": 3.0,
    "trade_every_n_scans": 2.0,
    "max_applied_trades_per_day": 5.0,
    "max_trade_evaluations_per_symbol": 8.0,
    "max_holdings": 10.0,
    "max_total_symbols": 15.0,
    "holding_lock_days": 1.0,
    "stop_loss_ma20_pct": 0.04,
    "friction_min_return_pct": 0.005,
}

_RUNTIME_FIXED: dict[str, float] = dict(_RUNTIME_NEUTRAL)

_FORECAST_NEUTRAL: dict[str, float] = {
    "base_spread": 8.0,
    "vol_multiplier": 6.0,
}

_FORECAST_FIXED: dict[str, float] = dict(_FORECAST_NEUTRAL)

_LOOKBACK_NEUTRAL: list[float] = [0.5, 0.3, 0.2]
_LOOKBACK_SCAN_SPARSE: list[float] = [0.6, 0.25, 0.15]
_LOOKBACK_OFFENSIVE: list[float] = [0.45, 0.35, 0.2]
_LOOKBACK_DEFENSIVE: list[float] = [0.55, 0.28, 0.17]

_EVOLVED_SYMBOL_SCORE_KEYS: tuple[str, ...] = (
    "base_mss",
    "change_pct_weight",
    "position_20d_weight",
    "kronos_bullish_mult",
    "kronos_bearish_mult",
    "symbol_bias_penalty",
    "symbol_bias_boost",
)

_SYMBOL_SCORE_NEUTRAL: dict[str, float] = {
    "base_mss": 50.0,
    "change_pct_weight": 0.5,
    "position_20d_weight": 10.0,
    "kronos_bullish_mult": 2.0,
    "kronos_bearish_mult": 1.5,
    "symbol_bias_penalty": 15.0,
    "symbol_bias_boost": 8.0,
}

_SYMBOL_BIAS_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

_SYMBOL_BIAS_NEGATIVE: tuple[str, ...] = (
    "深浮亏",
    "浮亏警示",
    "回避",
    "减仓",
    "禁止接飞刀",
    "止损",
    "接飞刀",
)

_SYMBOL_BIAS_POSITIVE: tuple[str, ...] = (
    "优先处置",
    "优先",
    "偏强",
    "进攻",
    "热点匹配",
)

_RUNTIME_SECTIONS: dict[str, str] = {
    "trade_min_scans": "schedule",
    "trade_every_n_scans": "schedule",
    "max_applied_trades_per_day": "schedule",
    "max_trade_evaluations_per_symbol": "schedule",
    "max_holdings": "portfolio",
    "max_total_symbols": "portfolio",
    "holding_lock_days": "trading",
    "stop_loss_ma20_pct": "trading",
    "friction_min_return_pct": "trading",
}

# Public catalog for config walkthrough / stale-key detection (harness evolution).
EVOLVED_CONFIG_KEYS_BY_SECTION: dict[str, tuple[str, ...]] = {
    "thresholds": _EVOLVED_THRESHOLD_KEYS,
    "schedule": (
        "trade_min_scans",
        "trade_every_n_scans",
        "max_applied_trades_per_day",
        "max_trade_evaluations_per_symbol",
    ),
    "portfolio": ("max_holdings", "max_total_symbols"),
    "trading": ("holding_lock_days", "stop_loss_ma20_pct", "friction_min_return_pct"),
    "mss_forecast": _EVOLVED_FORECAST_KEYS,
}
EVOLVED_TOP_LEVEL_KEYS: tuple[str, ...] = ("lookback_weights",)
EVOLVED_BACKTEST_KEYS: tuple[str, ...] = ("macro_veto", "aggressive_entry")

HARNESS_CONSUMER_HELPERS: dict[str, str] = {
    "macro_veto": "threshold_default(settings, 'macro_veto')",
    "aggressive_entry": "aggressive_entry_default(settings)",
    "min_cash_ratio": "min_cash_ratio_default(settings)",
    "max_price_deviation_pct": "threshold_default(settings, 'max_price_deviation_pct')",
    "high_position_20d": "threshold_default(settings, 'high_position_20d')",
    "min_volume_ratio": "threshold_default(settings, 'min_volume_ratio')",
    "max_vwap_deviation_pct": "threshold_default(settings, 'max_vwap_deviation_pct')",
    "trade_min_scans": "runtime_int_default(settings, 'schedule', 'trade_min_scans')",
    "trade_every_n_scans": "runtime_int_default(settings, 'schedule', 'trade_every_n_scans')",
    "max_applied_trades_per_day": (
        "runtime_int_default(settings, 'schedule', 'max_applied_trades_per_day')"
    ),
    "max_trade_evaluations_per_symbol": (
        "runtime_int_default(settings, 'schedule', 'max_trade_evaluations_per_symbol')"
    ),
    "max_holdings": "runtime_int_default(settings, 'portfolio', 'max_holdings')",
    "max_total_symbols": "runtime_int_default(settings, 'portfolio', 'max_total_symbols')",
    "holding_lock_days": "runtime_int_default(settings, 'trading', 'holding_lock_days')",
    "stop_loss_ma20_pct": "runtime_float_default(settings, 'trading', 'stop_loss_ma20_pct')",
    "friction_min_return_pct": "friction_min_return_default(settings)",
    "base_spread": "forecast_int_default(settings, 'base_spread')",
    "vol_multiplier": "forecast_int_default(settings, 'vol_multiplier')",
    "days_held": "effective_days_held(holding, settings=settings)",
    "lookback_weights": "lookback_weights_default(settings)",
}


def harness_evolution_mode(settings: dict[str, Any]) -> str:
    """Global harness vs fixed switch from settings."""
    harness = _harness_cfg(settings)
    return str(harness.get("threshold_evolution_mode") or "harness").strip().lower()


def list_static_config_pollution(settings: dict[str, Any]) -> list[str]:
    """Keys that should not live in JSON when harness evolution is active."""
    if harness_evolution_mode(settings) != "harness":
        return []
    found: list[str] = []
    for section, keys in EVOLVED_CONFIG_KEYS_BY_SECTION.items():
        block = settings.get(section) or {}
        for key in keys:
            if key in block:
                found.append(f"{section}.{key}")
    for key in EVOLVED_TOP_LEVEL_KEYS:
        if settings.get(key) is not None:
            found.append(key)
    backtest = settings.get("backtest") or {}
    for key in EVOLVED_BACKTEST_KEYS:
        if key in backtest:
            found.append(f"backtest.{key}")
    return found

_STRUCTURED_POLICY_THRESHOLDS: dict[str, dict[str, float]] = {
    "forecast_policy_macro_veto": {
        "macro_veto": 30.0,
        "min_cash_ratio": 0.5,
        "max_holdings": 5.0,
        "max_total_symbols": 10.0,
        "holding_lock_days": 2.0,
        "stop_loss_ma20_pct": 0.05,
    },
    "forecast_policy_deviation_threshold": {
        "max_price_deviation_pct": 0.08,
        "base_spread": 10.0,
        "vol_multiplier": 7.0,
    },
}

_MSS_WEIGHT_SCALE_KEYS: tuple[str, ...] = ("technical", "quant")
_MSS_WEIGHT_SCALE = 0.8

_APPLIED_CONFIG_RE = re.compile(
    r"(?:(?:thresholds|mss_forecast|trading)\.)?"
    r"(macro_veto|aggressive_entry|min_cash_ratio|max_price_deviation_pct|"
    r"high_position_20d|min_volume_ratio|max_vwap_deviation_pct|"
    r"trade_min_scans|trade_every_n_scans|max_applied_trades_per_day|"
    r"max_trade_evaluations_per_symbol|max_holdings|max_total_symbols|"
    r"holding_lock_days|stop_loss_ma20_pct|friction_min_return_pct|"
    r"base_spread|vol_multiplier)\s*[:=]\s*(\d+(?:\.\d+)?)",
    re.I,
)
_MSS_CAP_RE = re.compile(r"MSS\s*[<≤]\s*(\d+(?:\.\d+)?)", re.I)
_CASH_PCT_RE = re.compile(r"现金比例\s*[≥>]\s*(\d+(?:\.\d+)?)\s*%")
_DEVIATION_PCT_RE = re.compile(r"锚点阈值\s*(\d+(?:\.\d+)?)\s*%")
_KEY_VALUE_RE = re.compile(
    r"\b("
    r"macro_veto|aggressive_entry|min_cash_ratio|max_price_deviation_pct|"
    r"high_position_20d|min_volume_ratio|max_vwap_deviation_pct|"
    r"trade_min_scans|trade_every_n_scans|max_applied_trades_per_day|"
    r"max_trade_evaluations_per_symbol|max_holdings|max_total_symbols|"
    r"holding_lock_days|stop_loss_ma20_pct|friction_min_return_pct|"
    r"base_spread|vol_multiplier"
    r")\s*[=：]\s*(\d+(?:\.\d+)?)",
    re.I,
)
_FLAT_CONFIG_RE = re.compile(
    r"(?:(?:schedule|portfolio|trading|thresholds|mss_forecast)\.)?"
    r"(trade_min_scans|trade_every_n_scans|max_applied_trades_per_day|"
    r"max_trade_evaluations_per_symbol|max_holdings|max_total_symbols|"
    r"holding_lock_days|stop_loss_ma20_pct|friction_min_return_pct|"
    r"high_position_20d|min_volume_ratio|max_vwap_deviation_pct|"
    r"base_spread|vol_multiplier)\s*[:=]\s*(\d+(?:\.\d+)?)",
    re.I,
)
_STOP_LOSS_RE = re.compile(r"MA20[-−](\d+(?:\.\d+)?)\s*%")
_KRONOS_SYMBOL_RE = re.compile(
    r"([^\(（,、]+)?[\(（](\d{6})[\)）]\s*([+\-]?\d+(?:\.\d+)?)\s*%"
)

_MEMORY_ENTRY_NUDGES: tuple[tuple[str, dict[str, float]], ...] = (
    ("调低进攻阈值", {"aggressive_entry": -2.0}),
    ("缩窄仓位", {"aggressive_entry": -1.0}),
    ("MSS 预测偏离", {"aggressive_entry": -2.0}),
    ("盈亏目标奖励", {"aggressive_entry": 2.0}),
    ("盈亏目标未达", {"aggressive_entry": -2.0}),
    ("达进攻阈值未落账", {"aggressive_entry": -1.0}),
)

_MEMORY_CASH_NUDGES: tuple[tuple[str, float], ...] = (
    ("维持高现金", 0.5),
    ("禁止接飞刀", 0.5),
    ("取消一切买入", 0.5),
    ("降低现金", 0.25),
    ("宏观回暖", 0.25),
    ("进攻期", 0.2),
    ("放宽现金", 0.2),
)

_MEMORY_MSS_NUDGES: tuple[tuple[str, dict[str, float]], ...] = (
    ("进攻期", {"macro_veto": 38.0, "aggressive_entry": 52.0}),
    ("宏观回暖", {"macro_veto": 38.0, "aggressive_entry": 51.0}),
)

_MEMORY_RUNTIME_NUDGES: tuple[tuple[str, dict[str, float]], ...] = (
    ("缩窄仓位", {"max_holdings": 5.0, "max_total_symbols": 10.0}),
    ("扫描偏少", {"trade_min_scans": 2.0}),
    ("盘中扫描偏少", {"trade_min_scans": 2.0}),
    (
        "进攻期",
        {
            "trade_every_n_scans": 1.0,
            "holding_lock_days": 1.0,
            "stop_loss_ma20_pct": 0.03,
            "max_applied_trades_per_day": 6.0,
            "max_trade_evaluations_per_symbol": 10.0,
        },
    ),
    ("维持高现金", {"holding_lock_days": 2.0}),
    (
        "减少频繁调仓",
        {"friction_min_return_pct": 0.008, "max_applied_trades_per_day": 3.0},
    ),
    ("落账已达上限", {"max_applied_trades_per_day": 3.0}),
    ("评估已达上限", {"max_trade_evaluations_per_symbol": 10.0}),
    ("达进攻阈值未落账", {"trade_min_scans": 2.0}),
)

_MEMORY_FORECAST_NUDGES: tuple[tuple[str, dict[str, float]], ...] = (
    ("预测未命中", {"base_spread": 10.0, "vol_multiplier": 7.0}),
    ("增大 base_spread", {"base_spread": 10.0}),
    ("MSS 预测偏离", {"base_spread": 10.0, "vol_multiplier": 7.0}),
)

_MEMORY_TECHNICAL_NUDGES: tuple[tuple[str, dict[str, float]], ...] = (
    ("进攻期", {"high_position_20d": 0.75, "min_volume_ratio": 0.9, "max_vwap_deviation_pct": 0.05}),
    ("宏观回暖", {"high_position_20d": 0.75, "max_vwap_deviation_pct": 0.05, "friction_min_return_pct": 0.004}),
)

_CASH_SIGNAL_FLOORS: tuple[tuple[str, float], ...] = (
    ("defensive_trim", 0.5),
    ("deviation_active", 0.45),
    ("mss_forecast_miss", 0.35),
)

_DEVIATION_PHRASES: tuple[str, ...] = (
    "超过锚点阈值",
    "预测未命中",
    "MSS 预测偏离",
    "偏差：价格变动",
)

_MSS_MISS_PHRASES: tuple[str, ...] = (
    "MSS 预测偏离",
    "缩窄仓位",
)


def _harness_cfg(settings: dict[str, Any]) -> dict[str, Any]:
    return dict(settings.get("harness") or {})


def _overlay_enabled(settings: dict[str, Any]) -> bool:
    cfg = _harness_cfg(settings)
    if cfg.get("enabled") is False:
        return False
    return cfg.get("runtime_overlay", True) is not False


def _overlay_sources(settings: dict[str, Any]) -> set[str]:
    cfg = _harness_cfg(settings)
    raw = cfg.get("runtime_overlay_sources") or ["policy", "memory", "playbook"]
    if isinstance(raw, str):
        raw = [raw]
    return {str(x).strip().lower() for x in raw if str(x).strip()}


def threshold_mode(settings: dict[str, Any], key: str) -> str:
    """``harness`` = evolved at runtime; ``fixed`` = use config/default only."""
    harness = _harness_cfg(settings)
    per_key = harness.get("threshold_modes") or {}
    if key in per_key:
        mode = str(per_key[key]).strip().lower()
        if mode in ("harness", "fixed"):
            return mode
    legacy = harness.get(f"{key}_mode")
    if legacy is not None:
        mode = str(legacy).strip().lower()
        if mode in ("harness", "fixed"):
            return mode
    if str(harness.get("threshold_evolution_mode") or "harness").strip().lower() == "fixed":
        return "fixed"
    return "harness"


def min_cash_ratio_mode(settings: dict[str, Any]) -> str:
    return evolution_mode(settings, "min_cash_ratio")


def evolution_mode(settings: dict[str, Any], key: str) -> str:
    """Alias for ``threshold_mode`` — shared harness vs fixed evolution switch."""
    return threshold_mode(settings, key)


def flat_base(settings: dict[str, Any], key: str, config: dict[str, Any]) -> float:
    if key in _EVOLVED_THRESHOLD_KEYS:
        return threshold_base(settings, key, config)
    if key in _EVOLVED_FORECAST_KEYS:
        if evolution_mode(settings, key) == "fixed":
            block = settings.get("mss_forecast") or {}
            if key in block:
                return float(block[key])
            return float(_FORECAST_FIXED[key])
        return float(_FORECAST_NEUTRAL[key])
    if evolution_mode(settings, key) == "fixed":
        section = _RUNTIME_SECTIONS.get(key, "")
        block = settings.get(section) or {}
        if key in block:
            return float(block[key])
        return float(_RUNTIME_FIXED.get(key, 0.0))
    return float(_RUNTIME_NEUTRAL.get(key, 0.0))


def runtime_int_default(settings: dict[str, Any], section: str, key: str) -> int:
    block = settings.get(section) or {}
    if key in block:
        return int(block[key])
    return int(flat_base(settings, key, settings.get("thresholds") or {}))


def runtime_float_default(settings: dict[str, Any], section: str, key: str) -> float:
    block = settings.get(section) or {}
    if key in block:
        return float(block[key])
    return float(flat_base(settings, key, settings.get("thresholds") or {}))


def forecast_int_default(settings: dict[str, Any], key: str) -> int:
    block = settings.get("mss_forecast") or {}
    if key in block:
        return int(block[key])
    return int(flat_base(settings, key, settings.get("thresholds") or {}))


def friction_min_return_default(settings: dict[str, Any]) -> float:
    return runtime_float_default(settings, "trading", "friction_min_return_pct")


def resolve_harness_base_forecast(settings: dict[str, Any]) -> dict[str, float]:
    return {key: flat_base(settings, key, settings.get("thresholds") or {}) for key in _EVOLVED_FORECAST_KEYS}


def lookback_weights_default(settings: dict[str, Any]) -> list[float]:
    raw = settings.get("lookback_weights")
    if raw:
        return [float(w) for w in raw]
    return list(_LOOKBACK_NEUTRAL)


def resolve_harness_base_flat(settings: dict[str, Any], config_thresholds: dict[str, Any]) -> dict[str, float]:
    return {key: flat_base(settings, key, config_thresholds) for key in _EVOLVED_FLAT_KEYS}


def resolve_harness_base_lookback_weights(settings: dict[str, Any]) -> list[float]:
    if evolution_mode(settings, "lookback_weights") == "fixed":
        raw = settings.get("lookback_weights")
        if raw:
            return [float(w) for w in raw]
        return list(_LOOKBACK_NEUTRAL)
    return list(_LOOKBACK_NEUTRAL)


def threshold_base(settings: dict[str, Any], key: str, base_thresholds: dict[str, Any]) -> float:
    if threshold_mode(settings, key) == "fixed":
        return float(base_thresholds.get(key, _FIXED_FALLBACKS[key]))
    return float(_HARNESS_NEUTRAL[key])


def min_cash_ratio_base(settings: dict[str, Any], base_thresholds: dict[str, Any]) -> float:
    return threshold_base(settings, "min_cash_ratio", base_thresholds)


def threshold_default(settings: dict[str, Any], key: str) -> float:
    """Fallback for consumers reading ``thresholds`` before/without overlay."""
    thresholds = settings.get("thresholds") or {}
    if key in thresholds:
        return float(thresholds[key])
    return threshold_base(settings, key, thresholds)


def min_cash_ratio_default(settings: dict[str, Any]) -> float:
    return threshold_default(settings, "min_cash_ratio")


def aggressive_entry_default(settings: dict[str, Any]) -> float:
    return threshold_default(settings, "aggressive_entry")


def macro_veto_default(settings: dict[str, Any]) -> float:
    return threshold_default(settings, "macro_veto")


def resolve_harness_base_thresholds(
    settings: dict[str, Any],
    config_thresholds: dict[str, Any],
) -> dict[str, float]:
    """Pre-overlay bases used for harness transparency metadata."""
    return {
        key: threshold_base(settings, key, config_thresholds)
        for key in _EVOLVED_THRESHOLD_KEYS
    }


def _entry_sort_key(entry: Any) -> str:
    return str(getattr(entry, "updated_at", "") or getattr(entry, "created_at", "") or "")


def _clamp_thresholds(values: dict[str, float]) -> dict[str, float]:
    out = dict(values)
    if "macro_veto" in out:
        out["macro_veto"] = max(25.0, min(50.0, float(out["macro_veto"])))
    if "aggressive_entry" in out:
        out["aggressive_entry"] = max(40.0, min(60.0, float(out["aggressive_entry"])))
    if "min_cash_ratio" in out:
        out["min_cash_ratio"] = max(0.0, min(0.85, float(out["min_cash_ratio"])))
    if "max_price_deviation_pct" in out:
        pct = float(out["max_price_deviation_pct"])
        if pct > 1.0:
            pct /= 100.0
        out["max_price_deviation_pct"] = max(0.04, min(0.15, pct))
    if "high_position_20d" in out:
        out["high_position_20d"] = max(0.55, min(0.85, float(out["high_position_20d"])))
    if "min_volume_ratio" in out:
        out["min_volume_ratio"] = max(0.5, min(2.0, float(out["min_volume_ratio"])))
    if "max_vwap_deviation_pct" in out:
        pct = float(out["max_vwap_deviation_pct"])
        if pct > 1.0:
            pct /= 100.0
        out["max_vwap_deviation_pct"] = max(0.02, min(0.08, pct))
    macro = out.get("macro_veto")
    aggressive = out.get("aggressive_entry")
    if macro is not None and aggressive is not None and aggressive <= macro:
        out["aggressive_entry"] = macro + 2.0
    return out


def _clamp_flat_values(values: dict[str, float]) -> dict[str, float]:
    out = _clamp_thresholds(values)
    if "trade_min_scans" in out:
        out["trade_min_scans"] = float(max(2, min(5, int(out["trade_min_scans"]))))
    if "trade_every_n_scans" in out:
        out["trade_every_n_scans"] = float(max(1, min(3, int(out["trade_every_n_scans"]))))
    if "max_applied_trades_per_day" in out:
        out["max_applied_trades_per_day"] = float(max(2, min(8, int(out["max_applied_trades_per_day"]))))
    if "max_trade_evaluations_per_symbol" in out:
        out["max_trade_evaluations_per_symbol"] = float(
            max(5, min(12, int(out["max_trade_evaluations_per_symbol"])))
        )
    if "max_holdings" in out:
        out["max_holdings"] = float(max(3, min(12, int(out["max_holdings"]))))
    if "max_total_symbols" in out:
        out["max_total_symbols"] = float(max(5, min(20, int(out["max_total_symbols"]))))
    if "holding_lock_days" in out:
        out["holding_lock_days"] = float(max(1, min(5, int(out["holding_lock_days"]))))
    if "stop_loss_ma20_pct" in out:
        pct = float(out["stop_loss_ma20_pct"])
        if pct > 1.0:
            pct /= 100.0
        out["stop_loss_ma20_pct"] = max(0.03, min(0.08, pct))
    if "friction_min_return_pct" in out:
        pct = float(out["friction_min_return_pct"])
        if pct > 1.0:
            pct /= 100.0
        out["friction_min_return_pct"] = max(0.003, min(0.012, pct))
    if "base_spread" in out:
        out["base_spread"] = float(max(6.0, min(15.0, int(out["base_spread"]))))
    if "vol_multiplier" in out:
        out["vol_multiplier"] = float(max(4.0, min(10.0, int(out["vol_multiplier"]))))
    if "max_holdings" in out and "max_total_symbols" in out:
        if out["max_total_symbols"] < out["max_holdings"]:
            out["max_total_symbols"] = out["max_holdings"]
    return out


def _parse_text_overrides(text: str) -> dict[str, float]:
    overrides: dict[str, float] = {}
    blob = str(text or "")
    if not blob.strip():
        return overrides

    for match in _APPLIED_CONFIG_RE.finditer(blob):
        key = str(match.group(1)).lower()
        value = float(match.group(2))
        if key in (
            "max_price_deviation_pct",
            "stop_loss_ma20_pct",
            "max_vwap_deviation_pct",
            "friction_min_return_pct",
        ) and value > 1.0:
            value /= 100.0
        overrides[key] = value
    for match in _FLAT_CONFIG_RE.finditer(blob):
        key = str(match.group(1)).lower()
        value = float(match.group(2))
        if key in ("stop_loss_ma20_pct", "max_vwap_deviation_pct", "friction_min_return_pct") and value > 1.0:
            value /= 100.0
        overrides[key] = value
    for match in _KEY_VALUE_RE.finditer(blob):
        key = str(match.group(1)).lower()
        value = float(match.group(2))
        if key in (
            "max_price_deviation_pct",
            "stop_loss_ma20_pct",
            "max_vwap_deviation_pct",
            "friction_min_return_pct",
        ) and value > 1.0:
            value /= 100.0
        overrides[key] = value

    mss_cap = _MSS_CAP_RE.search(blob)
    if mss_cap:
        overrides["macro_veto"] = float(mss_cap.group(1))

    cash_pct = _CASH_PCT_RE.search(blob)
    if cash_pct:
        overrides["min_cash_ratio"] = float(cash_pct.group(1)) / 100.0

    deviation_pct = _DEVIATION_PCT_RE.search(blob)
    if deviation_pct:
        overrides["max_price_deviation_pct"] = float(deviation_pct.group(1)) / 100.0

    stop_loss = _STOP_LOSS_RE.search(blob)
    if stop_loss:
        overrides["stop_loss_ma20_pct"] = float(stop_loss.group(1)) / 100.0

    return overrides


def _renormalize_weights(weights: dict[str, Any]) -> dict[str, float]:
    total = sum(float(v) for v in weights.values())
    if total <= 0:
        return {k: float(v) for k, v in weights.items()}
    return {k: round(float(v) / total, 4) for k, v in weights.items()}


def _policy_overrides(state: Any, *, base: dict[str, float]) -> dict[str, float]:
    overrides = dict(base)
    policies = list((getattr(state, "entries", {}) or {}).get("policy", {}).values())
    policies.sort(key=_entry_sort_key)
    for entry in policies:
        entry_id = str(getattr(entry, "id", "") or "")
        structured = _STRUCTURED_POLICY_THRESHOLDS.get(entry_id)
        if structured:
            overrides.update(structured)
        content = f"{getattr(entry, 'title', '')}\n{getattr(entry, 'content', '')}"
        overrides.update(_parse_text_overrides(content))
    return overrides


def _memory_overrides(state: Any, *, base: dict[str, float]) -> dict[str, float]:
    overrides = dict(base)
    memories = list((getattr(state, "entries", {}) or {}).get("memory", {}).values())
    memories.sort(key=_entry_sort_key, reverse=True)

    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, ratio in _MEMORY_CASH_NUDGES:
            if phrase in blob:
                overrides["min_cash_ratio"] = float(ratio)
                break
        else:
            continue
        break

    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, values in _MEMORY_MSS_NUDGES:
            if phrase in blob:
                overrides.update(values)
                break
        else:
            continue
        break

    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, values in _MEMORY_RUNTIME_NUDGES:
            if phrase in blob:
                overrides.update(values)
                break
        else:
            continue
        break

    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, values in _MEMORY_FORECAST_NUDGES:
            if phrase in blob:
                overrides.update(values)
                break
        else:
            continue
        break

    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, values in _MEMORY_TECHNICAL_NUDGES:
            if phrase in blob:
                overrides.update(values)
                break
        else:
            continue
        break

    applied: set[str] = set()
    for entry in memories[:20]:
        blob = f"{getattr(entry, 'title', '')} {getattr(entry, 'content', '')}"
        for phrase, delta in _MEMORY_ENTRY_NUDGES:
            if phrase not in blob or phrase in applied:
                continue
            applied.add(phrase)
            for key, change in delta.items():
                default = _HARNESS_NEUTRAL.get(key, _RUNTIME_NEUTRAL.get(key, 0.0))
                current = float(overrides.get(key, default))
                overrides[key] = current + float(change)
    return overrides


def _apply_cash_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    if threshold_mode(settings, "min_cash_ratio") != "harness":
        return merged
    if float(merged.get("min_cash_ratio") or 0.0) > 0:
        return merged

    signals = resolve_harness_trade_signals(state, settings=settings)
    floor = 0.0
    for key, value in _CASH_SIGNAL_FLOORS:
        if signals.get(key):
            floor = max(floor, float(value))
    if floor > 0:
        merged["min_cash_ratio"] = floor
    return merged


def _apply_mss_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    signals = resolve_harness_trade_signals(state, settings=settings)
    if signals.get("defensive_trim"):
        if threshold_mode(settings, "macro_veto") == "harness":
            merged["macro_veto"] = min(float(merged.get("macro_veto", 40.0)), 30.0)
        if threshold_mode(settings, "aggressive_entry") == "harness":
            merged["aggressive_entry"] = min(float(merged.get("aggressive_entry", 50.0)), 45.0)
    elif signals.get("mss_forecast_miss"):
        if threshold_mode(settings, "aggressive_entry") == "harness":
            merged["aggressive_entry"] = min(float(merged.get("aggressive_entry", 50.0)), 48.0)
    return merged


def _apply_deviation_pct_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    if threshold_mode(settings, "max_price_deviation_pct") != "harness":
        return merged

    policies = (getattr(state, "entries", {}) or {}).get("policy", {})
    if "forecast_policy_deviation_threshold" in policies:
        return merged

    signals = resolve_harness_trade_signals(state, settings=settings)
    current = float(merged.get("max_price_deviation_pct", _HARNESS_NEUTRAL["max_price_deviation_pct"]))
    if signals.get("deviation_active"):
        merged["max_price_deviation_pct"] = min(current, 0.06)
    elif not signals.get("mss_forecast_miss"):
        merged["max_price_deviation_pct"] = max(current, 0.08)
    return merged


def _apply_runtime_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    signals = resolve_harness_trade_signals(state, settings=settings)
    if not signals.get("defensive_trim"):
        return merged

    if evolution_mode(settings, "max_holdings") == "harness":
        merged["max_holdings"] = min(float(merged.get("max_holdings", 10.0)), 5.0)
    if evolution_mode(settings, "max_total_symbols") == "harness":
        merged["max_total_symbols"] = min(float(merged.get("max_total_symbols", 15.0)), 10.0)
    if evolution_mode(settings, "stop_loss_ma20_pct") == "harness":
        merged["stop_loss_ma20_pct"] = max(float(merged.get("stop_loss_ma20_pct", 0.04)), 0.05)
    if evolution_mode(settings, "holding_lock_days") == "harness":
        merged["holding_lock_days"] = max(float(merged.get("holding_lock_days", 1.0)), 2.0)
    if evolution_mode(settings, "trade_min_scans") == "harness":
        merged["trade_min_scans"] = min(float(merged.get("trade_min_scans", 3.0)), 2.0)
    if evolution_mode(settings, "max_applied_trades_per_day") == "harness":
        merged["max_applied_trades_per_day"] = min(
            float(merged.get("max_applied_trades_per_day", 5.0)),
            3.0,
        )
    if evolution_mode(settings, "max_trade_evaluations_per_symbol") == "harness":
        merged["max_trade_evaluations_per_symbol"] = min(
            float(merged.get("max_trade_evaluations_per_symbol", 8.0)),
            6.0,
        )
    return merged


def _apply_technical_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    signals = resolve_harness_trade_signals(state, settings=settings)
    if not signals.get("defensive_trim"):
        return merged
    if evolution_mode(settings, "high_position_20d") == "harness":
        merged["high_position_20d"] = min(float(merged.get("high_position_20d", 0.7)), 0.65)
    if evolution_mode(settings, "min_volume_ratio") == "harness":
        merged["min_volume_ratio"] = max(float(merged.get("min_volume_ratio", 1.0)), 1.1)
    if evolution_mode(settings, "max_vwap_deviation_pct") == "harness":
        merged["max_vwap_deviation_pct"] = min(
            float(merged.get("max_vwap_deviation_pct", 0.04)),
            0.03,
        )
    if evolution_mode(settings, "friction_min_return_pct") == "harness":
        merged["friction_min_return_pct"] = max(
            float(merged.get("friction_min_return_pct", 0.005)),
            0.008,
        )
    return merged


def _apply_forecast_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    policies = (getattr(state, "entries", {}) or {}).get("policy", {})
    if "forecast_policy_deviation_threshold" in policies:
        return merged
    signals = resolve_harness_trade_signals(state, settings=settings)
    if not (signals.get("mss_forecast_miss") or signals.get("deviation_active")):
        return merged
    if evolution_mode(settings, "base_spread") == "harness":
        merged["base_spread"] = max(float(merged.get("base_spread", 8.0)), 10.0)
    if evolution_mode(settings, "vol_multiplier") == "harness":
        merged["vol_multiplier"] = max(float(merged.get("vol_multiplier", 6.0)), 7.0)
    return merged


def _blob_has_phrase(state: Any, phrase: str, *, settings: dict[str, Any]) -> bool:
    sources = _overlay_sources(settings)
    for kind in ("memory", "playbook"):
        for blob in _collect_text_blobs(state, sources=sources, kind=kind, settings=settings):
            if phrase in blob:
                return True
    return False


def resolve_harness_lookback_weights(
    state: Any,
    *,
    settings: dict[str, Any],
    flat: Optional[dict[str, float]] = None,
) -> list[float]:
    if evolution_mode(settings, "lookback_weights") == "fixed":
        raw = settings.get("lookback_weights")
        if raw:
            return [float(w) for w in raw]
        return list(_LOOKBACK_NEUTRAL)

    flat = flat or {}
    if _blob_has_phrase(state, "扫描偏少", settings=settings):
        return list(_LOOKBACK_SCAN_SPARSE)
    if float(flat.get("trade_min_scans", 3.0)) <= 2:
        return list(_LOOKBACK_SCAN_SPARSE)
    if _blob_has_phrase(state, "进攻期", settings=settings):
        return list(_LOOKBACK_OFFENSIVE)
    signals = resolve_harness_trade_signals(state, settings=settings)
    if signals.get("defensive_trim"):
        return list(_LOOKBACK_DEFENSIVE)
    return list(_LOOKBACK_NEUTRAL)


def _collect_text_blobs(
    state: Any,
    *,
    sources: set[str],
    kind: str,
    settings: Optional[dict[str, Any]] = None,
    bounded: bool = True,
) -> list[str]:
    if kind not in sources:
        return []
    entries = list((getattr(state, "entries", {}) or {}).get(kind, {}).values())
    entries.sort(key=_entry_sort_key, reverse=True)
    raw = [f"{getattr(e, 'title', '')} {getattr(e, 'content', '')}" for e in entries[:30]]
    if not bounded:
        return raw
    from agent_reach.daily_run.harness_apply_gate import bound_overlay_blobs, enforce_overlay_claims

    if not bounded:
        return raw
    bounded_raw, _bound_meta = bound_overlay_blobs(raw, settings=settings)
    adopted, _claim_meta = enforce_overlay_claims(bounded_raw, settings=settings)
    return adopted


def _has_deviation_signal(state: Any, *, sources: set[str], settings: Optional[dict[str, Any]] = None) -> bool:
    blobs = _collect_text_blobs(state, sources=sources, kind="memory", settings=settings)
    blobs += _collect_text_blobs(state, sources=sources, kind="policy", settings=settings)
    for blob in blobs:
        if any(p in blob for p in _DEVIATION_PHRASES):
            return True
        if "forecast_policy_mss_weight_update" in blob or "权重下调" in blob:
            return True
    policy = (getattr(state, "entries", {}) or {}).get("policy", {})
    return "forecast_policy_mss_weight_update" in policy


def _apply_pnl_target_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    signals = resolve_harness_trade_signals(state, settings=settings)
    if signals.get("pnl_target_hit"):
        if threshold_mode(settings, "aggressive_entry") == "harness":
            merged["aggressive_entry"] = max(float(merged.get("aggressive_entry", 50.0)), 52.0)
        if threshold_mode(settings, "macro_veto") == "harness":
            merged["macro_veto"] = max(float(merged.get("macro_veto", 40.0)), 38.0)
        if evolution_mode(settings, "trade_min_scans") == "harness":
            merged["trade_min_scans"] = min(float(merged.get("trade_min_scans", 3.0)), 2.0)
        if evolution_mode(settings, "max_applied_trades_per_day") == "harness":
            merged["max_applied_trades_per_day"] = max(
                float(merged.get("max_applied_trades_per_day", 5.0)),
                6.0,
            )
        if evolution_mode(settings, "max_trade_evaluations_per_symbol") == "harness":
            merged["max_trade_evaluations_per_symbol"] = max(
                float(merged.get("max_trade_evaluations_per_symbol", 8.0)),
                10.0,
            )
    elif signals.get("pnl_target_miss"):
        if threshold_mode(settings, "aggressive_entry") == "harness":
            merged["aggressive_entry"] = min(float(merged.get("aggressive_entry", 50.0)), 45.0)
        if threshold_mode(settings, "min_cash_ratio") == "harness":
            merged["min_cash_ratio"] = max(float(merged.get("min_cash_ratio", 0.0)), 0.45)
        if evolution_mode(settings, "max_holdings") == "harness":
            merged["max_holdings"] = min(float(merged.get("max_holdings", 10.0)), 5.0)
        if evolution_mode(settings, "max_applied_trades_per_day") == "harness":
            merged["max_applied_trades_per_day"] = min(
                float(merged.get("max_applied_trades_per_day", 5.0)),
                3.0,
            )
    return merged


def resolve_harness_flat_overrides(
    state: Any,
    base_thresholds: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    """Merge harness policy/memory into effective flat threshold + runtime values."""
    cfg = settings or {}
    base = resolve_harness_base_flat(cfg, base_thresholds)
    sources = _overlay_sources(cfg)
    merged = dict(base)
    if "policy" in sources:
        merged = _policy_overrides(state, base=merged)
    if "memory" in sources:
        merged = _memory_overrides(state, base=merged)
    merged = _apply_mss_signal_evolution(merged, state, settings=cfg)
    merged = _apply_deviation_pct_evolution(merged, state, settings=cfg)
    merged = _apply_runtime_signal_evolution(merged, state, settings=cfg)
    merged = _apply_technical_signal_evolution(merged, state, settings=cfg)
    merged = _apply_forecast_signal_evolution(merged, state, settings=cfg)
    merged = _apply_cash_signal_evolution(merged, state, settings=cfg)
    merged = _apply_pnl_target_signal_evolution(merged, state, settings=cfg)
    return _clamp_flat_values(merged)


def resolve_harness_threshold_overrides(
    state: Any,
    base_thresholds: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    flat = resolve_harness_flat_overrides(state, base_thresholds, settings=settings)
    return {key: flat[key] for key in _EVOLVED_THRESHOLD_KEYS if key in flat}


def resolve_harness_mss_weights(
    state: Any,
    base_weights: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    """Down-weight technical/quant when harness sees repeated forecast deviation."""
    weights = {k: float(v) for k, v in (base_weights or {}).items()}
    if not weights:
        return weights
    sources = _overlay_sources(settings or {})
    if not _has_deviation_signal(state, sources=sources, settings=settings):
        return weights

    scaled = dict(weights)
    for key in _MSS_WEIGHT_SCALE_KEYS:
        if key in scaled:
            scaled[key] = round(float(scaled[key]) * _MSS_WEIGHT_SCALE, 4)
    return _renormalize_weights(scaled)


def _parse_kronos_side(text: str, *, bullish: bool) -> dict[str, float]:
    out: dict[str, float] = {}
    marker = "偏强" if bullish else "偏弱"
    for line in str(text or "").splitlines():
        if marker not in line and "Kronos" not in line:
            continue
        if bullish and "偏弱" in line:
            continue
        if not bullish and "偏强" in line:
            continue
        for match in _KRONOS_SYMBOL_RE.finditer(line):
            code = _normalize_code(match.group(2))
            pct = float(match.group(3))
            if bullish and pct > 0:
                out[code] = max(out.get(code, pct), pct)
            elif not bullish and pct < 0:
                out[code] = min(out.get(code, pct), pct)
    return out


def resolve_harness_kronos_bias(
    state: Any,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Parse latest Kronos 偏强/偏弱 lists from harness playbook entries."""
    sources = _overlay_sources(settings or {})
    if "playbook" not in sources:
        return {}, {}

    bullish: dict[str, float] = {}
    bearish: dict[str, float] = {}
    playbooks = list((getattr(state, "entries", {}) or {}).get("playbook", {}).values())
    playbooks.sort(key=_entry_sort_key, reverse=True)
    for entry in playbooks[:20]:
        blob = f"{getattr(entry, 'title', '')}\n{getattr(entry, 'content', '')}"
        if "Kronos" not in blob and "偏强" not in blob and "偏弱" not in blob:
            continue
        for code, pct in _parse_kronos_side(blob, bullish=True).items():
            bullish[code] = max(bullish.get(code, pct), pct)
        for code, pct in _parse_kronos_side(blob, bullish=False).items():
            bearish[code] = min(bearish.get(code, pct), pct)
    return bullish, bearish


def resolve_harness_trade_signals(
    state: Any,
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Runtime trade flags derived from harness memory/policy."""
    sources = _overlay_sources(settings or {})
    cfg = settings or {}
    blobs = _collect_text_blobs(state, sources=sources, kind="memory", settings=cfg)
    blobs += _collect_text_blobs(state, sources=sources, kind="policy", settings=cfg)

    mss_miss = any(any(p in blob for p in _MSS_MISS_PHRASES) for blob in blobs)
    deviation = _has_deviation_signal(state, sources=sources, settings=cfg)
    bullish, bearish = resolve_harness_kronos_bias(state, settings=settings)
    pnl_hit = any("盈亏目标达成" in blob for blob in blobs)
    pnl_miss = any("盈亏目标未达" in blob for blob in blobs)

    return {
        "mss_forecast_miss": mss_miss,
        "defensive_trim": mss_miss or deviation or pnl_miss,
        "deviation_active": deviation,
        "kronos_bullish": bullish,
        "kronos_bearish": bearish,
        "pnl_target_hit": pnl_hit,
        "pnl_target_miss": pnl_miss,
    }


def harness_forecast_overlay_meta(
    base_forecast: dict[str, float],
    effective_forecast: dict[str, float],
) -> dict[str, Any]:
    changed: dict[str, dict[str, float]] = {}
    for key in _EVOLVED_FORECAST_KEYS:
        base_val = float(base_forecast.get(key, _FORECAST_NEUTRAL[key]))
        eff_val = float(effective_forecast.get(key, base_val))
        if abs(eff_val - base_val) >= 0.01:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def harness_runtime_overlay_meta(
    base_flat: dict[str, float],
    effective_flat: dict[str, float],
) -> dict[str, Any]:
    changed: dict[str, dict[str, float]] = {}
    for key in _EVOLVED_RUNTIME_KEYS:
        base_val = float(base_flat.get(key, _RUNTIME_NEUTRAL[key]))
        eff_val = float(effective_flat.get(key, base_val))
        if key == "stop_loss_ma20_pct":
            if abs(eff_val - base_val) >= 0.005:
                changed[key] = {"base": base_val, "effective": eff_val}
        elif abs(eff_val - base_val) >= 0.01:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def harness_lookback_overlay_meta(
    base_weights: list[float],
    effective_weights: list[float],
) -> dict[str, Any]:
    if [round(x, 4) for x in base_weights] == [round(x, 4) for x in effective_weights]:
        return {}
    return {"lookback_weights": {"base": base_weights, "effective": effective_weights}}


def harness_threshold_overlay_meta(
    base_thresholds: dict[str, float],
    effective_thresholds: dict[str, float],
) -> dict[str, Any]:
    """Return changed keys for logging / decision transparency."""
    changed: dict[str, dict[str, float]] = {}
    for key in _EVOLVED_THRESHOLD_KEYS:
        base_val = float(base_thresholds.get(key, _HARNESS_NEUTRAL.get(key, 0.0)))
        eff_val = float(effective_thresholds.get(key, base_val))
        if key in (
            "max_price_deviation_pct",
            "max_vwap_deviation_pct",
            "high_position_20d",
        ):
            if abs(eff_val - base_val) >= 0.005:
                changed[key] = {"base": base_val, "effective": eff_val}
        elif abs(eff_val - base_val) >= 0.01:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def harness_mss_weights_overlay_meta(
    base_weights: dict[str, Any],
    effective_weights: dict[str, float],
) -> dict[str, Any]:
    changed: dict[str, dict[str, float]] = {}
    for key in set(base_weights) | set(effective_weights):
        base_val = float(base_weights.get(key, 0))
        eff_val = float(effective_weights.get(key, base_val))
        if abs(eff_val - base_val) >= 0.0001:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def apply_harness_policy_overlay(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings copy with harness-derived runtime overlays applied."""
    if not _overlay_enabled(settings):
        return deepcopy(settings)

    from agent_reach.daily_run.harness import load_harness

    cfg = deepcopy(settings)
    state = load_harness()
    harness_meta: dict[str, Any] = dict(cfg.get("harness_runtime") or {})

    thresholds = dict(cfg.get("thresholds") or {})
    base_flat = resolve_harness_base_flat(cfg, thresholds)
    effective_flat = resolve_harness_flat_overrides(state, thresholds, settings=cfg)

    effective_thresholds = {key: effective_flat[key] for key in _EVOLVED_THRESHOLD_KEYS}
    thresholds.update(effective_thresholds)
    cfg["thresholds"] = thresholds
    threshold_meta = harness_threshold_overlay_meta(
        {key: base_flat[key] for key in _EVOLVED_THRESHOLD_KEYS},
        effective_thresholds,
    )
    if threshold_meta:
        harness_meta["threshold_overlay"] = threshold_meta

    runtime_meta = harness_runtime_overlay_meta(base_flat, effective_flat)
    if runtime_meta:
        harness_meta["runtime_overlay"] = runtime_meta

    schedule = dict(cfg.get("schedule") or {})
    schedule["trade_min_scans"] = int(effective_flat["trade_min_scans"])
    schedule["trade_every_n_scans"] = int(effective_flat["trade_every_n_scans"])
    schedule["max_applied_trades_per_day"] = int(effective_flat["max_applied_trades_per_day"])
    schedule["max_trade_evaluations_per_symbol"] = int(
        effective_flat["max_trade_evaluations_per_symbol"]
    )
    cfg["schedule"] = schedule

    portfolio = dict(cfg.get("portfolio") or {})
    portfolio["max_holdings"] = int(effective_flat["max_holdings"])
    portfolio["max_total_symbols"] = int(effective_flat["max_total_symbols"])
    cfg["portfolio"] = portfolio

    trading = dict(cfg.get("trading") or {})
    trading["holding_lock_days"] = int(effective_flat["holding_lock_days"])
    trading["stop_loss_ma20_pct"] = float(effective_flat["stop_loss_ma20_pct"])
    trading["friction_min_return_pct"] = float(effective_flat["friction_min_return_pct"])
    cfg["trading"] = trading

    forecast = dict(cfg.get("mss_forecast") or {})
    forecast["base_spread"] = int(effective_flat["base_spread"])
    forecast["vol_multiplier"] = int(effective_flat["vol_multiplier"])
    cfg["mss_forecast"] = forecast
    forecast_meta = harness_forecast_overlay_meta(
        {key: base_flat[key] for key in _EVOLVED_FORECAST_KEYS},
        {key: effective_flat[key] for key in _EVOLVED_FORECAST_KEYS},
    )
    if forecast_meta:
        harness_meta["forecast_overlay"] = forecast_meta

    base_lookback = resolve_harness_base_lookback_weights(cfg)
    effective_lookback = resolve_harness_lookback_weights(state, settings=cfg, flat=effective_flat)
    cfg["lookback_weights"] = effective_lookback
    lookback_meta = harness_lookback_overlay_meta(base_lookback, effective_lookback)
    if lookback_meta:
        harness_meta["lookback_overlay"] = lookback_meta

    base_weights = dict(cfg.get("mss_weights") or {})
    if base_weights:
        effective_weights = resolve_harness_mss_weights(state, base_weights, settings=cfg)
        cfg["mss_weights"] = effective_weights
        weight_meta = harness_mss_weights_overlay_meta(base_weights, effective_weights)
        if weight_meta:
            harness_meta["mss_weights_overlay"] = weight_meta

    trade_signals = resolve_harness_trade_signals(state, settings=cfg)
    if trade_signals.get("kronos_bullish"):
        harness_meta["kronos_bullish"] = trade_signals["kronos_bullish"]
    if trade_signals.get("kronos_bearish"):
        harness_meta["kronos_bearish"] = trade_signals["kronos_bearish"]
    base_score_weights = resolve_harness_base_symbol_score_weights(cfg)
    effective_score_weights = resolve_harness_symbol_score_weights(state, settings=cfg)
    harness_meta["symbol_score_weights"] = effective_score_weights
    score_weight_meta = harness_symbol_score_overlay_meta(base_score_weights, effective_score_weights)
    if score_weight_meta:
        harness_meta["symbol_score_overlay"] = score_weight_meta
    symbol_bias = resolve_harness_symbol_bias(state, settings=cfg, weights=effective_score_weights)
    if symbol_bias:
        harness_meta["symbol_bias"] = symbol_bias
    harness_meta["trade_signals"] = {
        k: trade_signals[k]
        for k in (
            "mss_forecast_miss",
            "defensive_trim",
            "deviation_active",
            "pnl_target_hit",
            "pnl_target_miss",
        )
    }

    try:
        from agent_reach.daily_run.harness_apply_gate import build_overlay_injection_audit

        injection_audit = build_overlay_injection_audit(state, settings=cfg)
        if injection_audit.get("kept_count") or injection_audit.get("ignored_count"):
            harness_meta["injection_gate"] = injection_audit
    except Exception:
        pass

    if harness_meta:
        try:
            from agent_reach.daily_run.harness_git import detect_git_branch

            harness_meta["git_branch"] = detect_git_branch()
        except Exception:
            pass
        cfg["harness_runtime"] = harness_meta
    return cfg


def symbol_score_weight_base(settings: dict[str, Any], key: str) -> float:
    if evolution_mode(settings, key) == "fixed":
        block = settings.get("symbol_score") or {}
        if key in block:
            return float(block[key])
    return float(_SYMBOL_SCORE_NEUTRAL.get(key, 0.0))


def resolve_harness_base_symbol_score_weights(settings: dict[str, Any]) -> dict[str, float]:
    return {key: symbol_score_weight_base(settings, key) for key in _EVOLVED_SYMBOL_SCORE_KEYS}


def _apply_symbol_score_signal_evolution(
    merged: dict[str, float],
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    signals = resolve_harness_trade_signals(state, settings=settings)
    if signals.get("defensive_trim"):
        if evolution_mode(settings, "change_pct_weight") == "harness":
            merged["change_pct_weight"] = float(merged.get("change_pct_weight", 0.5)) * 0.5
        if evolution_mode(settings, "position_20d_weight") == "harness":
            merged["position_20d_weight"] = float(merged.get("position_20d_weight", 10.0)) * 1.25
        if evolution_mode(settings, "symbol_bias_penalty") == "harness":
            merged["symbol_bias_penalty"] = max(float(merged.get("symbol_bias_penalty", 15.0)), 20.0)
    elif signals.get("pnl_target_hit"):
        if evolution_mode(settings, "change_pct_weight") == "harness":
            merged["change_pct_weight"] = float(merged.get("change_pct_weight", 0.5)) * 1.2
    if _blob_has_phrase(state, "进攻期", settings=settings):
        if evolution_mode(settings, "change_pct_weight") == "harness":
            merged["change_pct_weight"] = float(merged.get("change_pct_weight", 0.5)) * 1.3
    if signals.get("mss_forecast_miss") and not signals.get("defensive_trim"):
        if evolution_mode(settings, "change_pct_weight") == "harness":
            merged["change_pct_weight"] = float(merged.get("change_pct_weight", 0.5)) * 0.75
    return merged


def resolve_harness_symbol_score_weights(
    state: Any,
    *,
    settings: dict[str, Any],
) -> dict[str, float]:
    merged = resolve_harness_base_symbol_score_weights(settings)
    if not _overlay_enabled(settings):
        return merged
    return _apply_symbol_score_signal_evolution(merged, state, settings=settings)


def resolve_harness_symbol_bias(
    state: Any,
    *,
    settings: dict[str, Any],
    weights: Optional[dict[str, float]] = None,
) -> dict[str, float]:
    """Per-symbol score delta from harness memory/policy/playbook mentions."""
    if not _overlay_enabled(settings):
        return {}
    weights = weights or resolve_harness_base_symbol_score_weights(settings)
    penalty = float(weights.get("symbol_bias_penalty", 15.0))
    boost = float(weights.get("symbol_bias_boost", 8.0))
    sources = _overlay_sources(settings)
    bias: dict[str, float] = {}
    for kind in ("policy", "memory", "playbook"):
        for blob in _collect_text_blobs(state, sources=sources, kind=kind, settings=settings):
            codes = {_normalize_code(c) for c in _SYMBOL_BIAS_CODE_RE.findall(blob)}
            if not codes:
                continue
            delta = 0.0
            if any(p in blob for p in _SYMBOL_BIAS_NEGATIVE):
                delta -= penalty
            if any(p in blob for p in _SYMBOL_BIAS_POSITIVE):
                delta += boost
            if delta == 0.0:
                continue
            for code in codes:
                if code:
                    bias[code] = round(bias.get(code, 0.0) + delta, 2)
    return bias


def harness_symbol_score_overlay_meta(
    base_weights: dict[str, float],
    effective_weights: dict[str, float],
) -> dict[str, Any]:
    changed: dict[str, dict[str, float]] = {}
    for key in _EVOLVED_SYMBOL_SCORE_KEYS:
        base_val = float(base_weights.get(key, _SYMBOL_SCORE_NEUTRAL.get(key, 0.0)))
        eff_val = float(effective_weights.get(key, base_val))
        if abs(eff_val - base_val) >= 0.01:
            changed[key] = {"base": base_val, "effective": eff_val}
    return changed


def _symbol_score_weights(settings: dict[str, Any]) -> dict[str, float]:
    runtime = settings.get("harness_runtime") or {}
    weights = runtime.get("symbol_score_weights")
    if weights:
        return dict(weights)
    if _overlay_enabled(settings):
        from agent_reach.daily_run.harness import load_harness

        return resolve_harness_symbol_score_weights(load_harness(), settings=settings)
    return dict(_SYMBOL_SCORE_NEUTRAL)


def _kronos_score_delta(code: str, settings: dict[str, Any], weights: dict[str, float]) -> float:
    runtime = settings.get("harness_runtime") or {}
    norm = _normalize_code(code)
    if not norm:
        return 0.0
    bullish = runtime.get("kronos_bullish") or {}
    bearish = runtime.get("kronos_bearish") or {}
    b_mult = float(weights.get("kronos_bullish_mult", 2.0))
    s_mult = float(weights.get("kronos_bearish_mult", 1.5))
    boost = 0.0
    if norm in bullish:
        boost += min(abs(float(bullish[norm])) * b_mult, 12.0)
    if norm in bearish:
        boost -= min(abs(float(bearish[norm])) * s_mult, 10.0)
    return boost


def harness_symbol_score(
    row: dict[str, Any],
    settings: dict[str, Any],
    *,
    decision: Any = None,
    base_mss: Optional[float] = None,
) -> float:
    """Rank score for buy/watchlist selection — weights and bias from harness evolution."""
    weights = _symbol_score_weights(settings)
    score: Optional[float] = None
    if base_mss is not None:
        score = float(base_mss)
    elif row.get("mss_final") is not None:
        score = float(row["mss_final"])
    elif decision is not None:
        lb = getattr(decision, "lookback_mss", None)
        if lb is None and isinstance(decision, dict):
            lb = decision.get("lookback_mss")
        if lb is not None:
            score = float(lb)
    if score is None:
        score = float(weights.get("base_mss", 50.0))

    chg = row.get("change_pct")
    if chg is not None:
        score += float(chg) * float(weights.get("change_pct_weight", 0.5))

    pos = row.get("position_20d")
    if pos is not None:
        score += (0.5 - float(pos)) * float(weights.get("position_20d_weight", 10.0))

    code = _normalize_code(str(row.get("code", "")))
    score += _kronos_score_delta(code, settings, weights)

    runtime = settings.get("harness_runtime") or {}
    bias_map = runtime.get("symbol_bias")
    if bias_map is None and _overlay_enabled(settings):
        from agent_reach.daily_run.harness import load_harness

        bias_map = resolve_harness_symbol_bias(load_harness(), settings=settings, weights=weights)
    if code and bias_map and code in bias_map:
        score += float(bias_map[code])

    return score


def kronos_score_adjustment(code: str, settings: dict[str, Any]) -> float:
    """Score delta for watchlist ranking from harness Kronos bias."""
    return _kronos_score_delta(code, settings, _symbol_score_weights(settings))
