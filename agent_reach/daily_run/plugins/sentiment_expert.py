# -*- coding: utf-8
"""Built-in sentiment expert — flow / social + Xueqiu/Exa channel enrich."""

from __future__ import annotations

from agent_reach.daily_run.channel_helpers import (
    fetch_eastmoney_intent_snippet,
    fetch_xueqiu_hot_summary,
    hot_news_summary_from_snapshot,
    score_from_text,
    search_exa_snippet,
)
from agent_reach.daily_run.plugins.base import ExpertPlugin, PluginContext, PluginResult


class SentimentExpert(ExpertPlugin):
    name = "sentiment"
    description = "消息面猎手：资金流、舆情（支持雪球/Exa 增强）"

    def run(self, context: PluginContext) -> PluginResult:
        snap = context.snapshot
        settings = context.settings
        breakdown = snap.get("mss_breakdown") or {}
        flow = float(breakdown.get("flow", 50))
        sentiment = float(breakdown.get("sentiment", 50))
        score = round(flow * 0.4 + sentiment * 0.6, 1)

        sources = snap.get("sources") or {}
        parts: list[str] = []
        for key in ("sentiment", "flow"):
            item = sources.get(key)
            if isinstance(item, dict):
                parts.append(str(item.get("summary", key)))
            elif item:
                parts.append(str(item))

        channel_note = ""
        hot = hot_news_summary_from_snapshot(snap)
        if hot:
            channel_note = hot.split("\n")[0][:120]
            score = round((score + score_from_text(hot, score)) / 2, 1)
        elif settings.get("plugins", {}).get("channel_enrich", True):
            em = fetch_eastmoney_intent_snippet(snap, settings)
            if em:
                channel_note = em
                score = round((score + score_from_text(em, score)) / 2, 1)
            else:
                xq = fetch_xueqiu_hot_summary(limit=3)
                if xq:
                    channel_note = xq
                    score = round((score + score_from_text(xq, score)) / 2, 1)
                else:
                    name = snap.get("name") or snap.get("code") or "A股"
                    exa = search_exa_snippet(f"{name} stock sentiment news China 2026", settings)
                    if exa:
                        channel_note = exa
                        score = round((score + score_from_text(exa, score)) / 2, 1)

        summary = " | ".join(parts) if parts else f"舆情 flow={flow} sentiment={sentiment} → {score}"
        if channel_note:
            summary = f"{summary} | {channel_note[:100]}"

        return PluginResult(
            name=self.name,
            score=score,
            summary=summary[:200],
            details={"channel_enriched": bool(channel_note)},
        )
