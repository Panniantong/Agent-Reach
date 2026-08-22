# -*- coding: utf-8
"""Lightweight 12:30 midday refresh for afternoon intraday (macro + Lookback anchor)."""

from __future__ import annotations

from typing import Any, Optional

from agent_reach.daily_run.pipeline import evaluate_snapshot
from agent_reach.daily_run.settings import effective_settings, load_settings


def midday_cfg(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = effective_settings(settings or load_settings())
    raw = cfg.get("midday") or {}
    return {
        "enabled": raw.get("enabled", True) is not False,
        "macro_refresh": raw.get("macro_refresh", True) is not False,
        "mss_experts": raw.get("mss_experts", False) is True,
    }


def apply_midday_macro_refresh(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    config=None,
) -> dict[str, Any]:
    """Force full macro/hot-news collection and persist to daily cache."""
    from agent_reach.daily_run.macro_collector import collect_macro_context, enrich_macro_sources
    from agent_reach.daily_run.snapshot_builder import load_portfolio
    from agent_reach.daily_run.snapshot_cache import load_daily_cache, save_daily_cache

    cfg = effective_settings(settings or load_settings())
    pf = snapshot.get("portfolio") or load_portfolio()
    macro_ctx = collect_macro_context(
        pf,
        config=config,
        settings=cfg,
        workflow="midday",
        scope="full",
    )
    sources = enrich_macro_sources(pf, macro_ctx.get("sources") or {}, cfg)

    out = dict(snapshot)
    out["macro_signals"] = dict(macro_ctx.get("macro_signals") or {})
    if macro_ctx.get("macro_summary"):
        out["macro_summary"] = macro_ctx["macro_summary"]
    merged_sources = dict(out.get("sources") or {})
    merged_sources.update(sources)
    out["sources"] = merged_sources

    live_bd = dict(macro_ctx.get("mss_breakdown") or {})
    if live_bd:
        base_bd = dict(out.get("mss_breakdown") or {})
        for key, val in live_bd.items():
            if key.startswith("_") or key.endswith("_ref"):
                base_bd[key] = val
            elif key in {"fx", "flow", "global", "sentiment", "technical", "quant", "risk"}:
                base_bd[key] = val
        out["mss_breakdown"] = base_bd

    cache = load_daily_cache()
    cache["macro_ctx"] = {
        "mss_breakdown": out.get("mss_breakdown"),
        "sources": out.get("sources"),
        "macro_summary": out.get("macro_summary"),
        "macro_signals": out.get("macro_signals"),
    }
    save_daily_cache(cache)
    return out


def _morning_session_lines(state: dict[str, Any], baseline: Optional[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    if baseline:
        mss = baseline.get("mss_final") or (baseline.get("report") or {}).get("mss_final")
        verdict = baseline.get("verdict") or (baseline.get("report") or {}).get("verdict")
        if mss is not None or verdict:
            lines.append(f"- **08:00 早盘基线：** MSS **{mss or '—'}** · **{verdict or '—'}**")
    scans = list(state.get("scans") or [])
    if not scans:
        lines.append("- 上午尚无 intraday 扫描记录")
        return lines
    am = [s for s in scans if str(s.get("source") or "") in {"morning", ""} or s.get("scan_id", "") <= "S9"]
    if not am:
        am = scans[:-1] if len(scans) > 1 else scans
    if am:
        last = am[-1]
        lines.append(
            f"- **上午末扫 {last.get('scan_id', '—')}：** MSS **{last.get('mss_final', '—')}** · "
            f"**{last.get('verdict', '—')}**"
        )
        if len(am) >= 2:
            first = am[0]
            lines.append(
                f"- **上午首扫 {first.get('scan_id', '—')}：** MSS **{first.get('mss_final', '—')}**"
            )
    return lines


def render_midday_markdown(
    scan_result: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    narrative: Optional[dict[str, Any]] = None,
) -> str:
    scan = scan_result.get("scan") or {}
    report = (scan_result.get("evaluation") or {}).get("report") or {}
    lookback_mss = scan_result.get("lookback_mss", 0)
    lookback_detail = scan_result.get("lookback_detail") or []
    trend = scan_result.get("trend") or "flat"
    state = scan_result.get("state") or {}
    enriched = scan_result.get("enriched") or {}
    xueqiu_cross = scan_result.get("xueqiu_cross") or {}

    trend_map = {
        "rising": "上升",
        "falling": "下降",
        "turning_up": "拐点向上",
        "turning_down": "拐点向下",
        "flat": "横盘",
        "mixed": "震荡",
        "insufficient": "数据不足",
    }

    baseline = None
    try:
        from agent_reach.daily_run.workflows import load_morning_baseline

        baseline = load_morning_baseline()
    except (FileNotFoundError, OSError, ValueError):
        baseline = None

    lines = [
        f"**☀️ 午盘分析 · {scan.get('scan_id', '—')}**",
        "",
        f"**即时 MSS：** {scan.get('mss_final', '—')} 分 · **标签：** {scan.get('verdict', '—')}",
        f"**Lookback MSS：** {lookback_mss} 分 · **趋势：** {trend_map.get(trend, trend)}",
        "",
        "## 🌅 上午回顾",
        *_morning_session_lines(state, baseline),
        "",
        "## 🔄 午休宏观刷新",
    ]
    macro_summary = str(enriched.get("macro_summary") or "").strip()
    if macro_summary:
        lines.append(f"- {macro_summary[:240]}")
    else:
        lines.append("- 宏观摘要未更新（检查网络 / 60s / 雪球 Cookie）")

    from agent_reach.daily_run.xueqiu_hot_display import render_intraday_xueqiu_alert_markdown

    alert_md = render_intraday_xueqiu_alert_markdown(xueqiu_cross)
    if alert_md:
        lines.extend(["", alert_md])

    lines.extend(["", "## 🎯 午后 Lookback"])
    if lookback_detail:
        for item in lookback_detail:
            src = ""
            for s in state.get("scans") or []:
                if s.get("scan_id") == item.get("scan_id"):
                    if s.get("source") == "midday":
                        src = " · 午盘"
                    elif s.get("source") == "morning":
                        src = " · 早盘"
                    break
            lines.append(
                f"- {item.get('scan_id')}{src}: MSS {item.get('mss_final')} × "
                f"{float(item.get('weight', 0)):.0%} = {item.get('weighted')}"
            )
    else:
        lines.append("- 数据不足")

    lines.extend(["", "## 📌 午后策略"])
    if report.get("reasoning"):
        lines.append(f"- {report['reasoning']}")
    else:
        lines.append("- 13:00 开盘后以 S_n+1 扫描确认，Lookback 已含本午盘锚点")

    if narrative and not narrative.get("skipped"):
        from agent_reach.daily_run.report_narrative import render_narrative_markdown

        n_md = render_narrative_markdown(narrative, job="midday")
        if n_md.strip():
            lines.extend(["", n_md])

    lines.extend(
        [
            "",
            "_说明：12:30 行情与 11:30 相同；本卡侧重午休资讯刷新与午后 Lookback 锚点，13:00 仍有一次常规盘中扫描。_",
        ]
    )
    return "\n".join(lines)


def _midday_narrative_deterministic(
    scan: dict[str, Any],
    report: dict[str, Any],
    *,
    lookback_mss: float,
    trend: str,
) -> dict[str, Any]:
    focus: list[str] = []
    risks: list[str] = []
    verdict = str(scan.get("verdict") or report.get("verdict") or "观察")
    mss = scan.get("mss_final") or report.get("mss_final")
    focus.append(f"午后 Lookback MSS {lookback_mss:.1f}（趋势 {trend}）")
    if mss is not None:
        focus.append(f"午盘即时 MSS {float(mss):.1f} · {verdict}")
    focus.append("13:00 开盘后关注量价确认，勿仅凭午休资讯激进调仓")
    if verdict in {"回避", "观察"}:
        risks.append("上午至午盘 MSS 未确认进攻，午后宜守现金或轻仓试探")
    return {
        "summary": f"午盘 refresh · {verdict} · Lookback {lookback_mss:.1f}",
        "focus_points": focus[:3],
        "divergence_notes": [],
        "risk_alerts": risks[:2],
        "planner": "deterministic",
        "skipped": False,
        "job": "midday",
    }


def run_midday(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    doctor_channels: Optional[dict[str, dict]] = None,
    push: bool = True,
    title: Optional[str] = None,
    config=None,
) -> dict[str, Any]:
    """Midday macro refresh → evaluate → intraday scan (source=midday) → Feishu."""
    cfg = effective_settings(settings)
    mcfg = midday_cfg(cfg)
    if not mcfg["enabled"]:
        return {"steps": ["skipped"], "message": "midday disabled", "feishu": None}

    steps: list[str] = ["snapshot"]
    enriched = dict(snapshot)
    enriched.setdefault("report_type", "midday")
    enriched.setdefault("as_of", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())

    if mcfg["macro_refresh"]:
        enriched = apply_midday_macro_refresh(enriched, settings=cfg, config=config)
        steps.append("macro_refresh")

    if mcfg["mss_experts"]:
        from agent_reach.daily_run.team import enrich_with_team_or_experts

        enriched, expert_steps = enrich_with_team_or_experts(
            enriched,
            cfg,
            workflow="intraday",
            skip_experts=False,
        )
        steps.extend(expert_steps or ["mss_experts"])

    evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)
    steps.append("evaluate")

    from agent_reach.daily_run.intraday import record_scan_from_evaluation

    scan_result = record_scan_from_evaluation(
        enriched,
        evaluation,
        settings=cfg,
        source="midday",
    )
    scan_result["enriched"] = enriched
    scan_result["evaluation"] = evaluation
    steps.append("record_scan")

    scan = scan_result.get("scan") or {}
    narrative = _midday_narrative_deterministic(
        scan,
        evaluation.get("report") or {},
        lookback_mss=float(scan_result.get("lookback_mss") or 0),
        trend=str(scan_result.get("trend") or "flat"),
    )
    llm_cfg = (cfg.get("midday") or {}).get("llm_narrative") or {}
    if llm_cfg.get("enabled") is True and llm_cfg.get("planner") == "llm":
        from agent_reach.daily_run.report_narrative import generate_midday_narrative

        narrative = generate_midday_narrative(scan_result, settings=cfg)

    markdown = render_midday_markdown(scan_result, settings=cfg, narrative=narrative)
    steps.append("render")

    feishu_result = None
    push_error: Optional[str] = None
    if push:
        from agent_reach.config import Config
        from agent_reach.integrations.feishu import FeishuError, send_card

        cfg_obj = config or Config()
        tpl = cfg.get("report", {}).get("feishu_template_midday", "blue")
        name = scan.get("name") or scan.get("code") or "大盘"
        card_title = title or f"☀️ 午盘分析 · {scan.get('scan_id', '—')} · {name}"
        try:
            feishu_result = send_card(cfg_obj, card_title, markdown, template=tpl)
            steps.append("push")
        except FeishuError as exc:
            push_error = str(exc)

    out: dict[str, Any] = {
        "steps": steps,
        "snapshot": enriched,
        "evaluation": evaluation,
        "scan_result": scan_result,
        "scan": scan,
        "lookback_mss": scan_result.get("lookback_mss"),
        "markdown": markdown,
        "llm_narrative": narrative,
        "feishu": feishu_result,
    }
    if push_error:
        out["push_error"] = push_error
    return out
