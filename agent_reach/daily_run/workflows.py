# -*- coding: utf-8
"""One-click morning / close workflows for daily_run_skill."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_reach.daily_run.pipeline import evaluate_snapshot, render_markdown
from agent_reach.daily_run.report_push import (
    push_report_sections,
    render_close_sections,
    render_morning_sections,
    split_push_enabled,
)
from agent_reach.daily_run.settings import effective_settings, load_settings
from agent_reach.daily_run.close_code_review import render_code_review_markdown
from agent_reach.daily_run.close_research import render_research_markdown, run_exa_research
from agent_reach.daily_run.curve_analysis import analyze_intraday_curve, render_curve_markdown
from agent_reach.daily_run.experience import append_experience_entry, render_experience_markdown
from agent_reach.daily_run.team import (
    expert_card_enabled,
    experts_enabled,
    mss_experts_enabled,
    render_team_markdown,
    run_team_first,
    team_first_enabled,
)
from agent_reach.daily_run.verify import render_verify_markdown, verify_snapshots

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("agent_reach.daily_run.workflows")


def _workflow_harness_error(errors: list[str], context: str, exc: BaseException) -> None:
    msg = f"{context}: {exc}"
    errors.append(msg)
    logger.warning("daily-run workflow harness error: {}", msg)


def _default_baseline_path() -> Path:
    return Path.home() / ".agent-reach" / "daily_run" / "last_morning.json"


def _holdings_baseline_snapshot(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    out: list[dict[str, Any]] = []
    for h in holdings:
        code = _normalize_code(str(h.get("code", "")))
        if not code:
            continue
        row: dict[str, Any] = {
            "code": code,
            "name": h.get("name") or code,
        }
        for key in (
            "shares",
            "cost",
            "price",
            "change_pct",
            "market_value",
            "unrealized_pnl",
            "quote_source",
        ):
            if h.get(key) is not None:
                row[key] = h[key]
        shares = row.get("shares")
        price = row.get("price")
        if shares is not None and price is not None and row.get("market_value") is None:
            row["market_value"] = round(int(shares) * float(price), 2)
        out.append(row)
    return out


def _merge_holdings_for_baseline(
    snap_holdings: list[dict[str, Any]],
    cfg_holdings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    by_code: dict[str, dict[str, Any]] = {}
    for h in cfg_holdings:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            by_code[code] = dict(h)
    for h in snap_holdings:
        code = _normalize_code(str(h.get("code", "")))
        if code:
            by_code[code] = {**by_code.get(code, {}), **h}
    return list(by_code.values())


def enrich_morning_baseline(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Ensure morning baseline carries portfolio total and a holdings snapshot."""
    from agent_reach.daily_run.portfolio_manager import _recalc_totals
    from agent_reach.daily_run.snapshot_builder import load_portfolio
    from agent_reach.daily_run.symbols import build_enriched_symbols

    baseline = dict(snapshot)
    pf_block = dict(baseline.get("portfolio") or {})
    pf_cfg = load_portfolio()

    snap_holdings = list(pf_block.get("holdings") or baseline.get("holdings") or [])
    cfg_holdings = list(pf_cfg.get("holdings") or [])
    merged = _merge_holdings_for_baseline(snap_holdings, cfg_holdings)
    holdings = _holdings_baseline_snapshot(merged)
    missing_codes = [
        str(h.get("code") or "")
        for h in holdings
        if h.get("code") and h.get("price") is None
    ]
    if missing_codes:
        from agent_reach.daily_run.quote_fetch import fetch_quotes_map
        from agent_reach.daily_run.settings import load_settings

        quotes = fetch_quotes_map(missing_codes, settings=load_settings()).quotes
        for h in holdings:
            code = str(h.get("code") or "")
            q = quotes.get(code) or {}
            if h.get("price") is None and q.get("price") is not None:
                h["price"] = q["price"]
            if h.get("change_pct") is None and q.get("change_pct") is not None:
                h["change_pct"] = q["change_pct"]
            shares = h.get("shares")
            price = h.get("price")
            if shares is not None and price is not None and h.get("market_value") is None:
                h["market_value"] = round(int(shares) * float(price), 2)

    pf_work: dict[str, Any] = {
        "total": pf_block.get("total") if pf_block.get("total") is not None else pf_cfg.get("total"),
        "cash": pf_block.get("cash") if pf_block.get("cash") is not None else pf_cfg.get("cash"),
        "cash_ratio": (
            pf_block.get("cash_ratio")
            if pf_block.get("cash_ratio") is not None
            else pf_cfg.get("cash_ratio")
        ),
        "holdings": holdings,
    }
    if holdings:
        _recalc_totals(pf_work, build_enriched_symbols(baseline))
    baseline["portfolio"] = pf_work

    if baseline.get("watchlist") is None:
        watchlist = pf_cfg.get("watchlist") or []
        if watchlist:
            baseline["watchlist"] = [dict(w) for w in watchlist]

    baseline.setdefault(
        "baseline_saved_at",
        baseline.get("as_of") or datetime.now(timezone.utc).isoformat(),
    )
    return baseline


def _attach_intraday_scans(snapshot: dict[str, Any], *, code: Optional[str] = None) -> dict[str, Any]:
    """Merge today's intraday scans into close snapshot (source of truth)."""
    from agent_reach.daily_run.intraday import load_state

    enriched = dict(snapshot)
    sym = code or enriched.get("code")
    state = load_state(code=sym)
    if not state.scans:
        return enriched
    enriched["intraday_scans"] = state.scans
    enriched["mss_intraday_actual"] = [
        float(s["mss_final"]) for s in state.scans if s.get("mss_final") is not None
    ]
    return enriched


def run_morning(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    doctor_channels: Optional[dict[str, dict]] = None,
    plugin_names: Optional[list[str]] = None,
    team_first: Optional[bool] = None,
    push: bool = True,
    start_notify: bool = True,
    title: Optional[str] = None,
    config=None,
) -> dict[str, Any]:
    """
    Full morning pipeline:
    snapshot → audit/verdict/gate → Feishu push
    """
    cfg = effective_settings(settings)
    steps: list[str] = []
    morning_harness_errors: list[str] = []

    if start_notify and push:
        _send_start_notification(config, cfg)
        steps.append("start_notify")

    snapshot = dict(snapshot)
    snapshot.setdefault("report_type", "premarket")
    snapshot.setdefault("as_of", datetime.now(timezone.utc).isoformat())

    if team_first is None:
        use_team = team_first_enabled(cfg, workflow="morning")
    else:
        use_team = bool(team_first) and experts_enabled(cfg, workflow="morning")

    if use_team:
        enriched = run_team_first(snapshot, cfg, names=plugin_names)
        steps.append("team_first")
    elif experts_enabled(cfg, workflow="morning"):
        from agent_reach.daily_run.plugins.loader import run_experts

        enriched = run_experts(snapshot, cfg, names=plugin_names)
        steps.append("experts")
    elif mss_experts_enabled(cfg, workflow="morning"):
        from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, run_experts

        enriched = run_experts(snapshot, cfg, names=MSS_EXPERT_NAMES)
        steps.append("mss_experts")
    else:
        enriched = dict(snapshot)
        steps.append("snapshot")

    evaluation = evaluate_snapshot(enriched, cfg, doctor_channels=doctor_channels)
    steps.append("evaluate")

    audit = evaluation["audit"]
    gate = evaluation["gate"]
    report = evaluation["report"]

    if not audit.passed:
        raise RuntimeError(f"数据审计未通过：{audit.summary()}")
    if not gate.passed:
        raise RuntimeError(f"质量门禁未通过：{gate.summary()}")

    plan_close: dict[str, Any] = {}
    if datetime.now().weekday() == 0:
        from agent_reach.daily_run.harness import close_open_plans

        plan_close = close_open_plans(settings=cfg)
        if plan_close.get("count"):
            steps.append(f"harness_plans_closed_{plan_close['count']}")

    morning_harness_result: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.morning_harness import apply_morning_harness_refinement

        morning_harness_result = apply_morning_harness_refinement(
            {
                "snapshot": enriched,
                "evaluation": evaluation,
                "harness_plan_closeout": plan_close,
            },
            settings=cfg,
        )
    except Exception as exc:
        _workflow_harness_error(morning_harness_errors, "morning_harness", exc)
        morning_harness_result = {"skipped": True, "error": str(exc)}

    team_md = render_team_markdown(enriched) if expert_card_enabled(cfg, workflow="morning") else ""
    report_md = render_markdown(report)
    from agent_reach.daily_run.report_narrative import generate_morning_narrative

    morning_narrative = generate_morning_narrative(enriched, report, settings=cfg)
    push_harness_summary = _harness_push_summary_enabled(cfg, report_kind="morning")
    harness_md = ""
    if push_harness_summary:
        from agent_reach.daily_run.harness import format_harness_push_markdown

        harness_payload = {"morning": morning_harness_result}
        if plan_close.get("count"):
            harness_payload["harness_plan_closeout"] = plan_close
        harness_md = format_harness_push_markdown(
            harness_payload,
            job="morning",
            harness_errors=morning_harness_errors,
        )

    feishu_result = None
    if push:
        sections = render_morning_sections(
            team_markdown=team_md,
            report_markdown=report_md,
            report=report,
            harness_markdown=harness_md,
            narrative=morning_narrative,
        )
        feishu_result = push_report_sections(
            sections,
            settings=cfg,
            config=config,
            report_type="premarket",
            fallback_title=title or _morning_title(report),
            split=split_push_enabled(cfg, report_kind="morning"),
        )
        steps.append("push")
        if feishu_result.get("mode") == "split":
            steps.append(f"push_split_{feishu_result.get('count', 0)}")

    followup_steps = push_harness_followups(
        settings=cfg,
        config=config,
        report_kind="morning",
        harness_result={"morning": morning_harness_result},
        harness_errors=morning_harness_errors,
        push=push,
        summary_in_main_push=push_harness_summary,
    )
    steps.extend(followup_steps)

    return {
        "steps": steps,
        "snapshot": enriched,
        "evaluation": evaluation,
        "markdown": team_md + "\n\n---\n\n" + report_md,
        "team_markdown": team_md,
        "report_markdown": report_md,
        "llm_narrative": morning_narrative,
        "feishu": feishu_result,
        "harness_plan_closeout": plan_close,
        "harness_morning": morning_harness_result,
        **({"harness_errors": morning_harness_errors} if morning_harness_errors else {}),
    }


def _harness_push_summary_enabled(settings: dict[str, Any], *, report_kind: str) -> bool:
    harness_cfg = settings.get("harness") or {}
    if report_kind == "close":
        return bool(harness_cfg.get("push_summary_on_close", False))
    if report_kind == "weekly":
        if "push_summary_on_weekly" in harness_cfg:
            return bool(harness_cfg.get("push_summary_on_weekly"))
        return bool(harness_cfg.get("push_summary_on_close", False))
    if report_kind == "forecast":
        if "push_summary_on_forecast" in harness_cfg:
            return bool(harness_cfg.get("push_summary_on_forecast"))
        return bool(harness_cfg.get("push_summary_on_close", False))
    if report_kind == "morning":
        if "push_summary_on_morning" in harness_cfg:
            return bool(harness_cfg.get("push_summary_on_morning"))
        return bool(harness_cfg.get("push_summary_on_close", False))
    if report_kind == "intraday":
        if "push_summary_on_intraday" in harness_cfg:
            return bool(harness_cfg.get("push_summary_on_intraday"))
        return False
    return False


def _harness_errors_push_enabled(settings: dict[str, Any]) -> bool:
    harness_cfg = settings.get("harness") or {}
    return bool(harness_cfg.get("push_harness_errors_on_feishu", True))


def _harness_rollback_push_enabled(settings: dict[str, Any]) -> bool:
    harness_cfg = settings.get("harness") or {}
    return bool(harness_cfg.get("push_rollback_on_feishu", True))


def _harness_card_template(settings: dict[str, Any], report_kind: str) -> str:
    templates = (settings.get("report") or {})
    mapping = {
        "close": templates.get("feishu_template_verify", "purple"),
        "weekly": templates.get("feishu_template_weekly", "blue"),
        "forecast": templates.get("feishu_template_forecast", "blue"),
        "morning": templates.get("feishu_template_premarket", "orange"),
        "intraday": templates.get("feishu_template_intraday", "blue"),
    }
    return str(mapping.get(report_kind, "blue"))


def _harness_card_title(report_kind: str) -> str:
    titles = {
        "close": "🧬 Harness 进化 · 收盘",
        "weekly": "🧬 Harness 进化 · 周报",
        "forecast": "🧬 Harness 进化 · 预测",
        "morning": "🧬 Harness 进化 · 早盘",
        "intraday": "🧬 Harness 进化 · 盘中",
    }
    return titles.get(report_kind, f"🧬 Harness 进化 · {report_kind}")


def _push_harness_summary_card(
    harness_result: dict[str, Any],
    *,
    settings: dict[str, Any],
    config: Any,
    report_kind: str,
    title: Optional[str] = None,
    template: Optional[str] = None,
    harness_errors: Optional[list[str]] = None,
    body: Optional[str] = None,
    week_start: Optional[str] = None,
    week_end: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    from agent_reach.daily_run.harness import format_harness_push_markdown
    from agent_reach.daily_run.report_push import ReportSection, push_report_sections

    harness_md = body or format_harness_push_markdown(
        harness_result,
        job=report_kind,
        harness_errors=harness_errors,
        week_start=week_start,
        week_end=week_end,
        settings=settings,
    )
    if not harness_md.strip():
        return None
    card_title = title or _harness_card_title(report_kind)
    return push_report_sections(
        [ReportSection(category="harness", title=card_title, body=harness_md)],
        settings=settings,
        config=config,
        report_type=report_kind,
        fallback_title=card_title,
        template=template or _harness_card_template(settings, report_kind),
        split=False,
    )


def push_harness_followups(
    *,
    settings: dict[str, Any],
    config: Any,
    report_kind: str,
    harness_result: Optional[dict[str, Any]] = None,
    harness_errors: Optional[list[str]] = None,
    push: bool = True,
    summary_in_main_push: bool = False,
) -> list[str]:
    """Push standalone harness rollback/errors cards when not embedded in main report."""
    steps: list[str] = []
    if not push:
        return steps

    harness_result = harness_result or {}
    errors = list(harness_errors or [])
    rollback = harness_result.get("auto_rollback") or {}

    if rollback.get("triggered") and _harness_rollback_push_enabled(settings) and not summary_in_main_push:
        from agent_reach.daily_run.harness import format_harness_rollback_markdown, format_harness_errors_markdown

        body = format_harness_rollback_markdown(rollback, job=report_kind)
        errors_md = format_harness_errors_markdown(errors) if _harness_errors_push_enabled(settings) else ""
        if errors_md:
            body = f"{body}\n\n{errors_md}"
        if _push_harness_summary_card(
            harness_result,
            settings=settings,
            config=config,
            report_kind=report_kind,
            title=f"⚠️ {_harness_card_title(report_kind)} · 回滚",
            template="red",
            body=body,
        ):
            steps.append("push_harness_rollback")
        return steps

    if errors and _harness_errors_push_enabled(settings) and not summary_in_main_push:
        from agent_reach.daily_run.harness import format_harness_errors_markdown

        body = format_harness_errors_markdown(errors)
        if _push_harness_summary_card(
            harness_result,
            settings=settings,
            config=config,
            report_kind=report_kind,
            title=f"⚠️ {_harness_card_title(report_kind)} · 异常",
            template="red",
            body=body,
        ):
            steps.append("push_harness_errors")
    return steps


def push_scheduled_harness_card(
    *,
    job: str,
    harness_result: dict[str, Any],
    settings: dict[str, Any],
    config: Any,
    push: bool = True,
    harness_errors: Optional[list[str]] = None,
) -> list[str]:
    """Push harness summary card for scheduled jobs (e.g. intraday post-hook)."""
    steps: list[str] = []
    if not push or not _harness_push_summary_enabled(settings, report_kind=job):
        return push_harness_followups(
            settings=settings,
            config=config,
            report_kind=job,
            harness_result=harness_result,
            harness_errors=harness_errors,
            push=push,
            summary_in_main_push=False,
        )

    if _push_harness_summary_card(
        harness_result,
        settings=settings,
        config=config,
        report_kind=job,
        harness_errors=harness_errors,
    ):
        steps.append("push_harness_summary")
    return steps


def _attach_close_session_refinements(
    harness_result: dict[str, Any],
    *,
    harness_skills_report: Any = None,
    experience_harness: Optional[dict[str, Any]] = None,
) -> None:
    if harness_skills_report is not None:
        harness_result["close_skills"] = harness_skills_report.to_dict()
    if experience_harness and experience_harness.get("refinement_id"):
        harness_result["experience"] = experience_harness


def _run_close_harness_layer_ab(
    *,
    enriched: dict[str, Any],
    verify_dict: dict[str, Any],
    curve: Any,
    forecast_review: Any,
    portfolio_summary_obj: Any,
    settings: dict[str, Any],
    harness_skills_report: Any = None,
    experience_harness: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.close_harness_skills import run_close_layer_a_refinement
    from agent_reach.daily_run.harness import refine_after_job_llm

    curve_payload = curve.to_dict() if curve is not None and hasattr(curve, "to_dict") else curve
    close_evidence = {
        "snapshot": enriched,
        "verify": verify_dict,
        "curve": curve_payload,
        "forecast_review": forecast_review.to_dict() if forecast_review else None,
        "name": enriched.get("name"),
        "portfolio_summary": portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
    }
    layer_a = run_close_layer_a_refinement(close_evidence, settings=settings)
    layer_b = refine_after_job_llm("close", evidence=close_evidence, settings=settings)
    harness_result = {"layer_a": layer_a, "layer_b": layer_b}
    _attach_close_session_refinements(
        harness_result,
        harness_skills_report=harness_skills_report,
        experience_harness=experience_harness,
    )
    if harness_skills_report is not None:
        harness_skills_report.close_layer_a = layer_a
        enriched["harness_skills"] = harness_skills_report.to_dict()
    return harness_result


def _finalize_close_harness(
    harness_result: dict[str, Any],
    *,
    portfolio_summary_obj: Any,
    settings: dict[str, Any],
    harness_errors: Optional[list[str]] = None,
) -> str:
    from agent_reach.daily_run.harness import auto_rollback_on_bad_trade, format_harness_push_markdown

    rollback = auto_rollback_on_bad_trade(
        portfolio_summary=portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
        harness_result=harness_result,
        settings=settings,
        job="close",
    )
    if rollback.get("triggered"):
        harness_result["auto_rollback"] = rollback
    return format_harness_push_markdown(
        harness_result,
        job="close",
        harness_errors=harness_errors,
    )


def run_close(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    plugin_names: Optional[list[str]] = None,
    team_first: Optional[bool] = None,
    push: bool = True,
    title: Optional[str] = None,
    config=None,
    intraday_scans: Optional[list[dict[str, Any]]] = None,
    intraday_trades: Optional[list[dict[str, Any]]] = None,
    watchlist_adjust: Optional[dict[str, Any]] = None,
    code_review: Optional[dict[str, Any]] = None,
    verify_dict: Optional[dict[str, Any]] = None,
    portfolio_summary: bool = True,
    experts_already_ran: bool = False,
) -> dict[str, Any]:
    """Close workflow: Team-First experts → verify baseline vs current → Feishu push."""
    cfg = effective_settings(settings)
    harness_errors: list[str] = []
    current = _attach_intraday_scans(dict(current), code=current.get("code"))
    current.setdefault("report_type", "close")

    enriched = current
    team_md = ""
    if team_first is None:
        use_team = team_first_enabled(cfg, workflow="close")
    else:
        use_team = bool(team_first) and experts_enabled(cfg, workflow="close")

    from agent_reach.daily_run.kronos_predictor import attach_kronos_to_snapshot, is_kronos_enabled

    if is_kronos_enabled(cfg):
        enriched = attach_kronos_to_snapshot(dict(current), settings=cfg)

    if use_team:
        if not experts_already_ran:
            enriched = run_team_first(enriched, cfg, names=plugin_names)
        team_md = render_team_markdown(enriched)

    if verify_dict is not None:
        from agent_reach.daily_run.verify import verify_from_dict

        verify = verify_from_dict(verify_dict)
    else:
        verify = verify_snapshots(baseline, enriched, cfg)
    verify_dict = verify.to_dict()

    curve = None
    curve_md = ""
    mss_actual = enriched.get("mss_intraday_actual") or []
    scan_ids = [str(s.get("scan_id") or f"S{i + 1}") for i, s in enumerate(enriched.get("intraday_scans") or [])]
    if mss_actual:
        pred = baseline.get("mss_range")
        pred_tuple = (float(pred[0]), float(pred[1])) if pred and len(pred) == 2 else None
        curve = analyze_intraday_curve(
            [float(x) for x in mss_actual if x is not None],
            predicted_range=pred_tuple,
            scan_ids=scan_ids or None,
        )
        curve_md = render_curve_markdown(curve)

    research_results = run_exa_research(enriched, cfg)
    research_md = render_research_markdown(enriched, research_results=research_results, settings=cfg) or ""

    extra_parts: list[str] = []
    if watchlist_adjust is not None:
        from agent_reach.daily_run.watchlist_manager import (
            WatchlistAdjustResult,
            WatchlistChange,
            render_watchlist_adjust_markdown,
        )

        wl_md = render_watchlist_adjust_markdown(
            WatchlistAdjustResult(
                applied=bool(watchlist_adjust.get("applied")),
                portfolio={},
                changes=[
                    WatchlistChange(**c) for c in (watchlist_adjust.get("changes") or [])
                ],
                message=str(watchlist_adjust.get("message") or ""),
            )
        )
        if wl_md:
            extra_parts.append(wl_md)

    if code_review is not None:
        from agent_reach.daily_run.close_code_review import CodeReviewResult

        cr_obj = (
            code_review
            if isinstance(code_review, CodeReviewResult)
            else CodeReviewResult(**code_review)
        )
        cr_md = render_code_review_markdown(cr_obj)
        if cr_md:
            extra_parts.append(cr_md)

    forecast_review = None
    forecast_review_md = ""
    improvements_md = ""
    improvements = None
    try:
        from agent_reach.daily_run.week_forecast_tracker import (
            render_forecast_review_markdown,
            review_active_forecast,
        )

        mss_for_review = enriched.get("mss_final")
        if mss_for_review is None:
            mss_for_review = verify_dict.get("current_mss")
        forecast_review = review_active_forecast(
            enriched,
            settings=cfg,
            mss_actual=mss_for_review,
        )
        if forecast_review:
            forecast_review_md = render_forecast_review_markdown(forecast_review)
    except Exception as exc:
        _workflow_harness_error(harness_errors, "forecast_review", exc)

    exp_append = append_experience_entry(
        enriched,
        verify_dict,
        curve=curve,
        research=research_results,
        settings=cfg,
        forecast_review=forecast_review.to_dict() if forecast_review else None,
    )
    exp_path = exp_append.path
    experience_harness = exp_append.harness
    exp_md = render_experience_markdown(limit=3, settings=cfg) or ""

    if cfg.get("close_improvements", {}).get("enabled", True):
        from agent_reach.daily_run.close_improvements import (
            generate_close_improvements,
            render_improvements_markdown,
        )

        curve_payload = curve.to_dict() if hasattr(curve, "to_dict") else curve
        improvements = generate_close_improvements(
            baseline=baseline,
            current=enriched,
            verify=verify_dict,
            settings=cfg,
            curve=curve_payload,
            scans=enriched.get("intraday_scans"),
            trades=intraday_trades,
            watchlist_adjust=watchlist_adjust,
            forecast_review=forecast_review.to_dict() if forecast_review else None,
        )
        improvements_md = render_improvements_markdown(improvements) or ""

    verify_md = render_verify_markdown(verify)

    market_review_md = ""
    market_review_obj = None
    from agent_reach.daily_run.market_review import (
        get_or_collect_market_review,
        market_review_enabled,
        render_market_review_markdown,
    )
    from agent_reach.daily_run.redfox_collector import attach_redfox_close_markdown, redfox_enabled

    if market_review_enabled(cfg):
        market_review_obj = get_or_collect_market_review(settings=cfg)
        if market_review_obj:
            market_review_md = render_market_review_markdown(market_review_obj)
            enriched["market_review"] = market_review_obj

    redfox_md = ""
    if redfox_enabled(cfg):
        redfox_md, redfox_result = attach_redfox_close_markdown(
            enriched,
            market_review_obj,
            settings=cfg,
        )
        if redfox_result:
            enriched["redfox"] = redfox_result.to_dict()
        if redfox_md:
            market_review_md = (
                (market_review_md + "\n\n" + redfox_md) if market_review_md else redfox_md
            )

    portfolio_md = ""
    portfolio_summary_obj = None
    pnl_target_cycle: dict[str, Any] | None = None
    if portfolio_summary:
        from agent_reach.daily_run.close_portfolio_summary import (
            build_close_portfolio_summary,
            render_close_portfolio_markdown,
        )

        portfolio_summary_obj = build_close_portfolio_summary(
            enriched,
            baseline,
            trades=intraday_trades,
            intraday_trades=intraday_trades,
            watchlist_adjust=watchlist_adjust,
            settings=cfg,
        )
        from agent_reach.daily_run.pnl_target import run_pnl_target_close_cycle

        pnl_target_cycle = run_pnl_target_close_cycle(
            portfolio_summary_obj.to_dict(),
            settings=cfg,
        )
        portfolio_md = render_close_portfolio_markdown(
            portfolio_summary_obj,
            pnl_target_cycle=pnl_target_cycle,
        )
        from agent_reach.daily_run.daily_pnl_history import append_daily_pnl

        append_daily_pnl(
            portfolio_summary_obj.to_dict(),
            source="close",
        )

    from agent_reach.daily_run.auditor import run_data_audit

    audit = run_data_audit(enriched, cfg)
    harness_skills_report = None
    try:
        from agent_reach.daily_run.close_harness_skills import run_close_harness_refinements

        harness_skills_report = run_close_harness_refinements(
            verify=verify_dict,
            improvements=improvements,
            audit=audit,
            forecast_review=forecast_review.to_dict() if forecast_review else None,
            watchlist_adjust=watchlist_adjust,
            portfolio_summary=portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
            pnl_target_cycle=pnl_target_cycle,
            snapshot=enriched,
            settings=cfg,
        )
        enriched["harness_skills"] = harness_skills_report.to_dict()
    except Exception as exc:
        _workflow_harness_error(harness_errors, "close_harness_skills", exc)
        enriched["harness_skills"] = {"skipped": True, "error": str(exc)}

    audit_lines: list[str] = []
    if not audit.passed:
        audit_lines.append(f"**数据审计未通过：** {'；'.join(audit.issues)}")
    if audit.warnings:
        audit_lines.append("**审计警告：**")
        audit_lines.extend(f"- {w}" for w in audit.warnings)
    if audit_lines:
        audit_block = "\n".join(audit_lines)
        verify_md = audit_block + ("\n\n---\n\n" + verify_md if verify_md else "")

    md = "\n\n---\n\n".join(
        p
        for p in [
            market_review_md,
            team_md,
            curve_md,
            research_md,
            *extra_parts,
            forecast_review_md,
            improvements_md,
            exp_md,
            verify_md,
            portfolio_md,
        ]
        if p
    )

    curve_payload = curve.to_dict() if curve is not None and hasattr(curve, "to_dict") else curve
    from agent_reach.daily_run.report_narrative import generate_close_narrative

    close_narrative = generate_close_narrative(
        snapshot=enriched,
        verify=verify_dict,
        portfolio_summary=portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
        curve=curve_payload,
        forecast_review=forecast_review.to_dict() if forecast_review else None,
        settings=cfg,
    )

    push_harness_summary = _harness_push_summary_enabled(cfg, report_kind="close")
    harness_result: dict[str, Any] = {}
    harness_md = ""
    if push_harness_summary:
        try:
            harness_result = _run_close_harness_layer_ab(
                enriched=enriched,
                verify_dict=verify_dict,
                curve=curve,
                forecast_review=forecast_review,
                portfolio_summary_obj=portfolio_summary_obj,
                settings=cfg,
                harness_skills_report=harness_skills_report,
                experience_harness=experience_harness,
            )
            harness_md = _finalize_close_harness(
                harness_result,
                portfolio_summary_obj=portfolio_summary_obj,
                settings=cfg,
                harness_errors=harness_errors,
            )
        except Exception as exc:
            _workflow_harness_error(harness_errors, "close_harness_layer_ab", exc)
            harness_result = {"skipped": True, "error": str(exc)}

    feishu_result = None
    if push:
        audit_cfg = cfg.get("data_audit", {})
        if not audit.passed and audit_cfg.get("close_block_on_audit_fail", True):
            raise RuntimeError(f"收盘数据审计未通过：{audit.summary()}")

        from agent_reach.config import Config

        cfg_obj = config or Config()
        sections = render_close_sections(
            verify_name=verify.name or verify.code or "大盘",
            market_markdown=market_review_md,
            team_markdown=team_md,
            curve_markdown=curve_md,
            research_markdown=research_md or "",
            experience_markdown=exp_md or "",
            verify_markdown=verify_md,
            portfolio_markdown=portfolio_md,
            harness_markdown=harness_md,
            narrative=close_narrative,
        )
        feishu_result = push_report_sections(
            sections,
            settings=cfg,
            config=cfg_obj,
            report_type="verify",
            fallback_title=title or f"🧠 收盘复盘 · {verify.name or verify.code or '大盘'}",
            template=cfg.get("report", {}).get("feishu_template_verify", "purple"),
            split=split_push_enabled(cfg, report_kind="close"),
        )

    from agent_reach.daily_run.prior_close import save_close_baseline

    close_baseline_path = save_close_baseline(snapshot=enriched, verify=verify_dict)

    if not push_harness_summary:
        try:
            harness_result = _run_close_harness_layer_ab(
                enriched=enriched,
                verify_dict=verify_dict,
                curve=curve,
                forecast_review=forecast_review,
                portfolio_summary_obj=portfolio_summary_obj,
                settings=cfg,
                harness_skills_report=harness_skills_report,
                experience_harness=experience_harness,
            )
        except Exception as exc:
            _workflow_harness_error(harness_errors, "close_harness_layer_ab", exc)
            harness_result = {"skipped": True, "error": str(exc)}
        else:
            rollback = None
            try:
                from agent_reach.daily_run.harness import auto_rollback_on_bad_trade

                rollback = auto_rollback_on_bad_trade(
                    portfolio_summary=portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
                    harness_result=harness_result,
                    settings=cfg,
                    job="close",
                )
            except Exception as exc:
                _workflow_harness_error(harness_errors, "close_harness_auto_rollback", exc)
            if rollback and rollback.get("triggered"):
                harness_result["auto_rollback"] = rollback

    followup_steps = push_harness_followups(
        settings=cfg,
        config=config,
        report_kind="close",
        harness_result=harness_result,
        harness_errors=harness_errors,
        push=push,
        summary_in_main_push=push_harness_summary,
    )

    result: dict[str, Any] = {
        "verify": verify_dict,
        "snapshot": enriched,
        "markdown": md,
        "team_markdown": team_md,
        "curve_markdown": curve_md,
        "research_markdown": research_md,
        "experience_markdown": exp_md,
        "verify_markdown": verify_md,
        "market_review_markdown": market_review_md,
        "market_review": market_review_obj,
        "portfolio_markdown": portfolio_md,
        "portfolio_summary": portfolio_summary_obj.to_dict() if portfolio_summary_obj else None,
        "llm_narrative": close_narrative,
        "research": research_results,
        "experience_path": str(exp_path),
        "feishu": feishu_result,
        "close_baseline_path": str(close_baseline_path) if close_baseline_path else None,
        "forecast_review": forecast_review.to_dict() if forecast_review else None,
        "harness": harness_result,
        "audit": {
            "passed": audit.passed,
            "issues": audit.issues,
            "warnings": audit.warnings,
        },
        "harness_followup_steps": followup_steps,
    }
    if harness_errors:
        result["harness_errors"] = harness_errors
    return result


def prepare_close_run(
    snapshot: dict[str, Any],
    baseline: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    scans: Optional[list[dict[str, Any]]] = None,
    trades: Optional[list[dict[str, Any]]] = None,
    attach_intraday: bool = True,
) -> dict[str, Any]:
    """Shared pre-close pipeline for schedule cron and CLI."""
    cfg = effective_settings(settings)
    steps: list[str] = []
    snap = dict(snapshot)
    pf_work = portfolio
    scan_list = list(scans or [])
    trade_list = list(trades or [])

    if attach_intraday and scan_list:
        snap.setdefault("intraday_scans", scan_list)
        if not snap.get("mss_intraday_actual"):
            snap["mss_intraday_actual"] = [
                s.get("mss_final") for s in scan_list if s.get("mss_final") is not None
            ]

    from agent_reach.daily_run.close_code_review import run_close_code_review
    from agent_reach.daily_run.snapshot_builder import save_portfolio
    from agent_reach.daily_run.symbols import sync_snapshot_portfolio
    from agent_reach.daily_run.watchlist_manager import (
        adjust_watchlist,
        collect_intraday_sold_codes,
        is_watchlist_adjust_enabled,
    )

    close_team = (cfg.get("team") or {}).get("close_team_first", True) is not False
    if close_team and experts_enabled(cfg, workflow="close"):
        snap = run_team_first(snap, cfg)
        steps.append("team_first")
    elif mss_experts_enabled(cfg, workflow="close"):
        from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, run_experts

        snap = run_experts(snap, cfg, names=MSS_EXPERT_NAMES)
        steps.append("mss_experts")

    verify_result = verify_snapshots(baseline, snap, cfg)
    verify_out = verify_result.to_dict()
    steps.append("verify")

    wl_result = None
    portfolio_dirty = False
    if is_watchlist_adjust_enabled(cfg):
        wl_result = adjust_watchlist(
            pf_work,
            snap,
            cfg,
            "close",
            verify=verify_out,
            sold_codes=collect_intraday_sold_codes(cfg),
        )
        if wl_result.applied:
            pf_work = wl_result.portfolio
            portfolio_dirty = True
            steps.append("watchlist_adjust")

    code_review_result = run_close_code_review(
        portfolio=pf_work,
        snapshot=snap,
        settings=cfg,
        scans=scan_list,
        trades=trade_list,
    )
    steps.append("code_review")
    if code_review_result.portfolio_changed and code_review_result.portfolio:
        pf_work = code_review_result.portfolio
        portfolio_dirty = True

    if portfolio_dirty:
        save_portfolio(pf_work)
        sync_snapshot_portfolio(snap, pf_work)
        steps.append("portfolio_save")

    return {
        "snapshot": snap,
        "portfolio": pf_work,
        "verify": verify_out,
        "pre_verify": verify_out,
        "watchlist_adjust": wl_result.to_dict() if wl_result else None,
        "code_review": code_review_result.to_dict(),
        "steps": steps,
    }


def morning_baseline_path(code: str) -> Path:
    from agent_reach.daily_run.snapshot_builder import _normalize_code

    norm = _normalize_code(str(code))
    return Path.home() / ".agent-reach" / "daily_run" / "baselines" / "morning" / f"{norm}.json"


def save_morning_baseline(
    snapshot: dict[str, Any],
    path: Optional[Path] = None,
    *,
    code: Optional[str] = None,
    primary_code: Optional[str] = None,
) -> Path:
    """Persist morning snapshot for later close verification."""
    import json

    from agent_reach.daily_run.snapshot_builder import _normalize_code

    norm = _normalize_code(str(code or snapshot.get("code") or ""))
    record = enrich_morning_baseline(snapshot)
    written: Optional[Path] = None
    if norm and norm != "MARKET":
        out = morning_baseline_path(norm)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written = out

    pc = _normalize_code(str(primary_code)) if primary_code else None
    if path is not None or (pc and norm == pc):
        legacy = path or _default_baseline_path()
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return legacy
    if written:
        return written
    out = path or _default_baseline_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def load_morning_baseline(path: Optional[Path] = None, *, code: Optional[str] = None) -> dict[str, Any]:
    import json

    from agent_reach.daily_run.snapshot_builder import _normalize_code

    if code:
        norm = _normalize_code(str(code))
        per = morning_baseline_path(norm)
        if per.exists():
            return json.loads(per.read_text(encoding="utf-8"))
        legacy = _default_baseline_path()
        if legacy.exists():
            data = json.loads(legacy.read_text(encoding="utf-8"))
            if _normalize_code(str(data.get("code", ""))) == norm:
                return data
        raise FileNotFoundError(
            f"未找到 {norm} 的早盘基线：{per}，请先运行 daily-run morning --save-baseline"
        )

    p = path or _default_baseline_path()
    if not p.exists():
        raise FileNotFoundError(f"未找到早盘基线：{p}，请先运行 daily-run morning --save-baseline")
    return json.loads(p.read_text(encoding="utf-8"))


def _morning_title(report: dict[str, Any]) -> str:
    name = report.get("name") or report.get("code") or "大盘"
    verdict = report.get("verdict", "")
    return f"🌅 股票大师 · {name} · {verdict}"


def _push_markdown(
    title: str,
    markdown: str,
    settings: dict[str, Any],
    config,
    *,
    report_type: str = "premarket",
    template: Optional[str] = None,
) -> dict[str, Any]:
    from agent_reach.config import Config
    from agent_reach.integrations.feishu import send_card

    cfg_obj = config or Config()
    templates = settings.get("report", {})
    tpl = template or templates.get(f"feishu_template_{report_type}", "blue")
    return send_card(cfg_obj, title, markdown, template=tpl)


def _send_start_notification(config, settings: dict[str, Any]) -> None:
    from agent_reach.config import Config
    from agent_reach.integrations.feishu import send_card

    cfg = config or Config()
    tpl = settings.get("report", {}).get("feishu_template_premarket", "orange")
    send_card(
        cfg,
        "🌅 早盘分析已启动",
        "**股票大师 daily_run_skill**\n\n"
        "正在执行：**数据审计** → **MSS 决策** → 飞书推送\n\n"
        "预计完成时间：**1–3 分钟**",
        template=tpl,
    )


def run_weekly(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    push: bool = True,
    title: Optional[str] = None,
    config=None,
    portfolio: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Saturday weekly summary: PnL, holdings, watchlist, hot sectors → Feishu."""
    from agent_reach.daily_run.weekly_digest import save_weekly_digest
    from agent_reach.daily_run.weekly_report import (
        generate_weekly_report,
        render_weekly_markdown,
        weekly_report_title,
    )

    cfg = effective_settings(settings)
    weekly_cfg = cfg.get("weekly_report") or {}
    harness_errors: list[str] = []
    if weekly_cfg.get("enabled", True) is False:
        return {"steps": ["skipped"], "message": "weekly_report disabled", "feishu": None}

    steps: list[str] = ["generate"]
    report = generate_weekly_report(snapshot, cfg, portfolio=portfolio)
    digest_path = save_weekly_digest(report.to_dict())
    steps.append("digest")

    from agent_reach.daily_run.watchlist_candidates import update_candidates_from_weekly

    wl_candidates = update_candidates_from_weekly(report, cfg)
    report.watchlist_candidates_update = wl_candidates
    steps.append("watchlist_candidates")

    from agent_reach.daily_run.skill_improvements_apply import apply_weekly_skill_closure

    skill_writeback = apply_weekly_skill_closure(report.to_dict(), cfg)
    if skill_writeback.get("skipped"):
        steps.append("skill_writeback_skipped")
    else:
        steps.append("skill_writeback")
        if skill_writeback.get("synced_skills"):
            steps.append(f"skill_sync_{len(skill_writeback['synced_skills'])}")
        if skill_writeback.get("applied_config"):
            steps.append(f"settings_applied_{len(skill_writeback['applied_config'])}")
        audit = skill_writeback.get("skill_audit") or {}
        if audit and audit.get("ok") is not False:
            steps.append("skill_audit")
            if audit.get("fixes"):
                steps.append(f"skill_audit_fixes_{len(audit['fixes'])}")
        gates = audit.get("gates") or {}
        if gates and gates.get("ok") is False and not gates.get("skipped"):
            steps.append("skill_gates_failed")

    harness_result: dict[str, Any] = {}
    layer_a_refinement_id = ""
    weekly_skills_report = None
    try:
        from agent_reach.daily_run.weekly_harness_skills import (
            run_weekly_harness_refinements,
            run_weekly_layer_a_refinement,
        )

        weekly_skills_report = run_weekly_harness_refinements(
            report.to_dict(),
            settings=cfg,
            skill_writeback=skill_writeback,
        )
        harness_result["finance_variance"] = weekly_skills_report.finance_variance
        harness_result["finance_close_plan"] = weekly_skills_report.finance_close_plan
        harness_result["run_guard"] = weekly_skills_report.run_guard

        weekly_evidence = {
            "report": report.to_dict(),
            "applied_config": skill_writeback.get("applied_config") or [],
        }
        layer_a = run_weekly_layer_a_refinement(weekly_evidence, settings=cfg)
        harness_result["layer_a"] = layer_a
        weekly_skills_report.weekly_layer_a = layer_a
        if layer_a.get("refinement_id"):
            layer_a_refinement_id = str(layer_a["refinement_id"])
            steps.append("harness_layer_a")
        if weekly_skills_report.run_guard.get("refinement_id"):
            steps.append("harness_run_guard")
        harness_result["weekly_skills"] = weekly_skills_report.to_dict()
    except Exception as exc:
        _workflow_harness_error(harness_errors, "weekly_harness_layer_a", exc)
        harness_result["layer_a"] = {"skipped": True, "error": str(exc)}

    from agent_reach.daily_run.report_narrative import generate_weekly_narrative

    report.llm_narrative = generate_weekly_narrative(report.to_dict(), settings=cfg)
    steps.append("llm_narrative")

    md = render_weekly_markdown(report)
    steps.append("render")

    feishu_result = None
    gate_alert: str = ""
    gates = ((skill_writeback.get("skill_audit") or {}).get("gates") or {})
    block_push = bool(gates.get("block_weekly_push"))
    if block_push:
        from agent_reach.daily_run.skill_gates import format_gate_alert_markdown

        gate_alert = format_gate_alert_markdown(gates)
        steps.append("push_blocked_skill_gates")

    if push and not block_push:
        from agent_reach.config import Config

        from agent_reach.daily_run.report_push import (
            push_report_sections,
            render_weekly_push_sections,
            split_push_enabled,
        )

        cfg_obj = config or Config()
        sections = render_weekly_push_sections(report)
        feishu_result = push_report_sections(
            sections,
            settings=cfg,
            config=cfg_obj,
            report_type="weekly",
            fallback_title=title or weekly_report_title(report),
            template=cfg.get("report", {}).get("feishu_template_weekly", "blue"),
            split=split_push_enabled(cfg, report_kind="weekly"),
        )
        steps.append("push")
        if feishu_result.get("mode") == "split":
            steps.append(f"push_split_{feishu_result.get('count', 0)}")
    elif push and block_push and gate_alert:
        from agent_reach.config import Config
        from agent_reach.daily_run.report_push import ReportSection, push_report_sections

        cfg_obj = config or Config()
        feishu_result = push_report_sections(
            [ReportSection(category="weekly_insights", title="Skill 门禁", body=gate_alert)],
            settings=cfg,
            config=cfg_obj,
            report_type="weekly",
            fallback_title="⛔ 周六 Skill 门禁未通过",
            template="red",
            split=False,
        )
        steps.append("push_gate_alert")

    try:
        from agent_reach.daily_run.harness import refine_after_job_llm

        weekly_evidence = {
            "report": report.to_dict(),
            "applied_config": skill_writeback.get("applied_config") or [],
        }
        layer_b = refine_after_job_llm("weekly", evidence=weekly_evidence, settings=cfg)
        harness_result["layer_b"] = layer_b
        if layer_b.get("refinement_id"):
            steps.append("harness_layer_b")
    except Exception as exc:
        _workflow_harness_error(harness_errors, "weekly_harness_layer_b", exc)
        harness_result["layer_b"] = {"skipped": True, "error": str(exc)}

    harness_result["weekly_skills"] = harness_result.get("weekly_skills") or (
        weekly_skills_report.to_dict() if weekly_skills_report is not None else {}
    )
    if push and not block_push:
        from agent_reach.config import Config
        from agent_reach.daily_run.harness import auto_rollback_on_bad_trade

        rollback = auto_rollback_on_bad_trade(
            portfolio_summary={"weekly_pnl_pct": report.weekly_pnl_pct},
            harness_result=harness_result,
            settings=cfg,
            job="weekly",
        )
        if rollback.get("triggered"):
            harness_result["auto_rollback"] = rollback
        cfg_obj = config or Config()
        summary_enabled = _harness_push_summary_enabled(cfg, report_kind="weekly")
        if summary_enabled and _push_harness_summary_card(
            harness_result,
            settings=cfg,
            config=cfg_obj,
            report_kind="weekly",
            harness_errors=harness_errors,
            week_start=str(report.week_start or ""),
            week_end=str(report.week_end or ""),
        ):
            steps.append("push_harness_summary")
        steps.extend(
            push_harness_followups(
                settings=cfg,
                config=cfg_obj,
                report_kind="weekly",
                harness_result=harness_result,
                harness_errors=harness_errors,
                push=True,
                summary_in_main_push=summary_enabled,
            )
        )

    layer_b_refinement_id = ""
    for layer in (harness_result.get("layer_b") or {},):
        if isinstance(layer, dict) and layer.get("refinement_id"):
            layer_b_refinement_id = str(layer["refinement_id"])
            break
    if layer_b_refinement_id and layer_b_refinement_id != layer_a_refinement_id:
        from agent_reach.daily_run.skill_improvements_apply import annotate_weekly_harness_audit

        audit_note = annotate_weekly_harness_audit(
            week_start=str(report.week_start or ""),
            week_end=str(report.week_end or ""),
            refinement_id=layer_b_refinement_id,
            settings=cfg,
            skip_sync=True,
        )
        steps.append("harness_skill_annotate")
        skill_writeback["harness_annotation"] = audit_note
        if (audit_note.get("skill_changed") or audit_note.get("fragment_changed")) and weekly_cfg.get(
            "skill_sync_local", True
        ) is not False:
            from agent_reach.daily_run.skill_improvements_apply import sync_canonical_skill_to_local

            sync_canonical_skill_to_local(cfg)
            steps.append("skill_sync_post_harness")

    return {
        "steps": steps,
        "report": report.to_dict(),
        "digest_path": str(digest_path),
        "watchlist_candidates": wl_candidates,
        "skill_writeback": skill_writeback,
        "llm_narrative": report.llm_narrative,
        "harness": harness_result,
        "markdown": md,
        "feishu": feishu_result,
        **({"harness_errors": harness_errors} if harness_errors else {}),
    }


def run_forecast(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    push: bool = True,
    title: Optional[str] = None,
    config=None,
    portfolio: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Sunday next-week forecast: MSS paths, symbols, news → Feishu."""
    from agent_reach.daily_run.week_forecast import (
        forecast_title,
        generate_week_forecast,
        persist_week_forecast,
        render_forecast_markdown,
    )

    cfg = effective_settings(settings)
    wf_cfg = cfg.get("week_forecast") or {}
    harness_errors: list[str] = []
    if wf_cfg.get("enabled", True) is False:
        return {"steps": ["skipped"], "message": "week_forecast disabled", "feishu": None}

    steps: list[str] = ["generate"]
    forecast = generate_week_forecast(snapshot, cfg, portfolio=portfolio)
    path = persist_week_forecast(forecast)
    steps.append("persist")

    md = render_forecast_markdown(forecast)
    steps.append("render")

    feishu_result = None
    if push:
        from agent_reach.config import Config

        from agent_reach.daily_run.report_push import (
            push_report_sections,
            render_forecast_push_sections,
            split_push_enabled,
        )

        cfg_obj = config or Config()
        sections = render_forecast_push_sections(forecast)
        feishu_result = push_report_sections(
            sections,
            settings=cfg,
            config=cfg_obj,
            report_type="forecast",
            fallback_title=title or forecast_title(forecast),
            template=cfg.get("report", {}).get("feishu_template_forecast", "blue"),
            split=split_push_enabled(cfg, report_kind="forecast"),
        )
        steps.append("push")
        if feishu_result.get("mode") == "split":
            steps.append(f"push_split_{feishu_result.get('count', 0)}")

    harness_result: dict[str, Any] = {}
    try:
        from agent_reach.daily_run.forecast_harness_skills import (
            run_forecast_harness_refinements,
            run_forecast_layer_a_refinement,
        )
        from agent_reach.daily_run.harness import refine_after_job_llm

        forecast_dict = forecast.to_dict()
        skills_report = run_forecast_harness_refinements(forecast_dict, settings=cfg)
        forecast_evidence = {"forecast": forecast_dict}
        layer_a = run_forecast_layer_a_refinement(forecast_evidence, settings=cfg)
        layer_b = refine_after_job_llm("forecast", evidence=forecast_evidence, settings=cfg)
        harness_result = {
            "forecast_calibrate": skills_report.forecast_calibrate,
            "layer_a": layer_a,
            "layer_b": layer_b,
            "forecast_skills": skills_report.to_dict(),
        }
    except Exception as exc:
        _workflow_harness_error(harness_errors, "forecast_harness", exc)
        harness_result = {"skipped": True, "error": str(exc)}

    if push:
        from agent_reach.config import Config

        cfg_obj = config or Config()
        summary_enabled = _harness_push_summary_enabled(cfg, report_kind="forecast")
        if summary_enabled and _push_harness_summary_card(
            harness_result,
            settings=cfg,
            config=cfg_obj,
            report_kind="forecast",
            harness_errors=harness_errors,
        ):
            steps.append("push_harness_summary")
        steps.extend(
            push_harness_followups(
                settings=cfg,
                config=cfg_obj,
                report_kind="forecast",
                harness_result=harness_result,
                harness_errors=harness_errors,
                push=True,
                summary_in_main_push=summary_enabled,
            )
        )

    return {
        "steps": steps,
        "forecast": forecast.to_dict(),
        "forecast_path": str(path),
        "harness": harness_result,
        "markdown": md,
        "feishu": feishu_result,
        **({"harness_errors": harness_errors} if harness_errors else {}),
    }
