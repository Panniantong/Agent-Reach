# -*- coding: utf-8 -*-
"""Per-topic industry wiki knowledge base (Karpathy-KB style, human-gated).

Mirrors the backfill→distill→review flow: ``run_wiki_update`` drafts a new
version of each topic's wiki page from today's collected papers + deep-dive
reports (LLM merge-rewrite of the narrative sections), writes the draft to
``RADAR_DIR/wiki/drafts/`` (never committed), and a human promotes it over
the committed page under ``agent_reach/knowledge/wiki/`` — git diff is the
review gate.

Two update mechanisms, deliberately split:
- Narrative sections (全景圖/核心技術主題/精要規則/近期動態): LLM full-page
  merge with hard caps in the prompt — synthesis with bounded growth.
- 里程碑論文索引: code-managed append list (``_merge_paper_index``, pure,
  deterministic, capped) — the LLM is told to leave it alone.

Without an API key a PENDING scaffold is written (same philosophy as the
deep-dive path) so an interactive Claude can complete the draft.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import RADAR_DIR, Item, load_sources

WIKI_DRAFTS_DIR = RADAR_DIR / "wiki" / "drafts"
WIKI_PAGES_DIR = Path(__file__).parent / "knowledge" / "wiki"

PAPER_INDEX_HEADING = "## 里程碑論文索引"

WIKI_MERGE_SYSTEM = """你是產業 wiki 維護者。給你「現行 wiki 頁」與「今日新材料」（arXiv 論文摘要與深讀報告），輸出**完整的新版 wiki 頁** markdown（繁體中文、台灣用語），結構嚴格保持：

# <主題> 產業 Wiki
> 最後更新 <今日日期> · 由 radar-wiki 起草、人工審核後 commit
## 全景圖
- 3-6 段內講清楚該領域現況與大趨勢；只在新材料真的改變圖景時修改。
## 核心技術主題
- 每個主題小節：現況 / 代表論文 / 工程與投資含義；同類合併，不重複。
## 精要規則
- 7-10 條 terse、無事實內容的行動規則（不得含公司名/數字/日期，只留可遷移的判讀方法）。
## 近期動態
- 帶日期條目，**最多 30 條**；新條目在上，超過上限刪最舊。
## 里程碑論文索引
- 此節現有內容**原樣保留輸出，不要新增或刪改**（由程式碼維護）。

硬性要求：每個新增敘述都要能在材料中找到根據；材料裡沒有的不要編；現行頁中沒被新材料推翻的內容要保留。輸出只有 wiki 頁本身，無前後說明。"""


# ── page access ───────────────────────────────────────────────────────────


def load_wiki_page(topic: str) -> str:
    """Committed wiki page for a topic; empty string when absent."""
    from agent_reach.knowledge import load_knowledge

    return load_knowledge(f"wiki/{topic}")


def topic_label(topic: str, sources: Optional[dict] = None) -> str:
    spec = ((sources or {}).get("topics") or {}).get(topic) or {}
    return str(spec.get("label") or topic)


# ── material assembly (pure) ──────────────────────────────────────────────


def assemble_wiki_material(
    topic: str,
    papers: list[Item],
    deepdives: list[str],
    max_chars: int = 40000,
) -> str:
    """Compact today's topic-relevant papers + deep-dive reports for the LLM."""
    lines: list[str] = [f"## 今日 arXiv 論文（主題: {topic}）"]
    for it in sorted(papers, key=lambda i: i.score, reverse=True):
        why = "、".join((it.extra.get("why") or [])[:4])
        lines.append(f"- [{it.extra.get('arxiv_id', '?')}] {it.title} · score {it.score:g}")
        if why:
            lines.append(f"  - 入選原因: {why}")
        if it.text:
            lines.append(f"  - 摘要: {' '.join(it.text.split())[:400]}")
    if deepdives:
        lines.append("")
        lines.append("## 今日深讀報告")
        for text in deepdives:
            lines.append("")
            lines.append(text)
    return "\n".join(lines)[:max_chars]


def _merge_paper_index(
    page: str,
    papers: list[Item],
    when: Optional[datetime] = None,
    cap: int = 100,
) -> str:
    """Deterministically merge papers into the 里程碑論文索引 section.

    Keeps existing bullet rows, appends rows for papers not yet indexed
    (deduped by arXiv id), trims to the newest ``cap`` rows. Pure — the LLM
    never touches this section.
    """
    when = when or datetime.now(timezone.utc).astimezone()
    m = re.search(
        rf"^{re.escape(PAPER_INDEX_HEADING)}\s*$(.*?)(?=^## |\Z)",
        page,
        re.MULTILINE | re.DOTALL,
    )
    existing = [
        ln for ln in (m.group(1).splitlines() if m else []) if ln.strip().startswith("- ")
    ]
    seen_ids = set(re.findall(r"\[([\w.\-/]+)\]\(https://arxiv\.org/abs/", "\n".join(existing)))
    new_rows = []
    for it in sorted(papers, key=lambda i: i.score, reverse=True):
        aid = str(it.extra.get("arxiv_id") or "").strip()
        if not aid or aid in seen_ids:
            continue
        seen_ids.add(aid)
        new_rows.append(f"- {when:%Y-%m-%d} · [{aid}]({it.url}) · {it.title} · score {it.score:g}")
    rows = (existing + new_rows)[-cap:]
    section = PAPER_INDEX_HEADING + "\n\n" + "\n".join(rows) + "\n"
    if m:
        return page[: m.start()] + section + page[m.end():]
    return page.rstrip() + "\n\n" + section


# ── LLM draft ─────────────────────────────────────────────────────────────


def draft_wiki_update(
    topic: str,
    material: str,
    current_page: str,
    config: Optional[Config] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """LLM merge-rewrite of the wiki page. None without an API key."""
    from agent_reach.radar_report import DEFAULT_MENTOR_MODEL, _panel_chat

    config = config or Config()
    model = model or config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL
    user = (
        f"【主題】{topic}\n\n"
        f"【現行 wiki 頁】\n{current_page or '（空頁 — 這是第一次更新，請按結構起草）'}\n\n"
        f"【今日新材料】\n{material}"
    )
    return _panel_chat("anthropic", model, WIKI_MERGE_SYSTEM, user, config)


def _pending_scaffold(topic: str, material: str, current_page: str, when: datetime) -> str:
    """Draft scaffold for an interactive Claude to complete (no API key path)."""
    return (
        f"---\nstatus: PENDING\ntopic: {topic}\ndate: {when:%Y-%m-%d}\n---\n\n"
        f"<!-- 給互動式 Claude：依下方 system 模板，把「現行頁 + 新材料」合併成完整新版 wiki 頁，"
        f"移除 PENDING frontmatter -->\n\n"
        f"## 合併模板\n\n{WIKI_MERGE_SYSTEM}\n\n"
        f"## 現行 wiki 頁\n\n{current_page or '（空頁）'}\n\n"
        f"## 今日新材料\n\n{material}\n"
    )


# ── orchestration ─────────────────────────────────────────────────────────


def _load_all_papers(sources: dict, config: Optional[Config], when: datetime) -> list[Item]:
    """Today's papers from the run_radar sidecar; fall back to a fresh collect."""
    sidecar = RADAR_DIR / "latest-items.json"
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if data.get("date") == f"{when:%Y-%m-%d}":
                return [Item(**d) for d in (data.get("items") or {}).get("paper", [])]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"latest-items.json unreadable, re-collecting: {e}")
    from agent_reach.radar_arxiv import collect_arxiv

    return collect_arxiv(sources, config)


def _today_deepdives(topic: str, when: datetime, max_each: int = 8000) -> list[str]:
    """Completed (non-PENDING) deep-dive report texts for this topic, today."""
    from agent_reach.radar_arxiv import DEEPDIVE_DIR

    idx = DEEPDIVE_DIR / f"{when:%Y-%m-%d}-index.json"
    if not idx.exists():
        return []
    try:
        entries = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for e in entries:
        if topic and e.get("topic") != topic:
            continue
        p = DEEPDIVE_DIR / str(e.get("file") or "")
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            if "status: PENDING" not in text:
                out.append(text[:max_each])
    return out


def _topic_papers(all_papers: list[Item], topic: str) -> list[Item]:
    return [
        p for p in all_papers
        if p.extra.get("topic") == topic or topic in (p.extra.get("topics") or [])
    ]


def run_wiki_update(
    topics: Optional[list[str]] = None,
    sources: Optional[dict] = None,
    config: Optional[Config] = None,
    when: Optional[datetime] = None,
) -> dict:
    """Draft a wiki update per topic. Returns {topic: draft_path | None}.

    Per-topic failures never abort the run; topics with no new material are
    skipped (None). ``None`` topics = every committed wiki page plus every
    configured topic.
    """
    from agent_reach.knowledge import list_wiki_topics

    config = config or Config()
    when = when or datetime.now(timezone.utc).astimezone()
    sources = sources or load_sources()
    wanted = list(topics) if topics else sorted(
        set(list_wiki_topics()) | set(sources.get("topics") or {})
    )
    all_papers = _load_all_papers(sources, config, when)
    WIKI_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Optional[str]] = {}
    for topic in wanted:
        try:
            papers = _topic_papers(all_papers, topic)
            deepdives = _today_deepdives(topic, when)
            if not papers and not deepdives:
                logger.info(f"wiki[{topic}]: no new material today, skipping")
                results[topic] = None
                continue
            current = load_wiki_page(topic)
            material = assemble_wiki_material(topic, papers, deepdives)
            draft = draft_wiki_update(topic, material, current, config)
            if draft:
                page = _merge_paper_index(draft, papers, when=when)
            else:
                page = _pending_scaffold(topic, material, current, when)
            out = WIKI_DRAFTS_DIR / f"{when:%Y-%m-%d}-{topic}.md"
            out.write_text(page, encoding="utf-8")
            logger.info(
                f"wiki[{topic}] {'drafted' if draft else 'PENDING scaffold'} → {out}"
            )
            results[topic] = str(out)
        except Exception as e:  # noqa: BLE001 - one topic failing must not kill the run
            logger.warning(f"wiki update failed for {topic}: {e}")
            results[topic] = None
    return results


def promote_draft(topic: str) -> Path:
    """Copy the newest non-PENDING draft over the committed page.

    The human gate stays git: review ``git diff`` before committing.
    """
    drafts = sorted(WIKI_DRAFTS_DIR.glob(f"*-{topic}.md"))
    if not drafts:
        raise FileNotFoundError(f"沒有 {topic} 的 draft — 先跑 agent-reach radar-wiki update")
    latest = drafts[-1]
    text = latest.read_text(encoding="utf-8")
    if "status: PENDING" in text:
        raise ValueError(f"{latest.name} 仍是 PENDING 鷹架 — 先讓 Claude 補完再 promote")
    WIKI_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    page = WIKI_PAGES_DIR / f"{topic}.md"
    page.write_text(text, encoding="utf-8")
    return page


def wiki_status() -> list[dict]:
    """Per-topic: committed page state + newest draft, for CLI/UI display."""
    from agent_reach.knowledge import list_wiki_topics

    out: list[dict] = []
    drafts = list(WIKI_DRAFTS_DIR.glob("*.md")) if WIKI_DRAFTS_DIR.is_dir() else []
    for topic in list_wiki_topics():
        page = load_wiki_page(topic)
        updated = ""
        m = re.search(r"最後更新\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", page)
        if m:
            updated = m.group(1)
        mine = sorted(d.name for d in drafts if d.name.endswith(f"-{topic}.md"))
        out.append({
            "topic": topic,
            "page_exists": bool(page),
            "last_updated": updated,
            "latest_draft": mine[-1] if mine else "",
        })
    return out
