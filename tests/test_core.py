# -*- coding: utf-8 -*-
"""Tests for AgentReach core class."""

import pytest

from agent_reach.config import Config
from agent_reach.core import AgentReach


@pytest.fixture
def eyes(tmp_path):
    config = Config(config_path=tmp_path / "config.yaml")
    return AgentReach(config=config)


class TestAgentReach:
    def test_init(self, eyes):
        assert eyes.config is not None

    def test_doctor(self, eyes):
        results = eyes.doctor()
        assert isinstance(results, dict)
        assert "web" in results
        assert "github" in results

    def test_doctor_report(self, eyes):
        report = eyes.doctor_report()
        assert isinstance(report, str)
        assert "Agent Reach" in report
