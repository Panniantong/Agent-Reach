# -*- coding: utf-8
"""LLM narrative layer for week forecast (Kronos/MC numbers stay unchanged)."""

from __future__ import annotations

import json
from typing import Any, Optional


def _narrative_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    wf = (settings or {}).get("week_forecast") or {}
    cfg = dict(wf.get("llm_narrative") or {})
    if cfg.get("enabled") is False:
        return {"enabled": False}
    harness_llm = ((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if not cfg.get("provider") and harness_llm.get("provider"):
        cfg["provider"] = harness_llm["provider"]
    if not cfg.get("model") and harness_llm.get("model"):
        cfg["model"] = harness_llm["model"]
    cfg.setdefault("enabled", True)
    return cfg


def build_narrative_context(forecast: dict[str, Any]) -> dict[str, Any]:
    """Compact, numeric-safe context for LLM interpretation."""
    symbols_out: list[dict[str, Any]] = []
    for code, sym in (forecast.get("symbols") or {}).items():
        kronos = sym.get("kronos") or {}
        days = sym.get("days") or {}
        div_days = sym.get("kronos_divergence_days") or []
        symbols_out.append(
            {
                "code": code,
                "name": sym.get("name") or code,
                "role": sym.get("role") or "",
                "kronos_available": bool(kronos.get("available")),
                "kronos_cum_pct": kronos.get("cum_change_pct"),
                "kronos_direction": kronos.get("direction_nd"),
                "divergence_days": div_days,
                "week_direction": _week_direction(days),
            }
        )

    mss_rows: list[dict[str, Any]] = []
    for ds, row in sorted((forecast.get("mss_daily") or {}).items()):
        rng = row.get("range") or []
        mss_rows.append(
            {
                "date": ds,
                "range": rng,
                "median": row.get("median"),
            }
        )

    news = [
        {"title": ev.get("title"), "source": ev.get("source"), "summary": (ev.get("summary") or "")[:120]}
        for ev in (forecast.get("news_events") or [])[:6]
    ]

    return {
        "week_start": forecast.get("week_start"),
        "week_end": forecast.get("week_end"),
        "notes": forecast.get("notes") or [],
        "calibration": forecast.get("calibration_used") or {},
        "symbols": symbols_out,
        "mss_daily": mss_rows,
        "news_events": news,
    }


def _week_direction(days: dict[str, Any]) -> str:
    if not days:
        return "flat"
    exp = sum(float(d.get("expected_change_pct") or 0) for d in days.values())
    if exp >= 1.0:
        return "up"
    if exp <= -1.0:
        return "down"
    return "flat"


def _deterministic_narrative(context: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    divergences: list[str] = []
    risks: list[str] = []

    cal = context.get("calibration") or {}
    hit = cal.get("hit_rate")
    if hit is not None:
        focus.append(f"历史预测命中率 {float(hit):.0%}，bias={cal.get('bias_pct', 0):+.2f}%")

    bullish: list[str] = []
    bearish: list[str] = []
    for sym in context.get("symbols") or []:
        name = sym.get("name") or sym.get("code")
        cum = sym.get("kronos_cum_pct")
        if cum is not None:
            if float(cum) >= 1.0:
                bullish.append(f"{name} Kronos 累计 {float(cum):+.1f}%")
            elif float(cum) <= -1.0:
                bearish.append(f"{name} Kronos 累计 {float(cum):+.1f}%")
        div = sym.get("divergence_days") or []
        if div:
            divergences.append(f"{name}：Kronos 与 MC 方向分歧日 {', '.join(div)}")

    if bullish:
        focus.append("Kronos 偏强：" + "、".join(bullish[:4]))
    if bearish:
        focus.append("Kronos 偏弱：" + "、".join(bearish[:4]))
        risks.append("偏弱标的勿追高，等待 MSS 与宏观共振确认")

    for note in context.get("notes") or []:
        if "宏观" in note or "否决" in note or "digest" in note.lower():
            risks.append(str(note)[:120])

    mss = context.get("mss_daily") or []
    if mss:
        medians = [row.get("median") for row in mss if row.get("median") is not None]
        if medians and min(medians) < 40:
            risks.append("下周 MSS 中位偏低，维持高现金与防守仓位")

    summary = f"下周 {context.get('week_start')}~{context.get('week_end')}："
    if bullish or bearish:
        summary += " Kronos 路径已给出强弱分化；"
    if divergences:
        summary += f" {len(divergences)} 只存在 MC/Kronos 分歧，需盘中验证。"
    else:
        summary += " 数值路径与 Kronos 总体一致。"

    return {
        "summary": summary,
        "focus_points": focus[:5] or ["关注持仓与观察池 Kronos 累计方向"],
        "divergence_notes": divergences[:5],
        "risk_alerts": risks[:4],
        "planner": "deterministic",
    }


def generate_forecast_narrative(
    forecast: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Generate interpretation card; does not alter numeric forecast paths."""
    cfg = _narrative_cfg(settings)
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "llm_narrative disabled"}

    context = build_narrative_context(forecast)
    from agent_reach.daily_run.llm_chat import chat_json, resolve_chat_provider

    provider = str(cfg.get("provider") or "auto")
    if resolve_chat_provider(provider):
        payload = chat_json(
            system=(
                "你是 A 股量化助手的 forecast 解读员。基于已算好的 Kronos+MC 数值路径，"
                "输出 JSON："
                '{"summary":"一段总览","focus_points":["..."],'
                '"divergence_notes":["..."], "risk_alerts":["..."]}。'
                "禁止编造具体涨跌幅数字；只能引用输入里已有的数值；"
                "重点解释 Kronos/MC 分歧、MSS 区间、宏观与新闻对操作的影响；中文简洁。"
            ),
            user=json.dumps(context, ensure_ascii=False),
            provider=provider,
            model=cfg.get("model") or None,
            timeout=int(cfg.get("timeout_seconds") or 60),
        )
        if isinstance(payload, dict) and payload.get("summary"):
            payload["planner"] = "llm"
            payload["skipped"] = False
            return payload

    out = _deterministic_narrative(context)
    out["skipped"] = False
    return out


def render_forecast_narrative_markdown(narrative: dict[str, Any]) -> str:
    if narrative.get("skipped"):
        return ""
    lines = ["## 🧠 AI 解读（数值路径不变）", ""]
    if narrative.get("summary"):
        lines.append(str(narrative["summary"]))
        lines.append("")
    if narrative.get("focus_points"):
        lines.append("**本周关注**")
        for item in narrative["focus_points"]:
            lines.append(f"- {item}")
        lines.append("")
    if narrative.get("divergence_notes"):
        lines.append("**Kronos / MC 分歧**")
        for item in narrative["divergence_notes"]:
            lines.append(f"- {item}")
        lines.append("")
    if narrative.get("risk_alerts"):
        lines.append("**风险提示**")
        for item in narrative["risk_alerts"]:
            lines.append(f"- {item}")
    planner = narrative.get("planner")
    if planner:
        lines.append("")
        lines.append(f"_解读来源：{planner}_")
    return "\n".join(lines).strip()


def attach_forecast_narrative(forecast_dict: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    narrative = generate_forecast_narrative(forecast_dict, settings=settings)
    out = dict(forecast_dict)
    out["llm_narrative"] = narrative
    return out
