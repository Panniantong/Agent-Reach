# -*- coding: utf-8
"""Dragon-tiger board (龙虎榜) analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LHBAnalysis:
    buyers: list[dict[str, Any]] = field(default_factory=list)
    sellers: list[dict[str, Any]] = field(default_factory=list)
    total_net: float = 0.0
    total_buy: float = 0.0
    total_sell: float = 0.0
    capital_preference: str = ""
    bias: str = "多空均衡"
    buy_count: int = 0
    sell_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "buyers": self.buyers,
            "sellers": self.sellers,
            "total_net": round(self.total_net, 2),
            "total_buy": round(self.total_buy, 2),
            "total_sell": round(self.total_sell, 2),
            "capital_preference": self.capital_preference,
            "summary": {
                "total_net": round(self.total_net, 2),
                "total_buy": round(self.total_buy, 2),
                "total_sell": round(self.total_sell, 2),
                "buy_count": self.buy_count,
                "sell_count": self.sell_count,
                "bias": self.bias,
            },
        }


def analyze_lhb(lhb_stocks: list[dict[str, Any]]) -> LHBAnalysis:
    buyers = sorted(
        [s for s in lhb_stocks if float(s.get("net_buy") or 0) > 0],
        key=lambda x: float(x.get("net_buy") or 0),
        reverse=True,
    )
    sellers = sorted(
        [s for s in lhb_stocks if float(s.get("net_buy") or 0) < 0],
        key=lambda x: float(x.get("net_buy") or 0),
    )
    total_net = sum(float(s.get("net_buy") or 0) for s in lhb_stocks)
    total_buy = sum(float(s.get("buy_amt") or 0) for s in lhb_stocks)
    total_sell = sum(float(s.get("sell_amt") or 0) for s in lhb_stocks)

    if total_net > 5:
        bias, detail = "偏进攻", "龙虎榜资金大幅净买入，大资金积极做多"
    elif total_net > 0:
        bias, detail = "略偏进攻", "龙虎榜资金净买入为主"
    elif total_net < -5:
        bias, detail = "偏防守", "龙虎榜资金大幅净卖出，获利了结意愿强"
    elif total_net < 0:
        bias, detail = "略偏防守", "龙虎榜资金净卖出为主，偏谨慎"
    else:
        bias, detail = "多空均衡", "龙虎榜买卖基本均衡"

    capital_preference = (
        f"{bias}。{detail}。净买入 {len(buyers)} 家，净卖出 {len(sellers)} 家，"
        f"净差额 {total_net:.1f} 亿"
    )

    return LHBAnalysis(
        buyers=buyers[:10],
        sellers=sellers[:10],
        total_net=total_net,
        total_buy=total_buy,
        total_sell=total_sell,
        capital_preference=capital_preference,
        bias=bias,
        buy_count=len(buyers),
        sell_count=len(sellers),
    )
