# -*- coding: utf-8
"""Rule-based report narrative cards (optional LLM) for morning / close / weekly / forecast."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

_JOB_LABELS = {
    "morning": "早报",
    "midday": "午盘分析",
    "intraday": "盘中扫描",
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

_INTRADAY_RISK_LIMITS: dict[str, int] = {
    "max_risk_alerts": 6,
    "max_item_chars": 72,
}

_RISK_SUFFIXES = (
    "摩擦惩罚阻断，预期收益不足以覆盖交易成本",
    "摩擦惩罚阻断",
    "MSS 低于 macro_veto 区间，维持高现金防守",
    "MSS 低于 macro_veto 区间",
)


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


def _format_grouped_symbol_risk(label: str, names: list[str], *, max_show: int = 3) -> str:
    clean = [str(n).strip() for n in names if str(n or "").strip()]
    if not clean:
        return label
    n = len(clean)
    if n == 1:
        return f"{clean[0]}：{label}"
    if n <= max_show:
        return f"{'、'.join(clean)}：{label}"
    head = "、".join(clean[:max_show])
    return f"{head}等{n}只：{label}"


def _split_symbol_risk_line(text: str) -> tuple[str, str] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if "：" in raw:
        prefix, label = raw.split("：", 1)
        prefix = prefix.strip()
        label = label.strip()
        if prefix and label:
            return prefix, label
    for suffix in _RISK_SUFFIXES:
        if raw.endswith(suffix):
            name = raw[: -len(suffix)].strip()
            if name:
                return name, suffix
    return None


def _merge_duplicate_risk_alerts(alerts: list[str] | None) -> list[str]:
    """Merge repeated risk labels (e.g. friction block on many symbols) into one line."""
    groups: dict[str, list[str]] = {}
    passthrough: list[str] = []
    for item in alerts or []:
        parsed = _split_symbol_risk_line(str(item or ""))
        if parsed is None:
            text = str(item or "").strip()
            if text:
                passthrough.append(text)
            continue
        name, label = parsed
        groups.setdefault(label, []).append(name)
    merged = [_format_grouped_symbol_risk(label, names) for label, names in groups.items()]
    return passthrough + merged


def _collect_merged_intraday_risks(symbols: list[dict[str, Any]]) -> list[str]:
    friction: list[str] = []
    macro: list[str] = []
    for sym in symbols:
        name = str(sym.get("name") or sym.get("code") or "").strip()
        if not name:
            continue
        if sym.get("friction_blocked"):
            friction.append(name)
        mss = sym.get("mss_final")
        if mss is not None and float(mss) < 40:
            macro.append(name)
    risks: list[str] = []
    if friction:
        risks.append(_format_grouped_symbol_risk("摩擦惩罚阻断", friction))
    if macro:
        risks.append(_format_grouped_symbol_risk("MSS 低于 macro_veto 区间", macro))
    return risks


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
        _merge_duplicate_risk_alerts(out.get("risk_alerts")),
        max_items=limits["max_risk_alerts"],
        max_chars=limits["max_item_chars"],
    )
    if out.get("trade_operations"):
        out["trade_operations"] = _trim_string_list(
            out.get("trade_operations"),
            max_items=12,
            max_chars=160,
        )
    if out.get("context_trace"):
        out["context_trace"] = _trim_string_list(
            out.get("context_trace"),
            max_items=6,
            max_chars=160,
        )
    verdict = out.get("whatif_verdict")
    if isinstance(verdict, dict):
        trimmed = dict(verdict)
        trimmed["summary"] = _trim_text(trimmed.get("summary"), limits["max_summary_chars"] * 2)
        trimmed["detail_lines"] = _trim_string_list(
            trimmed.get("detail_lines"),
            max_items=5,
            max_chars=120,
        )
        if trimmed.get("harness_note"):
            trimmed["harness_note"] = _trim_text(trimmed.get("harness_note"), 120)
        out["whatif_verdict"] = trimmed
    tuning = out.get("harness_tuning")
    if isinstance(tuning, dict):
        trimmed_tuning = dict(tuning)
        trimmed_tuning["summary"] = _trim_text(trimmed_tuning.get("summary"), limits["max_summary_chars"] * 2)
        for key in ("policy_lines", "plan_lines", "playbook_lines", "execution_lines", "overlay_lines", "notes"):
            if trimmed_tuning.get(key):
                trimmed_tuning[key] = _trim_string_list(
                    trimmed_tuning.get(key),
                    max_items=4 if key == "policy_lines" else 3,
                    max_chars=120,
                )
        out["harness_tuning"] = trimmed_tuning
    evolution = out.get("harness_evolution")
    if isinstance(evolution, dict):
        trimmed_evolution = dict(evolution)
        trimmed_evolution["summary"] = _trim_text(
            trimmed_evolution.get("summary"),
            limits["max_summary_chars"] * 2,
        )
        for key in ("overlay_lines", "execution_lines", "signal_lines", "notes"):
            if trimmed_evolution.get(key):
                trimmed_evolution[key] = _trim_string_list(
                    trimmed_evolution.get(key),
                    max_items=8 if key == "overlay_lines" else 4,
                    max_chars=120,
                )
        out["harness_evolution"] = trimmed_evolution
    return out


def _narrative_system_prompt(job: str, *, limits: dict[str, int]) -> str:
    label = _JOB_LABELS.get(job, job)
    trade_hint = ""
    if job == "intraday":
        trade_hint = (
            "若有 trade_operations 输入，summary 须概括 T 编号调仓动作（买入/卖出/观望）；"
            "禁止编造未提供的成交价/股数。"
        )
    elif job == "close":
        trade_hint = (
            '若有 trade_operations 输入，summary 须概括当日买卖与已实现盈亏；'
            'focus_points 可含明日建议；禁止编造未提供的成交价/股数。'
        )
    return (
        f"你是 A 股量化助手 {label} AI 解读员。基于已给数据输出 JSON："
        '{"summary":"...","focus_points":["..."],'
        '"divergence_notes":[],"risk_alerts":[]}。'
        f"summary 一句总结今日/本周关注点，≤{limits['max_summary_chars']}字；"
        f"focus_points 最多 {limits['max_focus_points']} 条、每条 ≤{limits['max_item_chars']}字；"
        f"divergence_notes 仅实质分歧时填，最多 {limits['max_divergence_notes']} 条；"
        f"risk_alerts 最多 {limits['max_risk_alerts']} 条。"
        f"{trade_hint}"
        "禁止编造未提供数字；禁止复述输入；省略废话；中文。"
    )


def _narrative_cfg(settings: Optional[dict[str, Any]], job: str) -> dict[str, Any]:
    root = dict((settings or {}).get("llm_narrative") or {})
    if job == "forecast":
        wf = dict(((settings or {}).get("week_forecast") or {}).get("llm_narrative") or {})
        for key, val in wf.items():
            if key != "jobs" and val is not None:
                root[key] = val
    if job == "midday":
        md = dict(((settings or {}).get("midday") or {}).get("llm_narrative") or {})
        for key, val in md.items():
            if val is not None:
                root[key] = val
    jobs = root.get("jobs") or {}
    if isinstance(jobs, dict) and job in jobs:
        entry = jobs[job]
        if entry is False:
            return {"enabled": False}
        if isinstance(entry, dict):
            if entry.get("enabled") is False:
                return {"enabled": False}
            for key in (
                "planner",
                "provider",
                "model",
                "timeout_seconds",
                "max_output_tokens",
            ):
                if entry.get(key) is not None:
                    root[key] = entry[key]
    if root.get("enabled") is False:
        return {"enabled": False}
    harness_llm = ((settings or {}).get("harness") or {}).get("llm_refine") or {}
    if not root.get("provider") and harness_llm.get("provider"):
        root["provider"] = harness_llm["provider"]
    if not root.get("model") and harness_llm.get("model"):
        root["model"] = harness_llm["model"]
    root.setdefault("enabled", True)
    root.setdefault("planner", "deterministic")
    return root


def narrative_use_llm(cfg: dict[str, Any]) -> bool:
    """``deterministic`` = code-only (no LLM tokens); ``llm`` = call provider when available."""
    return str(cfg.get("planner") or "deterministic").strip().lower() == "llm"


def _morning_focus_hint() -> str:
    return "优先 verdict、MSS 变化、现金比例。"


def _narrative_supplement_fields(
    *,
    snapshot: Optional[dict[str, Any]] = None,
    portfolio_summary: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
    include_hit_summary: bool = False,
) -> dict[str, str]:
    from agent_reach.daily_run.watchlist_intel import watchlist_intel_narrative_summary
    from agent_reach.daily_run.xueqiu_stock_search import xueqiu_stock_search_summary

    out = {
        "watchlist_intel_summary": watchlist_intel_narrative_summary(
            snapshot,
            portfolio_summary=portfolio_summary,
        ),
        "xueqiu_stock_search_summary": xueqiu_stock_search_summary(macro_signals),
    }
    if include_hit_summary:
        out["xueqiu_hit_summary"] = _xueqiu_hit_narrative_summary()
    return out


def _xueqiu_hit_narrative_summary(*, min_samples: int = 3) -> str:
    from agent_reach.daily_run.xueqiu_hit_outcomes import summarize_xueqiu_hit_outcomes

    stats = summarize_xueqiu_hit_outcomes()
    total = int(stats.get("total") or 0)
    if total < min_samples:
        return ""
    hr = stats.get("hit_rate")
    hr_s = f"{float(hr):.0%}" if isinstance(hr, (int, float)) else "—"
    return f"雪球热榜命中率 {hr_s}（近 {stats.get('window_days', 30)} 日 {total} 条）"


def _narrative_intel_focus(ctx: dict[str, Any]) -> list[str]:
    """Extra deterministic focus lines: watchlist intel + search (when not in hot summary)."""
    extras: list[str] = []
    intel = str(ctx.get("watchlist_intel_summary") or "").strip()
    if intel:
        extras.append(intel[:100])
    search = str(ctx.get("xueqiu_stock_search_summary") or "").strip()
    hot = str(ctx.get("xueqiu_hot_summary") or "").strip()
    if search and search != hot and search not in hot:
        extras.append(search[:100])
    exa = str(ctx.get("xueqiu_exa_summary") or "").strip()
    if exa:
        extras.append(exa[:100])
    hit = str(ctx.get("xueqiu_hit_summary") or "").strip()
    if hit:
        extras.append(hit[:100])
    return extras


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
    if job == "intraday":
        limits = dict(limits)
        for key, val in _INTRADAY_RISK_LIMITS.items():
            limits[key] = max(int(limits.get(key, 0)), int(val))
    compact_context = _compact_context(context, limits)
    base_system = _narrative_system_prompt(job, limits=limits)
    hint = system.strip()
    use_system = f"{base_system} {hint}".strip() if hint else base_system

    if narrative_use_llm(cfg):
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
    if job in ("close", "weekly") and isinstance(out, dict) and not out.get("skipped"):
        out = _attach_rule_interpretation_extras(out, context, settings=settings)
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
        "midday": "午后策略",
        "intraday": "盘中小结",
        "close": "复盘摘要",
        "weekly": "周报摘要",
    }
    sub = subtitles.get(use_job, "规则解读")
    lines = [f"## 📋 规则解读（{sub}）", ""]
    if narrative.get("summary"):
        lines.append(str(narrative["summary"]))
    verdict = narrative.get("whatif_verdict")
    if isinstance(verdict, dict) and (verdict.get("summary") or verdict.get("detail_lines")):
        lines.append("")
        lines.append("**基准值 vs 自进化**")
        if verdict.get("summary"):
            lines.append(str(verdict["summary"]))
        for item in verdict.get("detail_lines") or []:
            lines.append(f"- {item}")
        if verdict.get("harness_note"):
            lines.append(f"- _{verdict['harness_note']}_")
    harness_tuning = narrative.get("harness_tuning")
    if isinstance(harness_tuning, dict) and (
        harness_tuning.get("summary")
        or harness_tuning.get("policy_lines")
        or harness_tuning.get("execution_lines")
    ):
        lines.append("")
        lines.append("**Harness 调参总结**")
        if harness_tuning.get("summary"):
            lines.append(str(harness_tuning["summary"]))
        for item in harness_tuning.get("policy_lines") or []:
            lines.append(f"- 策略：{item}")
        for item in harness_tuning.get("plan_lines") or []:
            lines.append(f"- 计划：{item}")
        for item in harness_tuning.get("playbook_lines") or []:
            lines.append(f"- 演练：{item}")
        for item in harness_tuning.get("execution_lines") or []:
            lines.append(f"- 执行：{item}")
        for item in harness_tuning.get("overlay_lines") or []:
            lines.append(f"- 参数：{item}")
        for item in harness_tuning.get("notes") or []:
            lines.append(f"- _{item}_")
    harness_evolution = narrative.get("harness_evolution")
    if isinstance(harness_evolution, dict) and (
        harness_evolution.get("summary")
        or harness_evolution.get("overlay_lines")
        or harness_evolution.get("execution_lines")
    ):
        lines.append("")
        lines.append("**Harness 进化总结**")
        if harness_evolution.get("summary"):
            lines.append(str(harness_evolution["summary"]))
        for item in harness_evolution.get("overlay_lines") or []:
            lines.append(f"- 参数：{item}")
        for item in harness_evolution.get("signal_lines") or []:
            lines.append(f"- 信号：{item}")
        for item in harness_evolution.get("execution_lines") or []:
            lines.append(f"- 执行：{item}")
        for item in harness_evolution.get("notes") or []:
            lines.append(f"- _{item}_")
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
    if narrative.get("trade_operations"):
        lines.append("")
        trade_title = "**调仓操作**" if use_job == "intraday" else "**当日买卖**"
        lines.append(trade_title)
        for item in narrative["trade_operations"]:
            lines.append(f"- {item}")
    if narrative.get("context_trace"):
        lines.append("")
        lines.append("**上下文轨迹**")
        for item in narrative["context_trace"]:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


def _attach_context_trace(
    narrative: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    job: str = "",
    ctx: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.context_layers import build_context_trace
    from agent_reach.daily_run.settings import effective_settings

    cfg = effective_settings(settings)
    trace = build_context_trace(cfg, job=job or str(narrative.get("job") or ""), ctx=ctx)
    if trace:
        narrative["context_trace"] = trace
    return narrative


# --- Morning ---


def build_morning_context(
    snapshot: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    pf = snapshot.get("portfolio") or {}
    holdings = pf.get("holdings") or []
    macro_signals = snapshot.get("macro_signals") or {}
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_hot_context_summary,
    )

    supplements = _narrative_supplement_fields(snapshot=snapshot, macro_signals=macro_signals)
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
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        **supplements,
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
    overlap = (
        ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(1, overlap[:100])
    for idx, extra in enumerate(_narrative_intel_focus(ctx)):
        focus.insert(2 + idx, extra)
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


def generate_midday_narrative(
    scan_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    scan = scan_result.get("scan") or {}
    report = (scan_result.get("evaluation") or {}).get("report") or {}
    context = {
        "job": "midday",
        "scan_id": scan.get("scan_id"),
        "mss_final": scan.get("mss_final") or report.get("mss_final"),
        "verdict": scan.get("verdict") or report.get("verdict"),
        "lookback_mss": scan_result.get("lookback_mss"),
        "trend": scan_result.get("trend"),
        "macro_summary": (scan_result.get("enriched") or {}).get("macro_summary"),
        "summary": f"午盘 refresh · {scan.get('verdict') or report.get('verdict') or '观察'}",
        "focus_points": [],
        "risk_alerts": [],
    }

    def _deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": str(ctx.get("summary") or "午盘分析"),
            "focus_points": [
                f"Lookback MSS {float(ctx.get('lookback_mss') or 0):.1f}",
                "13:00 开盘后以新扫描确认",
            ],
            "divergence_notes": [],
            "risk_alerts": [],
            "planner": "deterministic",
        }

    return _attach_context_trace(
        _generate_narrative(
            "midday",
            context,
            settings=settings,
            system="解读午盘 refresh：上午回顾、午休宏观、午后 Lookback 与策略。",
            deterministic_fn=_deterministic,
        ),
        settings=settings,
        job="midday",
        ctx=context,
    )


def generate_morning_narrative(
    snapshot: dict[str, Any],
    report: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_morning_context(snapshot, report)
    return _attach_context_trace(
        _generate_narrative(
            "morning",
            context,
            settings=settings,
            system=_morning_focus_hint(),
            deterministic_fn=_morning_deterministic,
        ),
        settings=settings,
        job="morning",
        ctx=context,
    )


def merge_narrative_single_call(settings: Optional[dict[str, Any]]) -> bool:
    """When merge_by_category push is on, one LLM call for the whole portfolio."""
    cfg = (settings or {}).get("llm_narrative") or {}
    if "merge_single_call" in cfg:
        return bool(cfg["merge_single_call"])
    return True


def build_merged_morning_context(
    entries: list[tuple[str, str, dict[str, Any]]],
    *,
    primary_snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    for name, code, report in entries:
        symbols.append(
            {
                "name": name,
                "code": code,
                "verdict": report.get("verdict"),
                "mss_final": report.get("mss_final"),
                "prior_close_delta": report.get("prior_close_delta"),
                "confidence": report.get("confidence"),
            }
        )
    pf = (primary_snapshot or {}).get("portfolio") or {}
    macro_signals = (primary_snapshot or {}).get("macro_signals") or {}
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_hot_context_summary,
    )

    supplements = _narrative_supplement_fields(
        snapshot=primary_snapshot,
        macro_signals=macro_signals,
    )
    return {
        "job": "morning",
        "portfolio_scope": "merged",
        "symbol_count": len(symbols),
        "symbols": symbols,
        "cash_ratio": pf.get("cash_ratio"),
        "holdings_count": len(pf.get("holdings") or []),
        "macro_summary": ((primary_snapshot or {}).get("macro_summary") or "")[:120],
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        **supplements,
    }


def _merged_morning_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    symbols = ctx.get("symbols") or []
    focus: list[str] = []
    risks: list[str] = []
    n = int(ctx.get("symbol_count") or len(symbols))
    verdicts = [str(s.get("verdict")) for s in symbols if s.get("verdict")]
    mss_vals = [float(s["mss_final"]) for s in symbols if s.get("mss_final") is not None]
    if verdicts:
        dominant = max(set(verdicts), key=verdicts.count)
        focus.append(f"{n}只标的，主导结论 **{dominant}**")
    if mss_vals:
        focus.append(f"MSS 区间 {min(mss_vals):.1f}~{max(mss_vals):.1f}")
    cash = ctx.get("cash_ratio")
    if cash is not None:
        focus.append(f"组合现金 {float(cash):.0%}")
    overlap = (
        ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(1, overlap[:100])
    for idx, extra in enumerate(_narrative_intel_focus(ctx)):
        focus.insert(2 + idx, extra)
    if mss_vals and min(mss_vals) < 40:
        risks.append("部分标的 MSS 低于宏观否决线")
    summary = f"早盘全持仓 {n} 只"
    if mss_vals:
        summary += f"，MSS {min(mss_vals):.1f}~{max(mss_vals):.1f}"
    return {
        "summary": summary,
        "focus_points": focus[:3] or ["按 MSS 与宏观一票否决规则执行"],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def generate_merged_morning_narrative(
    entries: list[tuple[str, str, dict[str, Any]]],
    *,
    primary_snapshot: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_merged_morning_context(entries, primary_snapshot=primary_snapshot)
    return _attach_context_trace(
        _generate_narrative(
            "morning",
            context,
            settings=settings,
            system=f"{_morning_focus_hint()} 全组合视角，跨标的归纳，勿逐只复述。",
            deterministic_fn=_merged_morning_deterministic,
        ),
        settings=settings,
        job="morning",
        ctx=context,
    )


def _morning_narrative_cache_path(d: Optional[Any] = None) -> Path:
    from agent_reach.daily_run.trade_calendar import today_shanghai

    day = d.isoformat() if d is not None and hasattr(d, "isoformat") else today_shanghai().isoformat()
    return Path.home() / ".agent-reach" / "daily_run" / "cache" / f"morning_narrative_{day}.json"


def persist_morning_narrative(narrative: dict[str, Any], *, code: Optional[str] = None) -> None:
    """Cache today's morning AI narrative for intraday cards (portfolio or per-symbol)."""
    if not narrative or narrative.get("skipped"):
        return
    path = _morning_narrative_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    if code:
        from agent_reach.daily_run.snapshot_builder import _normalize_code

        payload["by_code"] = dict(payload.get("by_code") or {})
        payload["by_code"][_normalize_code(code)] = narrative
    else:
        payload["portfolio"] = narrative
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_today_morning_narrative(
    settings: Optional[dict[str, Any]] = None,
    *,
    code: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Load today's morning llm_narrative (cache first, then run manifest)."""
    from agent_reach.daily_run.run_manifest import runs_dir
    from agent_reach.daily_run.trade_calendar import today_shanghai

    if not intraday_append_morning_narrative(settings):
        return None

    today = today_shanghai().isoformat()
    cache_path = _morning_narrative_cache_path(today_shanghai())
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if code:
                from agent_reach.daily_run.snapshot_builder import _normalize_code

                by_code = cached.get("by_code") or {}
                hit = by_code.get(_normalize_code(code))
                if isinstance(hit, dict) and not hit.get("skipped"):
                    return hit
            portfolio = cached.get("portfolio")
            if isinstance(portfolio, dict) and not portfolio.get("skipped"):
                return portfolio
        except (json.JSONDecodeError, OSError):
            pass

    out_dir = runs_dir() / today
    if not out_dir.is_dir():
        return None

    for path in sorted(out_dir.glob("morning_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        payload = data.get("payload") or {}
        if payload.get("skipped"):
            continue

        symbol_results = payload.get("symbol_results") or []
        if symbol_results:
            if code:
                from agent_reach.daily_run.snapshot_builder import _normalize_code

                norm = _normalize_code(code)
                for row in symbol_results:
                    if _normalize_code(str(row.get("code") or "")) != norm:
                        continue
                    narrative = (row.get("result") or {}).get("llm_narrative")
                    if isinstance(narrative, dict) and not narrative.get("skipped"):
                        return narrative
            for row in symbol_results:
                narrative = (row.get("result") or {}).get("llm_narrative")
                if isinstance(narrative, dict) and not narrative.get("skipped"):
                    return narrative
            continue

        narrative = (payload.get("result") or {}).get("llm_narrative")
        if isinstance(narrative, dict) and not narrative.get("skipped"):
            return narrative
    return None


def intraday_append_narrative(settings: Optional[dict[str, Any]] = None) -> bool:
    intraday = (settings or {}).get("intraday") or {}
    if "append_narrative" in intraday:
        return intraday["append_narrative"] is not False
    return intraday.get("append_morning_narrative", True) is not False


def intraday_append_morning_narrative(settings: Optional[dict[str, Any]] = None) -> bool:
    """Backward-compatible alias for intraday_append_narrative."""
    return intraday_append_narrative(settings)


def render_morning_narrative_footer(
    settings: Optional[dict[str, Any]] = None,
    *,
    code: Optional[str] = None,
) -> str:
    """Legacy inline footer from cached morning narrative."""
    narrative = load_today_morning_narrative(settings, code=code)
    if not narrative:
        return ""
    md = render_narrative_markdown(narrative, job="morning")
    if not md.strip():
        return ""
    return "\n\n---\n\n" + md


def _intraday_row_context(row: dict[str, Any]) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import extract_intraday_trade_record

    inner = row.get("result") or {}
    scan_wrap = inner.get("scan") or {}
    scan = scan_wrap.get("scan") or {}
    evaluation = scan_wrap.get("evaluation") or {}
    report = evaluation.get("report") or {}
    trade = inner.get("trade") or {}
    decision = trade.get("decision") or {}
    trade_record = extract_intraday_trade_record(trade) or {}
    return {
        "name": row.get("name") or scan.get("name"),
        "code": row.get("code") or scan.get("code"),
        "scan_id": scan.get("scan_id"),
        "mss_final": scan.get("mss_final"),
        "verdict": scan.get("verdict"),
        "lookback_mss": scan_wrap.get("lookback_mss"),
        "trend": scan_wrap.get("trend"),
        "reasoning": (report.get("reasoning") or "")[:96],
        "trade_action": decision.get("action") or trade_record.get("action"),
        "trade_reasoning": (decision.get("reasoning") or trade_record.get("reasoning") or "")[:96],
        "trade_id": trade_record.get("trade_id"),
        "trade_record": trade_record or None,
        "friction_blocked": decision.get("friction_blocked") or trade_record.get("friction_blocked"),
        "portfolio_applied": trade_record.get("portfolio_applied"),
        "blocked": trade_record.get("blocked") or decision.get("blocked"),
        "portfolio_message": trade_record.get("portfolio_message"),
        "cash_limit_bypass": trade_record.get("cash_limit_bypass"),
        "consecutive_buy_streak": trade_record.get("consecutive_buy_streak"),
        "case_uri": trade_record.get("case_uri"),
    }


def build_intraday_context(
    *,
    scan_result: dict[str, Any],
    trade_result: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import extract_intraday_trade_record
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_exa_research_summary,
        xueqiu_hot_context_summary,
    )

    scan = scan_result.get("scan") or {}
    evaluation = scan_result.get("evaluation") or {}
    report = evaluation.get("report") or {}
    decision = (trade_result or {}).get("decision") or {}
    trade_record = extract_intraday_trade_record(trade_result) or {}
    lookback_detail = [
        {
            "scan_id": item.get("scan_id"),
            "mss_final": item.get("mss_final"),
            "weight": item.get("weight"),
        }
        for item in (scan_result.get("lookback_detail") or [])[:3]
    ]
    xq_signals = macro_signals or scan_result.get("xueqiu_cross") or {}
    return {
        "job": "intraday",
        "scan_id": scan.get("scan_id"),
        "name": scan.get("name"),
        "code": scan.get("code"),
        "mss_final": scan.get("mss_final"),
        "verdict": scan.get("verdict"),
        "lookback_mss": scan_result.get("lookback_mss"),
        "trend": scan_result.get("trend"),
        "reasoning": (report.get("reasoning") or "")[:120],
        "lookback_detail": lookback_detail,
        "trade_action": decision.get("action") or trade_record.get("action"),
        "trade_reasoning": (decision.get("reasoning") or trade_record.get("reasoning") or "")[:120],
        "trade_id": trade_record.get("trade_id"),
        "trade_record": trade_record or None,
        "friction_blocked": decision.get("friction_blocked") or trade_record.get("friction_blocked"),
        "portfolio_applied": trade_record.get("portfolio_applied"),
        "blocked": trade_record.get("blocked") or decision.get("blocked"),
        "trade_skip_reason": scan_result.get("trade_skip_reason"),
        "portfolio_message": trade_record.get("portfolio_message"),
        "cash_limit_bypass": trade_record.get("cash_limit_bypass"),
        "consecutive_buy_streak": trade_record.get("consecutive_buy_streak"),
        "case_uri": trade_record.get("case_uri"),
        "xueqiu_hot_summary": xueqiu_hot_context_summary(xq_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(xq_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(xq_signals),
        "portfolio_hot_stocks_new_summary": portfolio_hot_stocks_new_summary(xq_signals),
        "xueqiu_exa_summary": xueqiu_exa_research_summary(xq_signals),
    }


def _intraday_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    scan_id = ctx.get("scan_id") or "S?"
    verdict = ctx.get("verdict") or "—"
    mss = ctx.get("mss_final")
    lookback = ctx.get("lookback_mss")
    if lookback is not None:
        focus.append(f"Lookback MSS {lookback}" + (f"，趋势 {ctx.get('trend')}" if ctx.get("trend") else ""))
    overlap = (
        ctx.get("portfolio_hot_stocks_new_summary")
        or ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(0, overlap[:100])
    for extra in _narrative_intel_focus(ctx):
        if extra not in focus:
            focus.insert(min(1, len(focus)), extra)
    if ctx.get("trade_action"):
        action = str(ctx["trade_action"])
        action_map = {"buy": "买入", "sell": "卖出", "hold": "观望", "skip": "跳过"}
        focus.append(f"调仓建议 {action_map.get(action, action)}")
        if ctx.get("trade_reasoning"):
            focus.append(str(ctx["trade_reasoning"])[:72])
    elif ctx.get("trade_skip_reason"):
        focus.append(str(ctx["trade_skip_reason"])[:72])
    if ctx.get("reasoning"):
        focus.append(str(ctx["reasoning"])[:72])
    if ctx.get("friction_blocked"):
        risks.append("摩擦惩罚阻断，预期收益不足以覆盖交易成本")
    if mss is not None and float(mss) < 40:
        risks.append("MSS 低于 macro_veto 区间，维持高现金防守")
    summary = f"{scan_id} {ctx.get('name') or ctx.get('code')}：{verdict}"
    if mss is not None:
        summary += f"，MSS {mss}"
    trade_id = ctx.get("trade_id")
    if trade_id and ctx.get("trade_action"):
        action_map = {"buy": "买入", "sell": "卖出", "hold": "观望", "skip": "跳过"}
        summary += f"，{trade_id} {action_map.get(str(ctx['trade_action']), ctx['trade_action'])}"
    return {
        "summary": summary,
        "focus_points": focus[:3] or [f"{scan_id} 扫描完成，按 MSS 规则执行"],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def _attach_intraday_trade_operations(
    narrative: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import format_intraday_trade_narrative_lines

    def _entry(row: dict[str, Any]) -> Optional[dict[str, Any]]:
        record = row.get("trade_record")
        if not record and row.get("trade_action"):
            record = {
                "action": row.get("trade_action"),
                "trade_id": row.get("trade_id"),
                "reasoning": row.get("trade_reasoning"),
                "portfolio_applied": row.get("portfolio_applied"),
                "portfolio_message": row.get("portfolio_message"),
                "blocked": row.get("blocked"),
                "block_kind": row.get("block_kind"),
                "friction_blocked": row.get("friction_blocked"),
                "cash_limit_bypass": row.get("cash_limit_bypass"),
                "consecutive_buy_streak": row.get("consecutive_buy_streak"),
                "name": row.get("name"),
                "code": row.get("code"),
            }
        if not record:
            return None
        return {
            "name": row.get("name"),
            "code": row.get("code"),
            "scan_id": row.get("scan_id"),
            "mss_final": row.get("mss_final"),
            "lookback_mss": row.get("lookback_mss"),
            "trend": row.get("trend"),
            "verdict": row.get("verdict"),
            "friction_blocked": row.get("friction_blocked"),
            "trade_record": record,
        }

    if context.get("portfolio_scope") == "merged":
        entries = [
            item
            for sym in (context.get("symbols") or [])
            if (item := _entry(sym)) is not None
        ]
    else:
        single = _entry(context)
        entries = [single] if single else []
    ops = format_intraday_trade_narrative_lines(entries)
    if ops:
        narrative["trade_operations"] = ops
    return narrative


def generate_intraday_narrative(
    *,
    scan_result: dict[str, Any],
    trade_result: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_intraday_context(
        scan_result=scan_result,
        trade_result=trade_result,
        macro_signals=macro_signals,
    )
    return _attach_context_trace(
        _attach_intraday_trade_operations(
            _generate_narrative(
                "intraday",
                context,
                settings=settings,
                system="解读本次盘中扫描与调仓评估结果；优先 MSS、Lookback、调仓动作。",
                deterministic_fn=_intraday_deterministic,
            ),
            context,
        ),
        settings=settings,
        job="intraday",
        ctx=context,
    )


def build_merged_intraday_context(
    symbol_results: list[dict[str, Any]],
    *,
    scan_id: Optional[str] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_exa_research_summary,
        xueqiu_hot_context_summary,
    )

    symbols = [_intraday_row_context(row) for row in symbol_results if not row.get("skipped")]
    return {
        "job": "intraday",
        "portfolio_scope": "merged",
        "scan_id": scan_id or (symbols[0].get("scan_id") if symbols else None),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        "portfolio_hot_stocks_new_summary": portfolio_hot_stocks_new_summary(macro_signals),
        "xueqiu_exa_summary": xueqiu_exa_research_summary(macro_signals),
    }


def _merged_intraday_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    symbols = ctx.get("symbols") or []
    n = int(ctx.get("symbol_count") or len(symbols))
    scan_id = ctx.get("scan_id") or "S?"
    mss_vals = [float(s["mss_final"]) for s in symbols if s.get("mss_final") is not None]
    verdicts = [str(s.get("verdict") or "") for s in symbols if s.get("verdict")]
    dominant = max(set(verdicts), key=verdicts.count) if verdicts else "—"
    if mss_vals:
        focus.append(f"MSS 区间 {min(mss_vals):.1f}~{max(mss_vals):.1f}")
    overlap = (
        ctx.get("portfolio_hot_stocks_new_summary")
        or ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(0, overlap[:100])
    for extra in _narrative_intel_focus(ctx):
        if extra not in focus:
            focus.insert(min(1, len(focus)), extra)
    focus.append(f"{n} 只标的，主导结论 {dominant}")
    risks = _collect_merged_intraday_risks(symbols)
    trade_records = [sym.get("trade_record") for sym in symbols if sym.get("trade_record")]
    if trade_records:
        action_map = {"buy": "买入", "sell": "卖出", "hold": "观望", "skip": "跳过"}
        trade_ids = [
            f"{rec.get('trade_id') or '调仓'} {action_map.get(str(rec.get('action') or ''), rec.get('action') or '')}"
            for rec in trade_records[:3]
        ]
        if trade_ids:
            focus.append(f"调仓 {len(trade_records)} 只：{' · '.join(trade_ids)}")
    summary = f"{scan_id} 全持仓 {n} 只扫描"
    if mss_vals:
        summary += f"，MSS {min(mss_vals):.1f}~{max(mss_vals):.1f}"
    if trade_records:
        summary += f"，调仓 {len(trade_records)} 只"
    return {
        "summary": summary,
        "focus_points": focus[:3] or [f"{scan_id} 扫描完成"],
        "divergence_notes": [],
        "risk_alerts": risks,
        "planner": "deterministic",
    }


def generate_merged_intraday_narrative(
    symbol_results: list[dict[str, Any]],
    *,
    scan_id: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_merged_intraday_context(
        symbol_results,
        scan_id=scan_id,
        macro_signals=macro_signals,
    )
    return _attach_context_trace(
        _attach_intraday_trade_operations(
            _generate_narrative(
                "intraday",
                context,
                settings=settings,
                system="解读本次定时盘中任务的整体扫描与调仓结论；禁止复述早报。",
                deterministic_fn=_merged_intraday_deterministic,
            ),
            context,
        ),
        settings=settings,
        job="intraday",
        ctx=context,
    )


def intraday_narrative_card_title(
    *,
    scan_id: Optional[str] = None,
    symbol_count: int = 1,
) -> str:
    if scan_id:
        return f"📋 盘中规则解读 · {scan_id} · {symbol_count}只"
    return f"📋 盘中规则解读 · {symbol_count}只"


def push_intraday_narrative_card(
    config,
    settings: dict[str, Any],
    *,
    scan_id: Optional[str] = None,
    symbol_count: int = 1,
    scan_result: Optional[dict[str, Any]] = None,
    trade_result: Optional[dict[str, Any]] = None,
    symbol_results: Optional[list[dict[str, Any]]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Push AI interpretation of this intraday scheduled run (always last)."""
    if not intraday_append_narrative(settings):
        return None
    xq_signals = macro_signals
    if xq_signals is None and scan_result:
        xq_signals = scan_result.get("xueqiu_cross")
    if symbol_results and len(symbol_results) > 1:
        narrative = generate_merged_intraday_narrative(
            symbol_results,
            scan_id=scan_id,
            settings=settings,
            macro_signals=xq_signals,
        )
    elif scan_result:
        narrative = generate_intraday_narrative(
            scan_result=scan_result,
            trade_result=trade_result,
            settings=settings,
            macro_signals=xq_signals,
        )
    elif symbol_results:
        row = next((r for r in symbol_results if not r.get("skipped")), None)
        if not row:
            return None
        inner = row.get("result") or {}
        if xq_signals is None:
            scan_payload = inner.get("scan") or {}
            xq_signals = scan_payload.get("xueqiu_cross")
        narrative = generate_intraday_narrative(
            scan_result=inner.get("scan") or {},
            trade_result=inner.get("trade"),
            settings=settings,
            macro_signals=xq_signals,
        )
    else:
        return None
    if narrative.get("skipped"):
        return None
    md = render_narrative_markdown(narrative, job="intraday")
    if not md.strip():
        return None
    from agent_reach.integrations.feishu import send_card

    tpl = (settings.get("report") or {}).get("feishu_template_intraday", "orange")
    title = intraday_narrative_card_title(scan_id=scan_id, symbol_count=symbol_count)
    return send_card(config, title, md, template=tpl)


# --- Close ---


def build_close_context(
    *,
    snapshot: dict[str, Any],
    verify: dict[str, Any],
    portfolio_summary: Optional[dict[str, Any]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import extract_close_trade_operations
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_hot_context_summary,
    )

    trade_ops = extract_close_trade_operations(portfolio_summary)
    sell_rules_whatif = (portfolio_summary or {}).get("sell_rules_whatif")
    macro_signals = snapshot.get("macro_signals") or {}
    ctx = {
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
        "realized_pnl": (portfolio_summary or {}).get("realized_pnl"),
        "cumulative_realized_pnl": (portfolio_summary or {}).get("cumulative_realized_pnl"),
        "total_unrealized": (portfolio_summary or {}).get("total_unrealized"),
        "total_return_pnl": (portfolio_summary or {}).get("total_return_pnl"),
        "trade_operations": trade_ops,
        "sell_rules_whatif": sell_rules_whatif,
        "buy_rules_whatif": (portfolio_summary or {}).get("buy_rules_whatif"),
        "intraday_friction_whatif": (portfolio_summary or {}).get("intraday_friction_whatif"),
        "intraday_sell_whatif": (portfolio_summary or {}).get("intraday_sell_whatif"),
        "harness_result": (portfolio_summary or {}).get("harness_result"),
        "curve_trend": (curve or {}).get("trend"),
        "forecast_review_accuracy": (forecast_review or {}).get("accuracy"),
        "macro_summary": (snapshot.get("macro_summary") or "")[:120],
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        **_narrative_supplement_fields(
            snapshot=snapshot,
            portfolio_summary=portfolio_summary,
            macro_signals=macro_signals,
        ),
    }
    return ctx


def _attach_close_trade_operations(
    narrative: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import format_trade_operations_narrative_lines

    ops = format_trade_operations_narrative_lines(
        list(context.get("trade_operations") or []),
        realized_pnl_total=context.get("realized_pnl"),
    )
    if ops:
        narrative["trade_operations"] = ops
    return narrative


def build_baseline_evolved_verdict(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Synthesize what-if blocks into an overall baseline vs evolved verdict for 规则解读."""
    sell = ctx.get("sell_rules_whatif") or {}
    buy = ctx.get("buy_rules_whatif") or {}
    friction = ctx.get("intraday_friction_whatif") or {}
    intraday_sell = ctx.get("intraday_sell_whatif") or {}

    has_any = any(block and not block.get("skipped") for block in (sell, buy, friction, intraday_sell))
    if not has_any:
        return None

    detail_lines: list[str] = []
    highlights: list[str] = []
    evolved_score = 0
    baseline_score = 0
    harness_note = ""

    daily_pnl = ctx.get("portfolio_daily_pnl")
    if daily_pnl is None:
        daily_pnl = ctx.get("weekly_pnl")
    pnl_negative = daily_pnl is not None and float(daily_pnl) < 0

    if sell and not sell.get("skipped"):
        actual_pnl = float(sell.get("actual_realized_pnl") or 0)
        hypo_pnl = float(sell.get("hypothetical_realized_pnl") or 0)
        pnl_delta = float(sell.get("realized_pnl_delta") or 0)
        if pnl_delta >= 200:
            evolved_score += 1
            sell_winner = "自进化"
            highlights.append(f"卖出少亏 ¥{pnl_delta:,.0f}")
        elif pnl_delta <= -200:
            baseline_score += 1
            sell_winner = "基准值"
            highlights.append(f"卖出多赚 ¥{abs(pnl_delta):,.0f}")
        else:
            sell_winner = "持平"
        sign_a = "+" if actual_pnl >= 0 else ""
        sign_h = "+" if hypo_pnl >= 0 else ""
        sign_d = "+" if pnl_delta >= 0 else ""
        detail_lines.append(
            f"卖出：基准已实现 {sign_a}¥{actual_pnl:,.0f} → 自进化 {sign_h}¥{hypo_pnl:,.0f}"
            f"（差 {sign_d}¥{pnl_delta:,.0f}，{sell_winner}更优）"
        )

    if buy and not buy.get("skipped"):
        actual_n = float(buy.get("actual_buy_notional") or 0)
        hypo_n = float(buy.get("hypothetical_buy_notional") or 0)
        notional_delta = float(buy.get("buy_notional_delta") or 0)
        if abs(notional_delta) >= 5000:
            if pnl_negative and notional_delta <= -5000:
                evolved_score += 1
                buy_winner = "自进化"
                highlights.append(f"买入少部署 ¥{abs(notional_delta):,.0f}")
                harness_note = (
                    "harness 买入侧会标「基准更优」（机制性少买判定），"
                    "但按当日盈亏应是自进化更优"
                )
            elif (not pnl_negative) and notional_delta >= 5000:
                evolved_score += 1
                buy_winner = "自进化"
                highlights.append(f"买入多部署 ¥{notional_delta:,.0f}")
            elif pnl_negative and notional_delta >= 5000:
                baseline_score += 1
                buy_winner = "基准值"
            elif (not pnl_negative) and notional_delta <= -5000:
                baseline_score += 1
                buy_winner = "基准值"
                harness_note = "harness 买入侧标「基准更优」，上涨日可能错失加仓机会"
            else:
                buy_winner = "持平"
        else:
            buy_winner = "持平"
        sign_d = "+" if notional_delta >= 0 else ""
        detail_lines.append(
            f"买入：基准 ¥{actual_n:,.0f} → 自进化 ¥{hypo_n:,.0f}"
            f"（差 {sign_d}¥{notional_delta:,.0f}，{buy_winner}更优）"
        )

    if intraday_sell and not intraday_sell.get("skipped"):
        rows = list(intraday_sell.get("rows") or [])
        actual_total = sum(int(r.get("actual_sold") or 0) for r in rows)
        hypo_total = sum(int(r.get("hypothetical_sold") or 0) for r in rows)
        sell_share_delta = int(
            intraday_sell.get("sell_share_delta") or (hypo_total - actual_total)
        )
        missed = int(intraday_sell.get("missed_sell_signals") or 0)
        realized = float(ctx.get("realized_pnl") or sell.get("actual_realized_pnl") or 0)
        if abs(sell_share_delta) >= 100:
            if sell_share_delta < 0 and realized < 0:
                evolved_score += 1
                scan_winner = "自进化"
                highlights.append(f"盘中少卖 {abs(sell_share_delta)} 股")
            elif sell_share_delta > 0 and realized >= 0:
                evolved_score += 1
                scan_winner = "自进化"
                highlights.append(f"盘中多卖 {sell_share_delta} 股")
            elif sell_share_delta < 0 and realized >= 0:
                baseline_score += 1
                scan_winner = "基准值"
            else:
                if sell_share_delta < 0:
                    evolved_score += 1
                    scan_winner = "自进化"
                    highlights.append(f"盘中少卖 {abs(sell_share_delta)} 股")
                else:
                    baseline_score += 1
                    scan_winner = "基准值"
        elif missed >= 1:
            baseline_score += 1
            scan_winner = "基准值"
        else:
            scan_winner = "持平"
        detail_lines.append(
            f"盘中卖出 scan：基准 {actual_total} 股 → 自进化 {hypo_total} 股"
            f"（差 {sell_share_delta:+d} 股，{scan_winner}更优）"
        )

    if friction and not friction.get("skipped"):
        friction_pass = int(friction.get("friction_would_pass") or 0)
        trend_miss = int(friction.get("trend_mismatch") or 0)
        rows = list(friction.get("rows") or [])
        diffs = [r for r in rows if (r.get("actual_action") or "") != (r.get("evolved_action") or "")]
        if friction_pass == 0 and trend_miss == 0 and not diffs:
            detail_lines.append("盘中摩擦/趋势：无差异（持平）")
        else:
            if friction_pass >= 1:
                evolved_score += 1
                fr_winner = "自进化"
            elif trend_miss >= 1:
                baseline_score += 1
                fr_winner = "基准值"
            else:
                fr_winner = "持平"
            detail_lines.append(
                f"盘中摩擦/趋势：可放行 {friction_pass} 次 · 趋势误判 {trend_miss} 次（{fr_winner}更优）"
            )

    if not detail_lines:
        return None

    if evolved_score > baseline_score:
        overall = "evolved"
        overall_label = "整体自进化更优"
    elif baseline_score > evolved_score:
        overall = "baseline"
        overall_label = "整体基准值更优"
    else:
        overall = "mixed"
        overall_label = "整体基本持平"

    if highlights:
        summary = f"{overall_label}：" + "，".join(highlights[:3])
    else:
        summary = overall_label

    out: dict[str, Any] = {
        "overall": overall,
        "summary": summary,
        "detail_lines": detail_lines[:5],
    }
    if harness_note:
        out["harness_note"] = harness_note
    return out


def _dedupe_text_lines(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _compact_harness_execution_summary(harness_result: dict[str, Any]) -> list[str]:
    if not harness_result:
        return []
    if harness_result.get("skipped") and harness_result.get("error"):
        return [f"Harness 跳过：{harness_result['error']}"]

    from agent_reach.daily_run.harness import _collect_harness_refinement_layers

    layers = _collect_harness_refinement_layers(harness_result)
    total = sum(int(layer.get("changes") or 0) for _, layer in layers)
    lines: list[str] = []
    if layers:
        lines.append(f"本次 harness 精炼 {len(layers)} 个 job，合计 {total} 项参数变更")
        for _label, layer in layers[:4]:
            changes = int(layer.get("changes") or 0)
            if changes <= 0:
                continue
            rid = layer.get("refinement_id") or ""
            planner = layer.get("planner") or layer.get("layer") or _label
            summary = str(layer.get("proposal_summary") or layer.get("reason") or "").strip()
            bit = f"{planner} · `{rid}` · {changes} 项变更"
            if summary:
                bit += f" · {summary[:48]}"
            lines.append(bit)
    rollback = harness_result.get("auto_rollback") or {}
    if rollback.get("triggered"):
        lines.append(
            f"坏交易回滚：{rollback.get('pnl_label') or 'PnL'} "
            f"{rollback.get('pnl_pct')}% ≤ {rollback.get('threshold')}% · "
            f"已撤销 {rollback.get('count', 0)} 次 refine"
        )
    return lines


_RUNTIME_EVOLUTION_LABELS: dict[str, str] = {
    "trade_min_scans": "最少扫描次数",
    "trade_every_n_scans": "交易间隔扫描",
    "max_applied_trades_per_day": "日最大成交笔数",
    "max_trade_evaluations_per_symbol": "单票最大评估次数",
    "max_holdings": "最大持仓数",
    "max_total_symbols": "最大标的数",
    "holding_lock_days": "锁仓天数",
    "stop_loss_ma20_pct": "MA20止损比例",
    "friction_min_return_pct": "摩擦最小收益",
}

_POSITION_EVOLUTION_LABELS: dict[str, str] = {
    "deploy_ratio": "deploy_ratio",
    "max_position_pct": "max_position_pct",
}

_FORECAST_EVOLUTION_LABELS: dict[str, str] = {
    "base_spread": "base_spread",
    "vol_multiplier": "vol_multiplier",
    "bias_pct": "bias_pct",
    "vol_scale": "vol_scale",
}


def _overlay_evolution_label(section: str, key: str) -> str:
    from agent_reach.daily_run.harness_display import THRESHOLD_REF_SPECS

    if section == "threshold_overlay":
        return {spec[0]: spec[2] for spec in THRESHOLD_REF_SPECS}.get(key, key)
    if section == "position_overlay":
        return _POSITION_EVOLUTION_LABELS.get(key, key)
    if section == "runtime_overlay":
        return _RUNTIME_EVOLUTION_LABELS.get(key, key)
    if section in ("forecast_overlay", "calibration_overlay"):
        return _FORECAST_EVOLUTION_LABELS.get(key, key)
    return key


def _collect_harness_overlay_evolution_lines(
    settings: Optional[dict[str, Any]],
    *,
    effective_overlay: Optional[dict[str, Any]] = None,
    max_lines: int = 10,
) -> list[str]:
    """Collect base→effective overlay diffs for harness evolution summary."""
    from agent_reach.daily_run.context_layers import _format_overlay_item
    from agent_reach.daily_run.harness_display import format_lookback_weights_pct
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings or {})
    runtime = dict(eff.get("harness_runtime") or {})
    if effective_overlay:
        for section, block in effective_overlay.items():
            if block and not runtime.get(section):
                runtime[section] = block

    lines: list[str] = []
    sections = (
        "threshold_overlay",
        "position_overlay",
        "runtime_overlay",
        "forecast_overlay",
        "lookback_overlay",
        "calibration_overlay",
    )
    for section in sections:
        block = runtime.get(section) or {}
        if section == "lookback_overlay":
            lb = block.get("lookback_weights") if isinstance(block, dict) else block
            if isinstance(lb, dict):
                base = lb.get("base")
                eff_w = lb.get("effective")
                if base and eff_w and list(base) != list(eff_w):
                    lines.append(
                        f"Lookback {format_lookback_weights_pct(eff_w)}"
                        f"（基准 {format_lookback_weights_pct(base)}）"
                    )
            continue
        if not isinstance(block, dict):
            continue
        for key, change in block.items():
            if not isinstance(change, dict):
                continue
            label = _overlay_evolution_label(section, str(key))
            bit = _format_overlay_item(label, change)
            if bit:
                lines.append(bit)
            if len(lines) >= max_lines:
                return lines

    trade_signals = runtime.get("trade_signals") or {}
    if isinstance(trade_signals, dict):
        active = [str(k) for k, v in trade_signals.items() if v]
        if active:
            lines.append("交易信号 " + "、".join(active[:6]))
    return lines[:max_lines]


def build_harness_evolution_summary(
    ctx: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Build harness parameter evolution summary for weekly 规则解读."""
    if ctx.get("job") != "weekly":
        return None

    harness_result = dict(ctx.get("harness_result") or {})
    weekly_skills = harness_result.get("weekly_skills") or {}
    effective_overlay = ctx.get("effective_overlay") or weekly_skills.get("effective_overlay")

    overlay_lines = _collect_harness_overlay_evolution_lines(
        settings,
        effective_overlay=effective_overlay,
    )
    execution = _compact_harness_execution_summary(harness_result)

    total_changes = weekly_skills.get("total_changes")
    if total_changes is None:
        from agent_reach.daily_run.harness import _collect_harness_refinement_layers

        layers = _collect_harness_refinement_layers(harness_result)
        total_changes = sum(int(layer.get("changes") or 0) for _, layer in layers)

    signal_lines: list[str] = []
    buy_opt = weekly_skills.get("buy_rules_whatif") or {}
    if buy_opt and not buy_opt.get("skipped"):
        optimal = buy_opt.get("llm_optimal") or {}
        deploy = optimal.get("deploy_ratio")
        max_pct = optimal.get("max_position_pct")
        if deploy is not None or max_pct is not None:
            bits: list[str] = []
            if deploy is not None:
                bits.append(f"deploy_ratio={float(deploy):.0%}")
            if max_pct is not None:
                bits.append(f"max_position_pct={float(max_pct):.0f}%")
            if bits:
                signal_lines.append("买入 what-if DeepSeek 最优：" + " · ".join(bits))

    if not overlay_lines and not execution and not signal_lines and not total_changes:
        return None

    summary_parts: list[str] = []
    if total_changes:
        summary_parts.append(f"本周 harness 共 {int(total_changes)} 项参数变更")
    if overlay_lines:
        summary_parts.append(overlay_lines[0])
    elif execution:
        summary_parts.append(execution[0])
    elif signal_lines:
        summary_parts.append(signal_lines[0])

    notes: list[str] = []
    rollback = harness_result.get("auto_rollback") or {}
    if rollback.get("triggered"):
        notes.append(
            f"坏交易回滚已触发（{rollback.get('pnl_label') or 'PnL'} "
            f"{rollback.get('pnl_pct')}%），部分 refine 已撤销"
        )

    out: dict[str, Any] = {
        "summary": "；".join(summary_parts[:2]) if summary_parts else "维持当前 harness 有效参数",
        "total_changes": int(total_changes or 0),
    }
    if overlay_lines:
        out["overlay_lines"] = overlay_lines[:8]
    if signal_lines:
        out["signal_lines"] = signal_lines[:2]
    if execution:
        out["execution_lines"] = execution[:4]
    if notes:
        out["notes"] = notes
    return out


def build_harness_tuning_summary(
    ctx: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Build harness policy/plan tuning summary for 规则解读 from what-if + session refine."""
    from agent_reach.daily_run.sell_rules_whatif import (
        summarize_buy_whatif_for_harness,
        summarize_intraday_friction_for_harness,
        summarize_intraday_sell_for_harness,
        summarize_whatif_for_harness,
    )

    pnl = ctx.get("portfolio_daily_pnl")
    if pnl is None:
        pnl = ctx.get("weekly_pnl")
    pnl_pct = ctx.get("portfolio_daily_pnl_pct")
    if pnl_pct is None:
        pnl_pct = ctx.get("weekly_pnl_pct")

    policy: list[str] = []
    plan: list[str] = []
    playbook: list[str] = []

    sell = ctx.get("sell_rules_whatif") or {}
    if sell and not sell.get("skipped") and (
        sell.get("rows")
        or abs(float(sell.get("actual_realized_pnl") or 0)) >= 0.01
        or abs(float(sell.get("hypothetical_realized_pnl") or 0)) >= 0.01
    ):
        block = summarize_whatif_for_harness(sell, weekly_pnl=pnl, weekly_pnl_pct=pnl_pct)
        policy.extend(block.get("policy") or [])
        plan.extend(block.get("plan") or [])
        playbook.extend(block.get("playbook") or [])

    buy = ctx.get("buy_rules_whatif") or {}
    if buy and not buy.get("skipped") and buy.get("rows"):
        block = summarize_buy_whatif_for_harness(buy, weekly_pnl=pnl, weekly_pnl_pct=pnl_pct)
        policy.extend(block.get("policy") or [])
        plan.extend(block.get("plan") or [])
        playbook.extend(block.get("playbook") or [])

    friction = ctx.get("intraday_friction_whatif") or {}
    if friction and not friction.get("skipped"):
        block = summarize_intraday_friction_for_harness(friction)
        policy.extend(block.get("policy") or [])
        plan.extend(block.get("plan") or [])
        playbook.extend(block.get("playbook") or [])

    intraday_sell = ctx.get("intraday_sell_whatif") or {}
    if intraday_sell and not intraday_sell.get("skipped"):
        block = summarize_intraday_sell_for_harness(intraday_sell)
        policy.extend(block.get("policy") or [])
        plan.extend(block.get("plan") or [])
        playbook.extend(block.get("playbook") or [])

    policy = _dedupe_text_lines(policy)
    plan = _dedupe_text_lines(plan)
    playbook = _dedupe_text_lines(playbook)

    execution = _compact_harness_execution_summary(dict(ctx.get("harness_result") or {}))

    overlay_lines: list[str] = []
    if settings:
        from agent_reach.daily_run.harness_display import format_effective_thresholds_markdown

        overlay_md = format_effective_thresholds_markdown(settings)
        if overlay_md:
            overlay_lines = [
                line[2:].strip()
                for line in overlay_md.splitlines()
                if line.startswith("- ")
            ]

    if not policy and not plan and not playbook and not execution and not overlay_lines:
        return None

    summary_parts: list[str] = []
    if policy:
        summary_parts.append(policy[0])
    elif plan:
        summary_parts.append(plan[0][:72])
    elif playbook:
        summary_parts.append(playbook[0][:72])
    if execution:
        summary_parts.append(execution[0])
    summary = "；".join(summary_parts[:2]) if summary_parts else "维持当前 harness 参数"

    notes: list[str] = []
    buy_delta = float((buy or {}).get("buy_notional_delta") or 0)
    if (
        buy
        and not buy.get("skipped")
        and buy_delta <= -5000
        and pnl is not None
        and float(pnl) < 0
        and any("deploy_ratio" in item for item in policy)
    ):
        notes.append(
            "买入 harness 建议上调 deploy_ratio，与当日下跌盈亏方向相反，"
            "执行时需对照上方「基准值 vs 自进化」综合结论"
        )

    out: dict[str, Any] = {
        "summary": summary,
        "policy_lines": policy[:4],
        "plan_lines": plan[:3],
    }
    if playbook:
        out["playbook_lines"] = playbook[:2]
    if execution:
        out["execution_lines"] = execution[:3]
    if overlay_lines:
        out["overlay_lines"] = overlay_lines[:4]
    if notes:
        out["notes"] = notes
    return out


def _attach_rule_interpretation_extras(
    payload: dict[str, Any],
    ctx: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    verdict = build_baseline_evolved_verdict(ctx)
    if verdict:
        payload["whatif_verdict"] = verdict
    tuning = build_harness_tuning_summary(ctx, settings=settings)
    if tuning:
        payload["harness_tuning"] = tuning
    evolution = build_harness_evolution_summary(ctx, settings=settings)
    if evolution:
        payload["harness_evolution"] = evolution
    return payload


def _append_trade_whatif_focus(focus: list[str], ctx: dict[str, Any], *, max_rows: int = 3) -> None:
    sell = ctx.get("sell_rules_whatif") or {}
    if sell and not sell.get("skipped") and sell.get("rows"):
        deltas = [r for r in sell.get("rows") or [] if int(r.get("share_delta") or 0) != 0]
        if deltas:
            bits = []
            for row in deltas[:max_rows]:
                name = row.get("name") or row.get("code")
                bits.append(
                    f"{name} 基准{int(row.get('actual_sold') or 0)}股→自进化{int(row.get('hypothetical_sold') or 0)}股"
                )
            focus.append(f"卖出规则对比（基准值 vs 自进化）：{'；'.join(bits)}")
        pnl_delta = sell.get("realized_pnl_delta")
        if pnl_delta is not None and abs(float(pnl_delta)) >= 200:
            if float(pnl_delta) <= -200:
                focus.append(
                    f"卖出 what-if 基准优于自进化（已实现差 {float(pnl_delta):+,.0f}），"
                    "harness 将 step-up 卖出比例"
                )
            else:
                focus.append(
                    f"卖出 what-if 自进化优于基准（已实现差 {float(pnl_delta):+,.0f}），"
                    "维持 partial sell 纪律"
                )
        elif pnl_delta is not None and abs(float(pnl_delta)) >= 0.01:
            sign = "+" if float(pnl_delta) >= 0 else ""
            focus.append(f"卖出自进化已实现差异 {sign}¥{float(pnl_delta):,.0f}")

    buy = ctx.get("buy_rules_whatif") or {}
    if buy and not buy.get("skipped") and buy.get("rows"):
        deltas = [r for r in buy.get("rows") or [] if int(r.get("share_delta") or 0) != 0]
        if deltas:
            bits = []
            for row in deltas[:max_rows]:
                name = row.get("name") or row.get("code")
                bits.append(
                    f"{name} 基准{int(row.get('actual_bought') or 0)}股→自进化{int(row.get('hypothetical_bought') or 0)}股"
                )
            focus.append(f"买入规则对比（基准值 vs 自进化）：{'；'.join(bits)}")
        notional_delta = buy.get("buy_notional_delta")
        if notional_delta is not None and abs(float(notional_delta)) >= 5000:
            if float(notional_delta) <= -5000:
                focus.append(
                    f"买入 what-if 基准优于自进化（成交额差 {float(notional_delta):+,.0f}），"
                    "harness 可上调 deploy_ratio"
                )
            else:
                focus.append(
                    f"买入 what-if 自进化优于基准（成交额差 {float(notional_delta):+,.0f}），"
                    "收紧 deploy 纪律"
                )
        elif notional_delta is not None and abs(float(notional_delta)) >= 0.01:
            sign = "+" if float(notional_delta) >= 0 else ""
            focus.append(f"买入自进化成交额差异 {sign}¥{float(notional_delta):,.0f}")

    intraday = ctx.get("intraday_friction_whatif") or {}
    if intraday and not intraday.get("skipped"):
        rows = list(intraday.get("rows") or [])
        friction_pass = int(intraday.get("friction_would_pass") or 0)
        trend_miss = int(intraday.get("trend_mismatch") or 0)
        if rows:
            bits = []
            for row in rows[:max_rows]:
                name = row.get("name") or row.get("code")
                bits.append(
                    f"{name} 基准{row.get('actual_action') or '—'}"
                    f"→自进化{row.get('evolved_action') or '—'}"
                )
            focus.append(f"盘中摩擦/趋势对比（基准值 vs 自进化）：{'；'.join(bits)}")
        if friction_pass >= 2:
            focus.append(
                f"摩擦 what-if 自进化可放行 {friction_pass} 次，"
                "harness 可略降 friction_min_return_pct"
            )
        elif friction_pass == 1:
            focus.append("摩擦 what-if 自进化可放行 1 次")
        if trend_miss >= 2:
            focus.append(
                f"趋势误判 {trend_miss} 次，harness 可调整 trend_min_points / trend_delta_threshold"
            )
        elif trend_miss == 1:
            focus.append("趋势误判 1 次")

    intraday_sell = ctx.get("intraday_sell_whatif") or {}
    if intraday_sell and not intraday_sell.get("skipped"):
        rows = list(intraday_sell.get("rows") or [])
        missed = int(intraday_sell.get("missed_sell_signals") or 0)
        delta = int(intraday_sell.get("sell_share_delta") or 0)
        if rows:
            bits = []
            for row in rows[:max_rows]:
                name = row.get("name") or row.get("code")
                bits.append(
                    f"{name} 基准{row.get('actual_action') or '—'}"
                    f"→自进化{row.get('evolved_action') or '—'}"
                )
            focus.append(f"盘中卖出 scan replay（基准值 vs 自进化）：{'；'.join(bits)}")
        if missed >= 2:
            focus.append(
                f"卖出 scan replay 自进化错失 {missed} 次，"
                "harness 可 step-up sell_ratio / defensive_trim"
            )
        elif missed == 1:
            focus.append("卖出 scan replay 自进化错失 1 次")
        elif delta > 0:
            focus.append(f"自进化卖出 scan 多卖 {delta} 股，维持 partial sell 纪律")


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
    total_return = ctx.get("total_return_pnl")
    if total_return is not None:
        cumulative = ctx.get("cumulative_realized_pnl")
        unrealized = ctx.get("total_unrealized")
        focus.append(
            f"总收益 {float(total_return):+,.0f}元"
            f"（历史已实现 {float(cumulative or 0):+,.0f}"
            f" + 当前持股 {float(unrealized or 0):+,.0f}）"
        )
    trade_ops = list(ctx.get("trade_operations") or [])
    if trade_ops:
        buys = sum(1 for op in trade_ops if op.get("side") == "buy")
        sells = sum(1 for op in trade_ops if op.get("side") == "sell")
        realized = ctx.get("realized_pnl")
        trade_bits = [f"买入 {buys} 笔" if buys else "", f"卖出 {sells} 笔" if sells else ""]
        trade_summary = " · ".join(bit for bit in trade_bits if bit)
        if realized is not None and abs(float(realized)) >= 0.01:
            sign = "+" if float(realized) >= 0 else ""
            trade_summary += f" · 已实现 {sign}¥{float(realized):,.0f}"
        if trade_summary:
            focus.append(f"当日成交：{trade_summary}")
    _append_trade_whatif_focus(focus, ctx)
    overlap = (
        ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(1, overlap[:100])
    for idx, extra in enumerate(_narrative_intel_focus(ctx)):
        focus.insert(2 + idx, extra)
    for rec in ctx.get("recommendations") or []:
        focus.append(f"明日：{rec}")
    for dev in ctx.get("deviations") or []:
        risks.append(str(dev)[:120])
    summary = f"收盘 {ctx.get('name') or ctx.get('code')} 复盘"
    if pnl is not None:
        summary += f"，当日盈亏 ¥{float(pnl):,.0f}"
    if trade_ops:
        summary += f"，成交 {len(trade_ops)} 笔"
    return {
        "summary": summary,
        "focus_points": focus[:4],
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
    return _attach_context_trace(
        _attach_close_trade_operations(
            _generate_narrative(
                "close",
                context,
                settings=settings,
                system="优先当日盈亏、成交买卖、偏差项、明日一条建议。",
                deterministic_fn=_close_deterministic,
            ),
            context,
        ),
        settings=settings,
        job="close",
        ctx=context,
    )


def build_merged_close_context(
    symbol_results: list[dict[str, Any]],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    harness_result: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.close_portfolio_summary import extract_close_trade_operations
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_hot_context_summary,
    )

    symbols: list[dict[str, Any]] = []
    for row in symbol_results:
        inner = row.get("result") or {}
        verify = inner.get("verify") or {}
        symbols.append(
            {
                "name": row.get("name") or inner.get("snapshot", {}).get("name"),
                "code": row.get("code") or inner.get("snapshot", {}).get("code"),
                "verify_summary": (verify.get("summary") or "")[:96],
                "verdict_current": verify.get("verdict_current"),
                "mss_delta": verify.get("mss_delta"),
            }
        )
    trade_ops = extract_close_trade_operations(portfolio_summary)
    return {
        "job": "close",
        "portfolio_scope": "merged",
        "symbol_count": len(symbols),
        "symbols": symbols,
        "portfolio_daily_pnl": (portfolio_summary or {}).get("daily_pnl"),
        "portfolio_daily_pnl_pct": (portfolio_summary or {}).get("daily_pnl_pct"),
        "realized_pnl": (portfolio_summary or {}).get("realized_pnl"),
        "cumulative_realized_pnl": (portfolio_summary or {}).get("cumulative_realized_pnl"),
        "total_unrealized": (portfolio_summary or {}).get("total_unrealized"),
        "total_return_pnl": (portfolio_summary or {}).get("total_return_pnl"),
        "trade_operations": trade_ops,
        "sell_rules_whatif": (portfolio_summary or {}).get("sell_rules_whatif"),
        "buy_rules_whatif": (portfolio_summary or {}).get("buy_rules_whatif"),
        "intraday_friction_whatif": (portfolio_summary or {}).get("intraday_friction_whatif"),
        "intraday_sell_whatif": (portfolio_summary or {}).get("intraday_sell_whatif"),
        "harness_result": harness_result or (portfolio_summary or {}).get("harness_result"),
        "curve_trend": (curve or {}).get("trend"),
        "forecast_review_accuracy": (forecast_review or {}).get("accuracy"),
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        **_narrative_supplement_fields(
            portfolio_summary=portfolio_summary,
            macro_signals=macro_signals,
        ),
    }


def _merged_close_deterministic(ctx: dict[str, Any]) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    n = int(ctx.get("symbol_count") or len(ctx.get("symbols") or []))
    pnl = ctx.get("portfolio_daily_pnl")
    pct = ctx.get("portfolio_daily_pnl_pct")
    if pnl is not None:
        sign = "+" if float(pnl) >= 0 else ""
        pct_s = f"（{float(pct):+.2f}%）" if pct is not None else ""
        focus.append(f"组合当日盈亏 {sign}¥{float(pnl):,.0f}{pct_s}")
    total_return = ctx.get("total_return_pnl")
    if total_return is not None:
        cumulative = ctx.get("cumulative_realized_pnl")
        unrealized = ctx.get("total_unrealized")
        focus.append(
            f"总收益 {float(total_return):+,.0f}元"
            f"（历史已实现 {float(cumulative or 0):+,.0f}"
            f" + 当前持股 {float(unrealized or 0):+,.0f}）"
        )
    trade_ops = list(ctx.get("trade_operations") or [])
    if trade_ops:
        buys = sum(1 for op in trade_ops if op.get("side") == "buy")
        sells = sum(1 for op in trade_ops if op.get("side") == "sell")
        realized = ctx.get("realized_pnl")
        trade_bits = [f"买入 {buys} 笔" if buys else "", f"卖出 {sells} 笔" if sells else ""]
        trade_summary = " · ".join(bit for bit in trade_bits if bit)
        if realized is not None and abs(float(realized)) >= 0.01:
            sign = "+" if float(realized) >= 0 else ""
            trade_summary += f" · 已实现 {sign}¥{float(realized):,.0f}"
        if trade_summary:
            focus.append(f"当日成交：{trade_summary}")
    _append_trade_whatif_focus(focus, ctx)
    overlap = (
        ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(1, overlap[:100])
    for idx, extra in enumerate(_narrative_intel_focus(ctx)):
        focus.insert(2 + idx, extra)
    for sym in ctx.get("symbols") or []:
        if sym.get("verify_summary"):
            focus.append(f"{sym.get('name') or sym.get('code')}：{sym['verify_summary'][:72]}")
        if len(focus) >= 4:
            break
    for sym in ctx.get("symbols") or []:
        delta = sym.get("mss_delta")
        if delta is not None and abs(float(delta)) >= 5:
            risks.append(f"{sym.get('name') or sym.get('code')} MSS Δ {float(delta):+.1f}")
    summary = f"收盘全持仓 {n} 只复盘"
    if pnl is not None:
        summary += f"，当日盈亏 ¥{float(pnl):,.0f}"
    if trade_ops:
        summary += f"，成交 {len(trade_ops)} 笔"
    return {
        "summary": summary,
        "focus_points": focus[:4] or ["复盘组合盈亏与明日执行"],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
    }


def generate_merged_close_narrative(
    symbol_results: list[dict[str, Any]],
    *,
    portfolio_summary: Optional[dict[str, Any]] = None,
    curve: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
    harness_result: Optional[dict[str, Any]] = None,
    macro_signals: Optional[dict[str, Any]] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_merged_close_context(
        symbol_results,
        portfolio_summary=portfolio_summary,
        curve=curve,
        forecast_review=forecast_review,
        harness_result=harness_result,
        macro_signals=macro_signals,
    )
    return _attach_context_trace(
        _attach_close_trade_operations(
            _generate_narrative(
                "close",
                context,
                settings=settings,
                system="全组合视角；优先当日盈亏、成交买卖、跨标的偏差、明日一条建议。",
                deterministic_fn=_merged_close_deterministic,
            ),
            context,
        ),
        settings=settings,
        job="close",
        ctx=context,
    )


# --- Weekly ---


def _weekly_xueqiu_hot_summary(report: dict[str, Any]) -> str:
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_stock_summary,
        xueqiu_hot_context_summary,
    )

    macro_signals = report.get("macro_signals") or {}
    return portfolio_hot_stock_summary(macro_signals) or xueqiu_hot_context_summary(macro_signals)


def build_weekly_context(
    report: dict[str, Any],
    *,
    harness_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
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
    from agent_reach.daily_run.xueqiu_hot_display import portfolio_hot_stock_summary

    supplements = _narrative_supplement_fields(
        snapshot={"watchlist_intel": report.get("watchlist_intel") or {}},
        macro_signals=report.get("macro_signals") or {},
        include_hit_summary=True,
    )
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
        "macro_signals": report.get("macro_signals") or {},
        "xueqiu_hot_summary": _weekly_xueqiu_hot_summary(report),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(report.get("macro_signals")),
        **supplements,
        "process_improvements": improvements,
        "experience_snippets": (report.get("experience_snippets") or [])[:3],
        "notes": report.get("notes") or [],
        "sell_rules_whatif": report.get("sell_rules_whatif"),
        "buy_rules_whatif": report.get("buy_rules_whatif"),
        "intraday_friction_whatif": report.get("intraday_friction_whatif"),
        "intraday_sell_whatif": report.get("intraday_sell_whatif"),
        "pnl_attribution": report.get("pnl_attribution"),
        "harness_result": harness_result or report.get("harness") or report.get("harness_result"),
        "effective_overlay": (
            (harness_result or {}).get("weekly_skills") or {}
        ).get("effective_overlay")
        or report.get("effective_overlay"),
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
    overlap = (
        ctx.get("portfolio_hot_stock_summary")
        or ctx.get("portfolio_hot_post_summary")
        or ctx.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(1, overlap[:100])
    for idx, extra in enumerate(_narrative_intel_focus(ctx)):
        focus.insert(2 + idx, extra)
    attr = ctx.get("pnl_attribution") or {}
    held = attr.get("held_week_chg")
    realized = attr.get("realized_pnl")
    rebalance = attr.get("rebalance_pnl")
    if held is not None or rebalance is not None:
        bits: list[str] = []
        if held is not None:
            bits.append(f"现持仓 {float(held):+,.0f}")
        if realized is not None and abs(float(realized)) >= 0.01:
            bits.append(f"已清仓 {float(realized):+,.0f}")
        if rebalance is not None:
            bits.append(f"换仓及其它 {float(rebalance):+,.0f}")
        if bits:
            focus.append("归因：" + " · ".join(bits))
    for sec in ctx.get("hot_sectors") or []:
        name = sec.get("sector") or sec.get("name") or "板块"
        chg = sec.get("avg_change_pct") or sec.get("change_pct")
        if chg is not None:
            focus.append(f"热点 {name} 周均 {float(chg):+.1f}%")
    for imp in ctx.get("process_improvements") or []:
        if imp.get("title"):
            focus.append(f"改进：{imp['title']}")
    _append_trade_whatif_focus(focus, ctx)
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
    harness_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = build_weekly_context(report, harness_result=harness_result)
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
    from agent_reach.daily_run.xueqiu_hot_display import (
        portfolio_hot_post_summary,
        portfolio_hot_stock_summary,
        portfolio_hot_stocks_new_summary,
        xueqiu_hot_context_summary,
    )

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
    macro_signals = forecast.get("macro_signals") or {}
    supplements = _narrative_supplement_fields(
        snapshot={"watchlist_intel": forecast.get("watchlist_intel") or {}},
        macro_signals=macro_signals,
        include_hit_summary=True,
    )
    return {
        "job": "forecast",
        "week_start": forecast.get("week_start"),
        "week_end": forecast.get("week_end"),
        "notes": forecast.get("notes") or [],
        "calibration": forecast.get("calibration_used") or {},
        "symbols": symbols_out,
        "mss_daily": mss_rows,
        "news_events": news,
        "xueqiu_hot_summary": xueqiu_hot_context_summary(macro_signals),
        "portfolio_hot_stock_summary": portfolio_hot_stock_summary(macro_signals),
        "portfolio_hot_post_summary": portfolio_hot_post_summary(macro_signals),
        **supplements,
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
    overlap = (
        context.get("portfolio_hot_stock_summary")
        or context.get("portfolio_hot_post_summary")
        or context.get("xueqiu_hot_summary")
    )
    if overlap:
        focus.insert(0, overlap[:100])
    for extra in _narrative_intel_focus(context):
        if extra not in focus:
            focus.insert(min(1, len(focus)), extra)
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
