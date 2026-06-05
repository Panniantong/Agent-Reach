# -*- coding: utf-8 -*-
"""Tests for doctor module."""

import pytest

import agent_reach.doctor as doctor
from agent_reach.config import Config


class _StubChannel:
    def __init__(self, name, description, tier, status, message, backends=None):
        self.name = name
        self.description = description
        self.tier = tier
        self._status = status
        self._message = message
        self.backends = backends or []

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
                _StubChannel("web", "Web", 0, "ok", "Can scrape web pages", ["requests"]),
                _StubChannel("github", "GitHub", 0, "warn", "gh not installed", ["gh"]),
                _StubChannel("exa_search", "Web-wide semantic search", 1, "off", "mcporter not configured", ["Exa"]),
            ],
        )

        results = doctor.check_all(tmp_config)

        assert results == {
            "web": {
                "status": "ok",
                "name": "Web",
                "message": "Can scrape web pages",
                "tier": 0,
                "backends": ["requests"],
            },
            "github": {
                "status": "warn",
                "name": "GitHub",
                "message": "gh not installed",
                "tier": 0,
                "backends": ["gh"],
            },
            "exa_search": {
                "status": "off",
                "name": "Web-wide semantic search",
                "message": "mcporter not configured",
                "tier": 1,
                "backends": ["Exa"],
            },
        }

    def test_format_report(self):
        report = doctor.format_report(
            {
                "web": {
                    "status": "ok",
                    "name": "Web",
                    "message": "Can scrape web pages",
                    "tier": 0,
                    "backends": ["requests"],
                },
                "exa_search": {
                    "status": "off",
                    "name": "Web-wide semantic search",
                    "message": "mcporter not configured",
                    "tier": 1,
                    "backends": ["Exa"],
                },
                "xiaohongshu": {
                    "status": "warn",
                    "name": "XiaoHongShu",
                    "message": "MCP configured but health check timed out",
                    "tier": 2,
                    "backends": ["mcporter"],
                },
            }
        )

        # Strip Rich markup tags for assertion (PR #170 added [bold], [yellow] etc.)
        import re
        plain = re.sub(r"\[[^\]]*\]", "", report)
        assert "Agent Reach" in plain
        assert "Ready to use:" in plain
        assert "1/3 channels available" in plain
        # Inactive optional channels should be summarized in one line
        assert "channels you can unlock" in plain
