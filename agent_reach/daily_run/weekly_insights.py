# -*- coding: utf-8
"""Weekly skill learning suggestions and process improvement recommendations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

Category = Literal["workflow", "schedule", "portfolio", "mss", "skill", "data"]


@dataclass
class InsightItem:
    category: Category
    priority: str  # high | medium | low
    title: str
    detail: str
    action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
        }


@dataclass
class SkillLearningItem:
    title: str
    source: str  # local | exa | experience
    summary: str
    action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "summary": self.summary,
            "action": self.action,
        }


@dataclass
class WeeklyInsights:
    skill_items: list[SkillLearningItem] = field(default_factory=list)
    skill_research: list[dict[str, Any]] = field(default_factory=list)
    improvements: list[InsightItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_items": [s.to_dict() for s in self.skill_items],
            "skill_research": self.skill_research,
            "improvements": [i.to_dict() for i in self.improvements],
        }


def _skill_package_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "skill"


def _guides_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "guides"


def _local_skill_inventory() -> list[dict[str, str]]:
    """List bundled Agent Reach / daily-run skill assets."""
    items: list[dict[str, str]] = []
    skill_dir = _skill_package_dir()
    if skill_dir.is_dir():
        for path in sorted(skill_dir.glob("*.md")):
            items.append({"name": path.stem, "path": str(path.relative_to(skill_dir.parent)), "type": "skill"})
        ref_dir = skill_dir / "references"
        if ref_dir.is_dir():
            for path in sorted(ref_dir.glob("*.md")):
                items.append(
                    {"name": path.stem, "path": str(path.relative_to(skill_dir.parent)), "type": "reference"}
                )
    guides = _guides_dir()
    if guides.is_dir():
        for path in sorted(guides.glob("setup-*.md")):
            items.append({"name": path.stem, "path": str(path.relative_to(guides.parent)), "type": "guide"})
    return items


def _load_rules_summary() -> list[str]:
    from agent_reach.daily_run.experience import load_experience_rules

    try:
        from agent_reach.daily_run.settings import load_settings

        return load_experience_rules(50, settings=load_settings())
    except Exception:
        return []


def _build_skill_learning_queries(
    hot_sectors: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = [
        {
            "type": "skill",
            "query": "AI agent stock trading skill MCP OpenClaw quant analysis 2026",
            "label": "Agent 量化技能生态",
        },
        {
            "type": "skill",
            "query": "A-share daily review automation agent skill Exa research workflow 2026",
            "label": "A股复盘自动化技能",
        },
    ]
    if hot_sectors:
        sector = hot_sectors[0].get("sector") or hot_sectors[0].get("name") or "semiconductor"
        queries.append(
            {
                "type": "skill",
                "query": f"China A-share {sector} sector analysis agent tool skill 2026",
                "label": f"{sector} 板块分析技能",
            }
        )
    elif holdings:
        name = holdings[0].get("name") or holdings[0].get("code")
        queries.append(
            {
                "type": "skill",
                "query": f"{name} stock fundamental analysis AI agent skill 2026",
                "label": f"{name} 基本面分析技能",
            }
        )
    return queries[:3]


def run_skill_research(
    queries: list[dict[str, str]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from agent_reach.daily_run.exa_client import ExaError, is_exa_available, summarize_hits, web_search_exa

    cfg = settings.get("weekly_report") or {}
    if cfg.get("exa_skill_research", True) is False:
        return []
    if not is_exa_available():
        return []

    plugin_cfg = settings.get("plugins") or {}
    timeout = int(plugin_cfg.get("exa_timeout", 45))
    max_q = int(cfg.get("max_skill_queries", 2))
    queries = queries[:max_q]
    if not queries:
        return []

    def _run_one(q: dict[str, str]) -> dict[str, Any]:
        try:
            from agent_reach.daily_run.exa_cache import cached_web_search_exa

            hits, _cached = cached_web_search_exa(
                q["query"], num_results=3, timeout=timeout, settings=settings
            )
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


def generate_skill_learning(
    *,
    settings: dict[str, Any],
    hot_sectors: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    experience_snippets: list[str],
    manifests: list[dict[str, Any]],
) -> tuple[list[SkillLearningItem], list[dict[str, Any]]]:
    """Suggest stock-market-related skills to learn or adopt this week."""
    cfg = settings.get("weekly_report") or {}
    if cfg.get("skill_learning", True) is False:
        return [], []

    items: list[SkillLearningItem] = []
    inventory = _local_skill_inventory()

    items.append(
        SkillLearningItem(
            title="daily_run_skill 主技能复盘",
            source="local",
            summary="每周通读 `agent_reach/skill/daily_run_skill.md`，将本周 Exa 调研结论与 MSS 权重调参写入技能「经验沉淀」章节。",
            action="agent-reach skill --install && 编辑 ~/.openclaw/skills/agent-reach/SKILL.md 或仓库内 daily_run_skill.md",
        )
    )

    guides = [g for g in inventory if g["type"] == "guide"]
    if guides:
        names = "、".join(g["name"].replace("setup-", "") for g in guides[:4])
        items.append(
            SkillLearningItem(
                title="平台接入指南",
                source="local",
                summary=f"已内置 {len(guides)} 份 setup 指南（{names} 等），用于扩展数据源与调研能力。",
                action="阅读 agent_reach/guides/setup-*.md，按需配置 Exa / 雪球 / Twitter",
            )
        )

    refs = [r for r in inventory if r["type"] == "reference"]
    if refs:
        items.append(
            SkillLearningItem(
                title="Agent Reach 参考技能",
                source="local",
                summary=f"references/ 含 {len(refs)} 类扩展能力（web/search/social 等），可组合进早盘舆情抓取。",
                action="浏览 agent_reach/skill/references/，在 macro_collector 或 close_research 中引用",
            )
        )

    rules = _load_rules_summary()
    if rules:
        top = "；".join(rules[-3:])
        items.append(
            SkillLearningItem(
                title="经验规则库更新",
                source="experience",
                summary=f"最近沉淀规则：{top}",
                action="将验证有效的规则写回 daily_run_skill.md「量化经验库」章节",
            )
        )

    close_jobs = sum(1 for m in manifests if m.get("job") == "close")
    if close_jobs < 3:
        items.append(
            SkillLearningItem(
                title="backtest / optimize 技能",
                source="local",
                summary="本周收盘复盘次数偏少，建议学习离线回测与 MSS 参数优化命令，补全策略验证闭环。",
                action="agent-reach daily-run backtest --help && daily-run optimize",
            )
        )

    if experience_snippets:
        miss = sum(1 for s in experience_snippets if "—" in s or "偏离" in s)
        if miss >= 2:
            items.append(
                SkillLearningItem(
                    title="MSS 预测校准技能",
                    source="experience",
                    summary=f"本周 {miss} 次 MSS 预测未命中，建议学习 mss_forecast 与 curve_analysis 调参。",
                    action="阅读 daily_run_skill 中「日内 MSS 范围预测」章节，运行 daily-run optimize",
                )
            )

    queries = _build_skill_learning_queries(hot_sectors, holdings)
    research: list[dict[str, Any]] = []
    if cfg.get("exa_skill_research", True) is not False:
        research = run_skill_research(queries, settings)

    for r in research:
        if not r.get("success"):
            continue
        label = r.get("label") or "外部技能调研"
        summary = (r.get("summary") or "")[:200]
        top_hit = (r.get("hits") or [{}])[0]
        url = top_hit.get("url") or ""
        action = f"阅读并评估是否接入 workflow：{url}" if url else "评估是否写入 watchlist.candidates 或 close_research 查询模板"
        items.append(
            SkillLearningItem(
                title=label,
                source="exa",
                summary=summary or "Exa 返回相关 Agent/量化技能资源",
                action=action,
            )
        )

    max_items = int(cfg.get("max_skill_items", 8))
    return items[:max_items], research


def generate_weekly_improvements(
    *,
    settings: dict[str, Any],
    week_start: date,
    week_end: date,
    manifests: list[dict[str, Any]],
    weekly_pnl: Optional[float],
    weekly_pnl_pct: Optional[float],
    holdings: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    mss_summary: list[dict[str, Any]],
    experience_snippets: list[str],
    hot_sectors: list[dict[str, Any]],
) -> list[InsightItem]:
    """Actionable process improvement suggestions based on the full trading week."""
    from agent_reach.daily_run.harness_display import effective_policy_settings

    settings = effective_policy_settings(settings)
    cfg = settings.get("weekly_report") or {}
    if cfg.get("process_improvements", True) is False:
        return []

    items: list[InsightItem] = []
    thresholds = settings.get("thresholds", {})
    portfolio_cfg = settings.get("portfolio") or {}
    schedule_cfg = settings.get("schedule") or {}

    trading_days = {(week_start + timedelta(days=i)).isoformat() for i in range(5)}
    days_with_morning = {m.get("_run_date") for m in manifests if m.get("job") == "morning"}
    days_with_close = {m.get("_run_date") for m in manifests if m.get("job") == "close"}
    days_with_intraday = {m.get("_run_date") for m in manifests if m.get("job") == "intraday"}

    missing_morning = sorted(trading_days - days_with_morning)
    missing_close = sorted(trading_days - days_with_close)
    if missing_morning:
        items.append(
            InsightItem(
                "schedule",
                "high",
                f"缺失 {len(missing_morning)} 天早盘任务",
                f"日期：{', '.join(missing_morning)}；无 morning manifest 会导致收盘 verify 缺基线",
                action="检查 GHA cron 0 8 * * 1-5 与 Fork 是否 Enable scheduled workflows",
            )
        )
    if missing_close:
        items.append(
            InsightItem(
                "schedule",
                "high",
                f"缺失 {len(missing_close)} 天收盘复盘",
                f"日期：{', '.join(missing_close)}；经验沉淀与观察池 adjust 会中断",
                action="检查 GHA cron 30 15 * * 1-5；手动补跑 daily-run schedule run close",
            )
        )

    intraday_by_day: dict[str, int] = {}
    for m in manifests:
        if m.get("job") != "intraday":
            continue
        day = str(m.get("_run_date") or "")
        intraday_by_day[day] = intraday_by_day.get(day, 0) + 1

    low_scan_days = [d for d, n in intraday_by_day.items() if n < 5]
    if low_scan_days:
        items.append(
            InsightItem(
                "schedule",
                "medium",
                f"{len(low_scan_days)} 天盘中扫描偏少",
                f"日期 {', '.join(low_scan_days[:3])} 等 intraday 次数 <5，Lookback MSS 可能失真",
                action="确认 GHA cache restore/save 正常；参考 PR #28 修复 intraday_state 累积",
            )
        )

    if not days_with_intraday and not intraday_by_day:
        items.append(
            InsightItem(
                "workflow",
                "high",
                "本周无盘中 intraday manifest",
                "S4–S15 扫描未落盘，T_n 调仓与 MSS 曲线无法复盘",
                action="排查 09:30–15:00 cron 与 resolve-job.sh 窗口",
            )
        )

    if weekly_pnl is not None and weekly_pnl < 0 and weekly_pnl_pct is not None and weekly_pnl_pct <= -2:
        items.append(
            InsightItem(
                "portfolio",
                "high",
                f"本周组合回撤 {weekly_pnl_pct:.1f}%",
                f"净值变动 ¥{weekly_pnl:,.0f}；需复盘 MSS 进攻阈值与持仓集中度",
                action="运行 daily-run optimize；评估 macro_veto 上调或 max_total_symbols 下调",
            )
        )
    elif weekly_pnl is not None and weekly_pnl > 0 and weekly_pnl_pct is not None and weekly_pnl_pct >= 3:
        items.append(
            InsightItem(
                "portfolio",
                "medium",
                f"本周组合盈利 {weekly_pnl_pct:.1f}%",
                "策略有效，建议固化本周有效规则到 daily_run_skill 与 experience",
                action="将 rules_summary.json 中命中规则写入技能文件",
            )
        )

    losers = [h for h in holdings if (h.get("unrealized_pnl") or 0) < -5000]
    if losers:
        names = "、".join(f"{h.get('name')}({h.get('unrealized_pct', 0):+.1f}%)" for h in losers[:3])
        items.append(
            InsightItem(
                "portfolio",
                "medium",
                "持仓浮亏标的需关注",
                names,
                action="收盘 verify 若 MSS<macro_veto 则优先纳入明日卖出候选",
            )
        )

    if not trades and len(mss_summary) >= 5:
        mss_vals = [float(x["mss_final"]) for x in mss_summary if x.get("mss_final") is not None]
        if mss_vals and max(mss_vals) - min(mss_vals) >= 10:
            from agent_reach.daily_run.harness_policy import runtime_int_default

            min_scans = runtime_int_default(settings, "schedule", "trade_min_scans")
            items.append(
                InsightItem(
                    "workflow",
                    "medium",
                    "MSS 波动大但本周无成交",
                    f"振幅 {max(mss_vals) - min(mss_vals):.0f} 分，trade_min_scans={min_scans} 可能过严",
                    action="评估降低 trade_every_n_scans 或在波动日手动 daily-run intraday --trade",
                )
            )

    if len(watchlist) >= 8:
        items.append(
            InsightItem(
                "workflow",
                "low",
                f"观察池 {len(watchlist)} 只偏多",
                "过多标的稀释 Exa 调研与早盘扫描质量",
                action="weekly 后手动精简 watchlist.candidates，保留 3–5 只核心",
            )
        )

    miss_exp = sum(1 for s in experience_snippets if "—" in s)
    if miss_exp >= 2:
        items.append(
            InsightItem(
                "mss",
                "high",
                f"本周 {miss_exp} 次 MSS 预测未命中",
                "早盘 mss_range 与实盘偏离，影响 T_n 与仓位决策",
                action="增大 mss_forecast.base_spread 或运行 daily-run optimize",
            )
        )

    if hot_sectors and not any(m.get("job") == "close" for m in manifests):
        items.append(
            InsightItem(
                "data",
                "medium",
                "热门板块有数据但缺少收盘复盘",
                "无法将板块热度与 Exa 深度调研联动",
                action="补跑 close job，启用 plugins.exa_research_on_close",
            )
        )

    from agent_reach.daily_run.harness_policy import min_cash_ratio_default

    min_cash = min_cash_ratio_default(settings)
    weekly_cfg = settings.get("weekly_report") or {}
    if weekly_cfg.get("skill_writeback", True) is False:
        items.append(
            InsightItem(
                "workflow",
                "low",
                "周报 → 技能闭环",
                "skill_writeback 已关闭，周六周报不会写入技能文件",
                action="在 weekly_report 中设置 skill_writeback: true",
            )
        )

    max_items = int(cfg.get("max_improvement_items", 12))
    return items[:max_items]


def render_skill_learning_markdown(items: list[SkillLearningItem], research: list[dict[str, Any]]) -> str:
    if not items and not research:
        return ""
    lines = ["## 🎓 股市技能学习", ""]
    source_label = {"local": "本地", "exa": "Exa 调研", "experience": "经验库"}
    for item in items:
        src = source_label.get(item.source, item.source)
        lines.append(f"- **[{src}] {item.title}**")
        lines.append(f"  {item.summary}")
        if item.action:
            lines.append(f"  → {item.action}")
    if research and not any(i.source == "exa" for i in items):
        lines.append("")
        lines.append("### Exa 技能调研")
        for r in research:
            status = "✅" if r.get("success") else "⚠️"
            lines.append(f"**{status} {r.get('label', '调研')}**")
            if r.get("summary"):
                lines.append(r["summary"])
    return "\n".join(lines).strip()


def render_improvements_markdown(items: list[InsightItem]) -> str:
    if not items:
        return (
            "**🔧 流程改进意见**\n\n"
            "本周 daily-run 运行正常，暂无专项流程调整建议。"
        )
    labels = {
        "workflow": "daily-run 工作流",
        "schedule": "定时与 GHA",
        "portfolio": "持仓与调仓",
        "mss": "MSS 模型",
        "skill": "技能文件",
        "data": "数据与调研",
    }
    lines = ["## 🔧 流程改进意见", ""]
    grouped: dict[str, list[InsightItem]] = {k: [] for k in labels}
    for item in items:
        grouped[item.category].append(item)

    for cat, title in labels.items():
        cat_items = grouped[cat]
        if not cat_items:
            continue
        lines.append(f"### {title}")
        for it in cat_items:
            badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(it.priority, "•")
            lines.append(f"- {badge} **{it.title}** — {it.detail}")
            if it.action:
                lines.append(f"  → {it.action}")
        lines.append("")
    return "\n".join(lines).strip()
