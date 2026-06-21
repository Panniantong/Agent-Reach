# -*- coding: utf-8 -*-
"""Tests for doctor module."""

import pytest

import agent_reach.doctor as doctor
from agent_reach.config import Config


class _StubChannel:
    def __init__(self, name, description, tier, status, message, backends=None,
                 active_backend=None):
        self.name = name
        self.description = description
        self.tier = tier
        self._status = status
        self._message = message
        self.backends = backends or []
        self.active_backend = active_backend

    def check(self, config=None):
        return self._status, self._message


@pytest.fixture
def tmp_config(tmp_path):
    return Config(config_path=tmp_path / "config.yaml")


class TestDoctor:
    def test_check_all_collects_channel_results(self, tmp_config, monkeypatch):
        monkeypatch.setattr(
            doctor,
            "get_all_channels",
            lambda: [
                _StubChannel("web", "网页", 0, "ok", "可抓取网页", ["requests"],
                             active_backend="requests"),
                _StubChannel("github", "GitHub", 0, "warn", "gh 未安装", ["gh"]),
                _StubChannel("exa_search", "全网语义搜索", 1, "off", "mcporter 未配置", ["Exa"]),
            ],
        )

        results = doctor.check_all(tmp_config)

        assert results == {
            "web": {
                "status": "ok",
                "name": "网页",
                "message": "可抓取网页",
                "tier": 0,
                "backends": ["requests"],
                "active_backend": "requests",
            },
            "github": {
                "status": "warn",
                "name": "GitHub",
                "message": "gh 未安装",
                "tier": 0,
                "backends": ["gh"],
                "active_backend": None,
            },
            "exa_search": {
                "status": "off",
                "name": "全网语义搜索",
                "message": "mcporter 未配置",
                "tier": 1,
                "backends": ["Exa"],
                "active_backend": None,
            },
        }

    def test_format_report(self):
        report = doctor.format_report(
            {
                "web": {
                    "status": "ok",
                    "name": "网页",
                    "message": "可抓取网页",
                    "tier": 0,
                    "backends": ["requests"],
                },
                "exa_search": {
                    "status": "off",
                    "name": "全网语义搜索",
                    "message": "mcporter 未配置",
                    "tier": 1,
                    "backends": ["Exa"],
                },
                "xiaohongshu": {
                    "status": "warn",
                    "name": "小红书",
                    "message": "MCP 已配置，但健康检查超时",
                    "tier": 2,
                    "backends": ["mcporter"],
                },
            }
        )

        # Strip Rich markup tags for assertion (PR #170 added [bold], [yellow] etc.)
        import re
        plain = re.sub(r"\[[^\]]*\]", "", report)
        assert "Agent Reach" in plain
        assert "装好即用：" in plain
        assert "1/3 个渠道可用" in plain
        # Inactive optional channels should be summarized in one line
        assert "可选渠道可以解锁" in plain


def test_stale_active_backend_does_not_leak_into_errored_result(monkeypatch):
    """渠道单例上一轮的 active_backend 不得泄漏进本轮异常结果(Codex review 发现)。"""
    from agent_reach import doctor

    class _ExplodingChannel:
        name = "boom"
        description = "爆炸渠道"
        tier = 0
        backends = ["a", "b"]
        active_backend = "a"  # 上一轮成功的残留

        def check(self, config=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(doctor, "get_all_channels", lambda: [_ExplodingChannel()])
    results = doctor.check_all(config=None)
    assert results["boom"]["status"] == "error"
    assert results["boom"]["active_backend"] is None



class TestDoctorHealthRegistryIntegration:
    """Verify that check_all() populates the shared HealthRegistry."""

    def test_registry_updated_after_check_all(self, tmp_config, monkeypatch):
        s1 = _StubChannel(
            "h_ok", "OK Channel", 0, "ok", "全部正常", ["tool"], active_backend="tool"
        )
        s2 = _StubChannel(
            "h_warn_auth", "Miss Auth", 1, "warn", "未登录",
        )
        s3 = _StubChannel(
            "h_warn_missing", "Not Installed", 1, "warn", "未安装 tool",
        )
        s4 = _StubChannel(
            "h_off", "Unavailable", 2, "off", "tool 不可用",
        )
        s5 = _StubChannel(
            "h_error", "Broken", 2, "error", "启动异常",
        )
        s6 = _StubChannel(
            "h_rate", "Rate Limited", 1, "warn", "rate limit exceeded",
        )

        monkeypatch.setattr(
            doctor,
            "get_all_channels",
            lambda: [s1, s2, s3, s4, s5, s6],
        )

        from agent_reach.health import ChannelStatus, get_registry

        doctor.check_all(tmp_config)
        registry = get_registry()

        assert registry.get_health("h_ok").status == ChannelStatus.HEALTHY
        assert registry.get_health("h_warn_auth").status == ChannelStatus.DEGRADED
        assert registry.get_health("h_warn_missing").status == ChannelStatus.DEGRADED
        assert registry.get_health("h_off").status == ChannelStatus.UNAVAILABLE
        assert registry.get_health("h_error").status == ChannelStatus.DEGRADED
        assert registry.get_health("h_rate").status == ChannelStatus.DEGRADED

    def test_health_record_contains_details(self, tmp_config, monkeypatch):
        s = _StubChannel("h_detail", "Detail Test", 0, "warn", "gh 未安装")
        monkeypatch.setattr(doctor, "get_all_channels", lambda: [s])

        from agent_reach.health import get_registry

        doctor.check_all(tmp_config)
        health = get_registry().get_health("h_detail")

        assert health is not None
        assert health.channel_name == "h_detail"
        assert health.failure_reason == "gh 未安装"
        assert health.last_checked is not None

