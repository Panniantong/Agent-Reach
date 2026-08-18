# -*- coding: utf-8
"""LLM narrative cards for morning / close / weekly / forecast reports."""

from __future__ import annotations

import json
from typing import Any, Optional

_JOB_LABELS = {
    "morning": "早报",
    "close": "收盘复盘",
    "weekly": "周六周报",
    "forecast": "周日预测",
}

_NARRATIVE_LIMITS_DEFAULT: dict[str, int] = {
    "max_summary_chars": 72,
    "max_focus_points": 3,
    "max_divergence_notes": 2,
    "max_risk_alerts": 2,
    "max_item_chars": 48,
    "max_context_chars": 1800,
}


def _narrative_limits(cfg: dict[str, Any]) -> dict[str, int]:
    out = dict(_NARRATIVE_LIMITS_DEFAULT)
    for key in out:
        if key in cfg and cfg[key] is not None:
            out[key] = max(1, int(cfg[key]))
    return out


def _trim_text(text: Any, limit: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def _trim_string_list(items: Any, *, max_items: int, max_chars: int) -> list[str]:
    out: list[str] = []
    for raw in items or []:
        line = _trim_text(raw, max_chars)
        if line:
            out.append(line)
        if len(out) >= max_items:
            break
    return out


def _compact_context(context: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
    """Shrink user JSON to cut prompt tokens."""

    def _walk(value: Any, depth: int = 0) -> Any:
        if depth > 4:
            return None
        if isinstance(value, str):
            return _trim_text(value, 160 if depth <= 1 else 96)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [_walk(item, depth + 1) for item in value[:6]]
        if isinstance(value, dict):
            trimmed: dict[str, Any] = {}
            for idx, (key, item) in enumerate(value.items()):
                if idx >= 12:
                    break
                trimmed[str(key)] = _walk(item, depth + 1)
            return trimmed
        return str(value)[:96]

    compact = _walk(context)
    if not isinstance(compact, dict):
        compact = dict(context)
    blob = json.dumps(compact, ensure_ascii=False)
    cap = limits["max_context_chars"]
    if len(blob) <= cap:
        return compact
    compact["summary_hint"] = _trim_text(context.get("summary") or context.get("verify_summary"), 120)
    compact.pop("mss_breakdown", None)
    compact.pop("experience_snippets", None)
    compact.pop("news_events", None)
    return compact


def _compact_narrative_payload(payload: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
    out = dict(payload)
    out["summary"] = _trim_text(out.get("summary"), limits["max_summary_chars"])
    out["focus_points"] = _trim_string_list(
        out.get("focus_points"),
        max_items=limits["max_focus_points"],
        max_chars=limits["max_item_chars"],
    )
    out["divergence_notes"] = _trim_string_list(
        out.get("divergence_notes"),
        max_items=limits["max_divergence_notes"],
        max_chars=limits["max_item_chars"],
    )
    out["risk_alerts"] = _trim_string_list(
        out.get("risk_alerts"),
        max_items=limits["max_risk_alerts"],
        max_chars=limits["max_item_chars"],
    )
    return out


def _narrative_system_prompt(job: str, *, limits: dict[str, int]) -> str:
    label = _JOB_LABELS.get(job, job)
    return (
        f"你是 A 股量化助手 {label} AI 解读员。基于已给数据输出 JSON："
        '{"summary":"...","focus_points":["..."],'
        '"divergence_notes":[],"risk_alerts":[]}。'
        f"summary 一句总结今日/本周关注点，≤{limits['max_summary_chars']}字；"
        f"focus_points 最多 {limits['max_focus_points']} 条、每条 ≤{limits['max_item_chars']}字；"
        f"divergence_notes 仅实质分歧时填，最多 {limits['max_divergence_notes']} 条；"
        f"risk_alerts 最多 {limits['max_risk_alerts']} 条。"
        "禁止编造未提供数字；禁止复述输入；省略废话；中文。"
    )


def _narrative_cfg(settings: Optional[dict[str, Any]], job: str) -> dict[str, Any]:
    root = dict((settings or {}).get("llm_narrative") or {})
    if job == "forecast":
        wf = dict(((settings or {}).get("week_forecast") or {}).get("llm_narrative") or {})
        for key, val in wf.items():
            if key != "jobs" and val is not None:
                root[key] = val
    jobs = root.get("jobs") or {}
    if isinstance(jobs, dict) and job in jobs and not jobs[job]:
        return {"enabled": False}
    if root.get("enabled") is False:
        return {"enabled": False}
    harness_llm = ((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if not root.get("provider") and harness_llm.get("provider"):
        root["provider"] = harness_llm["provider"]
    if not root.get("model") and harness_llm.get("model"):
        root["model"] = harness_llm["model"]
    root.setdefault("enabled", True)
    return root


def _morning_focus_hint() -> str:
    return "优先 verdict、MSS 变化、现金比例。"


def _generate_narrative(
    job: str,
    context: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    system: str = "",
    deterministic_fn=None,
) -> dict[str, Any]:
    cfg = _narrative_cfg(settings, job)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "llm_narrative disabled", "job": job}

    limits = _narrative_limits(cfg)
    compact_context = _compact_context(context, limits)
    base_system = _narrative_system_prompt(job, limits=limits)
    hint = system.strip()
    use_system = f"{base_system} {hint}".strip() if hint else base_system

    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("provider") or "auto")
    if resolve_chat_provider(provider):
        payload = chat_json(
            system=use_system,
            user=json.dumps(compact_context, ensure_ascii=False),
            provider=provider,
            model=cfg.get("model") or None,
            timeout=int(cfg.get("timeout_seconds") or 60),
            max_tokens=int(cfg.get("max_output_tokens") or 320),
        )
        if isinstance(payload, dict) and payload.get("summary"):
            payload = _compact_narrative_payload(payload, limits)
            payload["planner"] = "llm"
            payload["skipped"] = False
            payload["job"] = job
            return payload

    if deterministic_fn:
        out = deterministic_fn(context)
    else:
        out = _default_deterministic(context, job)
    out = _compact_narrative_payload(out, limits)
    out["skipped"] = False
    out["job"] = job
    return out


def _default_deterministic(context: dict[str, Any], job: str) -> dict[str, Any]:
    focus = list(context.get("focus_points") or [])[:3]
    risks = list(context.get("risk_alerts") or [])[:2]
    summary = str(context.get("summary") or f"{_JOB_LABELS.get(job, job)} 关注点")
    return {
        "summary": summary,
        "focus_points": focus or ["按 MSS 与宏观一票否决规则执行"],
        "divergence_notes": list(context.get("divergence_notes") or [])[:2],
        "risk_alerts": risks,
        "planner": "deterministic",
    }


def render_narrative_markdown(narrative: dict[str, Any], *, job: str = "") -> str:
    if narrative.get("skipped"):
        return ""
    use_job = job or str(narrative.get("job") or "")
    subtitles = {
        "forecast": "数值路径不变",
        "morning": "决策摘要",
        "close": "复盘摘要",
        "weekly": "周报摘要",
    }
    sub = subtitles.get(use_job, "AI解读")
    lines = [f"## 🧠 AI 解读（{sub}）", ""]
    if narrative.get("summary"):
        lines.append(str(narrative["summary"]))
    label_focus = {
        "morning": "关注点",
        "close": "关注点",
        "weekly": "关注点",
        "forecast": "关注点",
    }.get(use_job, "关注点")
    if narrative.get("focus_points"):
        if narrative.get("summary"):
            lines.append("")
        lines.append(f"**{label_focus}**")
        for item in narrative["focus_points"]:
            lines.append(f"- {item}")
    if narrative.get("divergence_notes"):
        lines.append("")
        title = "**分歧**" if use_job != "forecast" else "**Kronos 分歧**"
        lines.append(title)
        for item in narrative["divergence_notes"]:
            lines.append(f"- {item}")
    if narrative.get("risk_alerts"):
        lines.append("")
        lines.append("**风险**")
        for item in narrative["risk_alerts"]:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


# --- Morning ---


def build_morning_context(
    snapshot: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    pf = snapshot.get("portfolio") or {}
    holdings = pf.get("holdings") or []
    return {
        "job": "morning",
        "name": report.get("name") or snapshot.get("name"),
        "code": report.get("code") or snapshot.get("code"),
        "verdict": report.get("verdict"),
        "mss_final": report.get("mss_final"),
        "prior_close_mss": report.get("prior_close_mss"),
        "prior_close_delta": report.get("prior_close_delta"),
        "confidence": report.get("confidence"),
        "reasoning": (report.get("reasoning") or "")[:160],
        "macro_summary": (snapshot.get("macro_summary") or "")[:120],
        "change_pct": snapshot.get("change_pct"),
        "cash_ratio": pf.get("cash_ratio"),
        "holdings_count": len(holdings),
        "mss_breakdown": snapshot.get("mss_breakdown") or {},
        "invalidation": (report.get("invalidation") or "")[:120],
    }


def _morning_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    verdict = str(ctx.get("verdict") or "观察")
    mss = ctx.get("mss_final")
    focus.append(f"结论 **{verdict}**" + (f"，MSS **{mss}**" if mss is not None else ""))
    delta = ctx.get("prior_close_delta")
    if delta is not None:
        focus.append(f"相对昨收 MSS Δ {float(delta):+.1f}")
    cash = ctx.get("cash_ratio")
    if cash is not None and float(cash) >= 0.4:
        focus.append(f"现金仓位 {float(cash):.0%}，符合防守配置")
    if mss is not None and float(mss) < 40:
        risks.append("MSS 低于 macro_veto 区间，禁止接飞刀、取消买入计划")
    if ctx.get("invalidation"):
        risks.append(f"失效条件：{ctx['invalidation'][:120]}")
    summary = f"早盘 {ctx.get('name') or ctx.get('code')}：{verdict}"
    if mss is not None:
        summary += f"，MSS {mss}"
    return {
        "summary": summary,
        "focus_points": focus[:3],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def generate_morning_narrative(
    snapshot: dict[str, Any],
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_morning_context(snapshot, report)
    return _generate_narrative(
        "morning",
        context,
        settings=settings,
        system=_morning_focus_hint(),
        deterministic_fn=_morning_deterministic,
    )


# --- Close ---


def build_close_context(
    *,
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    portfolio_summary: Optional[dict[str, Any]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "job": "close",
        "name": snapshot.get("name"),
        "code": snapshot.get("code"),
        "verify_summary": (verify.get("summary") or "")[:120],
        "verdict_current": verify.get("verdict_current"),
        "mss_delta": verify.get("mss_delta"),
        "deviations": (verify.get("deviations") or [])[:3],
        "recommendations": (verify.get("recommendations") or [])[:2],
        "portfolio_daily_pnl": (portfolio_summary or {}).get("daily_pnl"),
        "portfolio_daily_pnl_pct": (portfolio_summary or {}).get("daily_pnl_pct"),
        "curve_trend": (curve or {}).get("trend"),
        "forecast_review_accuracy": (forecast_review or {}).get("accuracy"),
        "macro_summary": (snapshot.get("macro_summary") or "")[:120],
    }


def _close_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    if ctx.get("verify_summary"):
        focus.append(str(ctx["verify_summary"])[:160])
    pnl = ctx.get("portfolio_daily_pnl")
    pct = ctx.get("portfolio_daily_pnl_pct")
    if pnl is not None:
        sign = "+" if float(pnl) >= 0 else ""
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        focus.append(f"组合当日盈亏 {sign}¥{float(pnl):,.0f}{pct_s}")
    for rec in ctx.get("recommendations") or []:
        focus.append(f"明日：{rec}")
    for dev in ctx.get("deviations") or []:
        risks.append(str(dev)[:120])
    summary = f"收盘 {ctx.get('name') or ctx.get('code')} 复盘"
    if pnl is not None:
        summary += f"，当日盈亏 ¥{float(pnl):,.0f}"
    return {
        "summary": summary,
        "focus_points": focus[:3],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def generate_close_narrative(
    *,
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    portfolio_summary: Optional[dict[str, Any]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_close_context(
        snapshot=snapshot,
        verify=verify,
        portfolio_summary=portfolio_summary,
        curve=curve,
        forecast_review=forecast_review,
    )
    return _generate_narrative(
        "close",
        context,
        settings=settings,
        system="优先当日盈亏、偏差项、明日一条建议。",
        deterministic_fn=_close_deterministic,
    )


# --- Weekly ---


def build_weekly_context(report: dict[str, Any]) -> dict[str, Any]:
    holdings = []
    for h in (report.get("holdings") or [])[:8]:
        holdings.append(
            {
                "code": h.get("code"),
                "name": h.get("name"),
                "week_chg_pct": h.get("week_chg_pct"),
                "unrealized_pnl": h.get("unrealized_pnl"),
            }
        )
    improvements = [
        {
            "title": i.get("title"),
            "detail": (i.get("detail") or "")[:100],
            "action": (i.get("action") or "")[:100],
        }
        for i in (report.get("process_improvements") or [])[:3]
    ]
    return {
        "job": "weekly",
        "week_start": report.get("week_start"),
        "week_end": report.get("week_end"),
        "weekly_pnl": report.get("weekly_pnl"),
        "weekly_pnl_pct": report.get("weekly_pnl_pct"),
        "stock_pnl": report.get("stock_pnl"),
        "cash_pnl": report.get("cash_pnl"),
        "cash_ratio": report.get("cash_ratio"),
        "holdings": holdings,
        "hot_sectors": (report.get("hot_sectors") or [])[:5],
        "process_improvements": improvements,
        "experience_snippets": (report.get("experience_snippets") or [])[:3],
        "notes": report.get("notes") or [],
    }


def _weekly_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    pnl = ctx.get("weekly_pnl")
    pct = ctx.get("weekly_pnl_pct")
    if pnl is not None:
        sign = "+" if float(pnl) >= 0 else ""
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        focus.append(f"本周组合 {sign}¥{float(pnl):,.0f}{pct_s}")
    stock_pnl = ctx.get("stock_pnl")
    cash_pnl = ctx.get("cash_pnl")
    if stock_pnl is not None or cash_pnl is not None:
        focus.append(
            f"盈亏分解：股票 {float(stock_pnl or 0):+,.0f} · 现金 {float(cash_pnl or 0):+,.0f}"
        )
    for sec in ctx.get("hot_sectors") or []:
        name = sec.get("sector") or sec.get("name") or "板块"
        chg = sec.get("avg_change_pct") or sec.get("change_pct")
        if chg is not None:
            focus.append(f"热点 {name} 周均 {float(chg):+.1f}%")
    for imp in ctx.get("process_improvements") or []:
        if imp.get("title"):
            focus.append(f"改进：{imp['title']}")
    for snip in ctx.get("experience_snippets") or []:
        if "偏离" in snip or "否决" in snip:
            risks.append(str(snip)[:120])
    summary = f"周报 {ctx.get('week_start')}~{ctx.get('week_end')}"
    if pnl is not None:
        summary += f"，净值 {float(pnl):+,.0f} 元"
    return {
        "summary": summary,
        "focus_points": focus[:3] or ["复盘本周盈亏与流程改进项"],
        "divergence_notes": [],
        "risk_alerts": risks[:4],
        "planner": "deterministic",
    }


def generate_weekly_narrative(
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_weekly_context(report)
    return _generate_narrative(
        "weekly",
        context,
        settings=settings,
        system="优先本周盈亏分解、一条流程改进、一条经验教训。",
        deterministic_fn=_weekly_deterministic,
    )


# --- Forecast (unchanged logic, unified config) ---


def _week_direction(days: dict[str, Any]) -> str:
    if not days:
        return "flat"
    exp = sum(float(d.get("expected_change_pct") or 0) for d in days.values())
    if exp >= 1.0:
        return "up"
    if exp <= -1.0:
        return "down"
    return "flat"


def build_forecast_context(forecast: dict[str, Any]) -> dict[str, Any]:
    symbols_out: list[dict[str, Any]] = []
    for code, sym in (forecast.get("symbols") or {}).items():
        kronos = sym.get("kronos") or {}
        div_days = sym.get("kronos_divergence_days") or []
        symbols_out.append(
            {
                "code": code,
                "name": sym.get("name") or code,
                "role": sym.get("role") or "",
                "kronos_cum_pct": kronos.get("cum_change_pct"),
                "divergence_days": div_days,
                "week_direction": _week_direction(sym.get("days") or {}),
            }
        )
    mss_rows = [
        {"date": ds, "range": row.get("range"), "median": row.get("median")}
        for ds, row in sorted((forecast.get("mss_daily") or {}).items())
    ]
    news = [
        {"title": ev.get("title"), "summary": (ev.get("summary") or "")[:120]}
        for ev in (forecast.get("news_events") or [])[:3]
    ]
    return {
        "job": "forecast",
        "week_start": forecast.get("week_start"),
        "week_end": forecast.get("week_end"),
        "notes": forecast.get("notes") or [],
        "calibration": forecast.get("calibration_used") or {},
        "symbols": symbols_out,
        "mss_daily": mss_rows,
        "news_events": news,
    }


def _forecast_deterministic(context: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    divergences: list[str] = []
    risks: list[str] = []
    bullish: list[str] = []
    bearish: list[str] = []
    for sym in context.get("symbols") or []:
        name = sym.get("name") or sym.get("code")
        cum = sym.get("kronos_cum_pct")
        if cum is not None:
            if float(cum) >= 1.0:
                bullish.append(f"{name} {float(cum):+.1f}%")
            elif float(cum) <= -1.0:
                bearish.append(f"{name} {float(cum):+.1f}%")
        if sym.get("divergence_days"):
            divergences.append(f"{name}：分歧日 {', '.join(sym['divergence_days'])}")
    if bullish:
        focus.append("Kronos 偏强：" + "、".join(bullish[:4]))
    if bearish:
        focus.append("Kronos 偏弱：" + "、".join(bearish[:4]))
        risks.append("偏弱标的勿追高")
    summary = f"下周 {context.get('week_start')}~{context.get('week_end')} 预测解读"
    return {
        "summary": summary,
        "focus_points": focus[:3] or ["关注 Kronos 路径与 MSS 区间"],
        "divergence_notes": divergences[:2],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def generate_forecast_narrative(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_forecast_context(forecast)
    return _generate_narrative(
        "forecast",
        context,
        settings=settings,
        system="优先 Kronos 强弱、一条 MSS 区间判断、一条新闻影响。",
        deterministic_fn=_forecast_deterministic,
    )


# Backward-compatible aliases
build_narrative_context = build_forecast_context
render_forecast_narrative_markdown = lambda narrative: render_narrative_markdown(narrative, job="forecast")
