# -*- coding: utf-8
"""Compare baseline vs current snapshots/reports (prediction validation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.verdict import compute_mss, compute_verdict


@dataclass
class VerifyResult:
    code: Optional[str]
    name: Optional[str]
    price_baseline: Optional[float]
    price_current: Optional[float]
    price_delta_pct: Optional[float]
    mss_baseline: Optional[float]
    mss_current: Optional[float]
    mss_delta: Optional[float]
    verdict_baseline: Optional[str]
    verdict_current: Optional[str]
    verdict_changed: bool
    mss_range_baseline: Optional[tuple[float, float]]
    mss_within_prediction: Optional[bool]
    summary: str
    recommendations: list[str] = field(default_factory=list)
    deviations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "price_baseline": self.price_baseline,
            "price_current": self.price_current,
            "price_delta_pct": self.price_delta_pct,
            "mss_baseline": self.mss_baseline,
            "mss_current": self.mss_current,
            "mss_delta": self.mss_delta,
            "verdict_baseline": self.verdict_baseline,
            "verdict_current": self.verdict_current,
            "verdict_changed": self.verdict_changed,
            "mss_range_baseline": list(self.mss_range_baseline)
            if self.mss_range_baseline
            else None,
            "mss_within_prediction": self.mss_within_prediction,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "deviations": self.deviations,
        }


def verify_from_dict(data: dict[str, Any]) -> VerifyResult:
    """Rebuild VerifyResult from verify_snapshots().to_dict() output."""
    rng = data.get("mss_range_baseline")
    mss_range: Optional[tuple[float, float]] = None
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        mss_range = (float(rng[0]), float(rng[1]))
    return VerifyResult(
        code=data.get("code"),
        name=data.get("name"),
        price_baseline=data.get("price_baseline"),
        price_current=data.get("price_current"),
        price_delta_pct=data.get("price_delta_pct"),
        mss_baseline=data.get("mss_baseline"),
        mss_current=data.get("mss_current"),
        mss_delta=data.get("mss_delta"),
        verdict_baseline=data.get("verdict_baseline"),
        verdict_current=data.get("verdict_current"),
        verdict_changed=bool(data.get("verdict_changed")),
        mss_range_baseline=mss_range,
        mss_within_prediction=data.get("mss_within_prediction"),
        summary=str(data.get("summary") or ""),
        recommendations=list(data.get("recommendations") or []),
        deviations=list(data.get("deviations") or []),
    )


def verify_snapshots(
    baseline: dict[str, Any],
    current: dict[str, Any],
    settings: Optional[dict[str, Any]] = None,
) -> VerifyResult:
    """Compare two snapshots and explain deviations."""
    from agent_reach.daily_run.settings import effective_settings
    from agent_reach.daily_run.harness_policy import threshold_default

    cfg = effective_settings(settings)
    thresholds = cfg.get("thresholds", {})
    max_dev = float(threshold_default(cfg, "max_price_deviation_pct"))

    code = current.get("code") or baseline.get("code")
    name = current.get("name") or baseline.get("name")

    pb = _f(baseline.get("price"))
    pc = _f(current.get("price"))
    price_delta = None
    if pb and pc and pb > 0:
        price_delta = (pc - pb) / pb

    mb = baseline.get("mss_final")
    if mb is None:
        mb = compute_mss(baseline.get("mss_breakdown") or {}, cfg)
    mc = current.get("mss_final")
    if mc is None:
        mc = compute_mss(current.get("mss_breakdown") or {}, cfg)
    mss_delta = (mc - mb) if mb is not None and mc is not None else None

    vb = baseline.get("verdict")
    if vb is None:
        vb = compute_verdict(baseline, cfg).verdict
    vc = current.get("verdict")
    if vc is None:
        vc = compute_verdict(current, cfg).verdict

    mss_range = _parse_mss_range(baseline)
    within = None
    deviations: list[str] = []
    if mss_range and mc is not None:
        low, high = mss_range
        within = low <= mc <= high
        if not within:
            if mc < low:
                deviations.append(
                    f"MSS 实际 {mc:.1f} 低于预测下沿 {low:.1f}（偏差 {mc - low:.1f}）"
                )
            else:
                deviations.append(
                    f"MSS 实际 {mc:.1f} 高于预测上沿 {high:.1f}（偏差 {mc - high:.1f}）"
                )

    if price_delta is not None and abs(price_delta) > max_dev:
        deviations.append(f"价格变动 {price_delta:.1%} 超过锚点阈值 {max_dev:.1%}")

    if vb != vc:
        deviations.append(f"标签由「{vb}」变为「{vc}」")

    recommendations: list[str] = []
    if within is False:
        recommendations.append("复盘预测偏差原因（外资流速、汇率、突发政策等）并更新 MSS 权重")
    if vc == "回避":
        recommendations.append("维持高现金，取消一切买入计划")
    elif vc == "观察" and vb == "可做":
        recommendations.append("宏观或技术面转弱，降级为观望")
    elif vc == "可做" and vb in ("观察", "回避"):
        recommendations.append("右侧信号出现，可在 14:00 后条件性建仓")

    parts = [f"{name or code or '标的'} 验证完成"]
    if price_delta is not None:
        parts.append(f"价格 {price_delta:+.1%}")
    if mss_delta is not None:
        parts.append(f"MSS {mb:.0f}→{mc:.0f} ({mss_delta:+.0f})")
    if within is not None:
        parts.append("预测命中" if within else "预测偏离")

    return VerifyResult(
        code=code,
        name=name,
        price_baseline=pb,
        price_current=pc,
        price_delta_pct=price_delta,
        mss_baseline=float(mb) if mb is not None else None,
        mss_current=float(mc) if mc is not None else None,
        mss_delta=mss_delta,
        verdict_baseline=vb,
        verdict_current=vc,
        verdict_changed=vb != vc,
        mss_range_baseline=mss_range,
        mss_within_prediction=within,
        summary="；".join(parts),
        recommendations=recommendations,
        deviations=deviations,
    )


def render_verify_markdown(result: VerifyResult) -> str:
    lines = [
        f"**验证摘要：** {result.summary}",
        "",
        "| 指标 | 基线 | 当前 | 变化 |",
        "|------|------|------|------|",
    ]
    lines.append(
        f"| 价格 | {result.price_baseline} | {result.price_current} | "
        f"{_fmt_pct(result.price_delta_pct)} |"
    )
    lines.append(
        f"| MSS | {result.mss_baseline} | {result.mss_current} | "
        f"{result.mss_delta:+.0f} |"
        if result.mss_delta is not None
        else f"| MSS | {result.mss_baseline} | {result.mss_current} | — |"
    )
    lines.append(
        f"| 标签 | {result.verdict_baseline} | {result.verdict_current} | "
        f"{'变更' if result.verdict_changed else '不变'} |"
    )

    if result.mss_range_baseline:
        low, high = result.mss_range_baseline
        hit = "✅ 命中" if result.mss_within_prediction else "❌ 偏离"
        lines.extend(["", f"**MSS 预测区间：** [{low:.0f}, {high:.0f}] → {hit}"])

    if result.deviations:
        lines.extend(["", "**偏差拆解：**"])
        for d in result.deviations:
            lines.append(f"- {d}")

    if result.recommendations:
        lines.extend(["", "**明日建议：**"])
        for r in result.recommendations:
            lines.append(f"- {r}")

    return "\n".join(lines)


def _parse_mss_range(snapshot: dict[str, Any]) -> Optional[tuple[float, float]]:
    rng = snapshot.get("mss_range") or snapshot.get("mss_intraday_range")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        return float(rng[0]), float(rng[1])
    text = snapshot.get("macro_summary") or ""
    if "[" in text and "]" in text:
        import re

        match = re.search(r"\[(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\]", str(text))
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.1%}"
