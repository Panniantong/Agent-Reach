# -*- coding: utf-8 -*-
"""Tests for channel registry basics and health checks."""

import shutil
import subprocess

from agent_reach.channels import get_all_channels, get_channel
from agent_reach.channels.bosszhipin import BossZhipinChannel
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel


class TestChannelRegistry:
    def test_get_channel_by_name(self):
        ch = get_channel("github")
        assert ch is not None
        assert ch.name == "github"

    def test_get_unknown_channel_returns_none(self):
        assert get_channel("not-exists") is None

    def test_all_channels_registered(self):
        channels = get_all_channels()
        names = [ch.name for ch in channels]
        assert "web" in names
        assert "github" in names
        assert "twitter" in names


class TestBossZhipinChannel:
    def test_reports_ok_when_configured_and_logged_in(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/opt/homebrew/bin/mcporter")

        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["/opt/homebrew/bin/mcporter", "config", "get", "bosszhipin"]:
                return subprocess.CompletedProcess(cmd, 0, '{"name":"bosszhipin"}', "")
            if cmd[:3] == ["/opt/homebrew/bin/mcporter", "call", "bosszhipin.get_login_info_tool"]:
                return subprocess.CompletedProcess(cmd, 0, '{"is_logged_in": true}', "")
            raise AssertionError(f"unexpected command: {cmd}")

        monkeypatch.setattr(subprocess, "run", fake_run)

        assert BossZhipinChannel().check() == (
            "ok",
            "完整可用（职位搜索、登录态检查、向 HR 打招呼）",
        )


class TestXiaoHongShuChannel:
    def test_reports_ok_when_server_health_is_ok(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: "/opt/homebrew/bin/mcporter")

        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["/opt/homebrew/bin/mcporter", "config", "get", "xiaohongshu"]:
                return subprocess.CompletedProcess(cmd, 0, '{"name":"xiaohongshu"}', "")
            if cmd[:4] == ["/opt/homebrew/bin/mcporter", "list", "xiaohongshu", "--json"]:
                return subprocess.CompletedProcess(cmd, 0, '{"status": "ok"}', "")
            raise AssertionError(f"unexpected command: {cmd}")

        monkeypatch.setattr(subprocess, "run", fake_run)

        assert XiaoHongShuChannel().check() == (
            "ok",
            "MCP 已连接（阅读、搜索、发帖、评论、点赞）",
        )
