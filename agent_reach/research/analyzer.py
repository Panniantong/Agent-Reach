# -*- coding: utf-8 -*-
"""Paper quality scoring, ranking, and multi-source aggregation.

When an AI agent asks "find me the best papers on speech recognition",
this module:
  1. Searches arXiv + Semantic Scholar in parallel for the topic.
  2. Merges & deduplicates results.
  3. Scores each paper on quality signals (citations, venue, recency).
  4. Returns a ranked, analyzed result set ready for agent consumption.

Design: pure functions with no side effects. Does NOT import channel
modules at the top level — they are loaded lazily inside research_topic().
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple


# ------------------------------------------------------------------ #
# Data types
# ------------------------------------------------------------------ #

@dataclass
class PaperQuality:
    """Quality signals for a single paper."""

    citation_score: float = 0.0       # 0-1, normalized by field max
    venue_score: float = 0.0          # 0-1, top venues score high
    recency_score: float = 0.0        # 0-1, newer = higher (decays over 5 years)
    openness_score: float = 0.0       # 0-1, open-access bonus
    overall: float = 0.0              # weighted composite

    citation_count: int = 0
    influential_citations: int = 0
    venue: str = ""
    year: int = 0
    has_open_access: bool = False
    rating: str = ""  # "excellent" / "good" / "ok" / "unknown"


@dataclass
class ResearchResult:
    """A ranked paper with quality signals and source info."""

    title: str
    authors: List[str]
    abstract: str
    year: int
    url: str
    pdf_url: str
    source: str  # "arxiv" / "semantic_scholar" / "both"

    citation_count: int = 0
    influential_citations: int = 0
    venue: str = ""
    fields_of_study: List[str] = field(default_factory=list)
    doi: str = ""
    tldr: str = ""  # S2 TL;DR summary

    quality: Optional[PaperQuality] = None

    arxiv_id: str = ""
    s2_id: str = ""

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract[:500] if self.abstract else "",
            "year": self.year,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "source": self.source,
            "citation_count": self.citation_count,
            "influential_citations": self.influential_citations,
            "venue": self.venue,
            "fields_of_study": self.fields_of_study,
            "doi": self.doi,
            "tldr": self.tldr,
        }
        if self.quality:
            d["quality"] = {
                "rating": self.quality.rating,
                "overall": round(self.quality.overall, 2),
                "citation_score": round(self.quality.citation_score, 2),
                "venue_score": round(self.quality.venue_score, 2),
                "recency_score": round(self.quality.recency_score, 2),
            }
        return d

    def __hash__(self):
        return hash(self.title.lower())


# ------------------------------------------------------------------ #
# Venue ranking — well-known CS conferences/journals
# ------------------------------------------------------------------ #

# Tier 1: top conferences (score 1.0)
_TIER1_CONFERENCES = frozenset({
    "aaai", "ijcai", "neurips", "icml", "iclr", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "colt", "uai", "aistats", "www",
    "sigmod", "vldb", "kdd", "sigir", "wsdm", "recsys",
    "sosp", "osdi", "nsdi", "sigcomm", "mobicom", "sensys",
    "isca", "micro", "hpca", "asplos", "pldi", "popl",
    "ccs", "s&p", "usenix security", "ndss",
    "chi", "ubicomp", "cscw",
    "siggraph",
})

# Tier 2: good venues (score 0.7)
_TIER2_CONFERENCES = frozenset({
    "icassp", "interspeech", "coling", "conll", "eacl", "emnlp",
    "icdm", "cikm", "ecml", "pkdd", "pakdd",
    "icra", "iros", "rss",
    "issta", "icse", "fse", "ase",
    "nsdi", "fast", "eurosys", "cloud",
    "wacv", "bmvc", "3dv",
})

# Tier 3: journals (score 0.6)
_TIER1_JOURNALS = frozenset({
    "nature", "science", "cell", "pnas",
    "jmlr", "ieee transactions on pattern analysis and machine intelligence",
    "ieee transactions on neural networks and learning systems",
    "ieee transactions on information theory",
    "journal of the acm", "communications of the acm",
    "ieee transactions on software engineering",
    "ieee transactions on signal processing",
    "computer vision and image understanding",
    "artificial intelligence",
})


def _score_venue(venue_str: str, journal_str: str = "") -> float:
    """Score a venue from 0-1 based on normalized venue/journal name."""
    name = (venue_str or journal_str or "").strip().lower()

    # Normalize: strip "proceedings of", "international conference on", etc.
    for prefix in (
        "proceedings of the ", "proceedings of ", "international conference on ",
        "ieee/acm ", "ieee ", "acm ",
    ):
        if name.startswith(prefix):
            name = name[len(prefix):]

    # Check tier 1
    for v in _TIER1_CONFERENCES:
        if v in name:
            return 1.0
    for j in _TIER1_JOURNALS:
        if j in name:
            return 0.9

    # Check tier 2
    for v in _TIER2_CONFERENCES:
        if v in name:
            return 0.7

    # Heuristics
    if "transaction" in name or "journal" in name:
        return 0.4
    if "conference" in name or "symposium" in name or "workshop" in name:
        return 0.3
    if "arxiv" in name or "preprint" in name:
        return 0.1

    return 0.2  # unknown venue — slight credit for having one


def _normalize_citation_score(citations: int, field_max: int = 500) -> float:
    """Map raw citation count to 0-1, capped at field_max."""
    if citations <= 0:
        return 0.0
    return min(1.0, citations / field_max)


def _score_recency(year: int, current_year: int | None = None) -> float:
    """Score recency: 1.0 for current year, decaying over 5 years."""
    if not year:
        return 0.3  # unknown year — neutral
    cy = current_year or datetime.now().year
    age = max(0, cy - year)
    if age == 0:
        return 1.0
    if age == 1:
        return 0.9
    if age == 2:
        return 0.7
    if age == 3:
        return 0.5
    if age <= 5:
        return 0.3
    return 0.1  # >5 years = only relevant if highly cited


def _rating(overall: float) -> str:
    if overall >= 0.70:
        return "excellent"
    if overall >= 0.45:
        return "good"
    if overall >= 0.25:
        return "ok"
    return "unknown"


# ------------------------------------------------------------------ #
# Quality scoring
# ------------------------------------------------------------------ #

def score_paper(
    citation_count: int = 0,
    influential_citations: int = 0,
    venue: str = "",
    journal: str = "",
    year: int = 0,
    has_open_access: bool = False,
    weights: Tuple[float, float, float, float] = (0.40, 0.30, 0.20, 0.10),
) -> PaperQuality:
    """Compute quality scores for a paper.

    Args:
        citation_count: Total citations.
        influential_citations: Influential citations (from S2).
        venue: Conference/workshop name.
        journal: Journal name.
        year: Publication year.
        has_open_access: Whether open-access PDF is available.
        weights: (citation, venue, recency, openness) weights.

    Returns:
        PaperQuality with normalized scores and composite rating.
    """
    w_cite, w_venue, w_recency, w_open = weights

    # Citation: blend raw citations + influential citations
    raw_score = _normalize_citation_score(citation_count, 500)
    inf_score = _normalize_citation_score(influential_citations, 100)
    citation_score = 0.6 * raw_score + 0.4 * inf_score

    # Venue
    venue_score = _score_venue(venue, journal)

    # Recency
    recency_score = _score_recency(year)

    # Openness
    openness_score = 1.0 if has_open_access else 0.0

    # Composite
    overall = (
        w_cite * citation_score
        + w_venue * venue_score
        + w_recency * recency_score
        + w_open * openness_score
    )

    return PaperQuality(
        citation_score=round(citation_score, 2),
        venue_score=round(venue_score, 2),
        recency_score=round(recency_score, 2),
        openness_score=openness_score,
        overall=round(overall, 3),
        citation_count=citation_count,
        influential_citations=influential_citations,
        venue=venue or journal,
        year=year,
        has_open_access=has_open_access,
        rating=_rating(overall),
    )


# ------------------------------------------------------------------ #
# Deduplication
# ------------------------------------------------------------------ #

def _clean_title(title: str) -> str:
    """Normalize a title for dedup comparison."""
    t = title.lower().strip()
    # Remove trailing punctuation
    t = re.sub(r"[\.\s]+$", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t)
    return t


def _titles_match(t1: str, t2: str) -> bool:
    """Check if two titles likely refer to the same paper."""
    a = _clean_title(t1)
    b = _clean_title(t2)
    if a == b:
        return True
    # Fuzzy: if one contains the other and the shorter is >60% of longer
    if len(a) > len(b):
        a, b = b, a
    if len(a) >= 20 and a in b:
        return len(a) / len(b) >= 0.6
    return False


# ------------------------------------------------------------------ #
# Main research entry point
# ------------------------------------------------------------------ #

def research_topic(
    topic: str,
    max_results: int = 15,
    year: str = "",
    fields_of_study: str = "",
    config=None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> List[ResearchResult]:
    """Search for the best papers on a topic across multiple sources.

    This is the main entry point for research queries. It:
      1. Searches arXiv + Semantic Scholar in sequence.
      2. Merges & deduplicates results.
      3. Scores each paper on quality signals.
      4. Returns a ranked list.

    Args:
        topic: Research topic, e.g. "speech recognition transformer".
        max_results: Max papers to return after merging.
        year: Year range filter, e.g. "2022-2025".
        fields_of_study: Comma-separated, e.g. "Computer Science".
        config: Optional Config instance.
        on_progress: Optional callback for progress messages.

    Returns:
        Ranked list of ResearchResult, best first.
    """
    all_papers: List[ResearchResult] = []

    # --- Source 1: Semantic Scholar (richer metadata, citations, TLDR) ---
    if on_progress:
        on_progress(f"Searching Semantic Scholar for '{topic}'...")
    try:
        from agent_reach.channels.semantic_scholar import search_semantic_scholar

        api_key = config.get("semantic_scholar_api_key") if config else ""
        s2_papers = search_semantic_scholar(
            topic, limit=max_results, year=year, fields_of_study=fields_of_study, api_key=api_key,
        )
        for p in s2_papers:
            all_papers.append(ResearchResult(
                title=p.title,
                authors=[a.name for a in p.authors],
                abstract=p.abstract,
                year=p.year,
                url=p.url,
                pdf_url=p.open_access_pdf,
                source="semantic_scholar",
                citation_count=p.citation_count,
                influential_citations=p.influential_citation_count,
                venue=p.venue or p.journal,
                fields_of_study=p.fields_of_study,
                doi=p.doi,
                tldr=p.tldr,
                arxiv_id=p.arxiv_id,
                s2_id=p.paper_id,
            ))
        if on_progress:
            on_progress(f"  Semantic Scholar: {len(s2_papers)} papers found")
    except Exception as e:
        if on_progress:
            on_progress(f"  Semantic Scholar: skipped ({e})")

    # --- Source 2: arXiv ---
    if on_progress:
        on_progress(f"Searching arXiv for '{topic}'...")
    try:
        from agent_reach.channels.arxiv import search_arxiv

        arxiv_papers = search_arxiv(topic, max_results=max_results)
        for p in arxiv_papers:
            all_papers.append(ResearchResult(
                title=p.title,
                authors=p.authors,
                abstract=p.abstract,
                year=_extract_year(p.published),
                url=p.abs_url,
                pdf_url=p.pdf_url,
                source="arxiv",
                citation_count=0,  # arXiv itself has no citation data
                venue=p.comment or "",  # "Accepted at ICML 2025" etc.
                fields_of_study=p.categories,
                doi=p.doi,
                arxiv_id=p.arxiv_id,
            ))
        if on_progress:
            on_progress(f"  arXiv: {len(arxiv_papers)} papers found")
    except Exception as e:
        if on_progress:
            on_progress(f"  arXiv: skipped ({e})")

    # --- Merge & deduplicate ---
    if on_progress:
        on_progress(f"Merging and deduplicating {len(all_papers)} papers...")

    merged = _merge_duplicates(all_papers)

    # --- Score & rank ---
    if on_progress:
        on_progress(f"Scoring and ranking {len(merged)} unique papers...")

    ranked = rank_papers(merged)

    # ---- Brief pause between searches (polite API use) ----
    time.sleep(0.5)

    return ranked[:max_results]


def _extract_year(date_str: str) -> int:
    """Extract year from ISO date string like '2023-05-15T14:30:00Z'."""
    if not date_str:
        return 0
    try:
        return int(date_str[:4])
    except (ValueError, IndexError):
        return 0


def _merge_duplicates(papers: List[ResearchResult]) -> List[ResearchResult]:
    """Merge duplicate papers across sources.

    When the same paper appears in both arXiv and Semantic Scholar,
    we combine metadata: S2 contributes citation/venue data, arXiv
    contributes the PDF link if S2 doesn't have one.
    """
    merged: List[ResearchResult] = []
    seen_indices: Dict[str, int] = {}  # normalized title → index in merged

    for p in papers:
        norm = _clean_title(p.title)
        if norm in seen_indices:
            # Duplicate — enrich the existing entry
            existing = merged[seen_indices[norm]]
            existing.source = "both"
            if not existing.citation_count and p.citation_count:
                existing.citation_count = p.citation_count
                existing.influential_citations = p.influential_citations
            if not existing.venue and p.venue:
                existing.venue = p.venue
            if not existing.tldr and p.tldr:
                existing.tldr = p.tldr
            if not existing.pdf_url and p.pdf_url:
                existing.pdf_url = p.pdf_url
            if not existing.doi and p.doi:
                existing.doi = p.doi
            if not existing.year and p.year:
                existing.year = p.year
            if not existing.fields_of_study and p.fields_of_study:
                existing.fields_of_study = p.fields_of_study
            if not existing.s2_id and p.s2_id:
                existing.s2_id = p.s2_id
            if not existing.arxiv_id and p.arxiv_id:
                existing.arxiv_id = p.arxiv_id
            continue

        # Check fuzzy match against all existing (± it's in seen_indices already)
        matched = False
        for i, existing in enumerate(merged):
            if _titles_match(norm, _clean_title(existing.title)):
                existing.source = "both"
                if not existing.citation_count and p.citation_count:
                    existing.citation_count = p.citation_count
                if not existing.venue and p.venue:
                    existing.venue = p.venue
                if not existing.pdf_url and p.pdf_url:
                    existing.pdf_url = p.pdf_url
                if not existing.year and p.year:
                    existing.year = p.year
                seen_indices[norm] = i
                matched = True
                break

        if not matched:
            seen_indices[norm] = len(merged)
            merged.append(p)

    return merged


def rank_papers(
    papers: List[ResearchResult],
    citation_weight: float = 0.40,
    venue_weight: float = 0.30,
    recency_weight: float = 0.20,
    openness_weight: float = 0.10,
) -> List[ResearchResult]:
    """Score and rank papers by quality signals.

    Weights can be tuned by the caller:
      - citation_weight: emphasis on citation count (default 0.40)
      - venue_weight: emphasis on venue prestige (default 0.30)
      - recency_weight: emphasis on recency (default 0.20)
      - openness_weight: emphasis on open-access availability (default 0.10)

    For "classic paper" searches, increase citation_weight.
    For "latest advances", increase recency_weight.
    """
    weights = (citation_weight, venue_weight, recency_weight, openness_weight)

    for p in papers:
        p.quality = score_paper(
            citation_count=p.citation_count,
            influential_citations=p.influential_citations,
            venue=p.venue,
            year=p.year,
            has_open_access=bool(p.pdf_url),
            weights=weights,
        )

    # Sort by overall score descending
    papers.sort(key=lambda p: p.quality.overall if p.quality else 0.0, reverse=True)
    return papers


def analyze_paper(title: str, abstract: str = "", config=None) -> dict:
    """Provide a structured analysis of a single paper.

    This is a lightweight utility that enriches a paper with S2 data
    and provides a quality assessment. For full paper content analysis,
    agents should use the URL + Jina Reader or read the PDF directly.

    Args:
        title: Paper title.
        abstract: Paper abstract (optional, for additional context).
        config: Optional Config instance.

    Returns:
        Dict with enriched metadata and quality assessment.
    """
    result = {"title": title, "found": False}

    # Try Semantic Scholar lookup by title
    try:
        from agent_reach.channels.semantic_scholar import search_semantic_scholar

        api_key = config.get("semantic_scholar_api_key") if config else ""
        papers = search_semantic_scholar(title, limit=1, api_key=api_key)
        if papers:
            p = papers[0]
            quality = score_paper(
                citation_count=p.citation_count,
                influential_citations=p.influential_citation_count,
                venue=p.venue or p.journal,
                year=p.year,
                has_open_access=bool(p.open_access_pdf),
            )
            result.update({
                "found": True,
                "paper_id": p.paper_id,
                "title": p.title,
                "authors": [a.name for a in p.authors],
                "year": p.year,
                "citation_count": p.citation_count,
                "influential_citations": p.influential_citation_count,
                "venue": p.venue or p.journal,
                "fields_of_study": p.fields_of_study,
                "tldr": p.tldr,
                "url": p.url,
                "open_access_pdf": p.open_access_pdf,
                "quality": {
                    "rating": quality.rating,
                    "overall": quality.overall,
                    "citation_score": quality.citation_score,
                    "venue_score": quality.venue_score,
                    "recency_score": quality.recency_score,
                },
            })
    except Exception:
        pass

    # Fallback: try arXiv
    if not result["found"]:
        try:
            from agent_reach.channels.arxiv import search_arxiv

            papers = search_arxiv(title, max_results=1)
            if papers:
                p = papers[0]
                yr = _extract_year(p.published)
                quality = score_paper(venue=p.comment, year=yr)
                result.update({
                    "found": True,
                    "title": p.title,
                    "authors": p.authors,
                    "year": yr,
                    "abstract": p.abstract,
                    "venue": p.comment,
                    "url": p.abs_url,
                    "pdf_url": p.pdf_url,
                    "arxiv_id": p.arxiv_id,
                    "doi": p.doi,
                    "quality": {
                        "rating": quality.rating,
                        "overall": quality.overall,
                        "venue_score": quality.venue_score,
                        "recency_score": quality.recency_score,
                    },
                })
        except Exception:
            pass

    return result
