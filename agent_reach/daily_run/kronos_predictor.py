# -*- coding: utf-8
"""Kronos K-line path prediction (FaceCat-Kronos / Tsinghua Kronos)."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.akshare_adapter import AKShareError, normalize_symbol


class KronosError(RuntimeError):
    """Kronos prediction failed or dependencies missing."""


_PREDICTOR_CACHE: dict[str, Any] = {}


def kronos_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return dict((settings or {}).get("kronos") or {})


def is_kronos_enabled(settings: Optional[dict[str, Any]] = None) -> bool:
    return bool(kronos_cfg(settings).get("enabled", False))


def is_kronos_runtime_available() -> tuple[bool, str]:
    try:
        import pandas  # noqa: F401
        import torch  # noqa: F401
        from huggingface_hub import PyTorchModelHubMixin  # noqa: F401

        return True, "ok"
    except ImportError as exc:
        return False, str(exc)


def resolve_kronos_repo_path(settings: Optional[dict[str, Any]] = None) -> Optional[Path]:
    cfg = kronos_cfg(settings)
    candidates: list[Path] = []
    for raw in (cfg.get("repo_path"), os.environ.get("FACECAT_KRONOS_PATH")):
        if raw:
            candidates.append(Path(str(raw)).expanduser())
    candidates.append(Path.home() / ".agent-reach" / "vendor" / "FaceCat-Kronos")
    candidates.append(Path("/tmp/FaceCat-Kronos"))

    for path in candidates:
        if (path / "model" / "kronos.py").exists():
            return path
    return None


def _import_kronos_classes(repo_path: Path) -> tuple[Any, Any, Any]:
    root = str(repo_path.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from model import Kronos, KronosPredictor, KronosTokenizer  # type: ignore

    return Kronos, KronosTokenizer, KronosPredictor


def _resolve_device(cfg: dict[str, Any]) -> str:
    forced = cfg.get("device")
    if forced:
        return str(forced)
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _is_local_model_path(model_id: str) -> bool:
    path = Path(model_id).expanduser()
    return path.exists() and path.is_dir()


def _load_pretrained(model_cls: Any, model_id: str, *, settings: Optional[dict[str, Any]] = None) -> Any:
    cfg = kronos_cfg(settings)
    resolved = str(Path(model_id).expanduser()) if _is_local_model_path(model_id) else model_id
    kwargs: dict[str, Any] = {}
    if _is_local_model_path(model_id) or cfg.get("local_files_only", False):
        kwargs["local_files_only"] = True
    return model_cls.from_pretrained(resolved, **kwargs)


def get_kronos_predictor(settings: Optional[dict[str, Any]] = None) -> Any:
    """Lazy-load KronosPredictor singleton (per process)."""
    cfg = kronos_cfg(settings)
    cache_key = "|".join(
        [
            str(cfg.get("tokenizer_model", "NeoQuasar/Kronos-Tokenizer-base")),
            str(cfg.get("predictor_model", "NeoQuasar/Kronos-small")),
            str(cfg.get("device") or "auto"),
            str(resolve_kronos_repo_path(settings)),
        ]
    )
    if cache_key in _PREDICTOR_CACHE:
        return _PREDICTOR_CACHE[cache_key]

    ok, reason = is_kronos_runtime_available()
    if not ok:
        raise KronosError(f"Kronos 依赖未安装：{reason}（pip install 'agent-reach[daily-run-kronos]'）")

    repo = resolve_kronos_repo_path(settings)
    if repo is None:
        raise KronosError(
            "未找到 FaceCat-Kronos 仓库。设置 kronos.repo_path 或克隆到 "
            "~/.agent-reach/vendor/FaceCat-Kronos"
        )

    Kronos, KronosTokenizer, KronosPredictor = _import_kronos_classes(repo)
    device = _resolve_device(cfg)
    tokenizer_id = str(cfg.get("tokenizer_model", "NeoQuasar/Kronos-Tokenizer-base"))
    model_id = str(cfg.get("predictor_model", "NeoQuasar/Kronos-small"))
    max_context = int(cfg.get("max_context", 512))
    clip = float(cfg.get("clip", 5.0))

    tokenizer = _load_pretrained(KronosTokenizer, tokenizer_id, settings=settings)
    model = _load_pretrained(Kronos, model_id, settings=settings)
    predictor = KronosPredictor(model, tokenizer, device=device, max_context=max_context, clip=clip)
    _PREDICTOR_CACHE[cache_key] = predictor
    return predictor


def fetch_ohlcv_history(
    code: str,
    *,
    lookback: int = 90,
    adjust: str = "qfq",
    settings: Optional[dict[str, Any]] = None,
) -> Any:
    """Daily OHLCV DataFrame for Kronos (columns: open/high/low/close/volume/amount/timestamps)."""
    import pandas as pd

    from agent_reach.daily_run.akshare_adapter import _import_akshare

    ak_cfg = dict((settings or {}).get("akshare") or {})
    adj = adjust or str(ak_cfg.get("adjust", "qfq"))
    symbol, _market = normalize_symbol(code)
    ak = _import_akshare()
    hist = None
    try:
        hist = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust=adj)
    except Exception:
        market = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
        hist = ak.stock_zh_a_hist_tx(symbol=f"{market}{symbol}", adjust=adj)

    if hist is None or len(hist) < 10:
        raise AKShareError(f"历史 K 线不足：{symbol}")

    hist = hist.tail(max(lookback, 10)).copy()
    # East Money vs Tencent column names
    if "日期" in hist.columns:
        date_col = "日期"
        col_map = {
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
        }
    else:
        date_col = "date"
        col_map = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        }

    df = pd.DataFrame(
        {
            "open": hist[col_map["open"]].astype(float),
            "high": hist[col_map["high"]].astype(float),
            "low": hist[col_map["low"]].astype(float),
            "close": hist[col_map["close"]].astype(float),
            "volume": (
                hist[col_map["volume"]].astype(float)
                if col_map["volume"] in hist.columns
                else hist[col_map["amount"]].astype(float) / hist[col_map["close"]].astype(float).clip(lower=0.01)
            ),
            "amount": hist[col_map["amount"]].astype(float),
        }
    )
    df["timestamps"] = pd.to_datetime(hist[date_col])
    df.reset_index(drop=True, inplace=True)
    return df


def _direction_from_change(chg: float) -> str:
    if chg > 0.3:
        return "up"
    if chg < -0.3:
        return "down"
    return "flat"


def _direction_arrow(direction: str) -> str:
    return {"up": "↑", "down": "↓", "flat": "→"}.get(str(direction or ""), "→")


def resolve_kronos_trading_days(
    count: int,
    *,
    settings: Optional[dict[str, Any]] = None,
    as_of: Optional[date] = None,
) -> list[date]:
    """Next ``count`` A-share trading days after ``as_of`` (skips weekends/holidays)."""
    from agent_reach.daily_run.trade_calendar import next_trading_day, today_shanghai

    cfg = kronos_cfg(settings)
    if cfg.get("use_trade_calendar", True) is False:
        base = as_of or today_shanghai()
        return [base + timedelta(days=i) for i in range(1, max(count, 1) + 1)]

    cursor = as_of or today_shanghai()
    days: list[date] = []
    while len(days) < max(count, 1):
        cursor = next_trading_day(cursor, settings=settings)
        days.append(cursor)
    return days


def _confidence_band_from_prediction(
    pred_df: Any,
    *,
    anchor: float,
    daily_changes: list[float],
    settings: Optional[dict[str, Any]] = None,
) -> tuple[list[float], str]:
    cfg = kronos_cfg(settings)
    if cfg.get("dispersion_from_ohlc", True) is not False and anchor:
        try:
            last_low = float(pred_df["low"].astype(float).iloc[-1])
            last_high = float(pred_df["high"].astype(float).iloc[-1])
            cum_lo = (last_low - anchor) / anchor * 100
            cum_hi = (last_high - anchor) / anchor * 100
            lo, hi = sorted((cum_lo, cum_hi))
            return [round(lo, 2), round(hi, 2)], "ohlc_cumulative"
        except (KeyError, TypeError, ValueError, IndexError):
            pass
    lo = min(daily_changes) if daily_changes else 0.0
    hi = max(daily_changes) if daily_changes else 0.0
    return [round(lo, 2), round(hi, 2)], "daily_change"


def render_kronos_path_markdown(
    kronos: dict[str, Any],
    *,
    max_days: int = 5,
) -> str:
    """Compact virtual-K summary for Feishu cards (direction arrows + OHLC)."""
    if not kronos or not kronos.get("available"):
        return ""
    dir_cn = {"up": "↑看涨", "down": "↓看跌", "flat": "→震荡"}
    lines: list[str] = []
    days = kronos.get("days") or {}
    spark: list[str] = []
    for ds in sorted(days.keys())[:max_days]:
        day = days[ds]
        arrow = _direction_arrow(day.get("direction"))
        if all(day.get(k) is not None for k in ("open", "high", "low", "close")):
            spark.append(
                f"{ds[5:]} {arrow} "
                f"O{float(day['open']):.1f}/H{float(day['high']):.1f}/"
                f"L{float(day['low']):.1f}/C{float(day['close']):.1f}"
            )
        else:
            spark.append(f"{ds[5:]} {arrow} {float(day.get('change_pct') or 0):+.1f}%")
    if spark:
        lines.append("**Kronos 虚 K 路径：** " + " · ".join(spark))
    cum = kronos.get("cum_change_pct")
    band = kronos.get("confidence_band") or []
    dir_nd = kronos.get("direction_nd", "flat")
    band_kind = kronos.get("band_kind") or "daily_change"
    band_s = f"[{band[0]:+.1f}%, {band[1]:+.1f}%]" if len(band) == 2 else ""
    lines.append(
        f"_{dir_cn.get(dir_nd, '→震荡')} 累计 {float(cum or 0):+.1f}% {band_s} "
        f"(sample={kronos.get('sample_count', 1)}, band={band_kind})_"
    )
    return "\n".join(lines)


def _future_timestamps(trading_days: list[date]) -> Any:
    import pandas as pd

    return pd.Series(
        [datetime(d.year, d.month, d.day, 15, 0, 0) for d in trading_days],
        dtype="datetime64[ns]",
    )


def kronos_cache_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "cache" / "kronos"


def _kronos_cache_path(code: str, trading_days: list[date]) -> Path:
    from agent_reach.daily_run.trade_calendar import today_shanghai

    sym, _ = normalize_symbol(code)
    day_key = today_shanghai().isoformat()
    span_key = f"{trading_days[0].isoformat()}_{trading_days[-1].isoformat()}_{len(trading_days)}"
    return kronos_cache_dir() / f"{day_key}_{sym}_{span_key}.json"


def load_kronos_daily_cache(
    code: str,
    trading_days: list[date],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    cfg = kronos_cfg(settings)
    ttl = int(cfg.get("daily_cache_ttl_seconds", 86400))
    path = _kronos_cache_path(code, trading_days)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - float(data.get("ts") or 0) > ttl:
        return None
    result = data.get("result")
    return result if isinstance(result, dict) else None


def save_kronos_daily_cache(
    code: str,
    trading_days: list[date],
    result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Path:
    path = _kronos_cache_path(code, trading_days)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": time.time(), "result": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def predict_from_ohlcv_frames(
    x_df: Any,
    x_timestamp: Any,
    trading_days: list[date],
    *,
    base_price: Optional[float] = None,
    settings: Optional[dict[str, Any]] = None,
    code: str = "",
) -> Optional[dict[str, Any]]:
    """Run Kronos on pre-sliced OHLCV frames (used by live forecast and hold-out backtest)."""
    cfg = kronos_cfg(settings)
    if not trading_days:
        return None

    pred_window = int(cfg.get("predict_window", 10))
    pred_len = min(len(trading_days), pred_window)
    trading_days = trading_days[:pred_len]
    if len(x_df) < min(int(cfg.get("lookback_window", 90)) // 2, 30):
        return None

    try:
        y_timestamp = _future_timestamps(trading_days)
        predictor = get_kronos_predictor(settings)
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=float(cfg.get("inference_T", 0.6)),
            top_p=float(cfg.get("inference_top_p", 0.9)),
            top_k=int(cfg.get("inference_top_k", 0)),
            sample_count=int(cfg.get("inference_sample_count", 5)),
            verbose=bool(cfg.get("verbose", False)),
        )

        anchor = float(base_price if base_price is not None else x_df["close"].iloc[-1])
        days: dict[str, Any] = {}
        closes = pred_df["close"].astype(float).tolist()
        prev = anchor
        changes: list[float] = []
        for i, day in enumerate(trading_days):
            close_px = float(closes[i])
            chg_pct = (close_px - prev) / prev * 100 if prev else 0.0
            changes.append(chg_pct)
            day_payload: dict[str, Any] = {
                "close": round(close_px, 3),
                "change_pct": round(chg_pct, 2),
                "direction": _direction_from_change(chg_pct),
            }
            for col in ("open", "high", "low", "volume", "amount"):
                if col in pred_df.columns:
                    val = float(pred_df[col].iloc[i])
                    day_payload[col] = round(val, 3 if col not in {"volume", "amount"} else 0)
            days[day.isoformat()] = day_payload
            prev = close_px

        cum = (closes[-1] - anchor) / anchor * 100 if anchor else 0.0
        band, band_kind = _confidence_band_from_prediction(
            pred_df,
            anchor=anchor,
            daily_changes=changes,
            settings=settings,
        )
        sym = normalize_symbol(code)[0] if code else ""
        return {
            "available": True,
            "backend": str(cfg.get("predictor_model", "NeoQuasar/Kronos-small")),
            "code": sym,
            "lookback_used": len(x_df),
            "predict_window": pred_len,
            "direction_nd": _direction_from_change(cum),
            "cum_change_pct": round(cum, 2),
            "confidence_band": band,
            "band_kind": band_kind,
            "sample_count": int(cfg.get("inference_sample_count", 5)),
            "days": days,
        }
    except (KronosError, OSError, ValueError, RuntimeError) as exc:
        if cfg.get("log_errors", True):
            from loguru import logger

            logger.warning("Kronos predict_from_ohlcv_frames failed: {}", exc)
        return {
            "available": False,
            "code": normalize_symbol(code)[0] if code else "",
            "error": str(exc),
        }


def predict_symbol_paths(
    code: str,
    trading_days: list[date],
    *,
    base_price: Optional[float] = None,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Run Kronos on daily bars; return per-day predicted closes and summary.

    Returns None when disabled, unavailable, or on recoverable failure.
    """
    cfg = kronos_cfg(settings)
    if not cfg.get("enabled", False):
        return None
    if not trading_days:
        return None

    if cfg.get("daily_cache", True) is not False:
        cached = load_kronos_daily_cache(code, trading_days, settings=settings)
        if cached is not None:
            return cached

    try:
        lookback = int(cfg.get("lookback_window", 90))
        pred_window = int(cfg.get("predict_window", 10))
        pred_len = min(len(trading_days), pred_window)
        trading_days = trading_days[:pred_len]

        df = fetch_ohlcv_history(code, lookback=lookback, settings=settings)
        if len(df) < min(lookback // 2, 30):
            return None

        use_len = min(len(df), lookback)
        x_df = df.iloc[-use_len:][["open", "high", "low", "close", "volume", "amount"]]
        x_timestamp = df.iloc[-use_len:]["timestamps"]
        result = predict_from_ohlcv_frames(
            x_df,
            x_timestamp,
            trading_days,
            base_price=base_price or float(df["close"].iloc[-1]),
            settings=settings,
            code=code,
        )
        if not result or not result.get("available"):
            return result
        if cfg.get("daily_cache", True) is not False:
            save_kronos_daily_cache(code, trading_days, result, settings=settings)
        return result
    except (KronosError, AKShareError, OSError, ValueError, RuntimeError) as exc:
        if cfg.get("log_errors", True):
            from loguru import logger

            logger.warning("Kronos predict failed for {}: {}", code, exc)
        return {
            "available": False,
            "code": normalize_symbol(code)[0],
            "error": str(exc),
        }


def attach_kronos_to_snapshot(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    trading_days: Optional[list[date]] = None,
) -> dict[str, Any]:
    """Attach Kronos summary to primary snapshot code (for technical expert)."""
    cfg = kronos_cfg(settings)
    if not cfg.get("enabled", False) or not cfg.get("attach_to_snapshot", True):
        return snapshot

    code = str(snapshot.get("code") or "")
    if not code:
        return snapshot

    if trading_days is None:
        n = int(cfg.get("attach_predict_days", 5))
        trading_days = resolve_kronos_trading_days(n, settings=settings)

    result = predict_symbol_paths(
        code,
        trading_days,
        base_price=snapshot.get("price"),
        settings=settings,
    )
    if not result:
        return snapshot

    out = dict(snapshot)
    out["kronos"] = result
    return out


def blend_symbol_days_with_kronos(
    symbol_entry: dict[str, Any],
    kronos: Optional[dict[str, Any]],
    *,
    blend_weight: float = 0.35,
) -> dict[str, Any]:
    """Blend Monte-Carlo day paths with Kronos daily change_pct."""
    if not kronos or not kronos.get("available"):
        if kronos:
            symbol_entry = dict(symbol_entry)
            symbol_entry["kronos"] = kronos
        return symbol_entry

    out = dict(symbol_entry)
    out["kronos"] = kronos
    days = dict(out.get("days") or {})
    k_days = kronos.get("days") or {}
    divergences: list[str] = []

    for ds, k_day in k_days.items():
        if ds not in days:
            continue
        mc = days[ds]
        k_chg = float(k_day.get("change_pct") or 0)
        mc_exp = float(mc.get("expected_change_pct") or 0)
        blended = round(mc_exp * (1 - blend_weight) + k_chg * blend_weight, 2)
        lo, hi = mc.get("change_pct_range") or [blended - 1, blended + 1]
        lo, hi = float(lo), float(hi)
        # Widen band slightly toward Kronos if outside MC range
        lo = min(lo, k_chg - 0.5)
        hi = max(hi, k_chg + 0.5)
        new_dir = _direction_from_change(blended)
        if new_dir != mc.get("direction") and k_day.get("direction") != mc.get("direction"):
            divergences.append(ds)
        days[ds] = {
            **mc,
            "expected_change_pct": blended,
            "change_pct_range": [round(lo, 2), round(hi, 2)],
            "direction": new_dir,
            "kronos_change_pct": k_chg,
            "blended": True,
        }

    out["days"] = days
    if divergences:
        out["kronos_divergence_days"] = divergences
    return out
