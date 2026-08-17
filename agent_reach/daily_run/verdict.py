# -*- coding: utf-8 -*-
"""Verdict labels: 可做 / 观察 / 回避."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VerdictResult:
    verdict: str
    confidence: str
    mss_final: float
    entry_price: Optional[float]
    stop_loss_price: Optional[float]
    invalidation: str
    reasoning: str
    downgrade_reasons: list[str] = field(default_factory=list)
    blocked: bool = False
    label_key: str = "watch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "mss_final": self.mss_final,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "invalidation": self.invalidation,
            "reasoning": self.reasoning,
            "downgrade_reasons": self.downgrade_reasons,
            "blocked": self.blocked,
            "label_key": self.label_key,
        }


def compute_mss(breakdown: dict[str, float], settings: dict[str, Any]) -> float:
    weights = settings.get("mss_weights", {})
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        if key in breakdown:
            total += float(breakdown[key]) * float(weight)
            weight_sum += float(weight)
    if weight_sum <= 0:
        return float(breakdown.get("total", 0))
    return round(total / weight_sum * (weight_sum if weight_sum < 1 else 1), 2)


def compute_verdict(snapshot: dict[str, Any], settings: dict[str, Any]) -> VerdictResult:
    """Compute trading label from MSS, technicals, and audit context."""
    labels = settings.get("verdict_labels", {})
    buy_label = labels.get("buy", "可做")
    watch_label = labels.get("watch", "观察")
    avoid_label = labels.get("avoid", "回避")

    thresholds = settings.get("thresholds", {})
    trading = settings.get("trading", {})

    from agent_reach.daily_run.harness_policy import threshold_default

    macro_veto = float(thresholds.get("macro_veto", threshold_default(settings, "macro_veto")))
    aggressive = float(thresholds.get("aggressive_entry", threshold_default(settings, "aggressive_entry")))
    high_pos = float(thresholds.get("high_position_20d", threshold_default(settings, "high_position_20d")))
    min_vol_ratio = float(thresholds.get("min_volume_ratio", threshold_default(settings, "min_volume_ratio")))
    max_vwap_dev = float(
        thresholds.get("max_vwap_deviation_pct", threshold_default(settings, "max_vwap_deviation_pct"))
    )

    breakdown = snapshot.get("mss_breakdown") or {}
    mss = snapshot.get("mss_final")
    if mss is None:
        mss = compute_mss(breakdown, settings)
    mss = float(mss)

    price = _optional_float(snapshot.get("price"))
    ma20 = _optional_float(snapshot.get("ma20"))
    position_20d = _optional_float(snapshot.get("position_20d"))
    volume_ratio = _optional_float(snapshot.get("volume_ratio"))
    vwap_deviation = _optional_float(snapshot.get("vwap_deviation_pct"))

    downgrade: list[str] = []
    label_key = "watch"
    blocked = False
    confidence = "高"

    technical_complete = all(v is not None for v in (price, ma20, position_20d))

    if mss < macro_veto:
        label_key = "avoid"
        blocked = True
        reasoning = f"MSS {mss:.0f} 低于宏观一票否决线 {macro_veto:.0f}，禁止买入"
    elif not technical_complete:
        label_key = "watch"
        downgrade.append("缺少完整技术面数据（price/ma20/position_20d）")
        reasoning = f"MSS {mss:.0f}，但技术面数据不完整，仅观察"
        confidence = "中"
    elif mss < aggressive:
        label_key = "watch"
        reasoning = f"MSS {mss:.0f} 低于进攻阈值 {aggressive:.0f}，维持高现金观望"
        confidence = "中"
    else:
        label_key = "buy"
        reasoning = f"MSS {mss:.0f} 达进攻阈值，技术面共振允许条件性建仓"

    if position_20d is not None and position_20d > high_pos and mss < aggressive:
        if label_key == "buy":
            label_key = "watch"
        downgrade.append(f"20日价格位置 {position_20d:.0%} 偏高且 MSS 未达 {aggressive:.0f}")
        confidence = "中"

    if volume_ratio is None:
        if confidence == "高":
            confidence = "中"
        downgrade.append("缺少量比 volume_ratio")
    elif volume_ratio < min_vol_ratio and label_key == "buy":
        label_key = "watch"
        downgrade.append(f"量比 {volume_ratio:.2f} < {min_vol_ratio}")

    if vwap_deviation is not None and abs(vwap_deviation) >= max_vwap_dev:
        if volume_ratio is not None and volume_ratio < min_vol_ratio:
            label_key = "avoid"
            blocked = True
            downgrade.append(f"VWAP 偏离 {vwap_deviation:.1%} 且量比不足")
        elif label_key == "buy":
            label_key = "watch"
            downgrade.append(f"VWAP 偏离 {vwap_deviation:.1%} 过大")

    if snapshot.get("audit_passed") is False:
        label_key = "watch" if label_key != "avoid" else "avoid"
        blocked = True
        downgrade.append("数据审计未通过")
        confidence = "低"

    if not snapshot.get("structured_review_complete", True):
        if label_key == "buy":
            label_key = "watch"
        downgrade.append("未完成结构化复核")
        confidence = "低"

    verdict_map = {"buy": buy_label, "watch": watch_label, "avoid": avoid_label}
    verdict = verdict_map[label_key]

    stop_loss = None
    entry = price
    if price is not None and ma20 is not None:
        from agent_reach.daily_run.harness_policy import runtime_float_default

        stop_pct = runtime_float_default(settings, "trading", "stop_loss_ma20_pct")
        stop_loss = round(min(ma20, price * (1 - stop_pct)), 2)

    invalidation = (
        f"MSS 跌破 {macro_veto:.0f} 或触发止损 "
        f"({stop_loss if stop_loss else 'MA20-4%'})"
    )

    return VerdictResult(
        verdict=verdict,
        confidence=confidence,
        mss_final=mss,
        entry_price=entry,
        stop_loss_price=stop_loss,
        invalidation=invalidation,
        reasoning=reasoning,
        downgrade_reasons=downgrade,
        blocked=blocked,
        label_key=label_key,
    )


def fuse_verdict_with_team(
    verdict: VerdictResult,
    snapshot: dict[str, Any],
    settings: dict[str, Any],
) -> VerdictResult:
    """Merge MSS verdict with Team supervisor, identifier block, and Buffett filter."""
    labels = settings.get("verdict_labels", {})
    buy_label = labels.get("buy", "可做")
    watch_label = labels.get("watch", "观察")
    avoid_label = labels.get("avoid", "回避")

    downgrade = list(verdict.downgrade_reasons)
    label_key = verdict.label_key
    blocked = verdict.blocked
    confidence = verdict.confidence
    reasoning = verdict.reasoning

    # Identifier block from team review
    team_review = snapshot.get("team_review") or {}
    if snapshot.get("identifier_blocked") or team_review.get("blocked"):
        if label_key == "buy":
            label_key = "watch"
        blocked = True
        reason = team_review.get("block_reason") or "专家鉴别 Agent 阻断"
        downgrade.append(reason)
        confidence = "低"

    # Team consensus label fusion
    consensus_label = snapshot.get("team_consensus_label") or team_review.get("consensus_label")
    if consensus_label:
        consensus_key = _label_to_key(consensus_label, labels)
        label_key = _merge_label_keys(label_key, consensus_key)
        if consensus_key == "avoid":
            blocked = True
        elif consensus_key == "watch" and label_key != "avoid":
            label_key = "watch"
        downgrade.append(f"Team 共识：{consensus_label}（{team_review.get('consensus_score', '—')} 分）")

    # Buffett hard veto when fundamentals present and fail
    buffett_blocked, buffett_notes = _check_buffett_filter(snapshot, settings)
    if buffett_blocked:
        if label_key == "buy":
            label_key = "watch"
        blocked = True
        downgrade.extend(buffett_notes)
        confidence = "低"

    verdict_map = {"buy": buy_label, "watch": watch_label, "avoid": avoid_label}
    return VerdictResult(
        verdict=verdict_map[label_key],
        confidence=confidence,
        mss_final=verdict.mss_final,
        entry_price=verdict.entry_price,
        stop_loss_price=verdict.stop_loss_price,
        invalidation=verdict.invalidation,
        reasoning=reasoning,
        downgrade_reasons=downgrade,
        blocked=blocked,
        label_key=label_key,
    )


def _label_to_key(label: str, labels: dict[str, str]) -> str:
    if label == labels.get("buy", "可做"):
        return "buy"
    if label == labels.get("avoid", "回避"):
        return "avoid"
    return "watch"


def _merge_label_keys(a: str, b: str) -> str:
    order = {"avoid": 0, "watch": 1, "buy": 2}
    return a if order.get(a, 1) <= order.get(b, 1) else b


def _check_buffett_filter(
    snapshot: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[bool, list[str]]:
    bf = settings.get("buffett_filter", {})
    notes: list[str] = []
    blocked = False
    fields_present = 0
    failures = 0

    checks = [
        ("gross_margin", float(bf.get("min_gross_margin", 0.35)), lambda v, t: v >= t, "毛利率"),
        ("peg", float(bf.get("max_peg", 1.2)), lambda v, t: v < t, "PEG"),
        ("roe", float(bf.get("min_roe", 0.15)), lambda v, t: v >= t, "ROE"),
    ]
    for field, threshold, ok_fn, label in checks:
        val = _optional_float(snapshot.get(field))
        if val is None:
            continue
        fields_present += 1
        if not ok_fn(val, threshold):
            failures += 1
            notes.append(f"Buffett {label} 不达标（{val} vs 阈值 {threshold}）")

    if fields_present > 0 and failures > 0:
        blocked = True
    return blocked, notes


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)
