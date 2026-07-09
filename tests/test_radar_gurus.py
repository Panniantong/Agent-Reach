# -*- coding: utf-8 -*-
"""Tests for the guru roster (pure, offline logic only)."""

from datetime import datetime, timezone

from agent_reach.radar import (
    DEFAULT_SOURCES,
    GURU_CATEGORY_LABELS,
    Item,
    build_digest,
    guru_author_names,
    guru_entries,
    guru_feed_meta,
    guru_rss_feeds,
    guru_twitter_accounts,
    load_sources,
)

SOURCES = {
    "gurus": {
        "research": [
            {"handle": "ilyasut", "name": "Ilya Sutskever", "lens": "少而精",
             "arxiv_names": ["Ilya Sutskever"]},
            {"handle": "@tri_dao", "name": "Tri Dao", "arxiv_names": ["Tri Dao"]},
        ],
        "industry_supply": [
            {"handle": "dylan522p", "name": "Dylan Patel", "lens": "個股結論自帶倉位",
             "rss": "https://semianalysis.com/feed/"},
            {"name": "TrendForce", "rss": "https://www.trendforce.com/news/feed/",
             "lens": "報價數據為主"},
        ],
    },
}


def test_guru_entries_flatten_with_category():
    entries = guru_entries(SOURCES)
    assert len(entries) == 4
    by_name = {e.get("name"): e for e in entries}
    assert by_name["Ilya Sutskever"]["category"] == "research"
    assert by_name["TrendForce"]["category"] == "industry_supply"


def test_guru_twitter_accounts_strips_at_and_skips_rss_only():
    accts = guru_twitter_accounts(SOURCES)
    handles = [a["handle"] for a in accts]
    assert handles == ["ilyasut", "tri_dao", "dylan522p"]  # TrendForce has no handle
    ilya = accts[0]
    assert ilya["note"] == "少而精"
    assert ilya["category"] == "research"


def test_guru_rss_feeds_deduped():
    doubled = {"gurus": {
        "a": [{"name": "x", "rss": "https://f/1"}],
        "b": [{"name": "y", "rss": "https://f/1"}, {"name": "z", "rss": "https://f/2"}],
    }}
    assert guru_rss_feeds(doubled) == ["https://f/1", "https://f/2"]


def test_guru_feed_meta_carries_lens_and_category():
    meta = guru_feed_meta(SOURCES)
    tf = meta["https://www.trendforce.com/news/feed/"]
    assert tf["name"] == "TrendForce"
    assert tf["lens"] == "報價數據為主"
    assert tf["category"] == "industry_supply"


def test_guru_author_names_deduped_case_insensitive():
    dup = {"gurus": {"r": [
        {"handle": "a", "arxiv_names": ["Tri Dao"]},
        {"handle": "b", "arxiv_names": ["tri dao", "Ilya Sutskever"]},
    ]}}
    assert guru_author_names(dup) == ["Tri Dao", "Ilya Sutskever"]


def test_default_sources_roster_is_wellformed():
    entries = guru_entries(DEFAULT_SOURCES)
    assert len(entries) >= 20
    for e in entries:
        assert e.get("handle") or e.get("rss") or e.get("name")
        assert e["category"] in GURU_CATEGORY_LABELS
        assert e.get("lens"), f"{e.get('name') or e.get('handle')} missing lens"
    # Karpathy is the methodology anchor and must be present.
    assert any(e.get("handle") == "karpathy" for e in entries)


def test_load_sources_explicit_path(tmp_path):
    p = tmp_path / "radar.yaml"
    p.write_text("twitter_accounts: [onlyme]\n", encoding="utf-8")
    sources = load_sources(p)
    assert sources["twitter_accounts"] == ["onlyme"]
    # Defaults merged in for keys the file doesn't set.
    assert "gurus" in sources


def test_load_sources_creates_file_at_explicit_path(tmp_path):
    p = tmp_path / "sub" / "radar.yaml"
    sources = load_sources(p)
    assert p.exists()
    assert "gurus" in sources


def test_build_digest_groups_by_guru_category():
    when = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    t1 = Item(source="twitter:@ilyasut", kind="tweet", title="", url="",
              text="compute is destiny", score=10,
              extra={"guru_category": "research", "lens": "少而精"})
    t2 = Item(source="twitter:@aleabitoreddit", kind="tweet", title="", url="",
              text="HBM bottleneck take", score=99, extra={})
    md = build_digest({"tweet": [t1, t2], "web": [], "rss": [], "trend": []}, {}, when)
    assert "### 自選帳號" in md
    assert "### 研究派" in md
    # Uncategorized bucket renders before roster categories.
    assert md.index("### 自選帳號") < md.index("### 研究派")
    assert "怎么读" in md


def test_build_digest_flat_when_no_categories():
    when = datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)
    t = Item(source="twitter:@x", kind="tweet", title="", url="", text="hello ai", score=1)
    md = build_digest({"tweet": [t], "web": [], "rss": [], "trend": []}, {}, when)
    assert "###" not in md.split("## 🐦")[1].split("##")[0]
