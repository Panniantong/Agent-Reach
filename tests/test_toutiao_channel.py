# -*- coding: utf-8 -*-
"""Tests for Toutiao channel."""

import unittest
from unittest.mock import patch, MagicMock

from agent_reach.channels.toutiao import ToutiaoChannel, _parse_search_results


class TestToutiaoChannel(unittest.TestCase):

    def setUp(self):
        self.ch = ToutiaoChannel()

    def test_can_handle_toutiao_urls(self):
        assert self.ch.can_handle("https://www.toutiao.com/article/123")
        assert self.ch.can_handle("https://so.toutiao.com/search?keyword=test")
        assert self.ch.can_handle("https://m.toutiao.com/abc")

    def test_can_handle_rejects_other_urls(self):
        assert not self.ch.can_handle("https://www.baidu.com")
        assert not self.ch.can_handle("https://weibo.com/123")
        assert not self.ch.can_handle("https://github.com/user/repo")

    def test_check_ok(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read = lambda: b'{"data":{"title":"test"}}'

        mock_enter = MagicMock(return_value=mock_resp)
        mock_exit = MagicMock(return_value=False)
        mock_resp.__enter__ = mock_enter
        mock_resp.__exit__ = mock_exit

        with patch("urllib.request.urlopen", return_value=mock_resp):
            status, msg = self.ch.check()
            assert status == "ok"

    def test_check_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            status, msg = self.ch.check()
            assert status == "warn"
            assert "连接失败" in msg

    def test_channel_attributes(self):
        assert self.ch.name == "toutiao"
        assert self.ch.tier == 0
        assert len(self.ch.backends) > 0

    def test_parse_search_results_with_article(self):
        abstract = "摘要内容" + "x" * 1000
        html = (
            '<script>{"data":{"title":"测试文章","abstract":"' + abstract + '",'
            '"media_name":"测试媒体","publish_time":1774332253,'
            '"read_count":100,"comment_count":5,'
            '"template_key":"undefined-default",'
            '"display":{"info":{"url":"https://www.toutiao.com/group/123/"}}}}</script>'
        )
        results = _parse_search_results(html)
        assert len(results) == 1
        assert results[0]["title"] == "测试文章"
        assert results[0]["source"] == "测试媒体"
        assert results[0]["url"] == "https://www.toutiao.com/group/123/"

    def test_parse_search_results_skips_non_article(self):
        html = (
            '<script>{"data":{"title":"搜索栏","template_key":"SearchBar",'
            '"display":{}}}</script>'
        )
        results = _parse_search_results(html)
        assert len(results) == 0

    def test_parse_search_results_empty_html(self):
        results = _parse_search_results("")
        assert results == []

    def test_parse_search_results_skips_short_scripts(self):
        html = "<script>{\"data\":{\"title\":\"短\"}}</script>"
        results = _parse_search_results(html)
        assert results == []