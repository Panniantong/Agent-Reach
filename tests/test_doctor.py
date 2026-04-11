# -*- coding: utf-8 -*-
"""Tests for doctor output."""

import re

import pytest

import agent_reach.doctor as doctor
from agent_reach.config import Config


class _StubChannel:
    auth_kind = "none"
    entrypoint_kind = "cli"
    operations = ["read"]
    required_commands = []
    host_patterns = []
    example_invocations = []
    supports_probe = True
    probe_operations = ["read"]
    install_hints = []
    operation_contracts = {
        "read": {
            "name": "read",
            "input_kind": "url",
            "accepts_limit": True,
            "options": [],
        }
    }

    def __init__(self, name, description, tier, status, message, backends=None):
        self.name = name
        self.description = description
        self.tier = tier
        self._status = status
        self._message = message
        self.backends = backends or []

    def check(self, config=None):
        return self._status, self._message

    def probe(self, config=None):
        return "ok", f"probe:{self.name}"

    def to_contract(self):
        return {
            "name": self.name,
            "description": self.description,
            "tier": self.tier,
            "backends": self.backends,
            "auth_kind": self.auth_kind,
            "entrypoint_kind": self.entrypoint_kind,
            "operations": self.operations,
            "required_commands": self.required_commands,
            "host_patterns": self.host_patterns,
            "example_invocations": self.example_invocations,
            "supports_probe": self.supports_probe,
            "probe_operations": self.probe_operations,
            "probe_coverage": "full" if self.supports_probe else "none",
            "install_hints": self.install_hints,
            "operation_contracts": self.operation_contracts,
        }


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

    results = doctor.check_all(tmp_config)
    assert results["web"]["name"] == "web"
    assert results["web"]["description"] == "Any web page"
    assert results["web"]["status"] == "ok"
    assert results["web"]["operation_statuses"]["read"]["status"] == "ok"
    assert results["web"]["operation_contracts"]["read"]["input_kind"] == "url"
    assert results["web"]["probe_operations"] == ["read"]
    assert results["web"]["probe_run_coverage"] == "not_run"
    assert results["web"]["unprobed_operations"] == ["read"]
    assert results["github"]["backends"] == ["gh"]
    assert results["twitter"]["tier"] == 1
    assert results["twitter"]["supports_probe"] is True


def test_check_all_uses_probe_when_requested(tmp_config, monkeypatch):
    monkeypatch.setattr(doctor, "get_all_channels", lambda: [_StubChannel("web", "Any web page", 0, "warn", "ignored")])

    results = doctor.check_all(tmp_config, probe=True)
    assert results["web"]["status"] == "ok"
    assert results["web"]["message"] == "probe:web"
    assert results["web"]["probed_operations"] == ["read"]
    assert results["web"]["unprobed_operations"] == []
    assert results["web"]["probe_run_coverage"] == "full"


def test_check_all_skips_probe_for_channels_without_probe_support(tmp_config, monkeypatch):
    class _NoProbeChannel(_StubChannel):
        supports_probe = False

        def probe(self, config=None):
            raise AssertionError("probe should not run when supports_probe is false")

    monkeypatch.setattr(
        doctor,
        "get_all_channels",
        lambda: [_NoProbeChannel("crawl4ai", "Browser-backed page reads", 2, "ok", "ready")],
    )

    results = doctor.check_all(tmp_config, probe=True)
    assert results["crawl4ai"]["status"] == "ok"
    assert results["crawl4ai"]["message"] == "ready"
    assert results["crawl4ai"]["probe_run_coverage"] == "unsupported"
    assert results["crawl4ai"]["probed_operations"] == []


def test_check_all_includes_extra_machine_readable_fields(tmp_config, monkeypatch):
    class _DetailedChannel(_StubChannel):
        def check(self, config=None):
            return "warn", "details available", {"operation_statuses": {"search": {"status": "warn"}}}

    monkeypatch.setattr(
        doctor,
        "get_all_channels",
        lambda: [_DetailedChannel("twitter", "Twitter/X search and timeline access", 1, "warn", "unused")],
    )

    results = doctor.check_all(tmp_config)
    assert results["twitter"]["operation_statuses"]["search"]["status"] == "warn"
    assert results["twitter"]["probe_run_coverage"] == "not_run"


def test_format_report_groups_core_and_optional():
    report = doctor.format_report(
        {
            "web": {
                "status": "ok",
                "name": "web",
                "description": "Any web page",
                "message": "Jina Reader is ready",
                "tier": 0,
                "backends": ["Jina"],
            },
            "exa_search": {
                "status": "off",
                "name": "exa_search",
                "description": "Cross-web search via Exa",
                "message": "mcporter missing",
                "tier": 0,
                "backends": ["mcporter"],
            },
            "twitter": {
                "status": "warn",
                "name": "twitter",
                "description": "Twitter/X search and timeline access",
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
    assert "Not ready: Cross-web search via Exa" in plain
    assert "Advisory only: Twitter/X search and timeline access" in plain


def test_doctor_payload_and_exit_code():
    results = {
        "web": {"name": "web", "description": "Any web page", "status": "ok", "message": "ok", "tier": 0},
        "github": {
            "name": "github",
            "description": "GitHub repositories and code search",
            "status": "warn",
            "message": "auth missing",
            "tier": 0,
        },
    }

    payload = doctor.make_doctor_payload(results, probe=True)
    assert payload["schema_version"]
    assert payload["probe"] is True
    assert payload["summary"]["ready"] == 1
    assert payload["summary"]["exit_policy"] == "core"
    assert payload["summary"]["exit_code"] == 1
    assert payload["summary"]["blocking_not_ready"] == ["github"]
    assert payload["summary"]["advisory_not_ready"] == []
    assert payload["channels"][0]["name"] == "web"
    assert doctor.doctor_exit_code(results) == 1


def test_doctor_exit_policy_core_ignores_optional_setup_gaps():
    results = {
        "web": {"name": "web", "description": "Any web page", "status": "ok", "message": "ok", "tier": 0},
        "twitter": {
            "name": "twitter",
            "description": "Twitter/X",
            "status": "warn",
            "message": "unprobed",
            "tier": 1,
        },
        "crawl4ai": {
            "name": "crawl4ai",
            "description": "Crawl4AI",
            "status": "off",
            "message": "missing extra",
            "tier": 2,
        },
    }

    payload = doctor.make_doctor_payload(results)

    assert doctor.doctor_exit_code(results) == 0
    assert doctor.doctor_exit_code(results, exit_policy="all") == 1
    assert payload["summary"]["exit_code"] == 0
    assert payload["summary"]["blocking_not_ready"] == []
    assert payload["summary"]["advisory_not_ready"] == ["twitter", "crawl4ai"]


def test_doctor_exit_policy_core_error_is_blocking_even_for_optional():
    results = {
        "web": {"name": "web", "description": "Any web page", "status": "ok", "message": "ok", "tier": 0},
        "reddit": {
            "name": "reddit",
            "description": "Reddit",
            "status": "error",
            "message": "health crashed",
            "tier": 2,
        },
    }

    payload = doctor.make_doctor_payload(results)

    assert doctor.doctor_exit_code(results) == 1
    assert payload["summary"]["blocking_not_ready"] == ["reddit"]
    assert payload["summary"]["advisory_not_ready"] == []


def test_doctor_exit_policy_core_off_returns_exit_2():
    results = {
        "web": {"name": "web", "description": "Any web page", "status": "off", "message": "missing", "tier": 0},
    }

    assert doctor.doctor_exit_code(results) == 2


def test_check_all_handles_channel_crash(tmp_config, monkeypatch):
    class _BrokenChannel(_StubChannel):
        def check(self, config=None):
            raise RuntimeError("broken")

    monkeypatch.setattr(
        doctor,
        "get_all_channels",
        lambda: [_BrokenChannel("web", "Any web page", 0, "ok", "unused")],
    )

    results = doctor.check_all(tmp_config)
    assert results["web"]["status"] == "error"
    assert "Health check crashed" in results["web"]["message"]
