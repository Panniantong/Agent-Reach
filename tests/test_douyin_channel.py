# -*- coding: utf-8 -*-
"""Dedicated tests for the ``douyin`` channel.

Douyin is a thin OpenCLI-backed channel (same pattern as Instagram/Facebook).
These tests verify can_handle URL matching, check() status codes with mocked
OpenCLI health, and channel metadata.
"""

from agent_reach.backends import OpenCLIStatus
from agent_reach.channels.douyin import DouyinChannel


class TestDouyinCanHandle:
    """URL matching for douyin.com domains."""

    def test_matches_douyin_urls(self):
        ch = DouyinChannel()
        assert ch.can_handle("https://www.douyin.com/video/123456")
        assert ch.can_handle("https://douyin.com/user/abc123")
        assert ch.can_handle("https://live.douyin.com/789012")
        assert ch.can_handle("https://www.douyin.com/search/python?type=video")

    def test_rejects_non_douyin_urls(self):
        ch = DouyinChannel()
        assert not ch.can_handle("https://www.tiktok.com/@user/video/123")
        assert not ch.can_handle("https://www.instagram.com/p/abc123/")
        assert not ch.can_handle("https://github.com/user/repo")
        assert not ch.can_handle("https://example.com")
        assert not ch.can_handle("")


class TestDouyinCheck:
    """OpenCLI-backed health checks for Douyin."""

    def test_reports_ok_when_opencli_ready(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda: OpenCLIStatus(
                installed=True,
                extension_connected=True,
                version="1.8.3",
            ),
        )
        ch = DouyinChannel()
        status, msg = ch.check()
        assert status == "ok"
        assert ch.active_backend == "OpenCLI"
        assert "opencli douyin search/video/user/feed -f yaml" in msg
        assert "douyin.com" in msg

    def test_reports_off_when_opencli_missing(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda: OpenCLIStatus(installed=False),
        )
        ch = DouyinChannel()
        status, msg = ch.check()
        assert status == "off"
        assert ch.active_backend is None
        assert "agent-reach install --channels opencli" in msg
        assert "douyin.com" in msg

    def test_reports_warn_when_opencli_installed_without_extension(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda: OpenCLIStatus(
                installed=True,
                hint="OpenCLI 已安装，但 Chrome 扩展未安装。",
            ),
        )
        ch = DouyinChannel()
        status, msg = ch.check()
        assert status == "warn"
        assert ch.active_backend == "OpenCLI"
        assert "Chrome 扩展" in msg

    def test_reports_error_when_opencli_broken(self, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.backends.opencli_status",
            lambda: OpenCLIStatus(
                installed=True,
                broken=True,
                hint="OpenCLI 已安装但无法执行（venv 断链）",
            ),
        )
        ch = DouyinChannel()
        status, msg = ch.check()
        assert status == "error"
        assert ch.active_backend is None
        assert "无法执行" in msg


class TestDouyinMetadata:
    """Channel metadata correctness."""

    def test_name_and_tier(self):
        ch = DouyinChannel()
        assert ch.name == "douyin"
        assert ch.tier == 1
        assert ch.backends == ["OpenCLI"]

    def test_description_and_usage(self):
        ch = DouyinChannel()
        assert "抖音" in ch.description
        assert "opencli" in ch.usage
        assert "douyin" in ch.usage

    def test_domains(self):
        ch = DouyinChannel()
        assert "douyin.com" in ch.domains
