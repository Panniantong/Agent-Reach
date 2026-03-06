# -*- coding: utf-8 -*-
"""Tests for Weibo channel."""

import pytest
from agent_reach.channels.weibo import WeiboChannel


class TestWeiboChannel:
    def setup_method(self):
        self.ch = WeiboChannel()

    def test_can_handle_weibo_com(self):
        assert self.ch.can_handle("https://weibo.com/1669879400/LxS6o5yGQ")
        assert self.ch.can_handle("https://www.weibo.com/u/1234567")
        assert self.ch.can_handle("https://m.weibo.com/detail/5144480215658498")

    def test_can_handle_weibo_cn(self):
        assert self.ch.can_handle("https://weibo.cn/u/1234567")
        assert self.ch.can_handle("https://m.weibo.cn/detail/5144480215658498")

    def test_cannot_handle_other_url(self):
        assert not self.ch.can_handle("https://twitter.com/test")
        assert not self.ch.can_handle("https://github.com/test/repo")
        assert not self.ch.can_handle("https://xiaohongshu.com/explore/123")

    def test_check_returns_tuple(self):
        result = self.ch.check()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] in ("ok", "warn", "off", "error")
        assert isinstance(result[1], str)

    def test_metadata(self):
        assert self.ch.name == "weibo"
        assert self.ch.tier == 2
        assert "weibo" in self.ch.backends[0].lower()
