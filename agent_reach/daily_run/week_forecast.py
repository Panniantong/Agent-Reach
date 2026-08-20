# -*- coding: utf-8
"""Next-week market forecast — holdings/watchlist daily paths, news, MSS."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.mss_forecast import forecast_mss_range
from agent_reach.daily_run.kronos_predictor import (
    blend_symbol_days_with_kronos,
    is_kronos_enabled,
    kronos_cfg,
    predict_symbol_paths,
)
from agent_reach.daily_run.snapshot_builder import _normalize_code
from agent_reach.daily_run.symbols import build_enriched_symbols
from agent_reach.daily_run.trade_calendar import is_trading_day, today_shanghai


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def forecasts_dir() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "forecasts"


def calibration_path() -> Path:
    return forecasts_dir() / "calibration.json"


def next_trading_week_range(as_of: Optional[date] = None) -> tuple[date, date]:
    """Mon–Fri of the upcoming trading week (Sunday run → next Mon–Fri)."""
    d = as_of or today_shanghai()
    if d.weekday() == 6:
        monday = d + timedelta(days=1)
    elif d.weekday() == 5:
        monday = d + timedelta(days=2)
    else:
        monday = d + timedelta(days=(7 - d.weekday()))
    friday = monday + timedelta(days=4)
    return monday, friday


def list_trading_days(start: date, end: date, *, settings: Optional[dict[str, Any]] = None) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        ok, _ = is_trading_day(cur, settings=settings)
        if ok:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def load_calibration_file() -> dict[str, Any]:
    """Read calibration.json only (no harness overlay)."""
    path = calibration_path()
    if not path.exists():
        return {"bias_pct": 0.0, "vol_scale": 1.0, "hit_rate": None, "reviews": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"bias_pct": 0.0, "vol_scale": 1.0, "hit_rate": None, "reviews": 0}


def load_calibration(*, settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    base = load_calibration_file()
    if settings is None:
        return base
    fc = settings.get("forecast_calibration")
    if isinstance(fc, dict):
        merged = dict(base)
        for key in ("bias_pct", "vol_scale"):
            if key in fc:
                merged[key] = fc[key]
        return merged
    return base


def save_calibration(data: dict[str, Any]) -> Path:
    forecasts_dir().mkdir(parents=True, exist_ok=True)
    path = calibration_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _forecast_path(week_start: date) -> Path:
    return forecasts_dir() / f"{week_start.isoformat()}.json"


def save_forecast(forecast: dict[str, Any]) -> Path:
    forecasts_dir().mkdir(parents=True, exist_ok=True)
    week_start = date.fromisoformat(str(forecast["week_start"]))
    path = _forecast_path(week_start)
    path.write_text(json.dumps(forecast, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_forecast(week_start: date) -> Optional[dict[str, Any]]:
    path = _forecast_path(week_start)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_active_forecast(as_of: Optional[date] = None) -> Optional[dict[str, Any]]:
    """Return forecast whose week contains as_of (typically Mon–Fri)."""
    d = as_of or today_shanghai()
    root = forecasts_dir()
    if not root.exists():
        return None
    best: Optional[dict[str, Any]] = None
    for path in sorted(root.glob("20*.json")):
        if path.name == "calibration.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ws = date.fromisoformat(str(data.get("week_start", "")))
        we = date.fromisoformat(str(data.get("week_end", "")))
        if ws <= d <= we:
            best = data
    return best


def _direction(mid: float) -> str:
    if mid > 0.3:
        return "up"
    if mid < -0.3:
        return "down"
    return "flat"


def _predict_symbol_days(
    code: str,
    row: dict[str, Any],
    role: str,
    trading_days: list[date],
    calibration: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    base_price = float(row.get("price") or row.get("cost") or 0)
    base_chg = float(row.get("change_pct") or 0)
    pos = row.get("position_20d")
    vol_scale = float(calibration.get("vol_scale") or 1.0)
    bias = float(calibration.get("bias_pct") or 0)

    rng = random.Random(int(code[-6:]) % 9973)
    days: dict[str, Any] = {}
    for i, day in enumerate(trading_days):
        vol = (abs(base_chg) * 0.4 + 0.8) * vol_scale
        drift = base_chg * 0.25 * (1 - i * 0.08)
        if pos is not None:
            drift += (0.5 - float(pos)) * 0.4
        drift -= bias
        noise = rng.gauss(0, vol * 0.15)
        mid = drift + noise
        lo = round(mid - vol, 2)
        hi = round(mid + vol, 2)
        days[day.isoformat()] = {
            "direction": _direction(mid),
            "change_pct_range": [lo, hi],
            "expected_change_pct": round(mid, 2),
            "confidence": round(max(0.35, min(0.85, 0.55 - abs(mid) * 0.02)), 2),
        }

    return {
        "code": code,
        "name": row.get("name") or code,
        "role": role,
        "base_price": base_price,
        "days": days,
    }


def _predict_mss_daily(
    snapshot: dict[str, Any],
    trading_days: list[date],
    settings: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    mss_range, meta = forecast_mss_range(snapshot, settings)
    lo, hi = float(mss_range[0]), float(mss_range[1])
    bias = float(calibration.get("bias_pct") or 0)
    out: dict[str, Any] = {}
    for i, day in enumerate(trading_days):
        shift = i * 0.5 - bias * 0.1
        out[day.isoformat()] = {
            "range": [round(lo + shift, 1), round(hi + shift, 1)],
            "median": round(float(meta.get("median", (lo + hi) / 2)) + shift, 1),
        }
    return out


def _load_experience_rules(limit: int = 5) -> list[str]:
    from agent_reach.daily_run.experience import experience_dir

    path = experience_dir() / "rules_summary.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rules = list(data.get("rules") or [])
    return [str(r) for r in rules[-limit:]]


def _events_from_weekly_digest(digest: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in digest.get("hot_sectors") or []:
        name = item.get("sector") or item.get("name") or "热点板块"
        chg = item.get("avg_change_pct") or item.get("change_pct")
        summary = f"周均 {chg:+.1f}%" if chg is not None else str(item.get("summary") or "")
        events.append({"source": "weekly_digest", "title": name, "summary": summary})
    for row in digest.get("sector_research") or []:
        events.append(
            {
                "source": "weekly_research",
                "title": row.get("label") or row.get("sector") or "板块调研",
                "summary": str(row.get("summary") or "")[:200],
            }
        )
    for skill in digest.get("skill_learning") or []:
        title = skill.get("title") or skill.get("topic") or "技能学习"
        events.append(
            {
                "source": "skill_learning",
                "title": title,
                "summary": str(skill.get("summary") or skill.get("insight") or "")[:160],
            }
        )
    return events


def _historical_vol_scale(calibration: dict[str, Any]) -> float:
    """Blend calibration vol_scale with recent forecast review errors."""
    base = float(calibration.get("vol_scale") or 1.0)
    root = forecasts_dir()
    if not root.exists():
        return base

    errors: list[float] = []
    for path in sorted(root.glob("20*.json"))[-4:]:
        if path.name == "calibration.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for review in (data.get("reviews") or [])[-5:]:
            for ev in review.get("symbol_evals") or []:
                err = ev.get("error_pct")
                if err is not None:
                    errors.append(abs(float(err)))

    if not errors:
        return base

    mean_abs = sum(errors) / len(errors)
    if mean_abs > 2.5:
        return min(1.6, base * 1.08)
    if mean_abs < 0.8:
        return max(0.6, base * 0.95)
    return base


def build_news_queries(snapshot: dict[str, Any], week_start: date) -> list[dict[str, str]]:
    macro = snapshot.get("macro_summary") or ""
    sector = snapshot.get("industry") or snapshot.get("sector") or "A-share"
    ws = week_start.isoformat()
    queries = [
        {
            "type": "news",
            "query": f"China A-share stock market news catalysts events week of {ws} 2026 policy",
            "label": "下周宏观与政策事件",
        },
        {
            "type": "news",
            "query": f"China {sector} sector hot stocks news next week 2026 earnings policy",
            "label": f"{sector} 板块热点",
        },
    ]
    if macro:
        queries.append(
            {
                "type": "news",
                "query": f"China stock market {macro[:60]} outlook next trading week 2026",
                "label": "延续本周宏观主题",
            }
        )
    return queries[:3]


def run_news_research(
    queries: list[dict[str, str]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from agent_reach.daily_run.exa_client import ExaError, is_exa_available, summarize_hits, web_search_exa

    cfg = settings.get("week_forecast") or {}
    if cfg.get("exa_news_research", True) is False:
        return []
    if not is_exa_available():
        return []

    plugin_cfg = settings.get("plugins") or {}
    timeout = int(plugin_cfg.get("exa_timeout", 45))
    max_q = int(cfg.get("max_news_queries", 2))
    queries = queries[:max_q]
    if not queries:
        return []

    def _run_one(q: dict[str, str]) -> dict[str, Any]:
        try:
            hits = web_search_exa(q["query"], num_results=3, timeout=timeout)
            return {**q, "hits": hits, "summary": summarize_hits(hits), "success": True}
        except ExaError as exc:
            return {**q, "hits": [], "summary": str(exc), "success": False}

    workers = min(len(queries), 2)
    ordered: list[Optional[dict[str, Any]]] = [None] * len(queries)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, q): i for i, q in enumerate(queries)}
        for fut in as_completed(futures):
            ordered[futures[fut]] = fut.result()
    return [r for r in ordered if r is not None]


@dataclass
class WeekForecast:
    week_start: date
    week_end: date
    trading_days: list[str]
    symbols: dict[str, Any]
    mss_daily: dict[str, Any]
    news_events: list[dict[str, Any]]
    news_research: list[dict[str, Any]]
    calibration_used: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    kronos_paths: dict[str, Any] = field(default_factory=dict)
    llm_narrative: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": self.week_start.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "trading_days": self.trading_days,
            "symbols": self.symbols,
            "kronos_paths": self.kronos_paths,
            "mss_daily": self.mss_daily,
            "news_events": self.news_events,
            "news_research": self.news_research,
            "calibration_used": self.calibration_used,
            "reviews": [],
            "notes": self.notes,
            "llm_narrative": self.llm_narrative,
        }


def generate_week_forecast(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    as_of: Optional[date] = None,
    portfolio: Optional[dict[str, Any]] = None,
) -> WeekForecast:
    """Build next-week daily path forecast for holdings + watchlist."""
    cfg = settings.get("week_forecast") or {}
    week_start, week_end = next_trading_week_range(as_of)
    trading_days = list_trading_days(week_start, week_end, settings=settings)
    calibration = load_calibration(settings=settings)
    vol_scale = _historical_vol_scale(calibration)
    calibration = {**calibration, "vol_scale": vol_scale}
    pf = portfolio or (snapshot.get("portfolio") or {})
    enriched = build_enriched_symbols(snapshot)
    notes: list[str] = []

    from agent_reach.daily_run.weekly_digest import load_weekly_digest

    digest = load_weekly_digest()
    if digest:
        notes.append(f"复用周六周报 digest（{digest.get('week_end', '')}）")

    experience_rules = _load_experience_rules()
    if experience_rules:
        notes.append("经验规则：" + "；".join(experience_rules[:2]))

    if not trading_days:
        notes.append("下周无交易日（节假日），预测仅作参考")

    symbols: dict[str, Any] = {}
    kronos_paths: dict[str, Any] = {}
    held_codes: set[str] = set()
    k_cfg = kronos_cfg(settings)
    use_kronos = is_kronos_enabled(settings) and bool(trading_days)
    blend_w = float(k_cfg.get("week_forecast_blend_weight", 0.35))

    for h in pf.get("holdings") or []:
        code = _normalize_code(str(h.get("code", "")))
        if not code:
            continue
        held_codes.add(code)
        row = {**dict(h), **enriched.get(code, {})}
        entry = _predict_symbol_days(
            code, row, "holding", trading_days, calibration, settings
        )
        if use_kronos:
            kronos = predict_symbol_paths(
                code,
                trading_days,
                base_price=row.get("price"),
                settings=settings,
            )
            if kronos:
                kronos_paths[code] = kronos
                entry = blend_symbol_days_with_kronos(entry, kronos, blend_weight=blend_w)
        symbols[code] = entry

    for w in pf.get("watchlist") or []:
        code = _normalize_code(str(w.get("code", "")))
        if not code or code in held_codes:
            continue
        row = {**dict(w), **enriched.get(code, {})}
        entry = _predict_symbol_days(
            code, row, "watchlist", trading_days, calibration, settings
        )
        if use_kronos:
            kronos = predict_symbol_paths(
                code,
                trading_days,
                base_price=row.get("price"),
                settings=settings,
            )
            if kronos:
                kronos_paths[code] = kronos
                entry = blend_symbol_days_with_kronos(entry, kronos, blend_weight=blend_w)
        symbols[code] = entry

    if kronos_paths:
        ok = sum(1 for v in kronos_paths.values() if v.get("available"))
        notes.append(f"Kronos 路径预测 {ok}/{len(kronos_paths)} 只")
    elif use_kronos:
        notes.append("Kronos 已启用但未产出路径（依赖或 repo_path 未就绪）")

    mss_daily = _predict_mss_daily(snapshot, trading_days, settings, calibration)

    news_events: list[dict[str, Any]] = []
    if digest:
        news_events.extend(_events_from_weekly_digest(digest))
    macro = snapshot.get("macro_summary")
    if macro:
        news_events.append({"source": "macro", "title": "宏观摘要", "summary": macro[:200]})
    for cat, src in (snapshot.get("sources") or {}).items():
        if isinstance(src, dict) and src.get("summary"):
            news_events.append(
                {"source": cat, "title": f"{cat} 信号", "summary": str(src["summary"])[:160]}
            )

    news_queries = build_news_queries(snapshot, week_start)
    if digest and cfg.get("reuse_weekly_digest_exa", True) is not False:
        cached_research = [
            {
                "type": "digest",
                "label": r.get("title") or "周报调研",
                "summary": r.get("summary") or "",
                "hits": [],
                "success": True,
                "from_digest": True,
            }
            for r in (digest.get("sector_research") or [])[:2]
        ]
        news_research = cached_research + run_news_research(news_queries[:1], settings)
    else:
        news_research = run_news_research(news_queries, settings)

    forecast = WeekForecast(
        week_start=week_start,
        week_end=week_end,
        trading_days=[d.isoformat() for d in trading_days],
        symbols=symbols,
        kronos_paths=kronos_paths,
        mss_daily=mss_daily,
        news_events=news_events,
        news_research=news_research,
        calibration_used=dict(calibration),
        notes=notes,
    )
    from agent_reach.daily_run.report_narrative import generate_forecast_narrative

    narrative = generate_forecast_narrative(forecast.to_dict(), settings=settings)
    forecast.llm_narrative = narrative
    return forecast


def persist_week_forecast(forecast: WeekForecast) -> Path:
    return save_forecast(forecast.to_dict())


@dataclass
class ForecastSection:
    """One Feishu card body when split_push is enabled."""

    label: str
    markdown: str


def _render_mss_section(data: dict[str, Any]) -> str:
    lines: list[str] = []
    ws, we = data["week_start"], data["week_end"]
    lines.append(f"**📅 预测周期：** {ws} ~ {we}")
    lines.append("")
    lines.append("## 📈 下周 MSS 预测")
    mss_daily = data.get("mss_daily") or {}
    if mss_daily:
        for ds, row in sorted(mss_daily.items()):
            wd = WEEKDAY_CN[date.fromisoformat(ds).weekday()]
            rng = row.get("range") or []
            med = row.get("median")
            if len(rng) == 2:
                lines.append(f"- **{ds} {wd}** 区间 [{rng[0]}, {rng[1]}] 中位 {med}")
    else:
        lines.append("- 暂无 MSS 日预测")
    cal = data.get("calibration_used") or {}
    if cal.get("hit_rate") is not None:
        lines.append("")
        lines.append("## 🎯 预测校准")
        lines.append(
            f"- 历史命中率 **{float(cal['hit_rate']):.0%}** · "
            f"偏差校正 bias={cal.get('bias_pct', 0):+.2f}% vol_scale={cal.get('vol_scale', 1):.2f}"
        )
    for note in data.get("notes") or []:
        lines.append(f"\n_{note}_")
    return "\n".join(lines).strip()


def _render_symbols_section(data: dict[str, Any]) -> str:
    lines: list[str] = ["## 📊 持股 / 观察池 · 每日走势预测"]
    symbols = data.get("symbols") or {}
    if not symbols:
        lines.append("- 无持仓或观察池标的")
        return "\n".join(lines)
    dir_cn = {"up": "↑看涨", "down": "↓看跌", "flat": "→震荡"}
    for code, sym in symbols.items():
        role = "持仓" if sym.get("role") == "holding" else "观察"
        lines.append(f"### {sym.get('name')} ({code}) · {role}")
        days = sym.get("days") or {}
        for ds in sorted(days.keys()):
            day = days[ds]
            wd = WEEKDAY_CN[date.fromisoformat(ds).weekday()]
            lo, hi = day.get("change_pct_range") or [0, 0]
            d_label = dir_cn.get(day.get("direction"), "→震荡")
            conf = day.get("confidence")
            conf_s = f" 置信 {conf:.0%}" if conf is not None else ""
            k_note = ""
            if day.get("kronos_change_pct") is not None:
                k_note = f" · Kronos {float(day['kronos_change_pct']):+.1f}%"
            lines.append(f"- **{ds} {wd}** {d_label} 预期 {lo:+.1f}% ~ {hi:+.1f}%{conf_s}{k_note}")
        kronos = sym.get("kronos") or {}
        if kronos.get("available"):
            cum = kronos.get("cum_change_pct")
            band = kronos.get("confidence_band") or []
            dir_nd = kronos.get("direction_nd", "flat")
            k_dir = dir_cn.get(dir_nd, "→震荡")
            band_s = f"[{band[0]:+.1f}%, {band[1]:+.1f}%]" if len(band) == 2 else ""
            lines.append(
                f"_Kronos {k_dir} 累计 {cum:+.1f}% {band_s} "
                f"(sample={kronos.get('sample_count', 1)})_"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _render_news_section(data: dict[str, Any]) -> str:
    lines: list[str] = ["## 📰 新闻与热点事件"]
    events = data.get("news_events") or []
    research = data.get("news_research") or []
    if not events and not research:
        lines.append("- 暂无新闻调研")
        return "\n".join(lines)
    for ev in events:
        lines.append(f"- **{ev.get('title', '事件')}** ({ev.get('source', '')})")
        if ev.get("summary"):
            lines.append(f"  {ev['summary']}")
    for r in research:
        status = "✅" if r.get("success") else "⚠️"
        lines.append(f"**{status} {r.get('label', '调研')}**")
        if r.get("summary"):
            lines.append(r["summary"])
        lines.append("")
    return "\n".join(lines).strip()


def render_forecast_sections(forecast: WeekForecast | dict[str, Any]) -> list[ForecastSection]:
    data = forecast.to_dict() if isinstance(forecast, WeekForecast) else forecast
    sections: list[ForecastSection] = []
    mss_md = _render_mss_section(data)
    if mss_md.strip():
        sections.append(ForecastSection(label="MSS预测", markdown=mss_md))
    sym_md = _render_symbols_section(data)
    if sym_md.strip():
        sections.append(ForecastSection(label="个股路径", markdown=sym_md))
    news_md = _render_news_section(data)
    if news_md.strip():
        sections.append(ForecastSection(label="新闻热点", markdown=news_md))
    from agent_reach.daily_run.report_narrative import render_narrative_markdown

    narrative_md = render_narrative_markdown(data.get("llm_narrative") or {}, job="forecast")
    if narrative_md.strip():
        sections.append(ForecastSection(label="规则解读", markdown=narrative_md))
    return sections


def render_forecast_markdown(forecast: WeekForecast | dict[str, Any]) -> str:
    parts = [s.markdown for s in render_forecast_sections(forecast) if s.markdown.strip()]
    return "\n\n".join(parts).strip()


def forecast_section_title(
    forecast: WeekForecast | dict[str, Any],
    index: int,
    total: int,
    label: str,
) -> str:
    if isinstance(forecast, WeekForecast):
        ws, we = forecast.week_start, forecast.week_end
    else:
        ws = date.fromisoformat(str(forecast["week_start"]))
        we = date.fromisoformat(str(forecast["week_end"]))
    return f"🔮 下周预测 {index}/{total} · {label} · {ws:%m/%d}–{we:%m/%d}"


def forecast_title(forecast: WeekForecast | dict[str, Any]) -> str:
    if isinstance(forecast, WeekForecast):
        ws, we = forecast.week_start, forecast.week_end
    else:
        ws = date.fromisoformat(str(forecast["week_start"]))
        we = date.fromisoformat(str(forecast["week_end"]))
    return f"🔮 下周预测 · {ws:%m/%d}–{we:%m/%d}"
