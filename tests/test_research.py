# -*- coding: utf-8 -*-
"""Tests for the research channel and paper analyzer."""

import json
import urllib.request
from unittest.mock import MagicMock, patch

import pytest


# ------------------------------------------------------------------ #
# ArxivChannel
# ------------------------------------------------------------------ #

class TestArxivChannel:
    def test_can_handle_arxiv_urls(self):
        from agent_reach.channels.arxiv import ArxivChannel

        ch = ArxivChannel()
        assert ch.can_handle("https://arxiv.org/abs/2301.12345")
        assert ch.can_handle("https://arxiv.org/pdf/2301.12345.pdf")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://twitter.com/user")

    def test_check_ok_when_api_reachable(self):
        from agent_reach.channels.arxiv import ArxivChannel

        ch = ArxivChannel()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            status, msg = ch.check()
            assert status == "ok"
            assert ch.active_backend == "arXiv API (public)"
            assert "arXiv" in msg

    def test_search_returns_list_of_dicts(self):
        from agent_reach.channels.arxiv import ArxivChannel

        ch = ArxivChannel()
        # Mock the XML response from arXiv
        xml_response = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns="http://www.w3.org/2005/Atom"'
            b' xmlns:arxiv="http://arxiv.org/schemas/atom">'
            b"<entry>"
            b"<id>http://arxiv.org/abs/2301.12345v1</id>"
            b"<title>Test Paper</title>"
            b"<summary>An interesting abstract.</summary>"
            b"<published>2023-01-15T00:00:00Z</published>"
            b"<updated>2023-01-16T00:00:00Z</updated>"
            b'<arxiv:comment xmlns:arxiv="http://arxiv.org/schemas/atom">'
            b"Accepted at NeurIPS 2023</arxiv:comment>"
            b"<author><name>Alice Author</name></author>"
            b"<author><name>Bob Researcher</name></author>"
            b'<link href="https://arxiv.org/abs/2301.12345" rel="alternate"/>'
            b'<link href="https://arxiv.org/pdf/2301.12345.pdf" title="pdf"/>'
            b'<category term="cs.LG"/>'
            b'<category term="cs.AI"/>'
            b'<arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"'
            b' term="cs.LG"/>'
            b"</entry>"
            b"</feed>"
        )
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = xml_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            results = ch.search("test", max_results=5)
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["title"] == "Test Paper"
            assert "Alice Author" in results[0]["authors"]
            assert results[0]["comment"] == "Accepted at NeurIPS 2023"

    def test_can_handle_name(self):
        from agent_reach.channels.arxiv import ArxivChannel

        ch = ArxivChannel()
        assert ch.name == "arxiv"


# ------------------------------------------------------------------ #
# SemanticScholarChannel
# ------------------------------------------------------------------ #

class TestSemanticScholarChannel:
    def test_can_handle_s2_urls(self):
        from agent_reach.channels.semantic_scholar import SemanticScholarChannel

        ch = SemanticScholarChannel()
        assert ch.can_handle("https://www.semanticscholar.org/paper/abc123")
        assert not ch.can_handle("https://arxiv.org/abs/2301.12345")

    def test_check_ok_when_api_reachable(self):
        from agent_reach.channels.semantic_scholar import SemanticScholarChannel

        ch = SemanticScholarChannel()
        mock_resp = MagicMock(status=200)
        mock_resp.read.return_value = b'{"data": [{"paperId": "test123"}]}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            status, msg = ch.check()
            assert status == "ok"
            assert ch.active_backend is not None

    def test_search_returns_list_of_dicts(self):
        from agent_reach.channels.semantic_scholar import SemanticScholarChannel

        ch = SemanticScholarChannel()
        s2_response = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Deep Learning Paper",
                    "abstract": "We present a novel approach...",
                    "year": 2024,
                    "authors": [{"authorId": "1", "name": "Alice"}],
                    "citationCount": 150,
                    "influentialCitationCount": 30,
                    "venue": {"name": "NeurIPS"},
                    "journal": None,
                    "fieldsOfStudy": ["Computer Science"],
                    "publicationDate": "2024-06-01",
                    "url": "https://www.semanticscholar.org/paper/abc123",
                    "openAccessPdf": {
                        "url": "https://arxiv.org/pdf/2401.12345.pdf"
                    },
                    "externalIds": {"ArXiv": "2401.12345", "DOI": "10.1234/test"},
                    "tldr": {"text": "A novel approach to deep learning."},
                }
            ]
        }
        mock_resp = MagicMock(status=200)
        mock_resp.read.return_value = json.dumps(s2_response).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            results = ch.search("deep learning", limit=5)
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["title"] == "Deep Learning Paper"
            assert results[0]["citation_count"] == 150
            assert results[0]["influential_citation_count"] == 30
            assert results[0]["tldr"] == "A novel approach to deep learning."


# ------------------------------------------------------------------ #
# ResearchChannel (aggregator)
# ------------------------------------------------------------------ #

class TestResearchChannel:
    def test_can_handle_academic_urls(self):
        from agent_reach.channels.research import ResearchChannel

        ch = ResearchChannel()
        assert ch.can_handle("https://arxiv.org/abs/2301.12345")
        assert ch.can_handle("https://www.semanticscholar.org/paper/abc123")
        assert ch.can_handle("https://dl.acm.org/doi/10.1145/12345")
        assert ch.can_handle("https://ieeexplore.ieee.org/document/12345")
        assert ch.can_handle("https://proceedings.neurips.cc/paper/2023")
        assert ch.can_handle("https://openreview.net/forum?id=abc")
        assert ch.can_handle("https://www.nature.com/articles/s41586-023-12345")
        assert ch.can_handle("https://www.jmlr.org/papers/v24/23-1234.html")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://twitter.com/user/status/123")

    def test_name_and_tier(self):
        from agent_reach.channels.research import ResearchChannel

        ch = ResearchChannel()
        assert ch.name == "research"
        assert ch.tier == 0  # zero config

    def test_registered_in_all_channels(self):
        from agent_reach.channels import get_channel, get_all_channels

        ch = get_channel("research")
        assert ch is not None
        assert ch.name == "research"

        names = [c.name for c in get_all_channels()]
        assert "arxiv" in names
        assert "semantic_scholar" in names
        assert "research" in names

    def test_arxiv_registered(self):
        from agent_reach.channels import get_channel

        ch = get_channel("arxiv")
        assert ch is not None
        assert ch.tier == 0

    def test_semantic_scholar_registered(self):
        from agent_reach.channels import get_channel

        ch = get_channel("semantic_scholar")
        assert ch is not None
        assert ch.tier == 0

    def test_summary_formats_results(self):
        from agent_reach.channels.research import ResearchChannel
        from agent_reach.research.analyzer import ResearchResult, PaperQuality

        ch = ResearchChannel()
        results = [
            ResearchResult(
                title="Important Paper",
                authors=["Alice", "Bob"],
                abstract="Great work.",
                year=2024,
                url="https://example.com",
                pdf_url="https://example.com/paper.pdf",
                source="both",
                citation_count=200,
                venue="NeurIPS",
                quality=PaperQuality(
                    citation_score=0.8,
                    venue_score=1.0,
                    recency_score=0.9,
                    overall=0.85,
                    rating="excellent",
                ),
            ).to_dict()
        ]
        text = ch.summary(results)
        assert "Important Paper" in text
        assert "EXCELLENT" in text
        assert "NeurIPS" in text
        assert "200" in text


# ------------------------------------------------------------------ #
# Paper quality scoring
# ------------------------------------------------------------------ #

class TestPaperQuality:
    def test_score_top_venue_paper(self):
        from agent_reach.research.analyzer import score_paper

        q = score_paper(
            citation_count=500,
            influential_citations=80,
            venue="NeurIPS",
            year=2024,
            has_open_access=True,
        )
        assert q.rating == "excellent"
        assert q.overall >= 0.70
        assert q.venue_score == 1.0  # NeurIPS is tier 1

    def test_score_new_paper_no_citations(self):
        from agent_reach.research.analyzer import score_paper

        q = score_paper(
            citation_count=0,
            influential_citations=0,
            venue="arXiv preprint",
            year=2025,
            has_open_access=True,
        )
        # New paper — should get at least some recency + openness score
        assert q.recency_score >= 0.9  # current year
        assert q.overall >= 0.20  # some credit for recency + openness
        # But no citation or venue credit
        assert q.venue_score <= 0.2  # arxiv/preprint

    def test_score_old_classic_paper(self):
        from agent_reach.research.analyzer import score_paper

        q = score_paper(
            citation_count=5000,
            influential_citations=500,
            venue="Nature",
            year=2018,
            has_open_access=False,
        )
        # Classic paper — high citation compensates for age
        assert q.citation_score >= 0.9
        assert q.venue_score >= 0.8
        assert q.recency_score <= 0.3  # 8 years old

    def test_rating_labels(self):
        from agent_reach.research.analyzer import _rating

        assert _rating(0.80) == "excellent"
        assert _rating(0.70) == "excellent"
        assert _rating(0.50) == "good"
        assert _rating(0.45) == "good"
        assert _rating(0.30) == "ok"
        assert _rating(0.25) == "ok"
        assert _rating(0.10) == "unknown"


# ------------------------------------------------------------------ #
# Deduplication
# ------------------------------------------------------------------ #

class TestDedup:
    def test_exact_title_dedup(self):
        from agent_reach.research.analyzer import _merge_duplicates, ResearchResult

        p1 = ResearchResult(
            title="The Same Paper", authors=["A"], abstract="", year=2024,
            url="", pdf_url="", source="arxiv", arxiv_id="2401.001",
        )
        p2 = ResearchResult(
            title="The Same Paper", authors=["A"], abstract="", year=2024,
            url="", pdf_url="", source="semantic_scholar", citation_count=100,
            s2_id="abc123",
        )
        merged = _merge_duplicates([p1, p2])
        assert len(merged) == 1
        assert merged[0].source == "both"
        assert merged[0].citation_count == 100  # enriched from S2

    def test_different_papers_kept(self):
        from agent_reach.research.analyzer import _merge_duplicates, ResearchResult

        p1 = ResearchResult(
            title="Paper Alpha", authors=["A"], abstract="", year=2024,
            url="", pdf_url="", source="arxiv",
        )
        p2 = ResearchResult(
            title="Paper Beta", authors=["B"], abstract="", year=2024,
            url="", pdf_url="", source="semantic_scholar",
        )
        merged = _merge_duplicates([p1, p2])
        assert len(merged) == 2


# ------------------------------------------------------------------ #
# analyze_paper
# ------------------------------------------------------------------ #

class TestAnalyzePaper:
    def test_analyze_s2_found(self):
        from agent_reach.research import analyze_paper

        s2_response = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Attention Is All You Need",
                    "year": 2017,
                    "authors": [{"authorId": "1", "name": "Ashish Vaswani"}],
                    "citationCount": 120000,
                    "influentialCitationCount": 8000,
                    "venue": {"name": "NeurIPS"},
                    "tldr": {"text": "The Transformer architecture paper."},
                    "url": "https://www.semanticscholar.org/paper/abc123",
                    "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf"},
                }
            ]
        }
        mock_resp = MagicMock(status=200)
        mock_resp.read.return_value = json.dumps(s2_response).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = analyze_paper("Attention Is All You Need")
            assert result["found"] is True
            assert result["citation_count"] == 120000
            assert result["quality"]["rating"] == "excellent"


# ------------------------------------------------------------------ #
# CLI integration
# ------------------------------------------------------------------ #

class TestResearchCLI:
    def test_cli_research_search(self):
        from agent_reach.cli import main
        import sys
        from unittest.mock import patch

        with patch.object(
            sys, "argv", ["agent-reach", "research", "test topic", "-n", "3", "--json"]
        ), patch("sys.stdout", MagicMock()):
            try:
                main()
            except SystemExit:
                pass

    def test_cli_research_no_action_shows_help(self):
        from agent_reach.cli import main
        import sys
        from unittest.mock import patch

        with patch.object(
            sys, "argv", ["agent-reach", "research"]
        ), patch("sys.stdout", MagicMock()):
            try:
                main()
            except SystemExit:
                pass


# ------------------------------------------------------------------ #
# Config integration
# ------------------------------------------------------------------ #

class TestResearchConfig:
    def test_semantic_scholar_feature_registered(self):
        from agent_reach.config import Config

        assert "semantic_scholar" in Config.FEATURE_REQUIREMENTS
        assert "semantic_scholar_api_key" in Config.FEATURE_REQUIREMENTS["semantic_scholar"]

    def test_is_configured_for_s2(self):
        from agent_reach.config import Config
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(config_path=Path(tmp) / "config.yaml")
            assert not cfg.is_configured("semantic_scholar")
            cfg.set("semantic_scholar_api_key", "test_key_12345")
            assert cfg.is_configured("semantic_scholar")


# ================================================================== #
# PDF Reader
# ================================================================== #


class TestPDFReader:
    def test_find_pdf_url_direct(self):
        from agent_reach.research.pdf_reader import find_pdf_url

        paper = {"pdf_url": "https://arxiv.org/pdf/2301.12345.pdf"}
        assert find_pdf_url(paper) == "https://arxiv.org/pdf/2301.12345.pdf"

    def test_find_pdf_url_from_arxiv_id(self):
        from agent_reach.research.pdf_reader import find_pdf_url

        paper = {"arxiv_id": "2301.12345"}
        url = find_pdf_url(paper)
        assert "arxiv.org/pdf/2301.12345.pdf" in url

    def test_find_pdf_url_open_access(self):
        from agent_reach.research.pdf_reader import find_pdf_url

        paper = {"open_access_pdf": "https://example.com/paper.pdf"}
        assert find_pdf_url(paper) == "https://example.com/paper.pdf"

    def test_find_pdf_url_prioritizes_direct(self):
        """Direct pdf_url should win over arxiv_id."""
        from agent_reach.research.pdf_reader import find_pdf_url

        paper = {
            "pdf_url": "https://arxiv.org/pdf/2301.99999.pdf",
            "arxiv_id": "2301.12345",
        }
        assert find_pdf_url(paper) == "https://arxiv.org/pdf/2301.99999.pdf"

    def test_find_pdf_url_none(self):
        from agent_reach.research.pdf_reader import find_pdf_url

        paper = {"title": "No PDF available"}
        assert find_pdf_url(paper) is None

    def test_download_pdf_invalid_url(self):
        from agent_reach.research.pdf_reader import download_pdf

        result = download_pdf("https://invalid.example.com/fake.pdf", cache=False)
        assert result is None

    def test_extract_text_file_not_found(self, tmp_path):
        from agent_reach.research.pdf_reader import extract_text

        result = extract_text(tmp_path / "nonexistent.pdf")
        assert "文件不存在" in result

    def test_extract_text_no_library(self, tmp_path):
        """When no PDF library is installed, extract_text returns helpful message."""
        from agent_reach.research.pdf_reader import extract_text
        import builtins

        # Create a dummy PDF file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("fitz", "pdfplumber", "pypdf", "PyPDF2"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = extract_text(pdf_path)
            assert "无法提取" in result or "pip install" in result

    def test_download_and_read_bad_url(self):
        from agent_reach.research.pdf_reader import download_and_read

        result = download_and_read("https://invalid.example.com/fake.pdf", cache=False)
        assert "下载失败" in result

    def test_cache_dir_created(self, monkeypatch, tmp_path):
        from agent_reach.research import pdf_reader

        monkeypatch.setenv("AGENT_REACH_CACHE", str(tmp_path))
        cache = pdf_reader._cache_dir()
        assert cache.exists()
        assert "papers" in str(cache)


# ================================================================== #
# CLI: read command
# ================================================================== #


class TestReadCLI:
    def test_cli_read_command_with_url(self):
        from agent_reach.cli import main
        import sys

        with patch.object(
            sys, "argv", ["agent-reach", "read", "https://arxiv.org/pdf/2301.12345.pdf"]
        ), patch("sys.stdout", MagicMock()):
            try:
                main()
            except SystemExit:
                pass

    def test_cli_read_command_with_title(self):
        from agent_reach.cli import main
        import sys

        with patch.object(
            sys, "argv", ["agent-reach", "read", "Attention Is All You Need", "--pages", "10"]
        ), patch("sys.stdout", MagicMock()):
            try:
                main()
            except SystemExit:
                pass


# ================================================================== #
# Channel contract: all paper channels
# ================================================================== #


class TestPaperChannelsRegistered:
    """Verify all 8 paper channels are registered and pass basic contract."""

    def test_all_paper_channels_registered(self):
        from agent_reach.channels import get_channel

        for name in ("arxiv", "semantic_scholar", "research", "openalex",
                     "pubmed", "dblp", "core", "papers_with_code"):
            ch = get_channel(name)
            assert ch is not None, f"{name} channel not found"
            assert ch.tier == 0, f"{name} should be tier 0"

    def test_total_channel_count(self):
        from agent_reach.channels import get_all_channels

        channels = get_all_channels()
        assert len(channels) == 21  # 13 original + 8 paper
