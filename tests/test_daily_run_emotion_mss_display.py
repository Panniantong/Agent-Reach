# -*- coding: utf-8
"""Tests for parallel emotion vs MSS display."""

from agent_reach.daily_run.emotion_mss_display import render_emotion_mss_parallel_markdown
from agent_reach.daily_run.market_review import render_market_review_markdown


def test_render_emotion_mss_parallel_markdown():
    md = render_emotion_mss_parallel_markdown(
        {"emotion": {"rating": "强", "score": 5, "position": "7-8成"}},
        snapshot={
            "mss_final": 56.0,
            "mss_breakdown": {
                "global": 58.0,
                "sentiment": 54.0,
                "_emotion_fusion_ref": {"rating": "强", "score": 5, "deltas": {"global": 4.0}},
            },
        },
    )
    assert "情绪定级 × MSS" in md
    assert "市场宽度情绪" in md
    assert "MSS 宏观因子" in md


def test_market_review_markdown_includes_parallel_section():
    md = render_market_review_markdown(
        {
            "emotion": {
                "rating": "中",
                "score": 2,
                "position": "5成",
                "up_count": 2000,
                "down_count": 1800,
                "ratio": "2000:1800",
            },
            "sector_analysis": {"mainline_type": "单主线", "reasoning": "半导体"},
            "lhb_analysis": {},
            "comparison": {},
        },
        snapshot={"mss_final": 52.0, "mss_breakdown": {"global": 51.0, "sentiment": 50.0}},
    )
    assert "情绪定级 × MSS" in md
