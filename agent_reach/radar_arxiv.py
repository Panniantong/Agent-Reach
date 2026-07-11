# -*- coding: utf-8 -*-
"""Two-tier arXiv collector for the radar.

Tier 1 — daily abstract scan: one Atom API query across the configured
categories, scored by weighted keywords + guru-author boost + org mentions,
ranked into the digest (``kind="paper"``).

Tier 2 — deep dive: the top-N papers get their full text pulled (arXiv HTML
render, ar5iv fallback, both via Jina Reader like the web channel) and
distilled into a standalone Traditional-Chinese report by the main mentor
model. Without an API key a PENDING scaffold (material + template) is
written so an interactive Claude can complete it — same fallback philosophy
as the mentor in radar_report.

Glue-layer notes: the arXiv Atom API is public and feedparser-parseable —
no new dependency, no scraping. Collectors never raise.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import RADAR_DIR, Item, _parse_feed, guru_author_names

ARXIV_API = "http://export.arxiv.org/api/query"
DEEPDIVE_DIR = RADAR_DIR / "deepdive"

# arXiv API etiquette asks ≥3s between requests. Module-level so tests zero it.
_ARXIV_PACING_S = 3.0

DEFAULT_MENTOR_MODEL = "claude-fable-5"

DEEPDIVE_SYSTEM = """你是資深 AI 系統研究員兼投研顧問。深讀下面這篇 arXiv 論文，用「繁體中文（台灣用語）」寫一份深讀報告，markdown 結構如下：

# <論文標題>（<arXiv ID>）
## TL;DR
- 3 句話說清楚：做了什麼、憑什麼有效、數字證據。
## 方法核心
- 關鍵機制與設計選擇，講因果不講流水帳。
## 與現有架構的差異
- 對比目前主流做法（訓練/推理/系統層），差在哪、為什麼重要。
## 工程與供應鏈含義
- 對算力/記憶體/互連/功耗的影響；哪些硬體環節受益或承壓。
## 對投資敘事的影響
- 若結論成立，哪些公司/環節的敘事被強化或削弱（觀點標註為推論，非投資建議）。
## 局限與待驗證
- 實驗規模、基線公允性、可復現性疑點。

硬性要求：只根據給你的論文內容寫，數字要能在原文找到；沒把握的寫進「局限與待驗證」。"""


# ── tier 1: abstract scan ─────────────────────────────────────────────────


def _arxiv_query_url(categories: list[str], max_results: int) -> str:
    """Build the Atom API URL: newest submissions across all categories."""
    query = " OR ".join(f"cat:{c}" for c in categories)
    return (
        f"{ARXIV_API}?search_query={quote(query)}"
        f"&sortBy=submittedDate&sortOrder=descending&start=0&max_results={int(max_results)}"
    )


def _arxiv_entry_to_item(entry: dict) -> Optional[Item]:
    """Normalize a feedparser arXiv entry (mirrors _tweet_to_item)."""
    raw_id = entry.get("id") or ""
    m = re.search(r"abs/([^/\s]+?)(v\d+)?$", raw_id)
    arxiv_id = m.group(1) if m else ""
    title = re.sub(r"\s+", " ", entry.get("title") or "").strip()
    if not (arxiv_id and title):
        return None
    summary = re.sub(r"\s+", " ", entry.get("summary") or "").strip()
    authors = [a.get("name", "") for a in entry.get("authors", []) if a.get("name")]
    tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
    return Item(
        source="arxiv",
        kind="paper",
        title=title,
        url=f"https://arxiv.org/abs/{arxiv_id}",
        text=summary[:600],
        author=", ".join(authors),
        score=0.0,
        ts=entry.get("published"),
        extra={
            "arxiv_id": arxiv_id,
            "authors": authors,
            "primary_category": tags[0] if tags else "",
            "comment": re.sub(r"\s+", " ", entry.get("arxiv_comment") or "").strip(),
            "why": [],
        },
    )


def _kw_hits(text: str, kw: str) -> int:
    """Count keyword occurrences; word-boundary for alnum keywords (like _is_on_topic)."""
    kw = kw.lower().strip()
    if not kw:
        return 0
    if kw.replace(" ", "").isalnum():
        return len(re.findall(rf"\b{re.escape(kw)}\b", text))
    return text.count(kw)


def score_paper(
    item: Item,
    kw_weights: dict[str, float],
    guru_names: list[str],
    orgs: list[str],
    author_boost: float = 6.0,
    org_boost: float = 4.0,
) -> float:
    """Score a paper and record the reasons in ``extra["why"]``.

    Keywords: title hits count double, abstract hits single. Guru authors
    and org mentions (best-effort text match — arXiv metadata rarely
    carries affiliations) add flat boosts.
    """
    title = item.title.lower()
    abstract = item.text.lower()
    why: list[str] = []
    score = 0.0

    for kw, weight in (kw_weights or {}).items():
        hits = _kw_hits(title, kw) * 2 + _kw_hits(abstract, kw)
        if hits:
            score += float(weight) * hits
            why.append(f"關鍵字:{kw}")

    authors_lower = {a.lower() for a in item.extra.get("authors", [])}
    for name in guru_names or []:
        if name.lower() in authors_lower:
            score += author_boost
            why.append(f"作者:{name}")

    hay = f"{abstract} {item.extra.get('comment', '').lower()}"
    for org in orgs or []:
        if org.lower() in hay:
            score += org_boost
            why.append(f"機構:{org}")

    item.score = score
    item.extra["why"] = why
    return score


def arxiv_topic_plan(sources: dict) -> list[dict]:
    """Per-topic query plan from ``sources["topics"]``.

    Without ``topics`` this falls back to a single untagged entry built from
    the top-level ``arxiv_categories``/``arxiv_keywords`` — the legacy path
    that older configs and the evolve health fixtures ride (exactly one
    query, no pacing sleep).
    """
    plan: list[dict] = []
    for tid, spec in (sources.get("topics") or {}).items():
        if not isinstance(spec, dict):
            continue
        cats = [str(c) for c in (spec.get("arxiv_categories") or []) if str(c).strip()]
        if not cats:
            continue
        plan.append({
            "topic": str(tid),
            "label": str(spec.get("label") or tid),
            "categories": cats,
            "keywords": spec.get("arxiv_keywords") or {},
        })
    if plan:
        return plan
    cats = sources.get("arxiv_categories") or []
    if not cats:
        return []
    return [{
        "topic": "",
        "label": "",
        "categories": cats,
        "keywords": sources.get("arxiv_keywords") or {},
    }]


def collect_arxiv(sources: dict, config: Config) -> list[Item]:
    """One paced Atom query per topic, scored per-topic, cross-topic deduped.

    Papers get ``extra["topic"]`` (primary = first topic that hit) and
    ``extra["topics"]`` (all topics that hit). The legacy single-query path
    leaves ``topic`` as "". Never raises.
    """
    plan = arxiv_topic_plan(sources)
    if not plan:
        return []
    max_results = int(sources.get("arxiv_max_results", 100))
    gurus = guru_author_names(sources)
    orgs = sources.get("arxiv_orgs") or []
    author_boost = float(sources.get("arxiv_author_boost", 6))
    org_boost = float(sources.get("arxiv_org_boost", 4))
    best: dict[str, Item] = {}  # arxiv_id → highest-scoring copy across topics
    for idx, entry in enumerate(plan):
        if idx:
            time.sleep(_ARXIV_PACING_S)
        url = _arxiv_query_url(entry["categories"], max_results)
        try:
            feed = _parse_feed(url, timeout=30)
        except Exception as e:  # noqa: BLE001 - collector must never abort the run
            logger.warning(f"arXiv fetch failed ({entry['topic'] or 'default'}): {e}")
            continue
        for raw in feed.entries:
            it = _arxiv_entry_to_item(raw)
            if not it:
                continue
            # The scorer IS the relevance gate: unscored papers are off-radar.
            if score_paper(it, entry["keywords"], gurus, orgs, author_boost, org_boost) <= 0:
                continue
            it.extra["topic"] = entry["topic"]
            it.extra["topics"] = [entry["topic"]] if entry["topic"] else []
            aid = it.extra["arxiv_id"]
            prev = best.get(aid)
            if prev is None:
                best[aid] = it
                continue
            hits = prev.extra.get("topics") or []
            if entry["topic"] and entry["topic"] not in hits:
                hits.append(entry["topic"])
            if it.score > prev.score:
                it.extra["topics"] = hits
                best[aid] = it
            else:
                prev.extra["topics"] = hits
    items = list(best.values())
    items.sort(key=lambda i: i.score, reverse=True)
    return items


# ── tier 2: full-text deep dive ───────────────────────────────────────────


def fetch_paper_text(arxiv_id: str, max_chars: int = 30000) -> str:
    """Full text via arXiv's HTML render, ar5iv fallback (both through Jina). Never raises."""
    from agent_reach.channels.web import WebChannel

    web = WebChannel()
    for url in (
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ):
        try:
            text = web.read(url)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"paper text fetch failed ({url}): {e}")
            continue
        if text and len(text.strip()) > 500:
            return text[:max_chars]
    return ""


def distill_paper(
    item: Item,
    fulltext: str,
    config: Optional[Config] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Distill one paper with the main mentor model. None without an API key."""
    config = config or Config()
    key = os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key")
    if not key:
        return None
    model = model or config.get("radar_mentor_model") or DEFAULT_MENTOR_MODEL
    # Topic-tagged papers get that topic's accumulated wiki rules (fact-free
    # methodology only) folded into the system prompt.
    system = DEEPDIVE_SYSTEM
    topic = item.extra.get("topic")
    if topic:
        from agent_reach.knowledge import knowledge_rules

        rules = knowledge_rules(f"wiki/{topic}")
        if rules:
            system = f"{DEEPDIVE_SYSTEM}\n\n【該主題累積的精要規則（僅方法，不含事實）】\n{rules}"
    body = fulltext or item.text
    user = (
        f"【論文】{item.title}（arXiv:{item.extra.get('arxiv_id')}）\n"
        f"【作者】{item.author}\n"
        f"【入選原因】{'、'.join(item.extra.get('why', []))}\n\n"
        f"【論文內容（HTML 轉文字，可能有噪聲）】\n{body}"
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4000,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=300,
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"distill_paper failed for {item.extra.get('arxiv_id')}: {e}")
        return None
    return "".join(b.get("text", "") for b in resp.json().get("content", []))


def _pending_scaffold(item: Item, fulltext: str, when: datetime) -> str:
    """Scaffold for an interactive Claude to complete (no API key path)."""
    return (
        f"---\nstatus: PENDING\narxiv_id: {item.extra.get('arxiv_id')}\n"
        f"date: {when:%Y-%m-%d}\nscore: {item.score}\n---\n\n"
        f"<!-- 給互動式 Claude：依下方 system 模板深讀「論文原文」，把本檔改寫成完整報告並移除 PENDING -->\n\n"
        f"## 深讀模板\n\n{DEEPDIVE_SYSTEM}\n\n"
        f"## 論文\n\n- 標題: {item.title}\n- 作者: {item.author}\n- 連結: {item.url}\n"
        f"- 入選原因: {'、'.join(item.extra.get('why', []))}\n\n"
        f"## 論文原文（節錄）\n\n{fulltext or item.text}\n"
    )


def run_deep_dive(
    papers: list[Item],
    sources: dict,
    config: Optional[Config] = None,
    when: Optional[datetime] = None,
    topic: Optional[str] = None,
) -> list[Path]:
    """Distill the top-N papers into standalone reports; returns written paths.

    ``topic`` narrows the candidate pool to papers tagged with that topic
    (multi-topic collection); None keeps today's behavior.
    """
    config = config or Config()
    when = when or datetime.now(timezone.utc).astimezone()
    top_n = int(sources.get("arxiv_deep_dive_n", 4))
    pool = papers
    if topic:
        pool = [
            p for p in papers
            if p.extra.get("topic") == topic or topic in (p.extra.get("topics") or [])
        ]
    picks = sorted(pool, key=lambda i: i.score, reverse=True)[:top_n]
    if not picks:
        return []
    DEEPDIVE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in picks:
        arxiv_id = item.extra.get("arxiv_id", "unknown")
        path = DEEPDIVE_DIR / f"{when:%Y-%m-%d}-{arxiv_id.replace('/', '_')}.md"
        fulltext = fetch_paper_text(arxiv_id, int(sources.get("arxiv_fulltext_chars", 30000)))
        report = distill_paper(item, fulltext, config)
        path.write_text(report or _pending_scaffold(item, fulltext, when), encoding="utf-8")
        written.append(path)
        logger.info(f"deep dive {'distilled' if report else 'PENDING scaffold'} → {path}")
    index = [f"# 🔬 arXiv 深讀 — {when:%Y-%m-%d}", ""]
    for p, item in zip(written, picks):
        index.append(f"- [{item.title}]({p.name}) · score {item.score:g} · {item.url}")
    (DEEPDIVE_DIR / "latest-index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    # Machine-readable index — wiki/sync/scenarios pick today's reports up here.
    index_json = [
        {
            "file": p.name,
            "arxiv_id": item.extra.get("arxiv_id", ""),
            "topic": item.extra.get("topic", ""),
            "title": item.title,
            "score": item.score,
            "url": item.url,
        }
        for p, item in zip(written, picks)
    ]
    (DEEPDIVE_DIR / f"{when:%Y-%m-%d}-index.json").write_text(
        json.dumps(index_json, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return written
