# -*- coding: utf-8 -*-
"""Tests for doctor output."""

import re

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


def test_check_all_collects_channel_results(tmp_config, monkeypatch):
    monkeypatch.setattr(
        doctor,
        "get_all_channels",
        lambda: [
            _StubChannel("web", "Any web page", 0, "ok", "Jina Reader is ready", ["Jina"]),
            _StubChannel("github", "GitHub repositories and code search", 0, "warn", "gh missing", ["gh"]),
            _StubChannel("twitter", "Twitter/X search and timeline access", 1, "warn", "twitter missing", ["twitter-cli"]),
        ],
    )

    assert doctor.check_all(tmp_config) == {
        "web": {
            "status": "ok",
            "name": "Any web page",
            "message": "Jina Reader is ready",
            "tier": 0,
            "backends": ["Jina"],
        },
        "github": {
            "status": "warn",
            "name": "GitHub repositories and code search",
            "message": "gh missing",
            "tier": 0,
            "backends": ["gh"],
        },
        "twitter": {
            "status": "warn",
            "name": "Twitter/X search and timeline access",
            "message": "twitter missing",
            "tier": 1,
            "backends": ["twitter-cli"],
        },
    }


def test_format_report_groups_core_and_optional():
    report = doctor.format_report(
        {
            "web": {
                "status": "ok",
                "name": "Any web page",
                "message": "Jina Reader is ready",
                "tier": 0,
                "backends": ["Jina"],
            },
            "exa_search": {
                "status": "off",
                "name": "Cross-web search via Exa",
                "message": "mcporter missing",
                "tier": 0,
                "backends": ["mcporter"],
            },
            "twitter": {
                "status": "warn",
                "name": "Twitter/X search and timeline access",
                "message": "not authenticated",
                "tier": 1,
                "backends": ["twitter-cli"],
            },
        }
    )

    plain = re.sub(r"\[[^\]]*\]", "", report)
    assert "Agent Reach Health" in plain
    assert "Core channels" in plain
    assert "Optional channels" in plain
    assert "Summary: 1/3 channels ready" in plain
    assert "Not ready: Cross-web search via Exa, Twitter/X search and timeline access" in plain
