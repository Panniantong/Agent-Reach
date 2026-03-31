# -*- coding: utf-8 -*-
"""Tests for ToutiaoChannel."""

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_reach.channels.toutiao import ToutiaoChannel, _parse_search_results


@pytest.fixture
def ch():
    return ToutiaoChannel()


class TestToutiaoChannelAttributes:
    def test_name(self, ch):
        assert ch.name == "toutiao"

    def test_tier(self, ch):
        assert ch.tier == 0

    def test_backends(self, ch):
        assert ch.backends


class TestToutiaoCanHandle:
    def test_matches_toutiao(self, ch):
        assert ch.can_handle("https://www.toutiao.com/article/123")

    def test_matches_search(self, ch):
        assert ch.can_handle("https://so.toutiao.com/search?keyword=ai")

    def test_rejects_other(self, ch):
        assert not ch.can_handle("https://www.baidu.com")


class TestToutiaoCheck:
    def test_check_ok(self, ch):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"data": {"title": "test"}}'
        with patch("urllib.request.urlopen", return_value=mock_resp):
            status, msg = ch.check()
        assert status == "ok"

    def test_check_exception(self, ch):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            status, msg = ch.check()
        assert status == "warn"
        assert "timeout" in msg


class TestParseSearchResults:
    def _make_script(self, data: dict) -> str:
        # Production code skips scripts < 1000 chars; pad to exceed threshold
        payload = json.dumps({"data": data})
        padding = "x" * max(0, 1001 - len(payload))
        padded = payload[:-1] + f',"_pad":"{padding}"' + payload[-1]
        return f'<script type="text/javascript">{padded}</script>'

    def test_extracts_article_url_first(self):
        html = self._make_script({
            "title": "测试文章",
            "article_url": "https://www.toutiao.com/article/1",
            "template_key": "undefined-default",
        })
        results = _parse_search_results(html)
        assert len(results) == 1
        assert results[0]["url"] == "https://www.toutiao.com/article/1"
        assert results[0]["title"] == "测试文章"

    def test_fallback_to_source_url(self):
        html = self._make_script({
            "title": "备用 URL 文章",
            "source_url": "https://www.toutiao.com/source/1",
            "template_key": "undefined-default",
        })
        results = _parse_search_results(html)
        assert len(results) == 1
        assert results[0]["url"] == "https://www.toutiao.com/source/1"

    def test_skips_entries_without_url(self):
        html = self._make_script({
            "title": "无 URL 文章",
            "template_key": "undefined-default",
        })
        results = _parse_search_results(html)
        assert results == []

    def test_skips_entries_without_title(self):
        html = self._make_script({
            "article_url": "https://www.toutiao.com/article/1",
            "template_key": "undefined-default",
        })
        results = _parse_search_results(html)
        assert results == []

    def test_skips_skip_templates(self):
        html = self._make_script({
            "title": "广告",
            "article_url": "https://www.toutiao.com/article/1",
            "template_key": "Bottom-ad",
        })
        results = _parse_search_results(html)
        assert results == []

    def test_empty_html(self):
        assert _parse_search_results("") == []

    def test_short_scripts_ignored(self):
        # script < 1000 chars should be skipped
        html = '<script>{"data": {"title": "x", "article_url": "y"}}</script>'
        assert _parse_search_results(html) == []
