# -*- coding: utf-8 -*-
"""Tests for Xianyu channel."""

import shutil

from agent_reach.channels import get_all_channels
from agent_reach.channels.xianyu import XianyuChannel


class TestXianyuChannel:
    def test_can_handle_xianyu_urls(self):
        ch = XianyuChannel()
        assert ch.can_handle("https://www.goofish.com/item/id=123")
        assert ch.can_handle("https://2.taobao.com/item.htm?id=123")
        assert ch.can_handle("https://m.tb.cn/h.xxx")
        assert ch.can_handle("https://xy.taobao.com/search")
        assert not ch.can_handle("https://twitter.com/user")
        assert not ch.can_handle("https://github.com/user/repo")

    def test_check_ok_when_exa_installed(self, monkeypatch):
        import subprocess

        monkeypatch.setattr(
            shutil, "which", lambda cmd: "/usr/local/bin/mcporter" if cmd == "mcporter" else None
        )

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "exa\nother\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)

        status, msg = XianyuChannel().check()
        assert status == "ok"
        assert "完整可用" in msg

    def test_check_warn_when_exa_missing(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _: None)

        status, msg = XianyuChannel().check()
        assert status == "warn"
        assert "agent-reach install" in msg

    def test_registered_in_all_channels(self):
        names = [ch.name for ch in get_all_channels()]
        assert "xianyu" in names
