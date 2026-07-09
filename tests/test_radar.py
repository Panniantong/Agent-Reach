# -*- coding: utf-8 -*-
"""Tests for the AI×investment radar (pure, offline logic only)."""

from datetime import datetime, timezone

from agent_reach.radar import Item, _dedupe, _is_on_topic, _tweet_to_item, build_digest

KW = ["ai", "chip", "hbm", "funding", "$", "data center"]


def _item(title="", text="", url="", source="rss", kind="rss", score=0.0):
    return Item(source=source, kind=kind, title=title, url=url, text=text, score=score)


def test_on_topic_matches_keyword():
    assert _is_on_topic(_item(title="New HBM supercycle"), KW)
    assert _is_on_topic(_item(title="Startup raises huge funding round"), KW)
    assert _is_on_topic(_item(title="$NVDA jumps on earnings"), KW)
    assert _is_on_topic(_item(title="Hyperscaler data center buildout"), KW)


def test_on_topic_word_boundary_avoids_false_positive():
    # "ai" must not fire inside "maintenance"/"available"/"matching".
    assert not _is_on_topic(_item(title="Routine server maintenance available"), KW)
    assert not _is_on_topic(_item(title="Decompile GameCube into matching C"), KW)


def test_on_topic_empty_keywords_passes_everything():
    assert _is_on_topic(_item(title="anything at all"), [])


def test_dedupe_by_url():
    a = _item(title="x", url="https://x.com/1")
    b = _item(title="y", url="https://x.com/1")  # same url, different title
    c = _item(title="z", url="https://x.com/2")
    out = _dedupe([a, b, c])
    assert len(out) == 2
    assert {i.url for i in out} == {"https://x.com/1", "https://x.com/2"}


def test_dedupe_by_text_when_no_url():
    a = _item(text="Robotics is next and deal count is skyrocketing")
    b = _item(text="Robotics is next and deal count is skyrocketing")
    assert len(_dedupe([a, b])) == 1


def test_build_digest_structure_and_ranking():
    when = datetime(2026, 6, 28, 17, 0, tzinfo=timezone.utc)
    grouped = {
        "tweet": [
            _item(text="low signal", source="twitter:feed", kind="tweet", score=10),
            _item(text="high signal HBM", source="twitter:@x", kind="tweet", score=999),
        ],
        "web": [_item(title="CoWoS bottleneck", url="https://e/1", kind="web")],
        "rss": [],
        "trend": [],
    }
    md = build_digest(grouped, {"max_items_per_section": 8}, when)
    assert "AI × 投资 雷达" in md
    assert "今日洞察" in md  # insight placeholder section present
    assert "CoWoS bottleneck" in md
    # Higher-score tweet ranked above the lower one.
    assert md.index("high signal HBM") < md.index("low signal")


def test_tweet_to_item_captures_rt_and_screenname():
    raw = {
        "text": "gm",
        "id": "123",
        "author": {"name": "Ansem", "screenName": "blknoiz06"},
        "metrics": {"views": 100, "likes": 5},
        "isRetweet": True,
        "createdAtISO": "2026-06-28T00:00:00+00:00",
    }
    it = _tweet_to_item(raw, source="twitter:@blknoiz06")
    assert it.extra["screenName"] == "blknoiz06"
    assert it.extra["isRetweet"] is True
    assert it.url == "https://x.com/blknoiz06/status/123"


def test_build_digest_renders_contra_lens():
    when = datetime(2026, 6, 28, 17, 0, tzinfo=timezone.utc)
    t = _item(text="buy this microcap", source="twitter:@blknoiz06", kind="tweet", score=50)
    t.extra["lens"] = "最高喊单风险；别买他的小币"
    md = build_digest({"tweet": [t], "web": [], "rss": [], "trend": []}, {}, when)
    assert "怎么读" in md
    assert "最高喊单风险" in md
