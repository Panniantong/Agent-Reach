# -*- coding: utf-8
"""Expert plugin outputs → harness consensus checks (Team-First closed loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

ExpertMode = Literal["full_team", "mss_only", "partial"]


@dataclass
class ExpertConsensusReview:
    workflow: str
    expert_count: int
    consensus_score: float
    consensus_label: str
    expert_mode: ExpertMode = "partial"
    conflicts: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""
    counter_thesis: str = ""
    mss_drift: list[str] = field(default_factory=list)
    low_scorers: list[str] = field(default_factory=list)
    high_scorers: list[str] = field(default_factory=list)
    ready_for_policy: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "expert_count": self.expert_count,
            "consensus_score": self.consensus_score,
            "consensus_label": self.consensus_label,
            "expert_mode": self.expert_mode,
            "conflicts": list(self.conflicts),
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "counter_thesis": self.counter_thesis,
            "mss_drift": list(self.mss_drift),
            "low_scorers": list(self.low_scorers),
            "high_scorers": list(self.high_scorers),
            "ready_for_policy": self.ready_for_policy,
        }


def _expert_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    return dict((settings or {}).get("expert_consensus") or {})


def _score_drift(expert: float, mss: float, *, threshold: float) -> bool:
    return abs(float(expert) - float(mss)) > threshold


def detect_expert_mode(snapshot: dict[str, Any]) -> ExpertMode:
    """Classify full Team-First vs MSS-only expert plugin path."""
    from agent_reach.daily_run.plugins.loader import MSS_EXPERT_NAMES, TEAM_EXPERT_NAMES

    names = {str(r.get("name", "")) for r in (snapshot.get("expert_results") or []) if r.get("name")}
    if not names:
        return "partial"
    if "identifier" in names or names >= set(TEAM_EXPERT_NAMES) - {"identifier"}:
        return "full_team"
    if snapshot.get("team_review") and int((snapshot.get("team_review") or {}).get("expert_count") or 0) >= 7:
        return "full_team"
    if names <= set(MSS_EXPERT_NAMES):
        return "mss_only"
    return "partial"


def build_expert_consensus_review(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    workflow: str = "close",
) -> Optional[ExpertConsensusReview]:
    """Build consensus review from snapshot team/expert fields."""
    results = snapshot.get("expert_results") or []
    team_review = snapshot.get("team_review") or {}
    if not results and not team_review.get("expert_count"):
        return None

    cfg = _expert_cfg(settings)
    drift_threshold = float(cfg.get("mss_drift_threshold") or 12.0)
    low_cut = float(cfg.get("low_score_cutoff") or 42.0)
    high_cut = float(cfg.get("high_score_cutoff") or 62.0)

    if team_review:
        consensus = float(team_review.get("consensus_score") or snapshot.get("team_consensus_score") or 50)
        label = str(team_review.get("consensus_label") or snapshot.get("team_consensus_label") or "观察")
        conflicts = list(team_review.get("conflicts") or [])
        blocked = bool(team_review.get("blocked") or snapshot.get("identifier_blocked"))
        block_reason = str(team_review.get("block_reason") or "")
        counter_thesis = str(team_review.get("counter_thesis") or "")
        expert_count = int(team_review.get("expert_count") or len(results))
        result_rows = team_review.get("expert_results") or results
    else:
        from agent_reach.daily_run.team import supervisor_review

        review = supervisor_review(snapshot, settings or {}, mode=str(snapshot.get("team_mode") or "full_parallel"))
        consensus = review.consensus_score
        label = review.consensus_label
        conflicts = list(review.conflicts)
        blocked = review.blocked
        block_reason = review.block_reason
        counter_thesis = review.counter_thesis
        expert_count = review.expert_count
        result_rows = review.expert_results

    mss_drift: list[str] = []
    scores = snapshot.get("expert_scores") or {}
    breakdown = snapshot.get("mss_breakdown") or {}
    pairs = (
        ("macro", "global"),
        ("macro", "fx"),
        ("sentiment", "sentiment"),
        ("sentiment", "flow"),
        ("technical", "technical"),
        ("quant", "quant"),
        ("risk", "risk"),
    )
    for expert_key, mss_key in pairs:
        expert_val = scores.get(expert_key)
        mss_val = breakdown.get(mss_key)
        if expert_val is None or mss_val is None:
            continue
        if _score_drift(expert_val, mss_val, threshold=drift_threshold):
            mss_drift.append(
                f"{expert_key} expert={float(expert_val):.0f} vs mss.{mss_key}={float(mss_val):.0f}"
            )

    low_scorers = [
        f"{row.get('name')}={float(row.get('score', 0)):.0f}"
        for row in result_rows
        if float(row.get("score", 50)) < low_cut
    ]
    high_scorers = [
        f"{row.get('name')}={float(row.get('score', 0)):.0f}"
        for row in result_rows
        if float(row.get("score", 50)) >= high_cut
    ]

    ready = expert_count > 0 and not blocked
    mode = detect_expert_mode(snapshot)
    return ExpertConsensusReview(
        workflow=workflow,
        expert_count=expert_count,
        consensus_score=consensus,
        consensus_label=label,
        expert_mode=mode,
        conflicts=conflicts,
        blocked=blocked,
        block_reason=block_reason,
        counter_thesis=counter_thesis,
        mss_drift=mss_drift,
        low_scorers=low_scorers,
        high_scorers=high_scorers,
        ready_for_policy=ready,
    )


def run_expert_consensus_checks(
    snapshot: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
    workflow: str = "close",
) -> dict[str, Any]:
    review = build_expert_consensus_review(snapshot, settings=settings, workflow=workflow)
    if review is None:
        return {"passed": True, "skipped": True, "reason": "no expert data", "review": None}

    from agent_reach.daily_run.harness_policy import aggressive_entry_default, macro_veto_default
    from agent_reach.daily_run.settings import effective_settings

    eff = effective_settings(settings)
    macro_veto = macro_veto_default(eff)
    aggressive = aggressive_entry_default(eff)

    blocking: list[str] = []
    if review.blocked:
        blocking.append(review.block_reason or "identifier blocked")
    if review.consensus_score < macro_veto and review.consensus_label == "可做":
        blocking.append("consensus_label bullish but score below macro_veto")
    if review.conflicts and review.consensus_label == "可做" and not review.counter_thesis:
        blocking.append("bullish consensus with unresolved conflicts")

    passed = not blocking and review.expert_count > 0
    return {
        "passed": passed,
        "skipped": False,
        "review": review.to_dict(),
        "macro_veto": macro_veto,
        "aggressive_entry": aggressive,
        "blocking_flags": blocking,
    }


def aggregate_expert_consensus_audit(
    audit_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Roll up session expert_consensus apply_audit rows for weekly harness."""
    from collections import Counter

    stats: dict[str, Any] = {
        "runs": 0,
        "applied": 0,
        "skipped": 0,
        "conflicts": 0,
        "drift": 0,
        "blocked": 0,
        "forge_blocks": 0,
        "mss_only": 0,
        "full_team": 0,
        "workflows": Counter(),
    }
    for row in audit_rows:
        if str(row.get("job") or "") != "expert_consensus":
            continue
        stats["runs"] += 1
        if str(row.get("status") or "") == "applied":
            stats["applied"] += 1
        else:
            stats["skipped"] += 1
        if str(row.get("reason") or "") == "forge_gate_failed":
            stats["forge_blocks"] += 1

        gate = row.get("gate") or {}
        signals = [str(s) for s in (gate.get("verification_signals") or [])]
        if "expert_conflicts" in signals:
            stats["conflicts"] += 1
        if "expert_mss_drift" in signals:
            stats["drift"] += 1
        if "expert_identifier_blocked" in signals:
            stats["blocked"] += 1
        if "expert_mode_mss_only" in signals:
            stats["mss_only"] += 1
        if "expert_mode_full_team" in signals:
            stats["full_team"] += 1
        for sig in signals:
            if sig.startswith("expert_workflow_"):
                stats["workflows"][sig.replace("expert_workflow_", "", 1)] += 1

    stats["workflows"] = dict(stats["workflows"])
    stats["ready_for_review"] = stats["runs"] > 0
    return stats
