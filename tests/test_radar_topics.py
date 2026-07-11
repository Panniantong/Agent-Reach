# -*- coding: utf-8 -*-
"""Multi-topic collection tests: per-topic arXiv plan/loop, cross-topic
dedupe, digest topic sections, and platform-selectable collect_all.
All offline — feeds and collectors are monkeypatched."""

from datetime import datetime, timezone

import feedparser

import agent_reach.radar as radar
import agent_reach.radar_arxiv as ra
from agent_reach.radar import DEFAULT_SOURCES, Item, build_digest, collect_all
from agent_reach.radar_arxiv import arxiv_topic_plan, collect_arxiv

ATOM_EE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.11111v1</id>
    <title>Chiplet Interposer Co-Design with HBM</title>
    <summary>Advanced packaging with an interposer for HBM stacks.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Alice</name></author>
    <category term="cs.AR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2607.22222v1</id>
    <title>Medieval Basket Weaving Revisited</title>
    <summary>Nothing relevant here.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Nobody</name></author>
    <category term="cs.DL"/>
  </entry>
</feed>
"""

ATOM_QUANTUM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.33333v1</id>
    <title>Logical Qubit Error Correction at Scale</title>
    <summary>Error correction for superconducting qubit arrays.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Bob</name></author>
    <category term="quant-ph"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2607.11111v1</id>
    <title>Chiplet Interposer Co-Design with HBM</title>
    <summary>Advanced packaging with an interposer for HBM stacks.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Alice</name></author>
    <category term="cs.AR"/>
  </entry>
</feed>
"""

TWO_TOPIC_SOURCES = {
    "topics": {
        "ee": {
            "label": "電子工程",
            "arxiv_categories": ["cs.AR"],
            "arxiv_keywords": {"chiplet": 3, "interposer": 2, "hbm": 3},
        },
        "quantum": {
            "label": "量子科技",
            "arxiv_categories": ["quant-ph"],
            "arxiv_keywords": {"error correction": 3, "logical qubit": 3, "chiplet": 1},
        },
    },
}


def _patch_feeds(monkeypatch, feeds_by_call):
    """_parse_feed returns fixture feeds in call order; records URLs."""
    calls = []

    def fake(src, timeout=15):
        calls.append(src)
        return feedparser.parse(feeds_by_call[len(calls) - 1])

    monkeypatch.setattr(ra, "_parse_feed", fake)
    monkeypatch.setattr(ra, "_ARXIV_PACING_S", 0.0)
    return calls


def test_default_sources_have_five_topics():
    topics = DEFAULT_SOURCES["topics"]
    assert set(topics) == {"ai", "ee", "rf", "spacetech", "quantum"}
    for spec in topics.values():
        assert spec["arxiv_categories"] and spec["arxiv_keywords"] and spec["label"]
    # The ai topic mirrors the legacy top-level keys (backward-compatible tuning).
    assert topics["ai"]["arxiv_categories"] == DEFAULT_SOURCES["arxiv_categories"]
    assert topics["ai"]["arxiv_keywords"] == DEFAULT_SOURCES["arxiv_keywords"]


def test_topic_plan_legacy_fallback():
    plan = arxiv_topic_plan({"arxiv_categories": ["cs.AI"], "arxiv_keywords": {"ai": 1}})
    assert len(plan) == 1
    assert plan[0]["topic"] == ""
    assert plan[0]["categories"] == ["cs.AI"]


def test_topic_plan_prefers_topics():
    plan = arxiv_topic_plan(TWO_TOPIC_SOURCES)
    assert [p["topic"] for p in plan] == ["ee", "quantum"]
    assert plan[0]["label"] == "電子工程"


def test_legacy_collect_makes_exactly_one_query(monkeypatch):
    calls = _patch_feeds(monkeypatch, [ATOM_EE])
    items = collect_arxiv({"arxiv_categories": ["cs.AR"], "arxiv_keywords": {"chiplet": 3}}, None)
    assert len(calls) == 1
    assert len(items) == 1
    assert items[0].extra["topic"] == ""


def test_per_topic_collect_tags_and_dedupes(monkeypatch):
    calls = _patch_feeds(monkeypatch, [ATOM_EE, ATOM_QUANTUM])
    items = collect_arxiv(TWO_TOPIC_SOURCES, None)
    assert len(calls) == 2  # one query per topic
    by_id = {i.extra["arxiv_id"]: i for i in items}
    # Chiplet paper appears in both feeds → deduped to one Item.
    assert len(items) == 2
    chip = by_id["2607.11111"]
    # EE scores it higher (chiplet:3 vs 1) → EE copy wins, both topics recorded.
    assert chip.extra["topic"] == "ee"
    assert set(chip.extra["topics"]) == {"ee", "quantum"}
    assert by_id["2607.33333"].extra["topic"] == "quantum"
    # Basket weaving gated out by the scorer in every topic.
    assert "2607.22222" not in by_id


def test_digest_groups_papers_by_topic():
    when = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
    p_ee = Item(source="arxiv", kind="paper", title="Chiplet paper",
                url="https://arxiv.org/abs/1", score=9, extra={"topic": "ee", "why": []})
    p_q = Item(source="arxiv", kind="paper", title="Qubit paper",
               url="https://arxiv.org/abs/2", score=6, extra={"topic": "quantum", "why": []})
    md = build_digest({"paper": [p_ee, p_q]}, TWO_TOPIC_SOURCES, when)
    assert "### 電子工程" in md and "### 量子科技" in md
    assert md.index("### 電子工程") < md.index("### 量子科技")  # topics-dict order


def test_digest_flat_when_untagged():
    when = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
    p = Item(source="arxiv", kind="paper", title="Legacy paper",
             url="https://arxiv.org/abs/3", score=5, extra={"why": []})
    md = build_digest({"paper": [p]}, {}, when)
    assert "Legacy paper" in md
    assert "###" not in md.split("## 📄")[1].split("## ")[0].replace(">", "")


def test_collect_all_platform_filter(monkeypatch):
    ran = []
    monkeypatch.setattr(radar, "collect_twitter", lambda s, c: ran.append("twitter") or [])
    monkeypatch.setattr(radar, "collect_exa", lambda s: ran.append("exa") or [])
    monkeypatch.setattr(radar, "collect_rss", lambda s: ran.append("rss") or [])
    monkeypatch.setattr(radar, "collect_google_trends", lambda s: ran.append("trends") or [])
    import agent_reach.radar_arxiv as ra_mod
    monkeypatch.setattr(ra_mod, "collect_arxiv", lambda s, c: ran.append("arxiv") or [])

    grouped = collect_all({}, None, platforms=["arxiv", "rss"])
    assert set(ran) == {"arxiv", "rss"}
    # Stable shape: unselected groups still present, just empty.
    assert set(grouped) == {"tweet", "web", "rss", "trend", "paper"}
    assert grouped["tweet"] == [] and grouped["paper"] == []


def test_collect_all_ignores_unknown_platform(monkeypatch):
    monkeypatch.setattr(radar, "collect_rss", lambda s: [])
    grouped = collect_all({}, None, platforms=["rss", "myspace"])
    assert set(grouped) == {"tweet", "web", "rss", "trend", "paper"}
