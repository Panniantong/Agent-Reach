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


def test_check_all_runs_channels_concurrently(monkeypatch):
    """探测必须并发执行：墙钟时间应接近最慢渠道，而不是各渠道之和。

    同时校验结果顺序仍跟随注册表 —— format_report 的分层渲染依赖此顺序。
    """
    import time

    class _SlowChannel:
        tier = 0
        backends = []
        active_backend = None

        def __init__(self, name):
            self.name = name
            self.description = name

        def check(self, config=None):
            time.sleep(0.3)
            return "ok", "done"

    channels = [_SlowChannel(f"ch{i}") for i in range(8)]
    monkeypatch.setattr(doctor, "get_all_channels", lambda: channels)

    t0 = time.perf_counter()
    results = doctor.check_all(config=None)
    elapsed = time.perf_counter() - t0

    # 串行需 8 × 0.3 = 2.4s；并发（max_workers≥8）应远低于 1s。
    assert elapsed < 1.0, f"探测疑似未并发：耗时 {elapsed:.2f}s"
    # 顺序必须与注册表一致。
    assert list(results.keys()) == [f"ch{i}" for i in range(8)]


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
