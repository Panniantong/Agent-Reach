# -*- coding: utf-8
"""Run morning / close / intraday once per portfolio symbol."""

from __future__ import annotations

import gc
import time
from typing import Any, Optional

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.snapshot_builder import build_and_save, load_portfolio
from agent_reach.daily_run.symbols import resolve_target_symbols, symbol_display_name


def symbol_push_interval(settings: dict[str, Any]) -> float:
    sched = settings.get("schedule") or {}
    report = settings.get("report") or {}
    return float(
        sched.get("symbol_push_interval_seconds")
        or report.get("split_push_interval_seconds")
        or 0.3
    )


def symbol_push_mode(settings: dict[str, Any]) -> str:
    """merge_by_category | per_symbol"""
    sched = settings.get("schedule") or {}
    return str(sched.get("symbol_push_mode", "merge_by_category")).lower()


def _should_merge_push(settings: dict[str, Any]) -> bool:
    return symbol_push_mode(settings) == "merge_by_category"


def run_morning_for_symbols(
    *,
    settings: Optional[dict[str, Any]] = None,
    push: bool = True,
    config=None,
    doctor_channels: Optional[dict[str, dict]] = None,
    symbols: Optional[list[str]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.report_push import (
        merge_sections_by_category,
        morning_sections_from_run,
        push_report_sections,
        split_push_enabled,
    )
    from agent_reach.daily_run.workflows import run_morning, save_morning_baseline
    from agent_reach.daily_run.team import expert_card_enabled

    cfg = settings or load_settings()
    pf = load_portfolio()
    targets = symbols or resolve_target_symbols(pf, cfg)
    primary = pf.get("primary_code")
    merge_push = _should_merge_push(cfg)
    symbol_results: list[dict[str, Any]] = []
    section_groups: list[tuple[str, list]] = []
    expert_snapshots: list[tuple[str, str, dict[str, Any]]] = []
    decision_entries: list[tuple[str, str, dict[str, Any]]] = []
    errors: list[str] = []

    for i, code in enumerate(targets):
        name = symbol_display_name(pf, code)
        try:
            snap, path = build_and_save(
                report_type="premarket",
                config=config,
                primary_code=code,
                portfolio=pf,
            )
            run_result = run_morning(
                snap,
                settings=cfg,
                doctor_channels=doctor_channels,
                push=push and not merge_push,
                start_notify=push and not merge_push and i == 0,
                config=config,
            )
            baseline_path = save_morning_baseline(
                run_result["snapshot"],
                code=code,
                primary_code=primary,
            )
            from agent_reach.daily_run.intraday import record_morning_scan

            record_morning_scan(run_result, settings=cfg, code=code)
            if merge_push:
                section_groups.append((name, morning_sections_from_run(run_result)))
                report = (run_result.get("evaluation") or {}).get("report") or {}
                decision_entries.append((name, code, report))
                if expert_card_enabled(cfg, workflow="morning"):
                    expert_snapshots.append((name, code, run_result["snapshot"]))
            symbol_results.append(
                {
                    "code": code,
                    "name": name,
                    "snapshot_path": str(path),
                    "baseline_path": str(baseline_path),
                    "result": run_result,
                    "feishu": run_result.get("feishu"),
                }
            )
        except Exception as exc:
            errors.append(f"{code}: {exc}")

    if errors and not symbol_results:
        raise RuntimeError(errors[0])

    feishu_result = None
    if push and merge_push and section_groups:
        from agent_reach.config import Config
        from agent_reach.daily_run.workflows import _send_start_notification

        _send_start_notification(config, cfg)
        merged = merge_sections_by_category(
            section_groups,
            report_kind="morning",
            expert_snapshots=expert_snapshots or None,
            decision_entries=decision_entries or None,
        )
        feishu_result = push_report_sections(
            merged,
            settings=cfg,
            config=config or Config(),
            report_type="premarket",
            fallback_title="🌅 早盘 · 全持仓",
            split=split_push_enabled(cfg, report_kind="morning"),
        )

    return {
        "job": "morning",
        "symbols_mode": (cfg.get("schedule") or {}).get("symbols_mode", "primary"),
        "symbol_push_mode": symbol_push_mode(cfg),
        "symbols": targets,
        "symbol_results": symbol_results,
        "errors": errors,
        "feishu": feishu_result or (symbol_results[-1]["feishu"] if symbol_results else None),
    }


def run_intraday_for_symbols(
    *,
    settings: Optional[dict[str, Any]] = None,
    push: bool = True,
    config=None,
    doctor_channels: Optional[dict[str, dict]] = None,
    symbols: Optional[list[str]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.intraday import (
        default_state_path,
        load_state,
        run_intraday,
        should_evaluate_trade,
    )
    from agent_reach.daily_run.report_push import ReportSection, merged_category_title, push_report_sections
    from agent_reach.daily_run.schedule import INTRADAY_MAX_SCANS

    cfg = settings or load_settings()
    pf = load_portfolio()
    targets = symbols or resolve_target_symbols(pf, cfg, workflow="intraday")
    merge_push = _should_merge_push(cfg)
    sched = cfg.get("schedule") or {}
    gc_between = sched.get("intraday_gc_between_symbols", True) is not False
    symbol_results: list[dict[str, Any]] = []
    scan_bodies: list[tuple[str, str]] = []
    scan_id: Optional[str] = None
    errors: list[str] = []

    for code in targets:
        name = symbol_display_name(pf, code)
        state_path = default_state_path(code)
        state = load_state(state_path)

        if len(state.scans) >= INTRADAY_MAX_SCANS:
            symbol_results.append(
                {
                    "code": code,
                    "skipped": True,
                    "reason": f"今日扫描已达 {INTRADAY_MAX_SCANS} 次上限",
                }
            )
            continue
        try:
            snap, path = build_and_save(
                report_type="intraday",
                config=config,
                primary_code=code,
                portfolio=pf,
            )
            do_trade = should_evaluate_trade(state, cfg, state_path=state_path)
            run_result = run_intraday(
                snap,
                settings=cfg,
                doctor_channels=doctor_channels,
                push=push and not merge_push,
                trade=do_trade,
                config=config,
                state_path=state_path,
            )
            inner = run_result.get("scan") or {}
            scan = inner.get("scan") or {}
            scan_id = scan.get("scan_id") or scan_id
            md = inner.get("markdown") or ""
            if merge_push and md.strip():
                scan_bodies.append((name, md.strip()))
                trade_md = (run_result.get("trade") or {}).get("markdown")
                if trade_md:
                    scan_bodies[-1] = (name, md.strip() + "\n\n---\n\n" + trade_md.strip())
            symbol_results.append(
                {
                    "code": code,
                    "name": name,
                    "snapshot_path": str(path),
                    "trade_evaluated": do_trade,
                    "result": run_result,
                    "feishu": run_result.get("feishu"),
                }
            )
        except Exception as exc:
            errors.append(f"{code}: {exc}")
        finally:
            if gc_between:
                gc.collect()

    if errors and not symbol_results:
        raise RuntimeError(errors[0])

    feishu_result = None
    if push and merge_push and scan_bodies:
        from agent_reach.config import Config

        body = "\n\n---\n\n".join(f"## {name}\n\n{content}" for name, content in scan_bodies)
        title = merged_category_title(
            report_kind="intraday",
            category="scan",
            index=1,
            total=1,
            symbol_count=len(scan_bodies),
        )
        if scan_id:
            title = f"📊 盘中 {scan_id} · {len(scan_bodies)}只"
        tpl = cfg.get("report", {}).get("feishu_template_intraday", "blue")
        from agent_reach.integrations.feishu import send_card

        feishu_result = send_card(config or Config(), title, body, template=tpl)

    return {
        "job": "intraday",
        "symbol_push_mode": symbol_push_mode(cfg),
        "symbols": targets,
        "symbol_results": symbol_results,
        "errors": errors,
        "feishu": feishu_result or next((r.get("feishu") for r in reversed(symbol_results) if r.get("feishu")), None),
    }


def run_close_for_symbols(
    *,
    settings: Optional[dict[str, Any]] = None,
    push: bool = True,
    config=None,
    symbols: Optional[list[str]] = None,
) -> dict[str, Any]:
    from agent_reach.daily_run.intraday import load_state
    from agent_reach.daily_run.report_push import (
        ReportSection,
        close_sections_from_run,
        merge_sections_by_category,
        merged_category_title,
        push_report_sections,
        split_push_enabled,
    )
    from agent_reach.daily_run.workflows import load_morning_baseline, run_close
    from agent_reach.daily_run.team import expert_card_enabled

    cfg = settings or load_settings()
    pf = load_portfolio()
    targets = symbols or resolve_target_symbols(pf, cfg)
    merge_push = _should_merge_push(cfg)
    symbol_results: list[dict[str, Any]] = []
    section_groups: list[tuple[str, list]] = []
    expert_snapshots: list[tuple[str, str, dict[str, Any]]] = []
    errors: list[str] = []
    shared_state = load_state()

    for code in targets:
        name = symbol_display_name(pf, code)
        try:
            baseline = load_morning_baseline(code=code)
            snap, path = build_and_save(
                report_type="close",
                config=config,
                primary_code=code,
                portfolio=pf,
            )
            state = load_state(code=code)
            if state.scans:
                snap["intraday_scans"] = state.scans
                snap["mss_intraday_actual"] = [s.get("mss_final") for s in state.scans]

            run_result = run_close(
                snap,
                baseline,
                settings=cfg,
                push=push and not merge_push,
                config=config,
                intraday_trades=state.trades,
                portfolio_summary=not merge_push,
            )
            if merge_push:
                section_groups.append(
                    (name, close_sections_from_run(run_result, verify_name=name))
                )
                if expert_card_enabled(cfg, workflow="close"):
                    expert_snapshots.append((name, code, run_result["snapshot"]))
            symbol_results.append(
                {
                    "code": code,
                    "name": name,
                    "snapshot_path": str(path),
                    "result": run_result,
                    "feishu": run_result.get("feishu"),
                }
            )
        except Exception as exc:
            errors.append(f"{code}: {exc}")

    if errors and not symbol_results:
        raise RuntimeError(errors[0])

    feishu_result = None
    if push and merge_push and section_groups:
        from agent_reach.config import Config

        merged = merge_sections_by_category(
            section_groups,
            report_kind="close",
            expert_snapshots=expert_snapshots or None,
            decision_entries=None,
        )
        from agent_reach.daily_run.close_portfolio_summary import (
            build_close_portfolio_summary,
            render_close_portfolio_markdown,
        )
        from agent_reach.daily_run.snapshot_builder import save_portfolio
        from agent_reach.daily_run.symbols import sync_snapshot_portfolio
        from agent_reach.daily_run.watchlist_manager import (
            adjust_watchlist,
            collect_intraday_sold_codes,
            is_watchlist_adjust_enabled,
        )

        try:
            morning_bl = load_morning_baseline()
        except FileNotFoundError:
            morning_bl = load_morning_baseline(code=targets[0])
        primary_snap = symbol_results[0]["result"]["snapshot"]
        verify_dict = symbol_results[0]["result"].get("verify") or {}

        pf_work = load_portfolio()
        wl_result = None
        if is_watchlist_adjust_enabled(cfg):
            wl_result = adjust_watchlist(
                pf_work,
                primary_snap,
                cfg,
                "close",
                verify=verify_dict,
                sold_codes=collect_intraday_sold_codes(cfg),
            )
            if wl_result.applied:
                pf_work = wl_result.portfolio
                save_portfolio(pf_work)
                sync_snapshot_portfolio(primary_snap, pf_work)

        portfolio_md = render_close_portfolio_markdown(
            build_close_portfolio_summary(
                primary_snap,
                morning_bl,
                trades=shared_state.trades,
                intraday_trades=shared_state.trades,
                watchlist_adjust=wl_result.to_dict() if wl_result else None,
                settings=cfg,
            )
        )
        if portfolio_md.strip():
            merged.append(
                ReportSection(category="daily_portfolio", title="", body=portfolio_md.strip())
            )
            total = len(merged)
            for i, sec in enumerate(merged, start=1):
                sec.title = merged_category_title(
                    report_kind="close",
                    category=sec.category,
                    index=i,
                    total=total,
                    symbol_count=1 if sec.category == "daily_portfolio" else len(targets),
                )
        feishu_result = push_report_sections(
            merged,
            settings=cfg,
            config=config or Config(),
            report_type="verify",
            fallback_title="🧠 收盘复盘 · 全持仓",
            template=cfg.get("report", {}).get("feishu_template_verify", "purple"),
            split=split_push_enabled(cfg, report_kind="close"),
        )

    return {
        "job": "close",
        "symbol_push_mode": symbol_push_mode(cfg),
        "symbols": targets,
        "symbol_results": symbol_results,
        "errors": errors,
        "feishu": feishu_result or (symbol_results[-1]["feishu"] if symbol_results else None),
    }
