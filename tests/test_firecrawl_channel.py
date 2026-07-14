# -*- coding: utf-8 -*-
"""Tests for FirecrawlChannel."""

from unittest.mock import Mock, patch

from agent_reach.channels.firecrawl import FirecrawlChannel


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #

def _make_document(markdown="Test content", **kwargs):
    """Create a fake Firecrawl Document (pydantic or mock)."""
    doc = Mock()
    doc.markdown = markdown
    doc.html = kwargs.get("html", f"<p>{markdown}</p>")
    doc.metadata = kwargs.get("metadata", {"title": "Test Page", "url": "https://example.com"})
    doc.summary = kwargs.get("summary", "")
    doc.links = kwargs.get("links", [])
    return doc


def _make_credit_usage(remaining=500):
    """Create a fake credit usage response."""
    usage = Mock()
    usage.remaining = remaining
    return usage


def _make_crawl_job(pages=None, job_id="job-123", status="completed"):
    """Create a fake CrawlJob with optional pages."""
    job = Mock()
    job.id = job_id
    if pages is not None:
        job.pages = pages
    return job


def _make_search_data(items=None):
    """Create a fake SearchData."""
    data = Mock()
    data.model_dump = Mock(return_value=items or [])
    return data


def _make_extract_data(data=None):
    """Create a fake extract result."""
    result = Mock()
    result.model_dump = Mock(return_value=data or {})
    return result


# ------------------------------------------------------------------ #
# can_handle
# ------------------------------------------------------------------ #

class TestCanHandle:
    def test_accepts_http_url(self):
        ch = FirecrawlChannel()
        assert ch.can_handle("http://example.com") is True

    def test_accepts_https_url(self):
        ch = FirecrawlChannel()
        assert ch.can_handle("https://www.example.com/page?q=1") is True

    def test_accepts_any_string(self):
        ch = FirecrawlChannel()
        assert ch.can_handle("anything-at-all") is True

    def test_accepts_empty_string(self):
        ch = FirecrawlChannel()
        assert ch.can_handle("") is True


# ------------------------------------------------------------------ #
# check()
# ------------------------------------------------------------------ #

class TestCheckFailures:
    def test_missing_package(self):
        """firecrawl-py 未安装 → off + 安装指引。"""
        ch = FirecrawlChannel()
        with patch.object(
            FirecrawlChannel,
            "_check_import",
            return_value="未安装 firecrawl-py。安装：\n  pip install firecrawl-py",
        ):
            status, msg = ch.check()
        assert status == "off"
        assert "pip install firecrawl-py" in msg
        assert ch.active_backend is None

    def test_missing_api_key(self):
        """包已安装但 Key 未设置 → off + 配置指引。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_check_import", return_value=None), \
             patch.object(FirecrawlChannel, "_get_api_key", return_value=None):
            status, msg = ch.check()
        assert status == "off"
        assert "API Key" in msg
        assert "firecrawl.dev" in msg
        assert ch.active_backend is None

    def test_api_key_set_but_probe_fails(self):
        """Key 已配置但连通性探测失败 → warn。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_check_import", return_value=None), \
             patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.get_credit_usage.side_effect = Exception("Connection refused")
            status, msg = ch.check()
        assert status == "warn"
        assert "Connection refused" in msg
        assert ch.active_backend == "Firecrawl API"


class TestCheckSuccess:
    def test_everything_ok(self):
        """包已装、Key 已配、探测成功 → ok。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_check_import", return_value=None), \
             patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.get_credit_usage.return_value = _make_credit_usage(500)
            status, msg = ch.check()
        assert status == "ok"
        assert "Firecrawl API 可用" in msg
        assert ch.active_backend == "Firecrawl API"

    def test_ok_shows_remaining_credits(self):
        """探测成功时消息包含剩余额度。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_check_import", return_value=None), \
             patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.get_credit_usage.return_value = _make_credit_usage(500)
            _status, msg = ch.check()
        assert "剩余额度 500" in msg


# ------------------------------------------------------------------ #
# read()
# ------------------------------------------------------------------ #

class TestRead:
    def test_read_returns_markdown(self):
        """read() 应返回 scrape 得到的 markdown 内容。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.scrape.return_value = _make_document("# Hello World")
            result = ch.read("https://example.com")
        assert result == "# Hello World"

    def test_read_returns_empty_for_empty_page(self):
        """空页面返回空字符串。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.scrape.return_value = _make_document("")
            result = ch.read("https://example.com")
        assert result == ""

    def test_read_without_api_key_raises(self):
        """未配置 Key 时 read() 抛出 RuntimeError。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value=None):
            try:
                ch.read("https://example.com")
                assert False, "应抛出 RuntimeError"
            except RuntimeError as exc:
                assert "API Key" in str(exc)


# ------------------------------------------------------------------ #
# search()
# ------------------------------------------------------------------ #

class TestSearch:
    def test_search_returns_json_string(self):
        """search() 返回 JSON 字符串。"""
        ch = FirecrawlChannel()
        fake_items = [
            {"url": "https://example.com/1", "title": "Result 1", "description": "Desc 1"},
        ]
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.search.return_value = _make_search_data(fake_items)
            result = ch.search("test query", limit=3)
        assert "Result 1" in result
        assert "example.com" in result

    def test_search_respects_limit(self):
        """search() 传递 limit 参数。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.search.return_value = _make_search_data([])
            ch.search("query", limit=7)
        mock_client.return_value.search.assert_called_once_with("query", limit=7)


# ------------------------------------------------------------------ #
# crawl()
# ------------------------------------------------------------------ #

class TestCrawl:
    def test_crawl_with_pages_in_job(self):
        """crawl() 返回的 CrawlJob 直接包含 pages。"""
        ch = FirecrawlChannel()
        page = Mock()
        page.url = "https://example.com/page1"
        page.title = "Page 1"
        page.markdown = "# Page 1 Content"
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.crawl.return_value = _make_crawl_job(pages=[page])
            result = ch.crawl("https://example.com", max_depth=1, limit=5)
        assert "example.com" in result
        assert "Page 1" in result
        assert "# Page 1 Content" in result

    def test_crawl_polls_when_no_pages_directly(self):
        """crawl() 无直接 pages 时通过 get_crawl_status 轮询。"""
        ch = FirecrawlChannel()
        page = Mock()
        page.url = "https://example.com/page2"
        page.title = "Page 2"
        page.markdown = "Content 2"

        job = _make_crawl_job(pages=None, job_id="job-456")
        status_obj = Mock()
        status_obj.status = "completed"
        status_obj.pages = [page]

        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.crawl.return_value = job
            mock_client.return_value.get_crawl_status.return_value = status_obj
            with patch("time.sleep", return_value=None):  # 跳过等待
                result = ch.crawl("https://example.com")
        assert "Page 2" in result

    def test_crawl_failed_status(self):
        """爬取失败时返回错误信息。"""
        ch = FirecrawlChannel()
        job = _make_crawl_job(pages=None, job_id="job-789")
        status_obj = Mock()
        status_obj.status = "failed"
        status_obj.pages = None

        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.crawl.return_value = job
            mock_client.return_value.get_crawl_status.return_value = status_obj
            with patch("time.sleep", return_value=None):
                result = ch.crawl("https://example.com")
        assert "爬取失败" in result

    def test_crawl_passes_arguments_correctly(self):
        """crawl() 正确传递 max_depth 和 limit。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.crawl.return_value = _make_crawl_job(pages=[])
            ch.crawl("https://example.com", max_depth=3, limit=20)
        mock_client.return_value.crawl.assert_called_once()
        call_kwargs = mock_client.return_value.crawl.call_args.kwargs
        assert call_kwargs["max_discovery_depth"] == 3
        assert call_kwargs["limit"] == 20


# ------------------------------------------------------------------ #
# extract()
# ------------------------------------------------------------------ #

class TestExtract:
    def test_extract_returns_json(self):
        """extract() 返回结构化 JSON。"""
        ch = FirecrawlChannel()
        fake_data = {"name": "Test Co", "description": "A test company"}
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.extract.return_value = _make_extract_data(fake_data)
            result = ch.extract(
                ["https://example.com"],
                prompt="Extract company info",
            )
        assert "Test Co" in result
        assert "A test company" in result

    def test_extract_passes_schema(self):
        """extract() 传递可选的 JSON Schema。"""
        ch = FirecrawlChannel()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        with patch.object(FirecrawlChannel, "_get_api_key", return_value="fc-test"), \
             patch.object(FirecrawlChannel, "_make_client") as mock_client:
            mock_client.return_value.extract.return_value = _make_extract_data({})
            ch.extract(["https://example.com"], prompt="Extract name", schema=schema)
        mock_client.return_value.extract.assert_called_once()
        call_kwargs = mock_client.return_value.extract.call_args.kwargs
        assert call_kwargs["schema"] == schema

    def test_extract_without_api_key_raises(self):
        """未配置 Key 时 extract() 抛出 RuntimeError。"""
        ch = FirecrawlChannel()
        with patch.object(FirecrawlChannel, "_get_api_key", return_value=None):
            try:
                ch.extract(["https://example.com"], prompt="test")
                assert False, "应抛出 RuntimeError"
            except RuntimeError as exc:
                assert "API Key" in str(exc)


# ------------------------------------------------------------------ #
# Channel metadata
# ------------------------------------------------------------------ #

class TestChannelMetadata:
    def test_name_and_tier(self):
        ch = FirecrawlChannel()
        assert ch.name == "firecrawl"
        assert ch.tier == 1

    def test_description_is_chinese(self):
        ch = FirecrawlChannel()
        assert "Firecrawl" in ch.description
        assert "深度" in ch.description

    def test_backends_list(self):
        ch = FirecrawlChannel()
        assert ch.backends == ["Firecrawl API"]

    def test_active_backend_defaults_none(self):
        ch = FirecrawlChannel()
        assert ch.active_backend is None
