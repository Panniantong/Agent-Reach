# -*- coding: utf-8
"""Sector mainline detection from limit-up distribution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SectorMainline:
    mainline_type: str = "多题材轮动"
    reasoning: str = ""
    main_sectors: list[dict[str, Any]] = field(default_factory=list)
    ladder: list[dict[str, Any]] = field(default_factory=list)
    sector_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mainline_type": self.mainline_type,
            "reasoning": self.reasoning,
            "main_sectors": self.main_sectors,
            "ladder": self.ladder,
            "sector_counts": self.sector_counts,
        }


def analyze_sectors(
    limit_up_stocks: list[dict[str, Any]],
    *,
    industries: Optional[list[dict[str, Any]]] = None,
    concepts: Optional[list[dict[str, Any]]] = None,
) -> SectorMainline:
    """Detect single/dual/multi mainline from limit-up industry clusters."""
    _ = industries, concepts
    groups: dict[str, list[dict[str, Any]]] = {}
    for stock in limit_up_stocks:
        ind = str(stock.get("industry") or "其他").strip() or "其他"
        groups.setdefault(ind, []).append(stock)

    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
    top = len(sorted_groups[0][1]) if sorted_groups else 0
    second = len(sorted_groups[1][1]) if len(sorted_groups) > 1 else 0
    gap = top - second

    if top >= 15 and gap >= 5:
        mainline_type = "单主线"
        reasoning = f"主线明确：{sorted_groups[0][0]} 涨停 {top} 家，领先第二名 {gap} 家"
    elif top >= 8 and second >= 8 and gap < 5:
        mainline_type = "双主线"
        reasoning = (
            f"双主线并行：{sorted_groups[0][0]}({top}家) 与 {sorted_groups[1][0]}({second}家)"
        )
    else:
        mainline_type = "多题材轮动"
        strongest = sorted_groups[0][0] if sorted_groups else "无"
        reasoning = f"题材分散：最强 {strongest} 仅 {top} 家涨停"

    main_sectors = []
    for name, stocks in sorted_groups[:5]:
        main_sectors.append(
            {
                "name": name,
                "limit_up_count": len(stocks),
                "top_stocks": [
                    {
                        "code": s.get("code"),
                        "name": s.get("name"),
                        "change_pct": s.get("change_pct"),
                    }
                    for s in stocks[:5]
                ],
            }
        )

    ladder_map: dict[int, list[dict[str, Any]]] = {}
    for stock in limit_up_stocks:
        pct = float(stock.get("change_pct") or 0)
        board = min(int(round(pct / 10)) if pct > 20 else 1, 10)
        ladder_map.setdefault(board, []).append(stock)

    ladder = [
        {
            "board": board,
            "count": len(stocks),
            "stocks": [s.get("name") for s in stocks[:5]],
        }
        for board, stocks in sorted(ladder_map.items(), key=lambda x: x[0], reverse=True)
    ]

    sector_counts = {name: len(stocks) for name, stocks in sorted_groups[:15]}

    return SectorMainline(
        mainline_type=mainline_type,
        reasoning=reasoning,
        main_sectors=main_sectors,
        ladder=ladder,
        sector_counts=sector_counts,
    )
