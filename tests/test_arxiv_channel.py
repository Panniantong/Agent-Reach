# -*- coding: utf-8 -*-
"""Dedicated tests for the ``arxiv`` channel.

ArXiv uses the public Atom XML API (export.arxiv.org/api/query). Tests stub
_fetch to keep everything offline and verify URL matching, check logic,
search shaping, and get_paper retrieval. Follow-up to #671.
"""

from unittest.mock import patch

import pytest

from agent_reach.channels.arxiv import (
    ArxivChannel,
    ArxivRateLimitError,
    _fetch,
    _parse_entries,
    _quote_query,
)

# --- Sample XML fixtures ---

_XML_SINGLE_ENTRY = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2201.00978v1</id>
    <title>PyramidTNT: Improved Transformer-in-Transformer Baselines</title>
    <summary>Transformer networks have achieved great progress for computer vision.</summary>
    <published>2022-01-04T04:56:57Z</published>
    <link href="https://arxiv.org/abs/2201.00978v1" rel="alternate" type="text/html"/>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <category term="stat.ML" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""

_XML_MULTI_ENTRY = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2201.00978v1</id>
    <title>Paper One</title>
    <summary>Summary one.</summary>
    <published>2022-01-01T00:00:00Z</published>
    <link href="https://arxiv.org/abs/2201.00978v1" rel="alternate" type="text/html"/>
    <author><name>Author A</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2202.00123v2</id>
    <title>Paper Two</title>
    <summary>Summary two.</summary>
    <published>2022-02-01T00:00:00Z</published>
    <link href="https://arxiv.org/abs/2202.00123v2" rel="alternate" type="text/html"/>
    <author><name>Author B</name></author>
  </entry>
</feed>
"""

_XML_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
</feed>
"""


# --- can_handle ---

def test_can_handle_matches_arxiv_hosts():
    ch = ArxivChannel()
    for url in [
        "https://arxiv.org/abs/2201.00978",
        "https://arxiv.org/pdf/2201.00978.pdf",
        "https://ARXIV.ORG/abs/test",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://twitter.com",
        "",
        "https://not-arxiv.org/abs/1234",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() ---

def test_check_ok_sets_active_backend():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_SINGLE_ENTRY):
        status, message = ch.check()
    assert status == "ok"
    assert ch.active_backend == ch.backends[0]
    assert "可用" in message


def test_check_warn_on_network_error_clears_backend():
    ch = ArxivChannel()
    ch.active_backend = "stale"
    with patch("agent_reach.channels.arxiv._fetch", side_effect=OSError("no proxy")):
        status, message = ch.check()
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


def test_check_warn_on_empty_response():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_EMPTY):
        status, message = ch.check()
    assert status == "warn"
    assert "无响应" in message


def test_check_warn_on_rate_limit_not_proxy():
    """HTTP 429 must be reported as rate limiting, not as a proxy failure."""
    ch = ArxivChannel()
    ch.active_backend = "stale"
    with patch(
        "agent_reach.channels.arxiv._fetch",
        side_effect=ArxivRateLimitError("请求过于频繁（限流），请间隔至少 3 秒后重试"),
    ):
        status, message = ch.check()
    assert status == "warn"
    assert "过于频繁" in message
    assert "代理" not in message
    assert ch.active_backend is None


def test_fetch_raises_rate_limit_on_http_429():
    """A raw HTTP 429 from the API must surface as ArxivRateLimitError."""
    import urllib.error

    http_err = urllib.error.HTTPError(
        "https://export.arxiv.org/api/query", 429, "Too Many Requests", {}, None
    )
    with patch(
        "agent_reach.channels.arxiv.urllib.request.urlopen",
        side_effect=http_err,
    ):
        with pytest.raises(ArxivRateLimitError, match="过于频繁"):
            _fetch("search_query=test")


# --- _parse_entries ---

def test_parse_entries_maps_fields_correctly():
    entries = _parse_entries(_XML_SINGLE_ENTRY)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["title"] == "PyramidTNT: Improved Transformer-in-Transformer Baselines"
    assert entry["authors"] == ["Alice Smith", "Bob Jones"]
    assert entry["summary"] == "Transformer networks have achieved great progress for computer vision."
    assert entry["arxiv_id"] == "2201.00978v1"
    assert entry["link"] == "https://arxiv.org/abs/2201.00978v1"
    assert entry["published"] == "2022-01-04T04:56:57Z"
    assert entry["categories"] == ["cs.CV", "stat.ML"]


def test_parse_entries_multiple():
    entries = _parse_entries(_XML_MULTI_ENTRY)
    assert len(entries) == 2
    assert entries[0]["title"] == "Paper One"
    assert entries[1]["title"] == "Paper Two"


def test_parse_entries_empty():
    entries = _parse_entries(_XML_EMPTY)
    assert entries == []


def test_parse_entries_truncates_long_summary():
    long_summary = "x" * 1000
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2201.00978</id>
    <title>Test</title>
    <summary>{long_summary}</summary>
    <published>2022-01-01T00:00:00Z</published>
    <link href="https://arxiv.org/abs/2201.00978" rel="alternate" type="text/html"/>
    <author><name>Test Author</name></author>
  </entry>
</feed>"""
    entries = _parse_entries(xml)
    assert len(entries[0]["summary"]) == 500


def test_parse_entries_invalid_xml_raises_clear_error():
    """A non-XML API response must raise a clear ValueError, not ET.ParseError."""
    with pytest.raises(ValueError, match="无法解析"):
        _parse_entries("<not-xml>")


# --- search() ---

def test_search_returns_structured_results():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_SINGLE_ENTRY):
        results = ch.search("transformer", limit=3)
    assert len(results) == 1
    assert results[0]["title"] == "PyramidTNT: Improved Transformer-in-Transformer Baselines"


def test_search_respects_limit():
    """Verify limit parameter is passed correctly in API query."""
    ch = ArxivChannel()
    captured_params = {}

    def fake_fetch(params):
        captured_params["params"] = params
        return _XML_MULTI_ENTRY

    with patch("agent_reach.channels.arxiv._fetch", side_effect=fake_fetch):
        ch.search("test", limit=1)
    assert "max_results=1" in captured_params["params"]


def test_search_zero_limit_returns_empty():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_MULTI_ENTRY):
        results = ch.search("test", limit=0)
    assert results == []


def test_search_negative_limit_raises():
    ch = ArxivChannel()
    with pytest.raises(ValueError, match="non-negative"):
        ch.search("test", limit=-1)


def test_search_capped_at_100():
    ch = ArxivChannel()
    captured_params = {}

    def fake_fetch(params):
        captured_params["params"] = params
        return _XML_SINGLE_ENTRY

    with patch("agent_reach.channels.arxiv._fetch", side_effect=fake_fetch):
        ch.search("test", limit=200)
    assert "max_results=100" in captured_params["params"]


def test_search_preserves_field_prefix_syntax():
    """Queries with an explicit ArXiv field prefix must not get 'all:' added."""
    ch = ArxivChannel()
    captured = {}

    def fake_fetch(params):
        captured["params"] = params
        return _XML_SINGLE_ENTRY

    with patch("agent_reach.channels.arxiv._fetch", side_effect=fake_fetch):
        ch.search("au:Smith", limit=1)
    assert "search_query=au:Smith" in captured["params"]
    assert "all:" not in captured["params"]


# --- get_paper() ---

def test_get_paper_by_id():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_SINGLE_ENTRY):
        result = ch.get_paper("2201.00978v1")
    assert result["title"] == "PyramidTNT: Improved Transformer-in-Transformer Baselines"
    assert result["arxiv_id"] == "2201.00978v1"


def test_get_paper_from_abs_url():
    """URL https://arxiv.org/abs/2201.00978v2 → id_list=2201.00978 (version stripped)."""
    ch = ArxivChannel()
    captured = {}

    def fake_fetch(params):
        captured["params"] = params
        return _XML_SINGLE_ENTRY

    with patch("agent_reach.channels.arxiv._fetch", side_effect=fake_fetch):
        result = ch.get_paper("https://arxiv.org/abs/2201.00978v2")
    # Version suffix .v2 is stripped by split("v")[0]
    assert captured["params"] == "id_list=2201.00978"
    assert result["arxiv_id"] == "2201.00978v1"  # From fixture XML


def test_get_paper_from_pdf_url():
    """URL https://arxiv.org/pdf/2201.00978.pdf → id_list=2201.00978."""
    ch = ArxivChannel()
    captured = {}

    def fake_fetch(params):
        captured["params"] = params
        return _XML_SINGLE_ENTRY

    with patch("agent_reach.channels.arxiv._fetch", side_effect=fake_fetch):
        result = ch.get_paper("https://arxiv.org/pdf/2201.00978.pdf")
    assert captured["params"] == "id_list=2201.00978"
    # Result arxiv_id comes from the XML fixture, not the input URL
    assert result["arxiv_id"] == "2201.00978v1"


def test_get_paper_not_found_raises():
    ch = ArxivChannel()
    with patch("agent_reach.channels.arxiv._fetch", return_value=_XML_EMPTY):
        with pytest.raises(ValueError, match="Paper not found"):
            ch.get_paper("9999.99999")


# --- _quote_query ---

@pytest.mark.parametrize(
    "query,expected",
    [
        ("transformer", "transformer"),
        ("LLM reasoning", "LLM%20reasoning"),
        ("cs.CV", "cs.CV"),
        ("deep learning & NLP", "deep%20learning%20%26%20NLP"),
    ],
)
def test_quote_query_encodes_special_chars(query, expected):
    assert _quote_query(query) == expected
