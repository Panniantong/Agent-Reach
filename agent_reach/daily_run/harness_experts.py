# -*- coding: utf-8
"""Expert plugin outputs → harness consensus checks (Team-First closed loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExpertConsensusReview:
    workflow: str
    expert_count: int
    consensus_score: float
    consensus_label: str
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
    return ExpertConsensusReview(
        workflow=workflow,
        expert_count=expert_count,
        consensus_score=consensus,
        consensus_label=label,
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

    from agent_reach.daily_run.harness_policy import threshold_default

    thresholds = (settings or {}).get("thresholds") or {}
    macro_veto = float(thresholds.get("macro_veto", threshold_default(settings, "macro_veto")))
    aggressive = float(thresholds.get("aggressive_entry", threshold_default(settings, "aggressive_entry")))

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
