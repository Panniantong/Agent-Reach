# -*- coding: utf-8
"""Cross-source hot-topic deduplication (60s / RedFox / Xueqiu)."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from agent_reach.daily_run.harness_context_doctor import text_similarity
from agent_reach.daily_run.redfox_weekly import _norm_title


def _compact_title(title: str) -> str:
    """Strip whitespace/punctuation so 「半导体 政策」≈「半导体政策」."""
    norm = _norm_title(title)
    return re.sub(r"[\s·|/，。、；：\"'!！?？\-—]+", "", norm)


def _dedup_cfg(settings: Optional[dict[str, Any]]) -> dict[str, Any]:
    cfg = settings or {}
    macro = cfg.get("macro_collector") or {}
    nested = macro.get("hot_topic_dedup") or {}
    enabled = nested.get("enabled", macro.get("hot_topic_dedup_enabled", True))
    threshold = float(
        nested.get("similarity_threshold", macro.get("hot_topic_dedup_threshold", 0.86))
    )
    cross_source = nested.get("cross_source", macro.get("hot_topic_dedup_cross_source", True))
    return {
        "enabled": enabled is not False,
        "similarity_threshold": threshold,
        "cross_source": cross_source is not False,
    }


def _post_title(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    if title:
        return title
    text = str(item.get("text") or "").strip()
    return text[:80] if text else ""


def _is_near_duplicate(text: str, corpus: list[str], *, threshold: float) -> bool:
    norm = _norm_title(text)
    compact = _compact_title(text)
    if not norm and not compact:
        return False
    for prior in corpus:
        if norm and _norm_title(prior) == norm:
            return True
        if compact and _compact_title(prior) == compact:
            return True
        if text_similarity(text, prior) >= threshold:
            return True
    return False


def _filter_bucket(
    items: list[Any],
    corpus: list[str],
    *,
    title_fn: Callable[[dict[str, Any]], str],
    threshold: float,
    register_kept: bool,
) -> tuple[list[Any], list[str]]:
    kept: list[Any] = []
    dropped: list[str] = []
    for raw in items:
        if not isinstance(raw, dict):
            kept.append(raw)
            continue
        title = title_fn(raw)
        if not title:
            kept.append(raw)
            if register_kept:
                corpus.append(title)
            continue
        if _is_near_duplicate(title, corpus, threshold=threshold):
            dropped.append(title[:80])
            continue
        kept.append(raw)
        if register_kept:
            corpus.append(title)
    return kept, dropped


def dedupe_macro_hot_topics(
    signals: dict[str, Any],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Drop near-duplicate headlines across macro hot-topic buckets."""
    cfg = _dedup_cfg(settings)
    if not cfg["enabled"]:
        return {"enabled": False}

    threshold = cfg["similarity_threshold"]
    corpus: list[str] = []
    dropped_by_source: dict[str, list[str]] = {}
    input_counts: dict[str, int] = {}

    priority: list[tuple[str, Callable[[dict[str, Any]], str], bool]] = [
        ("portfolio_hot_posts", _post_title, True),
        ("hot_topics_matched", lambda item: str(item.get("title") or ""), True),
        ("redfox_matched", lambda item: str(item.get("title") or ""), True),
        ("sentiment_hits", _post_title, True),
    ]

    for bucket, title_fn, register in priority:
        items = list(signals.get(bucket) or [])
        input_counts[bucket] = len(items)
        kept, dropped = _filter_bucket(
            items,
            corpus,
            title_fn=title_fn,
            threshold=threshold,
            register_kept=register,
        )
        signals[bucket] = kept
        if dropped:
            dropped_by_source[bucket] = dropped

    if cfg["cross_source"]:
        posts = list(signals.get("sentiment_posts") or [])
        input_counts["sentiment_posts"] = len(posts)
        kept_posts, dropped_posts = _filter_bucket(
            posts,
            corpus,
            title_fn=_post_title,
            threshold=threshold,
            register_kept=False,
        )
        signals["sentiment_posts"] = kept_posts
        if dropped_posts:
            dropped_by_source["sentiment_posts"] = dropped_posts

    signals["hot_topic_hits"] = len(signals.get("hot_topics_matched") or [])
    signals["redfox_hits"] = len(signals.get("redfox_matched") or [])

    dropped_total = sum(len(v) for v in dropped_by_source.values())
    summary = {
        "enabled": True,
        "similarity_threshold": threshold,
        "cross_source": cfg["cross_source"],
        "input_counts": input_counts,
        "dropped_counts": {k: len(v) for k, v in dropped_by_source.items()},
        "dropped_total": dropped_total,
        "dropped_preview": [
            f"{src}: {title}" for src, titles in dropped_by_source.items() for title in titles[:2]
        ][:8],
    }
    if dropped_total:
        signals["hot_topic_dedup"] = summary
    else:
        signals.pop("hot_topic_dedup", None)
    return summary
