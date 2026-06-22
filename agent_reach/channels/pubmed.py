# -*- coding: utf-8 -*-
"""PubMed — biomedical literature via NCBI Entrez API. 34M+ papers.

Official API: https://www.ncbi.nlm.nih.gov/books/NBK25501/
Requires an email for identification (NCBI policy). No API key needed
for moderate use (3 req/sec without key, 10 req/sec with key).

Two-step process:
  1. ESearch: query → PMID list
  2. EFetch: PMID list → abstracts + metadata
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

from .base import Channel

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_UA = "agent-reach/1.0"
_TIMEOUT = 30
_EMAIL = "agent-reach@example.com"


@dataclass
class PubMedPaper:
    pmid: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    journal: str = ""
    doi: str = ""
    pmc_id: str = ""
    mesh_terms: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "authors": self.authors,
            "abstract": (self.abstract or "")[:500],
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "pmc_id": self.pmc_id,
            "mesh_terms": self.mesh_terms,
        }


def _esearch(query: str, max_results: int = 20, timeout: int = _TIMEOUT) -> List[str]:
    """Search PubMed and return PMIDs."""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": query,
        "retmax": str(max_results),
        "retmode": "json",
        "sort": "relevance",
        "email": _EMAIL,
        "tool": "agent-reach",
    })
    url = f"{_BASE}/esearch.fcgi?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []


def _efetch(pmids: List[str], timeout: int = _TIMEOUT) -> List[PubMedPaper]:
    """Fetch full records for PMIDs."""
    if not pmids:
        return []
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "email": _EMAIL,
        "tool": "agent-reach",
    })
    url = f"{_BASE}/efetch.fcgi?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []

    papers = []
    for article in root.findall(".//PubmedArticle"):
        try:
            papers.append(_parse_pubmed_article(article))
        except Exception:
            continue
    return papers


def _parse_pubmed_article(article) -> PubMedPaper:
    p = PubMedPaper()

    # PMID
    pmid_el = article.find(".//PMID")
    if pmid_el is not None and pmid_el.text:
        p.pmid = pmid_el.text

    # Article
    art = article.find(".//Article")
    if art is None:
        return p

    # Title
    title_el = art.find(".//ArticleTitle")
    if title_el is not None and title_el.text:
        p.title = title_el.text

    # Abstract
    parts = []
    for abs_el in art.findall(".//AbstractText"):
        label = abs_el.get("Label", "")
        text = abs_el.text or ""
        if label:
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)
        for sub in abs_el:
            if sub.tail:
                parts[-1] += sub.tail
    p.abstract = " ".join(parts)

    # Authors
    for author_el in art.findall(".//Author"):
        last = author_el.findtext("LastName", "")
        fore = author_el.findtext("ForeName", "")
        name = f"{fore} {last}".strip()
        if name:
            p.authors.append(name)

    # Journal
    journal_el = art.find(".//Journal")
    if journal_el is not None:
        p.journal = journal_el.findtext("Title", "") or ""

        # Year
        year_el = journal_el.find(".//PubDate/Year")
        if year_el is not None and year_el.text:
            try:
                p.year = int(year_el.text)
            except ValueError:
                pass

    # DOI
    for eid in article.findall(".//ArticleId"):
        if eid.get("IdType") == "doi":
            p.doi = eid.text or ""

    # PMC ID
    for other in article.findall(".//OtherID"):
        if (other.text or "").startswith("PMC"):
            p.pmc_id = other.text

    # MeSH terms
    for mesh in article.findall(".//MeshHeading"):
        desc = mesh.findtext("DescriptorName", "")
        if desc:
            p.mesh_terms.append(desc)

    return p


def search_pubmed(
    query: str,
    max_results: int = 15,
    timeout: int = _TIMEOUT,
) -> List[PubMedPaper]:
    """Search PubMed and return papers with abstracts."""
    pmids = _esearch(query, max_results=max_results, timeout=timeout)
    if not pmids:
        return []
    return _efetch(pmids, timeout=timeout * 2)


class PubMedChannel(Channel):
    name = "pubmed"
    description = "PubMed 生物医学文献（3400万篇）"
    backends = ["PubMed Entrez API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return "pubmed.ncbi.nlm.nih.gov" in url.lower() or "ncbi.nlm.nih.gov" in url.lower()

    def check(self, config=None):
        """Probe PubMed with a lightweight search."""
        pmids = _esearch("cancer", max_results=1, timeout=10)
        if pmids is not None and len(pmids) >= 0:
            self.active_backend = self.backends[0]
            return "ok", "PubMed Entrez API 可用（3400万篇生物医学论文，免费）"
        self.active_backend = None
        return "warn", "PubMed API 连接失败"

    def search(self, query: str, max_results: int = 15, config=None) -> List[dict]:
        papers = search_pubmed(query, max_results=max_results)
        return [p.to_dict() for p in papers]
