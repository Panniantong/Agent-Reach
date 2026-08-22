# -*- coding: utf-8
"""Tests for multi-source hot-topic dedup and Xueqiu hit outcome沉淀."""

import json
from pathlib import Path
from unittest.mock import patch

from agent_reach.daily_run.hot_topic_dedup import dedupe_macro_hot_topics
from agent_reach.daily_run.macro_collector import _derive_mss_breakdown
from agent_reach.daily_run.xueqiu_hit_outcomes import (
    build_xueqiu_hit_fingerprints,
    record_xueqiu_hit_fingerprints,
    render_xueqiu_hit_outcomes_markdown,
    settle_xueqiu_hits,
    summarize_xueqiu_hit_outcomes,
)


class TestHotTopicDedup:
    def test_dedupe_cross_source_titles(self):
        signals = {
            "portfolio_hot_posts": [{"title": "存储芯片景气延续", "text": "", "matched_keywords": ["存储"]}],
            "hot_topics_matched": [{"title": "存储芯片景气延续"}],
            "redfox_matched": [{"title": "存储芯片 景气延续"}],
            "sentiment_hits": [{"title": "存储芯片景气延续", "text": ""}],
            "sentiment_posts": [
                {"title": "存储芯片景气延续", "text": ""},
                {"title": "独立话题 A", "text": ""},
            ],
            "hot_topic_hits": 1,
            "redfox_hits": 1,
        }
        summary = dedupe_macro_hot_topics(
            signals,
            settings={"macro_collector": {"hot_topic_dedup_threshold": 0.86}},
        )
        assert summary["dropped_total"] >= 2
        assert len(signals["hot_topics_matched"]) == 0
        assert len(signals["redfox_matched"]) == 0
        assert len(signals["sentiment_hits"]) == 0
        assert signals["hot_topic_hits"] == 0
        assert signals["redfox_hits"] == 0
        assert len(signals["portfolio_hot_posts"]) == 1
        assert len(signals["sentiment_posts"]) == 1
        assert signals["sentiment_posts"][0]["title"] == "独立话题 A"

    def test_dedup_affects_mss_breakdown(self):
        signals = {
            "portfolio_hot_posts": [],
            "hot_topics_matched": [
                {"title": "半导体政策利好"},
                {"title": "半导体 政策利好"},
            ],
            "redfox_matched": [],
            "sentiment_hits": [],
            "hot_topic_hits": 2,
        }
        dedupe_macro_hot_topics(signals, settings={})
        assert signals["hot_topic_hits"] == 1
        before = _derive_mss_breakdown(
            {},
            {"hot_topic_hits": 2},
            {"hot_news": {"sentiment_boost_per_hit": 2}},
        )
        after = _derive_mss_breakdown(
            {},
            signals,
            {"hot_news": {"sentiment_boost_per_hit": 2}},
        )
        assert after["sentiment"] < before["sentiment"]


class TestXueqiuHitOutcomes:
    def test_build_fingerprints(self):
        snapshot = {
            "code": "688008",
            "name": "澜起科技",
            "macro_signals": {
                "portfolio_hot_stocks": [
                    {"code": "688008", "name": "澜起科技", "board": "人气榜", "rank": 2, "role": "holding"}
                ],
                "portfolio_hot_posts": [
                    {"title": "DDR5 需求旺盛", "matched_keywords": ["DDR"], "url": "https://xueqiu.com/1"}
                ],
            },
        }
        hits = build_xueqiu_hit_fingerprints(snapshot)
        assert len(hits) == 2
        assert hits[0]["hit_type"] == "hot_stock"
        assert hits[1]["hit_type"] == "hot_post"

    def test_record_and_settle(self, tmp_path: Path, monkeypatch):
        pending = tmp_path / "pending.json"
        outcomes = tmp_path / "outcomes.jsonl"
        monkeypatch.setattr(
            "agent_reach.daily_run.xueqiu_hit_outcomes.xueqiu_hit_pending_path",
            lambda: pending,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.xueqiu_hit_outcomes.xueqiu_hit_outcomes_path",
            lambda: outcomes,
        )
        monkeypatch.setattr(
            "agent_reach.daily_run.xueqiu_hit_outcomes.xueqiu_hit_outcomes_dir",
            lambda: tmp_path,
        )

        snapshot = {
            "date": "2026-07-25",
            "code": "688008",
            "name": "澜起科技",
            "macro_signals": {
                "portfolio_hot_stocks": [
                    {"code": "688008", "name": "澜起科技", "board": "人气榜", "rank": 2}
                ],
            },
        }
        record = record_xueqiu_hit_fingerprints(snapshot, settings={})
        assert record["recorded"] == 1
        assert pending.exists()

        with patch(
            "agent_reach.daily_run.xueqiu_hit_harness.apply_xueqiu_hit_harness_refinement",
            return_value={"skipped": True},
        ):
            settle = settle_xueqiu_hits(
                {"date": "2026-07-25", "code": "688008", "name": "澜起科技"},
                {"code": "688008"},
                {"price_delta_pct": 0.012, "mss_delta": 2.0},
                settings={},
            )
        assert settle["settled_count"] == 1
        assert settle["counts"]["hit"] == 1
        assert outcomes.exists()
        row = json.loads(outcomes.read_text(encoding="utf-8").strip())
        assert row["outcome"] == "hit"
        assert not json.loads(pending.read_text(encoding="utf-8"))

    def test_render_and_summarize(self):
        entries = [
            {"hit_type": "hot_stock", "outcome": "hit", "name": "A", "reason": "ok"},
            {"hit_type": "hot_stock", "outcome": "miss", "name": "B", "reason": "weak"},
            {"hit_type": "hot_post", "outcome": "neutral", "name": "C", "reason": "flat"},
        ]
        stats = summarize_xueqiu_hit_outcomes(entries)
        assert stats["total"] == 3
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        md = render_xueqiu_hit_outcomes_markdown(stats, settled=entries[:1])
        assert "雪球热榜命中复盘" in md
        assert "当日结算" in md
