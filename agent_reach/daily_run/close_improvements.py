# -*- coding: utf-8
"""Close review improvement suggestions for MSS, portfolio, watchlist, and S_n schedule."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

from agent_reach.daily_run.schedule import INTRADAY_SCAN_TIMES

Category = Literal["mss", "portfolio", "watchlist", "schedule"]

BEIJING = ZoneInfo("Asia/Shanghai")


@dataclass
class ImprovementItem:
    category: Category
    priority: str  # high | medium | low
    title: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass
class CloseImprovements:
    items: list[ImprovementItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        by_cat: dict[str, list[dict[str, Any]]] = {
            "mss": [],
            "portfolio": [],
            "watchlist": [],
            "schedule": [],
        }
        for item in self.items:
            by_cat[item.category].append(item.to_dict())
        return {"items": [i.to_dict() for i in self.items], "by_category": by_cat}

    def add(self, category: Category, priority: str, title: str, detail: str) -> None:
        self.items.append(ImprovementItem(category, priority, title, detail))


def expected_scan_slots() -> list[dict[str, str]]:
    """Premarket S1 + morning S2 + S3–S15 intraday expected Beijing times."""
    slots: list[dict[str, str]] = [
        {"scan_id": "S1", "time": "07:00", "label": "盘前"},
        {"scan_id": "S2", "time": "08:00", "label": "早报"},
    ]
    for i, (minute, hour) in enumerate(INTRADAY_SCAN_TIMES, start=3):
        slots.append(
            {
                "scan_id": f"S{i}",
                "time": f"{int(hour):02d}:{minute.zfill(2)}",
                "label": "盘中",
            }
        )
    return slots


def generate_close_improvements(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    verify: dict[str, Any],
    settings: dict[str, Any],
    curve: Optional[dict[str, Any]] = None,
    scans: Optional[list[dict[str, Any]]] = None,
    trades: Optional[list[dict[str, Any]]] = None,
    watchlist_adjust: Optional[dict[str, Any]] = None,
    forecast_review: Optional[dict[str, Any]] = None,
) -> CloseImprovements:
    """Produce actionable improvement notes for next-day tuning."""
    out = CloseImprovements()
    cfg = settings.get("close_improvements") or {}
    if cfg.get("enabled") is False:
        return out

    thresholds = settings.get("thresholds", {})
    portfolio_cfg = settings.get("portfolio") or {}
    watchlist_cfg = settings.get("watchlist") or {}
    schedule_cfg = settings.get("schedule") or {}

    _improve_mss(out, baseline, current, verify, curve, thresholds, settings)
    _improve_portfolio(out, current, verify, trades or [], portfolio_cfg, thresholds)
    _improve_watchlist(out, current, watchlist_adjust, watchlist_cfg, portfolio_cfg)
    _improve_schedule(out, scans or [], trades or [], schedule_cfg, settings)
    _improve_forecast(out, forecast_review, settings)

    # Always include a scan summary when we have data (confirms feature ran).
    from agent_reach.daily_run.intraday import MAX_SCANS

    n = len(scans or [])
    if n > 0 and not any(i.category == "schedule" for i in out.items):
        out.add(
            "schedule",
            "low",
            f"今日扫描 {n}/{MAX_SCANS} 次",
            "覆盖正常" if n >= MAX_SCANS else f"尚有 {MAX_SCANS - n} 个计划时段未记录",
        )

    return out


def render_improvements_markdown(
    result: CloseImprovements,
    *,
    enabled: bool = True,
) -> str:
    if not enabled:
        return ""
    if not result.items:
        return (
            "**🔧 复盘改进意见**\n\n"
            "今日 MSS / 持仓 / 观察池 / S_n 扫描未触发告警，暂无专项调参建议。"
        )

    labels = {
        "mss": "MSS 模型与阈值",
        "portfolio": "持仓与调仓",
        "watchlist": "观察池",
        "schedule": "S_n 扫描次数与时间",
    }
    lines = ["**🔧 复盘改进意见**", ""]
    grouped: dict[str, list[ImprovementItem]] = {k: [] for k in labels}
    for item in result.items:
        grouped[item.category].append(item)

    for cat, title in labels.items():
        items = grouped[cat]
        if not items:
            continue
        lines.append(f"### {title}")
        for it in items:
            badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(it.priority, "•")
            lines.append(f"- {badge} **{it.title}** — {it.detail}")
        lines.append("")

    return "\n".join(lines).strip()


def _improve_mss(
    out: CloseImprovements,
    baseline: dict[str, Any],
    current: dict[str, Any],
    verify: dict[str, Any],
    curve: Optional[dict[str, Any]],
    thresholds: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    if verify.get("mss_within_prediction") is False:
        out.add(
            "mss",
            "high",
            "MSS 预测区间偏离",
            "建议运行 `daily-run optimize` 微调 macro_veto / aggressive_entry，"
            "或增大 mss_forecast.base_spread 以覆盖实际波动",
        )

    mss_delta = verify.get("mss_delta")
    if mss_delta is not None and abs(float(mss_delta)) >= 8:
        direction = "走强" if float(mss_delta) > 0 else "走弱"
        out.add(
            "mss",
            "medium",
            f"全日 MSS {direction} {abs(float(mss_delta)):.0f} 分",
            "检查 mss_weights 中外资/舆情因子权重是否滞后于盘面；"
            "可考虑在 optimizer 中扩大 mss_weight_grid 搜索范围",
        )

    if curve:
        trend = curve.get("trend") or ""
        if trend in ("加速杀跌", "震荡走弱") and verify.get("verdict_current") != "回避":
            out.add(
                "mss",
                "high",
                "盘中 MSS 趋势偏弱但尾盘未给回避",
                f"曲线研判「{trend}」，建议下调 aggressive_entry 或加强 macro 因子 veto",
            )
        if curve.get("prediction_hit") is False and curve.get("deviation"):
            out.add("mss", "medium", "曲线与早盘预测不一致", str(curve["deviation"]))

    breakdown = current.get("mss_breakdown") or {}
    if breakdown.get("technical") is not None and float(breakdown.get("technical", 50)) < 45:
        out.add(
            "mss",
            "medium",
            "技术面因子拖累 MSS",
            "确认 AKShare 历史 K 线可用；缺失 ma20/position_20d 会导致技术分降级为中性",
        )

    for rec in verify.get("recommendations") or []:
        out.add("mss", "low", "验证建议", rec)


def _improve_portfolio(
    out: CloseImprovements,
    current: dict[str, Any],
    verify: dict[str, Any],
    trades: list[dict[str, Any]],
    portfolio_cfg: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    pf = current.get("portfolio") or {}
    holdings = pf.get("holdings") or []
    cash_ratio = pf.get("cash_ratio")
    min_cash = float(thresholds.get("min_cash_ratio", 0.4))
    max_t = int(
        portfolio_cfg["max_total_symbols"]
        if "max_total_symbols" in portfolio_cfg
        else portfolio_cfg.get("max_holdings", 10)
    )
    watchlist = current.get("watchlist") or []
    held_codes = {str(h.get("code", "")).zfill(6)[-6:] for h in holdings}
    wl_only = [
        w for w in watchlist if str(w.get("code", "")).zfill(6)[-6:] not in held_codes
    ]
    unique_n = len(held_codes) + len(wl_only)

    if cash_ratio is not None:
        cr = float(cash_ratio)
        if cr < min_cash - 0.05:
            out.add(
                "portfolio",
                "high",
                f"现金比例 {cr:.0%} 低于底线 {min_cash:.0%}",
                "明日早盘优先减仓弱势持仓或暂停 intraday 买入信号直至现金回升",
            )
        elif cr > 0.85 and verify.get("verdict_current") == "可做":
            out.add(
                "portfolio",
                "medium",
                f"现金比例 {cr:.0%} 过高",
                "MSS 允许进攻但仓位过轻，可在 aggressive_entry 确认后提高 deploy 比例或扩大观察池候选",
            )

    if unique_n >= max_t:
        out.add(
            "portfolio",
            "medium",
            f"持仓+观察池已达合计上限 {max_t} 只（持仓 {len(holdings)} + 观察 {len(wl_only)}）",
            "需先卖出或移出弱势观察标的，才能纳入新票；可在 portfolio.max_total_symbols 调整上限",
        )

    losers = [h for h in holdings if (h.get("change_pct") or 0) <= -5]
    if losers:
        names = "、".join(f"{h.get('name', h.get('code'))}({h.get('change_pct'):+.1f}%)" for h in losers[:3])
        out.add(
            "portfolio",
            "medium",
            "持仓日内弱势",
            f"{names}；若 MSS 持续低于 macro_veto，考虑在复盘观察池回收后明日优先卖出",
        )

    buy_count = sum(1 for t in trades if t.get("action") == "buy")
    sell_count = sum(1 for t in trades if t.get("action") == "sell")
    if not trades:
        out.add(
            "portfolio",
            "low",
            "今日无 T_n 调仓",
            "若 MSS 曲线有明显拐点但未触发 trade_min_scans，可考虑降低 trade_min_scans 或 trade_every_n_scans",
        )
    elif buy_count + sell_count >= 4:
        out.add(
            "portfolio",
            "medium",
            f"今日调仓 {buy_count + sell_count} 次偏频",
            "检查 friction 门槛与 holding_lock_days；过高频可能放大佣金损耗",
        )

    locked = [h for h in holdings if h.get("days_held") is not None and int(h["days_held"]) < 3]
    if locked and any(t.get("action") == "sell" for t in trades):
        out.add(
            "portfolio",
            "low",
            "锁定期内曾出现卖出信号",
            "holding_lock_days 生效中；若需灵活止损可评估缩短锁定期（默认 3 天）",
        )


def _improve_watchlist(
    out: CloseImprovements,
    current: dict[str, Any],
    watchlist_adjust: Optional[dict[str, Any]],
    watchlist_cfg: dict[str, Any],
    portfolio_cfg: dict[str, Any],
) -> None:
    watchlist = current.get("watchlist") or []
    holdings = (current.get("portfolio") or {}).get("holdings") or []
    held = {str(h.get("code", "")).zfill(6)[-6:] for h in holdings}
    max_t = int(
        portfolio_cfg["max_total_symbols"]
        if "max_total_symbols" in portfolio_cfg
        else portfolio_cfg.get("max_holdings", 10)
    )
    wl_capacity = max(0, max_t - len(held))
    wl_only = [w for w in watchlist if str(w.get("code", "")).zfill(6)[-6:] not in held]

    overlap = [w for w in watchlist if str(w.get("code", "")).zfill(6)[-6:] in held]
    if overlap:
        out.add(
            "watchlist",
            "medium",
            "观察池与持仓重复",
            f"{len(overlap)} 只仍同时在观察池；明日早盘 adjust_watchlist 应清理，或检查复盘 adjust 是否执行",
        )

    if len(wl_only) >= wl_capacity and wl_capacity > 0:
        out.add(
            "watchlist",
            "medium",
            f"观察池非持仓标的已达 {len(wl_only)}/{wl_capacity}（合计上限 {max_t}）",
            "新增候选需先移出弱势标的；可在 watchlist.candidates 中控制质量",
        )
    elif len(wl_only) < 2 and len(held) + len(wl_only) < max_t:
        out.add(
            "watchlist",
            "low",
            "观察池标的过少",
            "收盘 Exa 调研后可手动补充 candidates，或在复盘阶段纳入行业龙头",
        )

    weak = [w for w in watchlist if (w.get("change_pct") or 0) <= -5]
    if len(weak) >= 2:
        names = "、".join(str(w.get("name", w.get("code", ""))) for w in weak[:3])
        out.add(
            "watchlist",
            "medium",
            "观察池多标的走弱",
            f"{names}；明日早盘可考虑移出并替换为当日调研热点",
        )

    if watchlist_adjust and not watchlist_adjust.get("applied"):
        out.add(
            "watchlist",
            "low",
            "本次复盘未调整观察池",
            watchlist_adjust.get("message") or "无变更条件触发",
        )


def _improve_schedule(
    out: CloseImprovements,
    scans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    schedule_cfg: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    from agent_reach.daily_run.intraday import MAX_SCANS

    expected = expected_scan_slots()
    n = len(scans)
    if n == 0:
        out.add(
            "schedule",
            "high",
            "今日无 S_n 扫描记录",
            "检查本地 crontab / daily-run schedule install 是否生效；至少应有 S1(07:00 盘前) 与 S2(08:00 早盘)",
        )
        return

    if n < len(expected) // 2:
        out.add(
            "schedule",
            "high",
            f"扫描仅 {n}/{MAX_SCANS} 次，覆盖率偏低",
            f"缺失 scan 会导致 Lookback MSS 不准；建议补跑 intraday 或检查 Actions 失败日志",
        )
    elif n < MAX_SCANS:
        missing = MAX_SCANS - n
        out.add(
            "schedule",
            "medium",
            f"今日完成 S1–S{n}，尚有 {missing} 次空档",
            "可在波动放大日手动补跑 intraday；或确认 09:00–15:00 cron 是否全部触发",
        )

    # Timing drift: compare actual vs expected for completed scans (match by scan_id)
    expected_by_id = {slot["scan_id"]: slot for slot in expected}
    drifts: list[str] = []
    for scan in scans:
        sid = scan.get("scan_id") or "?"
        slot = expected_by_id.get(sid)
        if slot is None:
            continue
        actual = _scan_beijing_time(scan.get("as_of"))
        if actual and actual != slot["time"]:
            drifts.append(f"{sid} 预期 {slot['time']} 实际 {actual}")
    if drifts:
        out.add(
            "schedule",
            "low",
            "部分扫描时间与计划偏差",
            "；".join(drifts[:4]) + ("…" if len(drifts) > 4 else "")
            + "。GHA 调度可能有 1–5 分钟延迟，持续偏差可收紧 resolve 窗口",
        )

    # S2 should come from morning full analysis
    s2 = next((s for s in scans if s.get("scan_id") == "S2"), None)
    if s2 and s2.get("source") != "morning":
        out.add(
            "schedule",
            "medium",
            "S2 未标记为 morning 来源",
            "8:00 全量早盘应写入 S2；检查 run_scheduled(morning) 是否调用 record_morning_scan",
        )

    min_scans = int(schedule_cfg.get("trade_min_scans", 3))
    if n >= min_scans and not trades:
        out.add(
            "schedule",
            "low",
            f"已有 {n} 次扫描但未触发 T_n",
            f"trade_min_scans={min_scans}；若 MSS 趋势明显，可降低 trade_every_n_scans 或启用 trade=true 手动评估",
        )

    # Suggest extra slot if curve volatile (needs curve passed - use scans mss spread)
    mss_vals = [float(s["mss_final"]) for s in scans if s.get("mss_final") is not None]
    if len(mss_vals) >= 3:
        spread = max(mss_vals) - min(mss_vals)
        if spread >= 12 and n < MAX_SCANS:
            out.add(
                "schedule",
                "medium",
                f"盘中 MSS 振幅 {spread:.0f} 分",
                "波动大但扫描次数未满，可考虑在 10:30/14:00 附近增加 manual intraday 或缩短 cron 间隔",
            )


def _improve_forecast(
    out: CloseImprovements,
    forecast_review: Optional[dict[str, Any]],
    settings: dict[str, Any],
) -> None:
    if not forecast_review:
        return
    wf_cfg = settings.get("week_forecast") or {}
    if wf_cfg.get("enabled", True) is False:
        return

    acc = forecast_review.get("accuracy")
    total = int(forecast_review.get("symbol_total") or 0)
    if total and acc is not None and float(acc) < 0.45:
        out.add(
            "mss",
            "high",
            f"下周预测命中率 {float(acc):.0%}（{forecast_review.get('symbol_hits', 0)}/{total}）",
            "已在 calibration.json 上调 vol_scale / bias；"
            "若连续 3 日偏低，可增大 week_forecast.calibration_learning_rate",
        )

    if forecast_review.get("mss_hit") is False:
        out.add(
            "mss",
            "medium",
            "MSS 日预测未命中",
            f"预测区间 {forecast_review.get('mss_predicted')} vs 实际 {forecast_review.get('mss_actual')}；"
            "可增大 mss_forecast.base_spread 或检查 macro 因子滞后",
        )

    notes = forecast_review.get("optimization_notes") or []
    for note in notes[:2]:
        out.add("mss", "low", "预测校准", str(note))


def _scan_beijing_time(as_of: Any) -> Optional[str]:
    if not as_of:
        return None
    try:
        dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(BEIJING)
        return f"{local.hour:02d}:{local.minute:02d}"
    except (TypeError, ValueError):
        return None


def verify_label(current: dict[str, Any]) -> str:
    return str(current.get("verdict") or "")
