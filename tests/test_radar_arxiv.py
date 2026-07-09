# -*- coding: utf-8 -*-
"""Tests for the two-tier arXiv collector (pure, offline logic only)."""

from datetime import datetime, timezone

import feedparser

import agent_reach.radar_arxiv as ra
from agent_reach.radar_arxiv import (
    _arxiv_entry_to_item,
    _arxiv_query_url,
    _pending_scaffold,
    collect_arxiv,
    run_deep_dive,
    score_paper,
)

ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2607.01234v1</id>
    <title>FlashKV: KV Cache Compression for
      Long-Context Inference</title>
    <summary>We compress the KV cache to cut HBM pressure during inference.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Tri Dao</name></author>
    <author><name>Somebody Else</name></author>
    <category term="cs.LG"/>
    <arxiv:comment>NVIDIA technical report</arxiv:comment>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2607.09999v2</id>
    <title>A Survey of Medieval Basket Weaving</title>
    <summary>Nothing to do with machine learning at all.</summary>
    <published>2026-07-08T00:00:00Z</published>
    <author><name>Nobody</name></author>
    <category term="cs.DL"/>
  </entry>
</feed>
"""

KW = {"kv cache": 3, "hbm": 3, "inference": 2}
ORGS = ["NVIDIA", "OpenAI"]
GURUS = ["Tri Dao", "Ilya Sutskever"]


def test_query_url_composition():
    url = _arxiv_query_url(["cs.AI", "cs.LG"], 50)
    assert url.startswith("http://export.arxiv.org/api/query?search_query=")
    assert "cat%3Acs.AI" in url and "cat%3Acs.LG" in url and "OR" in url
    assert "sortBy=submittedDate" in url and "max_results=50" in url


def test_entry_to_item_normalizes():
    feed = feedparser.parse(ATOM_FIXTURE)
    it = _arxiv_entry_to_item(feed.entries[0])
    assert it.kind == "paper"
    assert it.extra["arxiv_id"] == "2607.01234"  # version stripped
    assert it.url == "https://arxiv.org/abs/2607.01234"
    assert "FlashKV: KV Cache Compression for Long-Context Inference" == it.title
    assert it.extra["authors"] == ["Tri Dao", "Somebody Else"]
    assert it.extra["primary_category"] == "cs.LG"
    assert "NVIDIA" in it.extra["comment"]


def test_score_paper_ordering_author_gt_org_gt_keyword():
    feed = feedparser.parse(ATOM_FIXTURE)
    it = _arxiv_entry_to_item(feed.entries[0])
    base = score_paper(it, {}, [], [])
    kw_only = score_paper(it, {"hbm": 1}, [], [])  # 1 abstract hit × weight 1 = 1
    org_only = score_paper(it, {}, [], ORGS)
    author_only = score_paper(it, {}, GURUS, [])
    assert base == 0
    assert author_only > org_only > kw_only > 0
    assert any(w.startswith("作者:Tri Dao") for w in it.extra["why"])


def test_score_paper_title_double_weight():
    feed = feedparser.parse(ATOM_FIXTURE)
    it = _arxiv_entry_to_item(feed.entries[0])
    # "kv cache" appears in title (×2) and abstract (×1) → 3 hits × weight 3 = 9
    assert score_paper(it, {"kv cache": 3}, [], []) == 9


def test_score_paper_word_boundary():
    it = _arxiv_entry_to_item(feedparser.parse(ATOM_FIXTURE).entries[1])
    # "ai" must not fire inside "weaving"/"medieval" etc.
    assert score_paper(it, {"ai": 5}, [], []) == 0


def test_collect_arxiv_filters_and_sorts(monkeypatch):
    parsed = feedparser.parse(ATOM_FIXTURE)  # parse BEFORE patching (shared module object)
    monkeypatch.setattr(ra.feedparser, "parse", lambda url: parsed)
    sources = {
        "arxiv_categories": ["cs.AI"], "arxiv_keywords": KW, "arxiv_orgs": ORGS,
        "gurus": {"research": [{"handle": "tri_dao", "arxiv_names": ["Tri Dao"]}]},
    }
    items = collect_arxiv(sources, config=None)
    # Basket weaving scores 0 → gated out.
    assert len(items) == 1
    assert items[0].extra["arxiv_id"] == "2607.01234"
    assert items[0].score > 0


def test_collect_arxiv_never_raises(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(ra.feedparser, "parse", boom)
    assert collect_arxiv({"arxiv_categories": ["cs.AI"]}, config=None) == []


def test_collect_arxiv_no_categories_is_noop():
    assert collect_arxiv({}, config=None) == []


def test_run_deep_dive_writes_pending_scaffold(monkeypatch, tmp_path):
    monkeypatch.setattr(ra, "DEEPDIVE_DIR", tmp_path)
    monkeypatch.setattr(ra, "fetch_paper_text", lambda arxiv_id, max_chars=30000: "full text here")
    monkeypatch.setattr(ra, "distill_paper", lambda item, fulltext, config=None, model=None: None)
    feed = feedparser.parse(ATOM_FIXTURE)
    it = _arxiv_entry_to_item(feed.entries[0])
    it.score = 12
    when = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    paths = run_deep_dive([it], {"arxiv_deep_dive_n": 1}, config=None, when=when)
    assert len(paths) == 1
    body = paths[0].read_text(encoding="utf-8")
    assert "status: PENDING" in body
    assert "full text here" in body
    assert "TL;DR" in body  # template embedded for interactive Claude
    index = (tmp_path / "latest-index.md").read_text(encoding="utf-8")
    assert "FlashKV" in index


def test_run_deep_dive_writes_distilled_report(monkeypatch, tmp_path):
    monkeypatch.setattr(ra, "DEEPDIVE_DIR", tmp_path)
    monkeypatch.setattr(ra, "fetch_paper_text", lambda arxiv_id, max_chars=30000: "full text")
    monkeypatch.setattr(
        ra, "distill_paper", lambda item, fulltext, config=None, model=None: "# 深讀報告\n內容"
    )
    it = _arxiv_entry_to_item(feedparser.parse(ATOM_FIXTURE).entries[0])
    when = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    paths = run_deep_dive([it], {"arxiv_deep_dive_n": 2}, config=None, when=when)
    assert paths[0].read_text(encoding="utf-8").startswith("# 深讀報告")
    assert "PENDING" not in paths[0].read_text(encoding="utf-8")


def test_pending_scaffold_contains_link_and_reasons():
    it = _arxiv_entry_to_item(feedparser.parse(ATOM_FIXTURE).entries[0])
    it.extra["why"] = ["作者:Tri Dao"]
    when = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    s = _pending_scaffold(it, "", when)
    assert "https://arxiv.org/abs/2607.01234" in s
    assert "作者:Tri Dao" in s
