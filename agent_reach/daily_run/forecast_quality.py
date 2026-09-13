# -*- coding: utf-8
"""Sunday forecast data quality — evidence, interval width, confidence, cross-check."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Optional

from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.trade_calendar import today_shanghai
from agent_reach.daily_run.week_forecast import forecasts_dir, load_forecast

MARKET_WIDTH_MIN = 2.0
MARKET_WIDTH_MAX = 4.0
STOCK_WIDTH_MIN = 8.0
STOCK_WIDTH_MAX = 15.0


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def interval_width_pct(lo: float, hi: float, *, mid: Optional[float] = None) -> float:
    center = mid if mid is not None else (lo + hi) / 2
    if center == 0:
        return abs(hi - lo)
    return round(abs(hi - lo) / abs(center) * 100.0, 2)


def confidence_tier(pct: float) -> str:
    if pct >= 80:
        return "高"
    if pct >= 60:
        return "中"
    return "低"


def confidence_tier_detail(pct: float) -> str:
    tier = confidence_tier(pct)
    if pct >= 80:
        return f"{pct:.0f}%（{tier}）"
    if pct >= 60:
        return f"{pct:.0f}%（{tier}）"
    return f"{pct:.0f}%（{tier}）"


def clamp_pct_band(
    lo: float,
    hi: float,
    *,
    mid: Optional[float] = None,
    min_width: float,
    max_width: float,
) -> tuple[float, float, float]:
    """Constrain absolute band width (hi-lo) in percentage points."""
    center = mid if mid is not None else (lo + hi) / 2
    width = hi - lo
    if width < min_width:
        half = min_width / 2
        lo, hi = center - half, center + half
    elif width > max_width:
        half = max_width / 2
        lo, hi = center - half, center + half
    width_pts = round(hi - lo, 2)
    return round(lo, 2), round(hi, 2), width_pts


def symbol_historical_hit_rate(code: str, *, lookback_weeks: int = 8) -> Optional[dict[str, Any]]:
    """Rolling hit rate for a symbol from saved forecast reviews."""
    norm = _normalize_code(code)
    hits = 0
    total = 0
    root = forecasts_dir()
    if not root.exists():
        return None
    paths = sorted(
        [p for p in root.glob("20*.json") if p.name != "calibration.json"],
        reverse=True,
    )[:lookback_weeks]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for review in data.get("reviews") or []:
            for ev in review.get("symbol_evals") or []:
                if _normalize_code(str(ev.get("code") or "")) != norm:
                    continue
                if ev.get("hit") is None:
                    continue
                total += 1
                if ev.get("hit"):
                    hits += 1
    if total < 3:
        return None
    rate = round(hits / total * 100.0, 1)
    note = ""
    if rate > 90:
        note = "历史命中率>90%，区间偏宽，下轮可收窄"
    elif rate < 50:
        note = "历史命中率<50%，区间偏窄，下轮应放宽"
    return {"hits": hits, "total": total, "hit_rate_pct": rate, "note": note}


def _mss_tone(score: float) -> str:
    if score >= 55:
        return "偏多"
    if score < 45:
        return "偏空"
    return "中性"


def build_market_evidence(
    *,
    snapshot: Optional[dict[str, Any]] = None,
    mss_daily: Optional[dict[str, Any]] = None,
    calibration: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> list[str]:
    lines: list[str] = []
    snap = snapshot or {}
    mss = _optional_float(snap.get("mss_final"))
    if mss is not None:
        lines.append(f"③模型MSS评分{int(round(mss))}/100（{_mss_tone(mss)}）")
    breakdown = snap.get("mss_breakdown") or {}
    flow = _optional_float(breakdown.get("flow"))
    if flow is not None:
        lines.append(f"②资金面flow分项{flow:.0f}分")
    elif snap.get("macro_summary"):
        macro = str(snap["macro_summary"])[:40]
        if "北向" in macro or "净流入" in macro:
            lines.append(f"②资金面{macro}")

    medians = [
        float(r.get("median"))
        for r in (mss_daily or {}).values()
        if r.get("median") is not None
    ]
    if len(medians) >= 2:
        delta = medians[-1] - medians[0]
        lines.append(f"①MSS周度漂移{delta:+.1f}分（Monte Carlo）")

    try:
        from agent_reach.daily_run.market_review import load_market_review

        prior = today_shanghai() - timedelta(days=1)
        review = load_market_review(prior.isoformat())
        indices = (review or {}).get("indices") or {}
        hs = indices.get("sh000300") or indices.get("000300") or {}
        price = _optional_float(hs.get("price"))
        ma20 = _optional_float(hs.get("ma20"))
        if price is not None and ma20 is not None:
            rel = "站稳" if price >= ma20 else "跌破"
            lines.append(f"①技术面沪深300 {rel}20日均线（收盘{price:.0f}/MA20 {ma20:.0f}）")
    except Exception:
        pass

    hit_rate = _optional_float((calibration or {}).get("hit_rate"))
    if hit_rate is not None and len(lines) < 3:
        lines.append(f"③历史预测校准命中率{hit_rate:.0%}")

    return lines[:3]


def build_symbol_evidence(
    *,
    code: str,
    sym: dict[str, Any],
    enriched: Optional[dict[str, Any]] = None,
    kronos: Optional[dict[str, Any]] = None,
) -> list[str]:
    row = enriched or {}
    lines: list[str] = []
    price = _optional_float(row.get("price") or sym.get("base_price"))
    ma20 = _optional_float(row.get("ma20"))
    if price is not None and ma20 is not None:
        rel = "站稳" if price >= ma20 else "跌破"
        lines.append(f"①技术面{rel}20日均线（{price:.2f}/{ma20:.2f}）")
    pos = _optional_float(row.get("position_20d"))
    if pos is not None:
        lines.append(f"②20日价格位置{pos:.0%}")
    mss = _optional_float(row.get("mss_final"))
    if mss is not None:
        lines.append(f"③MSS模型评分{int(round(mss))}/100（{_mss_tone(mss)}）")
    if kronos and kronos.get("available"):
        cum = _optional_float(kronos.get("cum_change_pct"))
        if cum is not None:
            lines.append(f"③Kronos模型周累计{cum:+.1f}%")
    hist = symbol_historical_hit_rate(code)
    if hist and hist.get("note"):
        lines.append(f"②历史区间命中{hist['hit_rate_pct']:.0f}%（{hist['note']}）")
    days = sym.get("days") or {}
    confs = [_optional_float(d.get("confidence")) for d in days.values()]
    confs = [c for c in confs if c is not None]
    if confs and len(lines) < 3:
        avg = sum(confs) / len(confs)
        lines.append(f"③日路径模型平均置信{avg:.0%}")
    return lines[:3]


def compute_market_confidence(
    *,
    width_pct: float,
    evidence_count: int,
    calibration: Optional[dict[str, Any]] = None,
    mss_daily: Optional[dict[str, Any]] = None,
) -> float:
    base = 68.0
    hit = _optional_float((calibration or {}).get("hit_rate"))
    if hit is not None:
        base = 55 + hit * 35
    if width_pct > MARKET_WIDTH_MAX:
        base -= min(15.0, (width_pct - MARKET_WIDTH_MAX) * 3)
    if evidence_count >= 3:
        base += 5
    elif evidence_count < 2:
        base -= 8
    medians = [
        float(r.get("median"))
        for r in (mss_daily or {}).values()
        if r.get("median") is not None
    ]
    if medians and abs(medians[-1] - medians[0]) >= 2:
        base += 3
    return round(max(35.0, min(92.0, base)), 1)


def compute_symbol_confidence(
    *,
    width_pct: float,
    evidence_count: int,
    sym: dict[str, Any],
    hist: Optional[dict[str, Any]] = None,
) -> float:
    days = sym.get("days") or {}
    confs = [_optional_float(d.get("confidence")) for d in days.values()]
    confs = [c for c in confs if c is not None]
    base = (sum(confs) / len(confs) * 100) if confs else 58.0
    if width_pct > STOCK_WIDTH_MAX:
        base -= min(20.0, (width_pct - STOCK_WIDTH_MAX) * 1.5)
    elif width_pct < STOCK_WIDTH_MIN:
        base += 3
    if evidence_count >= 2:
        base += 4
    if hist:
        rate = float(hist.get("hit_rate_pct") or 0)
        if rate < 50:
            base -= 6
        elif rate > 90:
            base -= 4
    return round(max(30.0, min(90.0, base)), 1)


def load_cross_reference_data(
    *,
    as_of: Optional[date] = None,
    portfolio: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Load last close / weekly digest figures for push-time cross-check."""
    from agent_reach.daily_run.prior_close import load_close_baseline, prev_trading_day

    d = as_of or today_shanghai()
    last_trade = prev_trading_day(d, settings=settings)
    pf = portfolio or {}
    holdings: dict[str, Any] = {}
    for h in pf.get("holdings") or []:
        code = _normalize_code(str(h.get("code") or ""))
        if not code:
            continue
        baseline = load_close_baseline(code, target_day=last_trade, settings=settings) or {}
        price = _optional_float(baseline.get("price") or h.get("price"))
        chg = _optional_float(baseline.get("change_pct") or h.get("change_pct"))
        source = baseline.get("_baseline_source") or "close_baseline"
        port_px = _optional_float(h.get("price"))
        if port_px is not None:
            if price is None or abs(port_px - price) / max(port_px, 0.01) > 0.005:
                price = port_px
                source = "portfolio_snapshot"
        holdings[code] = {
            "name": h.get("name") or baseline.get("name") or code,
            "close_price": price,
            "change_pct": chg,
            "source": source,
            "as_of": str(baseline.get("close_date") or last_trade.isoformat()),
            "adjusted": bool(baseline.get("ex_rights") or baseline.get("adjusted")),
        }

    bench: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.market_review import load_market_review

        review = load_market_review(last_trade.isoformat())
        indices = (review or {}).get("indices") or {}
        hs = indices.get("sh000300") or {}
        bench = {
            "close_price": _optional_float(hs.get("price")),
            "change_pct": _optional_float(hs.get("change_pct")),
            "source": "market_review",
            "as_of": last_trade.isoformat(),
        }
    except Exception:
        pass

    digest = None
    try:
        from agent_reach.daily_run.weekly_digest import load_weekly_digest

        digest = load_weekly_digest(max_age_days=3)
    except Exception:
        pass

    return {
        "cutoff_date": last_trade.isoformat(),
        "cutoff_label": f"{last_trade.isoformat()} 收盘",
        "holdings": holdings,
        "benchmark": bench,
        "weekly_digest_week_end": (digest or {}).get("week_end"),
    }


def audit_forecast_cross_check(
    structured: dict[str, Any],
    reference: dict[str, Any],
    *,
    tolerance_pct: float = 0.5,
) -> dict[str, Any]:
    """Compare forecast base prices vs close-card / baseline references."""
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    ref_holdings = reference.get("holdings") or {}
    for sym in structured.get("symbols") or []:
        code = _normalize_code(str(sym.get("code") or ""))
        ref = ref_holdings.get(code) or {}
        forecast_px = _optional_float(sym.get("base_price"))
        ref_px = _optional_float(ref.get("close_price"))
        if forecast_px is None or ref_px is None:
            continue
        diff_pct = abs(forecast_px - ref_px) / ref_px * 100 if ref_px else 0
        ok = diff_pct <= tolerance_pct
        row = {
            "code": code,
            "name": sym.get("name") or ref.get("name") or code,
            "forecast_price": forecast_px,
            "reference_price": ref_px,
            "reference_source": ref.get("source") or "—",
            "as_of": ref.get("as_of") or reference.get("cutoff_date"),
            "match": ok,
            "diff_pct": round(diff_pct, 2),
            "adjusted_note": "已除权调整" if ref.get("adjusted") else "",
        }
        rows.append(row)
        if not ok:
            issues.append(
                f"{row['name']} 基准价 {forecast_px:.2f} vs 收盘 {ref_px:.2f}（偏差{diff_pct:.2f}%）"
            )

    market = structured.get("market") or {}
    bench = reference.get("benchmark") or {}
    return {
        "ok": not issues,
        "rows": rows,
        "issues": issues,
        "cutoff_label": reference.get("cutoff_label"),
        "weekly_digest_week_end": reference.get("weekly_digest_week_end"),
        "market_note": market.get("data_source"),
    }


def position_hint_for_confidence(confidence_pct: float) -> str:
    tier = confidence_tier(confidence_pct)
    if tier == "高":
        return "正常仓位"
    if tier == "中":
        return "轻仓"
    return "观望或极小仓位"


def format_evidence_suffix(evidence: list[str]) -> str:
    if not evidence:
        return "依据：①数据不足（主观判断，待补充量化指标）"
    parts = []
    for i, line in enumerate(evidence[:3], start=1):
        if line[:2].startswith("①") or line[:2].startswith("②") or line[:2].startswith("③"):
            parts.append(line)
        else:
            markers = ["①", "②", "③"]
            parts.append(f"{markers[min(i - 1, 2)]}{line}")
    return "依据：" + "；".join(parts)


def enrich_market_prediction(
    pred: dict[str, Any],
    *,
    snapshot: Optional[dict[str, Any]] = None,
    mss_daily: Optional[dict[str, Any]] = None,
    calibration: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    lo = float(pred.get("change_pct_low") or 0)
    hi = float(pred.get("change_pct_high") or 0)
    mid = float(pred.get("change_pct_mid") or (lo + hi) / 2)
    lo, hi, width = clamp_pct_band(lo, hi, mid=mid, min_width=MARKET_WIDTH_MIN, max_width=MARKET_WIDTH_MAX)
    evidence = build_market_evidence(
        snapshot=snapshot,
        mss_daily=mss_daily,
        calibration=calibration,
        settings=settings,
    )
    conf = compute_market_confidence(
        width_pct=width,
        evidence_count=len(evidence),
        calibration=calibration,
        mss_daily=mss_daily,
    )
    index_name = pred.get("index_name") or "沪深300"
    ev_s = format_evidence_suffix(evidence)
    low_conf = f"；**低置信度，建议轻仓操作**" if conf < 60 else ""
    text = (
        f"{index_name}预测 {_fmt_pct(lo)}~{_fmt_pct(hi)}（宽度{width:.1f}%），"
        f"置信度 {confidence_tier_detail(conf)}{low_conf}；{ev_s}"
    )
    out = dict(pred)
    out.update(
        {
            "change_pct_low": lo,
            "change_pct_high": hi,
            "change_pct_mid": round((lo + hi) / 2, 2),
            "interval_width_pct": width,
            "confidence_pct": conf,
            "confidence_tier": confidence_tier(conf),
            "evidence": evidence,
            "text": text,
            "data_source": f"收盘基准截止 {today_shanghai().isoformat()}；MSS/Kronos 模型",
        }
    )
    if width > MARKET_WIDTH_MAX:
        out["width_warning"] = f"区间宽度{width:.1f}pp超上限，模型不确定性偏高"
    return out


def enrich_symbol_prediction(
    pred: dict[str, Any],
    *,
    sym: dict[str, Any],
    enriched: Optional[dict[str, Any]] = None,
    kronos: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    code = str(pred.get("code") or "")
    lo = float(pred.get("change_pct_low") or 0)
    hi = float(pred.get("change_pct_high") or 0)
    mid = float(pred.get("change_pct_mid") or (lo + hi) / 2)
    hist = symbol_historical_hit_rate(code)
    interval_meta: dict[str, Any] = {}
    base = _optional_float(pred.get("base_price")) or 0.0
    from agent_reach.daily_run.forecast_interval_policy import apply_symbol_interval_policy

    lo, hi, width_pts, interval_meta = apply_symbol_interval_policy(
        lo=lo,
        hi=hi,
        mid=mid,
        base_price=base,
        code=code,
        enriched=enriched,
        settings=settings,
    )
    price_lo = round(base * (1 + lo / 100), 2) if base > 0 else pred.get("price_low")
    price_hi = round(base * (1 + hi / 100), 2) if base > 0 else pred.get("price_high")
    price_mid = round(base * (1 + (lo + hi) / 200), 2) if base > 0 else pred.get("price_mid")
    width = interval_width_pct(float(price_lo or 0), float(price_hi or 0), mid=_optional_float(price_mid))
    evidence = build_symbol_evidence(code=code, sym=sym, enriched=enriched, kronos=kronos)
    conf = compute_symbol_confidence(
        width_pct=width_pts,
        evidence_count=len(evidence),
        sym=sym,
        hist=hist,
    )
    name = str(pred.get("name") or code)
    ev_s = format_evidence_suffix(evidence)
    low_conf = "；**低置信度，建议轻仓操作**" if conf < 60 else ""
    degrade_notes = list(interval_meta.get("notes") or [])
    if any("降级放宽" in str(n) for n in degrade_notes):
        low_conf = "；**低置信度（预测准确率下滑），区间已放宽**"
        conf = min(conf, 49.0)
    lo_s = f"{float(price_lo):.0f}" if price_lo is not None else "—"
    hi_s = f"{float(price_hi):.0f}" if price_hi is not None else "—"
    text = (
        f"{name}预测 {lo_s}-{hi_s}元（宽度{width:.1f}%），"
        f"置信度 {confidence_tier_detail(conf)}{low_conf}；{ev_s}"
    )
    out = dict(pred)
    out.update(
        {
            "change_pct_low": lo,
            "change_pct_high": hi,
            "change_pct_mid": round((lo + hi) / 2, 2),
            "price_low": price_lo,
            "price_high": price_hi,
            "price_mid": price_mid,
            "interval_width_pct": width,
            "confidence_pct": conf,
            "confidence_tier": confidence_tier(conf),
            "position_hint": position_hint_for_confidence(conf),
            "evidence": evidence,
            "historical_hit": hist,
            "interval_policy": interval_meta,
            "text": text,
            "reference_close": _optional_float((enriched or {}).get("price") or sym.get("base_price")),
            "reference_as_of": (enriched or {}).get("as_of"),
        }
    )
    if width > STOCK_WIDTH_MAX:
        out["width_warning"] = f"区间宽度{width:.1f}%偏宽，置信度已下调"
    return out


def _fmt_pct(value: float, *, signed: bool = True) -> str:
    if signed:
        return f"{value:+.1f}%"
    return f"{value:.1f}%"
