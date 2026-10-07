# -*- coding: utf-8 -*-
"""ArXiv — public API channel for academic paper search and metadata."""

import urllib.error
import urllib.request
from typing import List
from urllib.parse import quote

from agent_reach.channels.base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 15
_MAX_RESPONSE_BYTES = 1024 * 1024
_API_BASE = "https://export.arxiv.org/api/query"


class ArxivRateLimitError(Exception):
    """Raised when the ArXiv API responds HTTP 429 (request rate limit).

    export.arxiv.org allows roughly one request every three seconds;
    consecutive calls without a pause trigger this.
    """


def _quote_query(query: str) -> str:
    """URL-encode a search query for the ArXiv API.

    Spaces become %20 (matching the official docs). The colon is kept
    unencoded so explicit field prefixes such as ``au:Smith`` stay readable
    in the request URL.
    """
    return quote(query, safe=":")


#: ArXiv ``search_query`` field prefixes. A query starting with one of these
#: is used verbatim; anything else is searched across all fields (``all:``).
_ARXIV_FIELD_PREFIXES = (
    "all:",
    "ti:",
    "au:",
    "abs:",
    "co:",
    "jr:",
    "rn:",
    "cat:",
)


def _build_search_query(query: str) -> str:
    """Build the ArXiv ``search_query`` value for a user query.

    Queries that already carry an explicit ArXiv field prefix (e.g.
    ``au:Smith``) are passed through unchanged; plain keywords are prefixed
    with ``all:`` so they search across all fields.
    """
    if query.lstrip().lower().startswith(_ARXIV_FIELD_PREFIXES):
        return query
    return f"all:{query}"


def _strip_version(arxiv_id: str) -> str:
    """Remove the trailing revision suffix from an arXiv ID.

    arXiv IDs are ``YYYY.NNNNN`` (or legacy ``class/YYMMNNN``); an optional
    ``v<N>`` suffix marks the revision. The ID body itself never contains
    ``v``, so splitting on ``v`` and keeping the head is safe.
    """
    return arxiv_id.split("v")[0]


def _fetch(params: str) -> str:
    """Fetch from ArXiv API with bounded response size."""
    url = f"{_API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise ArxivRateLimitError(
                "请求过于频繁（限流），请间隔至少 3 秒后重试"
            ) from e
        raise
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("ArXiv API response exceeds the 1 MiB safety limit")
    return raw.decode("utf-8")


def _parse_entries(xml_text: str) -> List[dict]:
    """Parse Atom XML entries into structured dicts.

    Returns a list of dicts with keys:
      title, authors, summary, arxiv_id, link, published, categories
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(
            "ArXiv API 返回了无法解析的响应（内容不是合法 XML），请稍后重试"
        ) from e
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        title_elem = entry.find("atom:title", ns)
        summary_elem = entry.find("atom:summary", ns)
        id_elem = entry.find("atom:id", ns)
        published_elem = entry.find("atom:published", ns)
        link_elem = entry.find("atom:link[@rel='alternate']", ns)
        authors_elem = entry.findall("atom:author", ns)

        title = (title_elem.text or "").strip().replace("\n", " ")
        summary = (summary_elem.text or "").strip().replace("\n", " ")
        arxiv_id = (id_elem.text if id_elem is not None else "").strip()
        published = (published_elem.text or "").strip()
        link = link_elem.get("href", "") if link_elem is not None else ""

        # Extract categories
        categories = [
            cat.get("term", "")
            for cat in entry.findall("atom:category", ns)
        ]

        # Extract authors
        author_names = []
        for author in authors_elem:
            name_elem = author.find("atom:name", ns)
            if name_elem is not None and name_elem.text:
                author_names.append(name_elem.text.strip())

        results.append(
            {
                "title": title,
                "authors": author_names,
                "summary": summary[:500],  # Truncate long summaries
                "arxiv_id": arxiv_id.split("/")[-1] if "/" in arxiv_id else arxiv_id,
                "link": link or f"https://arxiv.org/abs/{arxiv_id.split('/')[-1]}",
                "published": published,
                "categories": categories,
            }
        )
    return results


class ArxivChannel(Channel):
    name = "arxiv"
    description = "ArXiv 学术论文搜索"
    backends = ["ArXiv API (public)"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "arxiv.org")

    def check(self, config=None):
        """Probe ArXiv API connectivity with a lightweight search."""
        self.active_backend = None
        try:
            xml_text = _fetch("search_query=all:test&start=0&max_results=1")
            entries = _parse_entries(xml_text)
            if entries:
                self.active_backend = self.backends[0]
                return "ok", "公开 API 可用（论文搜索、摘要读取）"
            return "warn", "API 连通但无响应结果"
        except ArxivRateLimitError as e:
            self.active_backend = None
            return "warn", f"ArXiv API {e}"
        except Exception as e:
            self.active_backend = None
            from agent_reach.utils.text import scrub_url_credentials

            return (
                "warn",
                f"ArXiv API 连接失败：{scrub_url_credentials(e)}",
            )

    def search(self, query: str, limit: int = 10) -> List[dict]:
        """搜索论文，返回结构化摘要列表。

        Args:
            query: 搜索关键词，如 "transformer"、"LLM"、"cs.CV"；
                支持 ArXiv 字段语法（如 "au:Smith"、"cat:cs.CV"）
            limit: 最多返回条数（上限 100）

        Returns:
            list of dicts with keys: title, authors, summary, arxiv_id, link, published, categories
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        limit = min(limit, 100)
        if limit == 0:
            return []

        query = _build_search_query(query)
        xml_text = _fetch(f"search_query={_quote_query(query)}&start=0&max_results={limit}")
        return _parse_entries(xml_text)

    def get_paper(self, arxiv_id: str) -> dict:
        """获取单篇论文详情。

        Args:
            arxiv_id: 论文 ID，如 "2301.00001" 或完整 URL "https://arxiv.org/abs/2301.00001"

        Returns:
            dict with keys: title, authors, summary, arxiv_id, link, published, categories
        """
        # Extract ID from URL if needed, then strip any version suffix.
        if "arxiv.org/abs/" in arxiv_id:
            arxiv_id = _strip_version(arxiv_id.split("/abs/")[-1])
        elif "arxiv.org/pdf/" in arxiv_id:
            arxiv_id = _strip_version(arxiv_id.split("/pdf/")[-1].replace(".pdf", ""))

        # Use id_list parameter for precise lookup
        xml_text = _fetch(f"id_list={quote(arxiv_id)}")
        entries = _parse_entries(xml_text)
        if not entries:
            raise ValueError(f"Paper not found: {arxiv_id}")
        return entries[0]
