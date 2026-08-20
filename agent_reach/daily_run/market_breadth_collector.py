# -*- coding: utf-8
"""Market breadth and emotion scoring (a-stock-review-skill)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MarketEmotion:
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up: int = 0
    limit_down: int = 0
    broken_count: int = 0
    broken_rate: float = 0.0
    ratio: str = "0:0"
    ratio_num: float = 0.0
    score: int = 0
    rating: str = "中"
    position: str = "5成"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    northbound_net_yi: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "up_count": self.up_count,
            "down_count": self.down_count,
            "flat_count": self.flat_count,
            "limit_up": self.limit_up,
            "limit_down": self.limit_down,
            "broken_count": self.broken_count,
            "broken_rate": round(self.broken_rate, 4),
            "ratio": self.ratio,
            "ratio_num": round(self.ratio_num, 3),
            "score": self.score,
            "rating": self.rating,
            "position": self.position,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "northbound_net_yi": self.northbound_net_yi,
        }


def analyze_emotion(
    stocks: list[dict[str, Any]],
    north: dict[str, Any],
    *,
    indices: Optional[dict[str, Any]] = None,
) -> MarketEmotion:
    """Score market emotion from full A-share snapshot (upstream analyzeEmotion)."""
    _ = indices  # reserved for future index-weighted scoring
    up_count = sum(1 for s in stocks if _pct(s) > 0)
    down_count = sum(1 for s in stocks if _pct(s) < 0)
    flat_count = sum(1 for s in stocks if _pct(s) == 0)
    limit_up = sum(1 for s in stocks if _pct(s) >= 9.8)
    limit_down = sum(1 for s in stocks if _pct(s) <= -9.8)
    near_limit = sum(1 for s in stocks if 8 <= _pct(s) < 9.8)
    return _score_market_emotion(
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        limit_up=limit_up,
        limit_down=limit_down,
        near_limit=near_limit,
        north=north,
        include_limit_scoring=True,
    )


def analyze_emotion_from_counts(
    up_count: int,
    down_count: int,
    flat_count: int,
    north: dict[str, Any],
    *,
    indices: Optional[dict[str, Any]] = None,
    by_market: Optional[dict[str, Any]] = None,
) -> MarketEmotion:
    """Score emotion from aggregate rise/fall/flat (Xueqiu index detail fallback)."""
    _ = indices
    em = _score_market_emotion(
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        limit_up=0,
        limit_down=0,
        near_limit=0,
        north=north,
        include_limit_scoring=False,
    )
    em.warnings.append("涨跌停/炸板率需 Eastmoney clist，当前为雪球宽度回退")
    if by_market:
        parts = []
        for label, row in by_market.items():
            if isinstance(row, dict):
                parts.append(
                    f"{label} {row.get('rise_count', 0)}:{row.get('fall_count', 0)}"
                )
        if parts:
            em.reasons.insert(0, f"雪球宽度（{' · '.join(parts)}）")
    else:
        em.reasons.insert(0, "雪球宽度（沪+深涨跌平汇总）")
    return em


def _score_market_emotion(
    *,
    up_count: int,
    down_count: int,
    flat_count: int,
    limit_up: int,
    limit_down: int,
    near_limit: int,
    north: dict[str, Any],
    include_limit_scoring: bool,
) -> MarketEmotion:
    broken_rate = near_limit / (limit_up + near_limit) if (limit_up + near_limit) > 0 else 0.0

    score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    ratio_num = up_count / down_count if down_count > 0 else float(up_count)

    if ratio_num > 2:
        score += 3
        reasons.append(f"涨跌比 {up_count}:{down_count}，赚钱效应强")
    elif ratio_num > 1:
        score += 1
        reasons.append(f"涨跌比 {up_count}:{down_count}，偏中性")
    else:
        score -= 2
        reasons.append(f"涨跌比 {up_count}:{down_count}，亏钱效应明显")

    if include_limit_scoring:
        if limit_up >= 80:
            score += 2
            reasons.append(f"涨停 {limit_up} 家，情绪火爆")
        elif limit_up >= 40:
            score += 1
            reasons.append(f"涨停 {limit_up} 家，情绪正常")
        else:
            reasons.append(f"涨停仅 {limit_up} 家")

        if limit_down >= 50:
            score -= 2
            warnings.append(f"跌停 {limit_down} 家，恐慌蔓延")
            reasons.append(f"跌停 {limit_down} 家")
        elif limit_down >= 20:
            score -= 1
            reasons.append(f"跌停 {limit_down} 家，局部恐慌")
        else:
            reasons.append(f"跌停 {limit_down} 家")

        if broken_rate > 0.3:
            score -= 2
            reasons.append(f"炸板率 {broken_rate * 100:.0f}%，追高意愿弱")
        elif broken_rate > 0.2:
            score -= 1
            reasons.append(f"炸板率 {broken_rate * 100:.0f}%，封板一般")

    net = float(north.get("net_yi") or north.get("net_100m") or 0)
    if net > 50:
        score += 1
        reasons.append(f"北向大幅流入 {net:.0f} 亿")
    elif net > 0:
        reasons.append(f"北向小幅流入 {net:.0f} 亿")
    elif net < -50:
        score -= 1
        warnings.append(f"北向大幅流出 {abs(net):.0f} 亿")
        reasons.append(f"北向大幅流出 {abs(net):.0f} 亿")
    elif net < 0:
        reasons.append(f"北向小幅流出 {abs(net):.0f} 亿")

    if score >= 4:
        rating, position = "强", "7-8成"
    elif score >= 1:
        rating, position = "中", "5成"
    else:
        rating, position = "弱", "2-3成"

    return MarketEmotion(
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        limit_up=limit_up,
        limit_down=limit_down,
        broken_count=near_limit,
        broken_rate=broken_rate,
        ratio=f"{up_count}:{down_count}",
        ratio_num=ratio_num,
        score=score,
        rating=rating,
        position=position,
        reasons=reasons,
        warnings=warnings,
        northbound_net_yi=net,
    )


def collect_market_breadth(
    stocks: list[dict[str, Any]],
    north: dict[str, Any],
    *,
    indices: Optional[dict[str, Any]] = None,
) -> MarketEmotion:
    return analyze_emotion(stocks, north, indices=indices)


def _pct(stock: dict[str, Any]) -> float:
    try:
        return float(stock.get("change_pct") or 0)
    except (TypeError, ValueError):
        return 0.0
