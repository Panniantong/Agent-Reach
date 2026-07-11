# -*- coding: utf-8 -*-
"""Wiki pipeline tests — pure/offline: LLM and collectors are monkeypatched."""

from datetime import datetime, timezone

import agent_reach.radar_wiki as rw
from agent_reach.knowledge import knowledge_rules, list_wiki_topics
from agent_reach.radar import Item
from agent_reach.radar_wiki import (
    _merge_paper_index,
    assemble_wiki_material,
    promote_draft,
    run_wiki_update,
)

WHEN = datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)


def _paper(aid, title, score, topic="ee"):
    return Item(
        source="arxiv", kind="paper", title=title,
        url=f"https://arxiv.org/abs/{aid}", text="abstract text", score=score,
        extra={"arxiv_id": aid, "topic": topic, "topics": [topic], "why": ["關鍵字:chiplet"]},
    )


PAGE = """# 電子工程 產業 Wiki

> 最後更新 2026-07-01 · 由 radar-wiki 起草

## 全景圖

現況段落。

## 精要規則

- 規則一

## 里程碑論文索引

- 2026-07-01 · [2606.00001](https://arxiv.org/abs/2606.00001) · Old paper · score 5
"""


# ── seed pages / knowledge helpers ─────────────────────────────────────────


def test_seed_pages_registered():
    topics = list_wiki_topics()
    assert {"ai", "ee", "rf", "spacetech", "quantum"} <= set(topics)


def test_knowledge_rules_extracts_wiki_section():
    rules = knowledge_rules("wiki/ee")
    assert rules  # seed placeholder bullet is extractable
    assert "精要規則" not in rules  # heading itself stripped


# ── pure helpers ───────────────────────────────────────────────────────────


def test_assemble_material_bounds_and_content():
    papers = [_paper("2607.1", "Chiplet paper", 9)]
    m = assemble_wiki_material("ee", papers, ["deep dive report text"], max_chars=200)
    assert len(m) <= 200
    m_full = assemble_wiki_material("ee", papers, ["deep dive report text"])
    assert "Chiplet paper" in m_full and "deep dive report text" in m_full


def test_merge_paper_index_appends_and_dedupes():
    papers = [_paper("2607.2", "New paper", 8), _paper("2606.00001", "Old paper", 5)]
    merged = _merge_paper_index(PAGE, papers, when=WHEN)
    section = merged.split("## 里程碑論文索引")[1]
    assert "2607.2" in section
    rows = [ln for ln in section.splitlines() if "2606.00001" in ln]
    assert len(rows) == 1  # deduped by arxiv id
    # Narrative sections untouched.
    assert "現況段落。" in merged and "- 規則一" in merged


def test_merge_paper_index_caps_rows():
    papers = [_paper(f"2607.{i}", f"P{i}", i) for i in range(10)]
    merged = _merge_paper_index(PAGE, papers, when=WHEN, cap=3)
    section = merged.split("## 里程碑論文索引")[1]
    rows = [ln for ln in section.splitlines() if ln.strip().startswith("- ")]
    assert len(rows) == 3


def test_merge_paper_index_creates_missing_section():
    merged = _merge_paper_index("# 頁\n\n## 全景圖\n\n內容\n", [_paper("2607.9", "X", 1)], when=WHEN)
    assert "## 里程碑論文索引" in merged and "2607.9" in merged


# ── orchestration ──────────────────────────────────────────────────────────


def _setup_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(rw, "WIKI_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(rw, "WIKI_PAGES_DIR", tmp_path / "pages")
    monkeypatch.setattr(rw, "_load_all_papers", lambda s, c, w: [_paper("2607.5", "EE paper", 7)])
    monkeypatch.setattr(rw, "_today_deepdives", lambda t, w, max_each=8000: [])


def test_run_wiki_update_llm_path(monkeypatch, tmp_path):
    _setup_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        rw, "draft_wiki_update",
        lambda topic, material, current, config=None, model=None: PAGE,
    )
    results = run_wiki_update(topics=["ee"], sources={}, when=WHEN)
    assert results["ee"]
    body = (tmp_path / "drafts" / "2026-07-11-ee.md").read_text(encoding="utf-8")
    assert "2607.5" in body  # code-managed index merged into the LLM draft
    assert "status: PENDING" not in body


def test_run_wiki_update_pending_path(monkeypatch, tmp_path):
    _setup_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        rw, "draft_wiki_update",
        lambda topic, material, current, config=None, model=None: None,
    )
    results = run_wiki_update(topics=["ee"], sources={}, when=WHEN)
    body = (tmp_path / "drafts" / "2026-07-11-ee.md").read_text(encoding="utf-8")
    assert results["ee"] and "status: PENDING" in body and "EE paper" in body


def test_run_wiki_update_skips_topics_without_material(monkeypatch, tmp_path):
    _setup_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(rw, "_load_all_papers", lambda s, c, w: [])
    results = run_wiki_update(topics=["quantum"], sources={}, when=WHEN)
    assert results == {"quantum": None}


def test_run_wiki_update_never_raises(monkeypatch, tmp_path):
    _setup_dirs(monkeypatch, tmp_path)

    def boom(topic, material, current, config=None, model=None):
        raise RuntimeError("api down")

    monkeypatch.setattr(rw, "draft_wiki_update", boom)
    results = run_wiki_update(topics=["ee"], sources={}, when=WHEN)
    assert results == {"ee": None}


def test_promote_rejects_pending_and_copies_good_draft(monkeypatch, tmp_path):
    monkeypatch.setattr(rw, "WIKI_DRAFTS_DIR", tmp_path / "drafts")
    monkeypatch.setattr(rw, "WIKI_PAGES_DIR", tmp_path / "pages")
    (tmp_path / "drafts").mkdir()
    draft = tmp_path / "drafts" / "2026-07-11-ee.md"

    draft.write_text("---\nstatus: PENDING\n---\n草稿", encoding="utf-8")
    try:
        promote_draft("ee")
        raise AssertionError("PENDING draft must be rejected")
    except ValueError:
        pass

    draft.write_text(PAGE, encoding="utf-8")
    page = promote_draft("ee")
    assert page.read_text(encoding="utf-8") == PAGE
