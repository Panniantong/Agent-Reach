# -*- coding: utf-8
"""Tests for 60s hot-news deploy (native + docker)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent_reach.daily_run.hot_news_deploy import (
    CONTAINER_NAME,
    LOCAL_BASE_URL,
    REBOOT_MARKER_BEGIN,
    install_60s_local,
    merge_user_hot_news_settings,
    render_reboot_crontab_block,
    status_60s,
    stop_60s,
)


class TestRebootCron:
    def test_render_reboot_crontab_block(self):
        block = render_reboot_crontab_block()
        assert REBOOT_MARKER_BEGIN in block
        assert "@reboot" in block
        assert "60s-reboot-start.sh" in block


class TestMergeSettings:
    def test_merge_writes_native_deploy(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.hot_news_deploy.Path.home",
            lambda: tmp_path,
        )
        out = merge_user_hot_news_settings(mode="native")
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["hot_news"]["base_urls"][0] == LOCAL_BASE_URL
        assert data["hot_news"]["deploy"]["mode"] == "native"
        assert data["hot_news"]["deploy"]["host_port"] == 8787


class TestInstallNative:
    def test_install_starts_native_process(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.hot_news_deploy.Path.home",
            lambda: tmp_path,
        )
        with (
            patch("agent_reach.daily_run.hot_news_deploy.node_version_ok", return_value=(True, "node 22.6.0")),
            patch("agent_reach.daily_run.hot_news_deploy.native_process_running", return_value=False),
            patch("agent_reach.daily_run.hot_news_deploy.resolve_local_base_url", side_effect=[None, LOCAL_BASE_URL]),
            patch("agent_reach.daily_run.hot_news_deploy.start_native", return_value=(True, "started")),
            patch("agent_reach.daily_run.hot_news_deploy.wait_healthy", return_value=(True, LOCAL_BASE_URL)),
        ):
            result = install_60s_local(mode="native")
        assert result["ok"] is True
        assert result["deploy_mode"] == "native"
        assert result["active_base_url"] == LOCAL_BASE_URL

    def test_install_without_node_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.hot_news_deploy.Path.home",
            lambda: tmp_path,
        )
        with (
            patch("agent_reach.daily_run.hot_news_deploy.resolve_local_base_url", return_value="https://60s.viki.moe"),
            patch("agent_reach.daily_run.hot_news_deploy.native_process_running", return_value=False),
            patch("agent_reach.daily_run.hot_news_deploy.start_native", return_value=(False, "node missing")),
        ):
            result = install_60s_local(mode="native")
        assert result["ok"] is True
        assert result["active_base_url"] == "https://60s.viki.moe"

    def test_install_skips_when_already_healthy(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.hot_news_deploy.Path.home",
            lambda: tmp_path,
        )
        with patch(
            "agent_reach.daily_run.hot_news_deploy.resolve_local_base_url",
            return_value=LOCAL_BASE_URL,
        ):
            result = install_60s_local(mode="native")
        assert result["ok"] is True
        assert "already healthy" in result["message"]


class TestInstallDocker:
    def test_install_docker_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.daily_run.hot_news_deploy.Path.home",
            lambda: tmp_path,
        )
        with (
            patch("agent_reach.daily_run.hot_news_deploy.resolve_local_base_url", side_effect=[None, LOCAL_BASE_URL]),
            patch("agent_reach.daily_run.hot_news_deploy.docker_path", return_value="/usr/bin/docker"),
            patch("agent_reach.daily_run.hot_news_deploy.start_container", return_value=(True, "started")),
            patch("agent_reach.daily_run.hot_news_deploy.wait_healthy", return_value=(True, LOCAL_BASE_URL)),
        ):
            result = install_60s_local(mode="docker", pull=False)
        assert result["ok"] is True
        assert result["deploy_mode"] == "docker"


class TestStatusAndStop:
    def test_status_native_ok(self):
        with (
            patch("agent_reach.daily_run.hot_news_deploy.node_version_ok", return_value=(True, "node 22.6.0")),
            patch("agent_reach.daily_run.hot_news_deploy.native_process_running", return_value=True),
            patch("agent_reach.daily_run.hot_news_deploy.read_pid", return_value=12345),
            patch(
                "agent_reach.daily_run.hot_news_deploy.resolve_local_base_url",
                return_value=LOCAL_BASE_URL,
            ),
            patch("agent_reach.daily_run.hot_news_portal.portal_running", return_value=True),
        ):
            st = status_60s()
        assert st["local_reachable"] is True
        assert st["native_running"] is True
        assert st["native_pid"] == 12345

    def test_stop_native(self):
        with (
            patch("agent_reach.daily_run.hot_news_deploy.native_process_running", return_value=True),
            patch("agent_reach.daily_run.hot_news_deploy.read_pid", return_value=999),
            patch("agent_reach.daily_run.hot_news_deploy.process_alive", return_value=True),
            patch("agent_reach.daily_run.hot_news_deploy.container_exists", return_value=False),
            patch("agent_reach.daily_run.hot_news_deploy.stop_native", return_value=(True, "stopped native 60s")),
            patch("agent_reach.daily_run.hot_news_portal.stop_portal", return_value=(True, "stopped portal")),
        ):
            ok, msg = stop_60s(mode="native")
        assert ok is True
        assert "native" in msg

    def test_stop_docker(self):
        with (
            patch("agent_reach.daily_run.hot_news_deploy.native_process_running", return_value=False),
            patch("agent_reach.daily_run.hot_news_deploy.container_exists", return_value=True),
            patch("agent_reach.daily_run.hot_news_deploy.stop_container", return_value=(True, f"stopped {CONTAINER_NAME}")),
            patch("agent_reach.daily_run.hot_news_portal.stop_portal", return_value=(True, "stopped portal")),
        ):
            ok, msg = stop_60s(mode="docker")
        assert ok is True
        assert CONTAINER_NAME in msg
