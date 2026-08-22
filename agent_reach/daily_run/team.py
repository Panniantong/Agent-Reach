# -*- coding: utf-8
"""Team-First 8-expert parallel runner and supervisor review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.plugins.base import PluginResult
from agent_reach.daily_run.plugins.loader import LITE_EXPERT_NAMES, MSS_EXPERT_NAMES, TEAM_EXPERT_NAMES, run_experts

EXPERT_LABELS: dict[str, str] = {
    "fundamental": "基本面大师",
    "technical": "技术分析派",
    "quant": "量化模型师",
    "risk": "风险控制官",
    "macro": "宏观策略师",
    "industry": "行业研究家",
    "sentiment": "消息面猎手",
    "identifier": "专家鉴别Agent",
}


def experts_enabled(settings: dict[str, Any], *, workflow: str = "morning") -> bool:
    """Whether to run full 8-expert plugins and show the expert card (requires team.enabled)."""
    team = settings.get("team") or {}
    if team.get("enabled", False) is not True:
        return False
    wf_keys = {
        "morning": "morning_experts",
        "close": "close_experts",
        "intraday": "intraday_experts",
    }
    legacy_keys = {
        "morning": "morning_team_first",
        "close": "close_team_first",
    }
    key = wf_keys.get(workflow)
    if key and key in team:
        return bool(team[key])
    legacy = legacy_keys.get(workflow)
    if legacy and legacy in team:
        return bool(team[legacy])
    if workflow == "intraday" and "intraday_experts" in team:
        return bool(team["intraday_experts"])
    return True


def mss_experts_enabled(settings: dict[str, Any], *, workflow: str = "morning") -> bool:
    """Run technical/quant/risk MSS scoring without requiring team.enabled."""
    if experts_enabled(settings, workflow=workflow):
        return True
    team = settings.get("team") or {}
    if team.get("mss_experts", False) is not True:
        return False
    wf_keys = {
        "morning": "morning_mss_experts",
        "close": "close_mss_experts",
        "intraday": "intraday_mss_experts",
    }
    key = wf_keys.get(workflow)
    if key and key in team:
        return bool(team[key])
    return True


def expert_card_enabled(settings: dict[str, Any], *, workflow: str = "morning") -> bool:
    """Whether merged Feishu push includes the 8-expert consensus card."""
    return experts_enabled(settings, workflow=workflow)


def team_first_enabled(settings: dict[str, Any], *, workflow: str = "morning") -> bool:
    """Whether to use Team-First supervisor path (requires experts_enabled)."""
    if not experts_enabled(settings, workflow=workflow):
        return False
    team = settings.get("team") or {}
    wf_keys = {
        "morning": "morning_team_first",
        "close": "close_team_first",
        "intraday": "intraday_team_first",
    }
    key = wf_keys.get(workflow)
    if key and key in team:
        return bool(team[key])
    return bool(team.get("supervisor", True))


def enrich_with_team_or_experts(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    workflow: str = "morning",
    plugin_names: Optional[list[str]] = None,
    team_first: Optional[bool] = None,
    skip_experts: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Run Team-First, full experts, or MSS experts for a workflow."""
    if skip_experts:
        return dict(snapshot), []

    steps: list[str] = []
    if team_first is None:
        use_team = team_first_enabled(settings, workflow=workflow)
    else:
        use_team = bool(team_first) and experts_enabled(settings, workflow=workflow)

    if use_team:
        enriched = run_team_first(snapshot, settings, names=plugin_names)
        steps.append("team_first")
        return enriched, steps
    if experts_enabled(settings, workflow=workflow):
        enriched = run_experts(snapshot, settings, names=plugin_names)
        steps.append("experts")
        return enriched, steps
    if mss_experts_enabled(settings, workflow=workflow):
        enriched = run_experts(snapshot, settings, names=MSS_EXPERT_NAMES)
        steps.append("mss_experts")
        return enriched, steps
    return dict(snapshot), steps


@dataclass
class TeamReview:
    mode: str
    expert_count: int
    consensus_score: float
    consensus_label: str
    conflicts: list[str] = field(default_factory=list)
    counter_thesis: str = ""
    counter_factors: list[str] = field(default_factory=list)
    counter_downgrade: bool = False
    blocked: bool = False
    block_reason: str = ""
    expert_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "expert_count": self.expert_count,
            "consensus_score": self.consensus_score,
            "consensus_label": self.consensus_label,
            "conflicts": self.conflicts,
            "counter_thesis": self.counter_thesis,
            "counter_factors": self.counter_factors,
            "counter_downgrade": self.counter_downgrade,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "expert_results": self.expert_results,
        }


def is_single_symbol_snapshot(snapshot: dict[str, Any]) -> bool:
    """True when snapshot targets one A-share (lite Team-First candidate)."""
    if not str(snapshot.get("code") or "").strip():
        return False
    report_type = str(snapshot.get("report_type") or "").lower()
    if report_type in {"weekly", "forecast", "portfolio", "verify"}:
        return False
    holdings = (snapshot.get("portfolio") or {}).get("holdings") or []
    if isinstance(holdings, list) and len(holdings) > 1:
        return False
    symbols = snapshot.get("symbols") or []
    if isinstance(symbols, list) and len(symbols) > 1:
        return False
    return True


def resolve_team_experts(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    names: Optional[list[str]] = None,
) -> tuple[str, list[str]]:
    """Pick full vs lite expert subset from team.mode (supports auto)."""
    if names:
        mode = str((settings.get("team") or {}).get("mode") or "full_parallel")
        return mode, list(names)

    team_cfg = settings.get("team") or {}
    mode = str(team_cfg.get("mode") or "full_parallel")
    if mode == "auto":
        lite_on_single = team_cfg.get("lite_on_single_symbol", True) is not False
        mode = "lite_parallel" if lite_on_single and is_single_symbol_snapshot(snapshot) else "full_parallel"

    if mode == "lite_parallel":
        allowed = team_cfg.get("experts") or TEAM_EXPERT_NAMES
        selected = [n for n in LITE_EXPERT_NAMES if n in allowed]
        return mode, selected or list(LITE_EXPERT_NAMES)

    return "full_parallel", list(team_cfg.get("experts") or TEAM_EXPERT_NAMES)


def run_team_first(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    mode: str | None = None,
    names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Team-First pipeline: experts in parallel → supervisor review → enrich snapshot.
    """
    team_cfg = settings.get("team", {})
    use_mode, expert_names = resolve_team_experts(snapshot, settings, names=names)
    if mode:
        use_mode = mode
    use_parallel = team_cfg.get("parallel", True)

    enriched = run_experts(
        snapshot,
        settings,
        names=expert_names,
        parallel=use_parallel,
    )

    review = supervisor_review(enriched, settings, mode=use_mode)
    enriched["team_mode"] = use_mode
    enriched["team_expert_names"] = expert_names
    enriched["team_review"] = review.to_dict()
    enriched["team_consensus_score"] = review.consensus_score
    enriched["team_consensus_label"] = review.consensus_label

    if review.blocked:
        enriched["identifier_blocked"] = True
        enriched.setdefault("downgrade_reasons", []).append(review.block_reason)

    return enriched


def supervisor_review(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
    *,
    mode: str = "full_parallel",
) -> TeamReview:
    """Aggregate parallel expert outputs; detect conflicts and identifier blocks."""
    results = snapshot.get("expert_results") or []
    scores = snapshot.get("expert_scores") or {}

    if not results:
        return TeamReview(
            mode=mode,
            expert_count=0,
            consensus_score=float(snapshot.get("mss_final") or 50),
            consensus_label="观察",
        )

    values = [float(r.get("score", 50)) for r in results]
    consensus = round(sum(values) / len(values), 1)

    from agent_reach.daily_run.harness_policy import aggressive_entry_default, macro_veto_default
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    macro_veto = macro_veto_default(eff)
    aggressive = aggressive_entry_default(eff)

    if consensus >= aggressive:
        label = "可做"
    elif consensus >= macro_veto:
        label = "观察"
    else:
        label = "回避"

    conflicts: list[str] = []
    by_name = {r["name"]: float(r["score"]) for r in results}

    tech = by_name.get("technical")
    risk = by_name.get("risk")
    if tech is not None and risk is not None and tech >= aggressive and risk < macro_veto + 5:
        conflicts.append(f"技术面 {tech:.0f} 偏多 vs 风控 {risk:.0f} 偏紧，需 supervisor 仲裁")

    macro = by_name.get("macro")
    sentiment = by_name.get("sentiment")
    if macro is not None and sentiment is not None and abs(macro - sentiment) > 20:
        conflicts.append(f"宏观 {macro:.0f} 与舆情 {sentiment:.0f} 分歧较大")

    identifier = next((r for r in results if r.get("name") == "identifier"), None)
    blocked = False
    block_reason = ""
    if identifier and not identifier.get("success", True):
        blocked = True
        block_reason = f"专家鉴别未通过：{identifier.get('summary', '')}"
        label = "观察"

    counter_thesis, counter_factors, counter_downgrade = _build_counter_thesis(
        snapshot,
        label=label,
        conflicts=conflicts,
        by_name=by_name,
        macro_veto=macro_veto,
        settings=settings,
    )

    return TeamReview(
        mode=mode,
        expert_count=len(results),
        consensus_score=consensus,
        consensus_label=label,
        conflicts=conflicts,
        counter_thesis=counter_thesis,
        counter_factors=counter_factors,
        counter_downgrade=counter_downgrade,
        blocked=blocked,
        block_reason=block_reason,
        expert_results=results,
    )


def _build_counter_thesis(
    snapshot: dict[str, Any],
    *,
    label: str,
    conflicts: list[str],
    by_name: dict[str, float],
    macro_veto: float,
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, list[str], bool]:
    """Devil's advocate factors when supervisor consensus is bullish."""
    if label != "可做":
        return "", [], False

    factors: list[str] = []
    if conflicts:
        factors.extend(conflicts[:2])

    risk = by_name.get("risk")
    if risk is not None and risk < macro_veto + 8:
        factors.append(f"风控 {risk:.0f} 分仍偏紧，需假设回撤可控")

    macro = by_name.get("macro")
    sentiment = by_name.get("sentiment")
    if macro is not None and sentiment is not None and abs(macro - sentiment) > 20:
        factors.append(f"宏观 {macro:.0f} vs 舆情 {sentiment:.0f} 分歧未解")

    breakdown = snapshot.get("mss_breakdown") or {}
    global_score = breakdown.get("global")
    if global_score is not None and float(global_score) < macro_veto + 5:
        factors.append(f"宏观分 {float(global_score):.0f} 未确认趋势反转")

    technical = by_name.get("technical")
    quant = by_name.get("quant")
    if technical is not None and quant is not None and technical >= macro_veto + 10 and quant < macro_veto:
        factors.append(f"技术 {technical:.0f} 偏热但量化 {quant:.0f} 未确认")

    for row in snapshot.get("expert_results") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if name not in {"risk", "macro", "identifier"}:
            continue
        if row.get("success", True) is False:
            factors.append(f"{EXPERT_LABELS.get(name, name)}未通过：{str(row.get('summary') or '')[:36]}")

    try:
        from agent_reach.daily_run.redfox_collector import _result_from_dict, _sentiment_score, _sentiment_titles

        raw = snapshot.get("redfox") or (snapshot.get("macro_signals") or {}).get("redfox")
        if isinstance(raw, dict):
            rf = _result_from_dict(raw)
            score = _sentiment_score(_sentiment_titles(rf))
            if score <= -1:
                factors.append("RedFox 跨平台舆情偏冷，需验证增量叙事")
    except Exception:
        pass

    if not factors:
        factors.append("若北向转流出或热点退潮，当前共识可能失效")

    unique_factors = list(dict.fromkeys(factors))[:4]

    team_cfg = (settings or {}).get("team") or {}
    llm_meta: dict[str, Any] = {}
    llm_downgrade = False
    try:
        from agent_reach.daily_run.supervisor_counter_llm import enrich_counter_thesis_llm

        unique_factors, markdown, llm_downgrade, llm_meta = enrich_counter_thesis_llm(
            snapshot,
            base_factors=unique_factors,
            conflicts=conflicts,
            by_name=by_name,
            label=label,
            settings=settings,
        )
    except Exception:
        markdown = "反面检验：" + "；".join(unique_factors[:3])

    downgrade_enabled = team_cfg.get("counter_thesis_downgrade", True) is not False
    should_downgrade = downgrade_enabled and (
        llm_downgrade
        or bool(conflicts)
        or (risk is not None and risk < macro_veto + 5)
        or len(unique_factors) >= 2
    )
    if llm_meta.get("planner") == "llm":
        snapshot.setdefault("team_counter_llm", llm_meta)
    return markdown, unique_factors, should_downgrade


def render_team_markdown(snapshot: dict[str, Any]) -> str:
    """Render Team-First expert panel for Feishu cards."""
    from agent_reach.daily_run.valuation_metrics import format_valuation_line

    review = snapshot.get("team_review") or {}
    results = review.get("expert_results") or snapshot.get("expert_results") or []
    mode = review.get("mode") or snapshot.get("team_mode") or "full_parallel"

    lines = [
        f"**👥 Team-First · {len(results)} 专家并行（{mode}）**",
        "",
        f"**Supervisor 共识：** {review.get('consensus_score', snapshot.get('team_consensus_score', '—'))} 分 · "
        f"**{review.get('consensus_label', snapshot.get('team_consensus_label', '观察'))}**",
    ]
    valuation = format_valuation_line(snapshot)
    if valuation:
        lines.extend(["", valuation])
    lines.extend(["", "| 专家 | 评分 | 摘要 |", "|------|------|------|"])

    for r in results:
        name = r.get("name", "")
        label = EXPERT_LABELS.get(name, name)
        score = r.get("score", "—")
        summary = str(r.get("summary", ""))[:60]
        flag = " ⚠️" if not r.get("success", True) else ""
        lines.append(f"| {label} | {score} | {summary}{flag} |")

    conflicts = review.get("conflicts") or []
    if conflicts:
        lines.extend(["", "**Supervisor 冲突仲裁：**"])
        for c in conflicts:
            lines.append(f"- {c}")

    if review.get("blocked"):
        lines.extend(["", f"⚠️ **鉴别阻断：** {review.get('block_reason', '')}"])

    counter = review.get("counter_thesis") or ""
    if counter:
        lines.extend(["", f"**{counter}**"])
    factors = review.get("counter_factors") or []
    if factors and len(factors) > 1:
        lines.extend(["", "**反面检验因子：**"])
        for factor in factors[:4]:
            lines.append(f"- {factor}")
    if review.get("counter_downgrade"):
        lines.extend(["", "⚠️ **Supervisor：** 反面检验触发，共识已从「可做」倾向观察"])

    return "\n".join(lines)


def render_merged_experts_markdown(
    entries: list[tuple[str, str, dict[str, Any]]],
) -> str:
    """Render one unified expert-consensus card for multiple symbols."""
    if not entries:
        return ""
    if len(entries) == 1:
        name, code, snap = entries[0]
        return render_team_markdown({**snap, "name": name, "code": code})

    lines = [
        f"**👥 专家共识 · {len(entries)} 只标的 · Team-First 8 专家并行**",
        "",
        "**组合共识概览**",
        "",
        "| 标的 | 代码 | 共识分 | 标签 |",
        "|------|------|--------|------|",
    ]
    for name, code, snap in entries:
        review = snap.get("team_review") or {}
        score = review.get("consensus_score", snap.get("team_consensus_score", "—"))
        label = review.get("consensus_label", snap.get("team_consensus_label", "观察"))
        lines.append(f"| {name} | {code} | {score} | {label} |")

    from agent_reach.daily_run.valuation_metrics import format_valuation_line

    val_lines = []
    for sym_name, code, snap in entries:
        line = format_valuation_line({**snap, "name": sym_name, "code": code})
        if line:
            val_lines.append(line.replace(f"**估值快照 · {sym_name}：** ", f"- **{sym_name}**："))
    if val_lines:
        lines.extend(["", "**估值快照**", ""] + val_lines)

    expert_order: list[str] = []
    seen_experts: set[str] = set()
    for _, _, snap in entries:
        for r in snap.get("expert_results") or []:
            key = str(r.get("name", ""))
            if key and key not in seen_experts:
                seen_experts.add(key)
                expert_order.append(key)
    for fallback in TEAM_EXPERT_NAMES:
        if fallback not in seen_experts:
            expert_order.append(fallback)

    lines.extend(["", "**各专家评分矩阵**", ""])
    header = "| 专家 | " + " | ".join(n for n, _, _ in entries) + " |"
    sep = "|------|" + "------|" * len(entries)
    lines.extend([header, sep])

    for en in expert_order:
        if not any(
            en in {str(r.get("name", "")) for r in (snap.get("expert_results") or [])}
            for _, _, snap in entries
        ):
            continue
        label = EXPERT_LABELS.get(en, en)
        cells: list[str] = []
        for _, _, snap in entries:
            by_name = {str(r.get("name", "")): r for r in (snap.get("expert_results") or [])}
            row = by_name.get(en, {})
            score = row.get("score", "—")
            flag = "⚠" if row and not row.get("success", True) else ""
            cells.append(f"{score}{flag}" if flag else str(score))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    lines.extend(["", "**专家摘要**", ""])
    for en in expert_order:
        if not any(
            en in {str(r.get("name", "")) for r in (snap.get("expert_results") or [])}
            for _, _, snap in entries
        ):
            continue
        label = EXPERT_LABELS.get(en, en)
        lines.append(f"**{label}**")
        for sym_name, _, snap in entries:
            by_name = {str(r.get("name", "")): r for r in (snap.get("expert_results") or [])}
            row = by_name.get(en)
            if not row:
                continue
            summary = str(row.get("summary", ""))[:80]
            lines.append(f"- {sym_name}：{summary}")
        lines.append("")

    conflicts: list[str] = []
    for sym_name, _, snap in entries:
        review = snap.get("team_review") or {}
        for c in review.get("conflicts") or []:
            conflicts.append(f"{sym_name} — {c}")
        if review.get("blocked"):
            conflicts.append(f"{sym_name} — 鉴别阻断：{review.get('block_reason', '')}")
    if conflicts:
        lines.extend(["**Supervisor 冲突仲裁**", ""])
        lines.extend(f"- {c}" for c in conflicts)

    return "\n".join(lines).strip()
