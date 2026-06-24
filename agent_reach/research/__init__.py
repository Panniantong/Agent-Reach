# -*- coding: utf-8 -*-
"""Research assistant — multi-source paper search, ranking, analysis, and PDF reading.

Aggregates arXiv + Semantic Scholar + OpenAlex + PubMed + DBLP + CORE + Papers With Code
to find and rank papers by quality signals (citations, venue, recency, etc.).

Also provides PDF download and text extraction for deep reading.
"""

from agent_reach.research.analyzer import (
    PaperQuality,
    ResearchResult,
    analyze_paper,
    rank_papers,
    research_topic,
)

from agent_reach.research.pdf_reader import (
    download_and_read,
    download_pdf,
    extract_text,
    find_pdf_url,
)

__all__ = [
    # Analyzer
    "ResearchResult",
    "PaperQuality",
    "research_topic",
    "rank_papers",
    "analyze_paper",
    # PDF Reader
    "download_and_read",
    "download_pdf",
    "extract_text",
    "find_pdf_url",
]
