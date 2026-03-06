# -*- coding: utf-8 -*-
"""Tests for Jobs (招聘聚合) channel."""

import pytest
from agent_reach.channels.jobs import JobsChannel


class TestJobsChannel:
    def setup_method(self):
        self.ch = JobsChannel()

    def test_can_handle_liepin(self):
        assert self.ch.can_handle("https://www.liepin.com/job/1234567.shtml")
        assert self.ch.can_handle("https://liepin.com/company/xxx")

    def test_can_handle_zhaopin(self):
        assert self.ch.can_handle("https://www.zhaopin.com/job/123")
        assert self.ch.can_handle("https://sou.zhaopin.com/jobs/searchresult.ashx")

    def test_can_handle_51job(self):
        assert self.ch.can_handle("https://www.51job.com/jobs/123")
        assert self.ch.can_handle("https://51job.com/xxx")

    def test_cannot_handle_other_url(self):
        assert not self.ch.can_handle("https://github.com/test/repo")
        assert not self.ch.can_handle("https://weibo.com/u/123")
        assert not self.ch.can_handle("https://arxiv.org/abs/2410.05390")

    def test_check_returns_tuple(self):
        result = self.ch.check()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] in ("ok", "warn", "off", "error")
        assert isinstance(result[1], str)

    def test_metadata(self):
        assert self.ch.name == "jobs"
        assert self.ch.tier == 0
        assert "mcp-jobs" in self.ch.backends[0]
