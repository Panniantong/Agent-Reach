# -*- coding: utf-8 -*-
"""Tests for repo-shipped integration artifacts."""

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from agent_reach.integrations.codex import export_codex_integration


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_codex_plugin_manifest_exists_and_is_valid():
    manifest_path = _repo_root() / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "agent-reach"
    assert manifest["skills"] == "../agent_reach/skills"
    assert manifest["mcpServers"] == "../.mcp.json"
    assert manifest["interface"]["displayName"] == "Agent Reach"
    assert "Collection" in manifest["interface"]["capabilities"]
    assert "Orchestration" in manifest["interface"]["capabilities"]
    assert len(manifest["interface"]["defaultPrompt"]) == 3


def test_mcp_config_contains_exa():
    mcp_path = _repo_root() / ".mcp.json"
    payload = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert payload["mcpServers"]["exa"]["url"] == "https://mcp.exa.ai/mcp"


def test_setup_agent_reach_action_installs_from_repo_root():
    action_path = _repo_root() / ".github" / "actions" / "setup-agent-reach" / "action.yml"
    action_text = action_path.read_text(encoding="utf-8")
    action = yaml.safe_load(action_text)

    assert action["name"] == "Setup Agent Reach"
    assert action["runs"]["using"] == "composite"
    assert 'repo_root="$(cd "$GITHUB_ACTION_PATH/../../.." && pwd)"' in action_text
    assert 'uv tool install --force "$repo_root"' in action_text
    assert "install-reddit-cli" in action["inputs"]
    assert 'uv tool install --force rdt-cli' in action_text
    assert "install-twitter-cli" in action["inputs"]


def test_agent_reach_smoke_workflow_collects_and_uploads_raw_artifacts():
    workflow_path = _repo_root() / ".github" / "workflows" / "agent-reach-smoke.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert "workflow_dispatch" in workflow["on"]
    assert "uses: ./.github/actions/setup-agent-reach" in workflow_text
    assert "agent-reach doctor --json" in workflow_text
    assert "agent-reach collect --json --save" in workflow_text
    assert "agent-reach plan candidates" in workflow_text
    assert "actions/upload-artifact" in workflow_text
    assert ".agent-reach/evidence.jsonl" in workflow_text
    assert ".agent-reach/candidates.json" in workflow_text


def test_downstream_examples_are_collect_only_patterns():
    example_paths = [
        _repo_root() / "examples" / "research-ledger.ps1",
        _repo_root() / "examples" / "discord_news_collect.ps1",
    ]

    for path in example_paths:
        text = path.read_text(encoding="utf-8")
        assert "agent-reach collect --json --save" in text
        assert "agent-reach plan candidates" in text
        assert ".codex-plugin" not in text
        assert ".mcp.json" not in text
        assert "agent_reach" not in text
        assert "Copy-Item" not in text


def test_export_points_at_existing_checkout_artifacts():
    payload = export_codex_integration()

    assert payload["client"] == "codex"
    assert payload["profile"] == "full"
    assert payload["execution_context"] == "checkout"
    assert payload["plugin_manifest"] is not None
    assert payload["mcp_config"] is not None
    assert Path(payload["plugin_manifest"]).exists()
    assert Path(payload["mcp_config"]).exists()
    assert all(Path(path).exists() for path in payload["recommended_docs"])
    assert {Path(path).name for path in payload["recommended_docs"]} == {
        "install.md",
        "codex-integration.md",
        "downstream-usage.md",
        "python-sdk.md",
        "troubleshooting.md",
    }
    channel_contracts = {channel["name"]: channel for channel in payload["channels"]}
    assert channel_contracts["qiita"]["operation_contracts"]["search"]["options"][0]["name"] == "body_mode"
    assert channel_contracts["qiita"]["operation_contracts"]["search"]["options"][1]["name"] == "page_size"
    assert channel_contracts["qiita"]["operation_contracts"]["search"]["options"][1]["minimum"] == 1
    assert channel_contracts["github"]["operation_contracts"]["search"]["options"][0]["name"] == "page_size"
    assert channel_contracts["github"]["operation_contracts"]["search"]["options"][2]["name"] == "page"
    assert channel_contracts["bluesky"]["operation_contracts"]["search"]["options"][2]["name"] == "cursor"
    assert channel_contracts["crawl4ai"]["operation_contracts"]["crawl"]["options"][0]["sdk_kwarg"] == "crawl_query"
    assert channel_contracts["twitter"]["operation_contracts"]["search"]["options"][0]["name"] == "since"
    assert channel_contracts["twitter"]["operation_contracts"]["search"]["options"][1]["name"] == "until"
    assert channel_contracts["twitter"]["probe_operations"] == ["user", "search"]
    assert channel_contracts["twitter"]["probe_coverage"] == "partial"
    assert channel_contracts["youtube"]["probe_coverage"] == "full"
    assert channel_contracts["reddit"]["auth_kind"] == "none"
    assert channel_contracts["reddit"]["required_commands"] == ["rdt"]
    assert channel_contracts["hacker_news"]["operations"][0] == "search"
    assert channel_contracts["mcp_registry"]["operations"] == ["search", "read"]
    assert payload["skill"]["names"] == [
        "agent-reach",
        "agent-reach-shape-brief",
        "agent-reach-orchestrate",
        "agent-reach-propose-improvements",
        "agent-reach-maintain-proposals",
        "agent-reach-maintain-release",
    ]
    assert payload["skill"]["targets"]
    assert Path(payload["skill"]["source"]).exists()
    assert payload["python_sdk"]["availability"] == "project_env_only"
    assert payload["python_sdk"]["import"] == "from agent_reach import AgentReachClient"
    assert any("client.exa_search.search" in line for line in payload["python_sdk"]["quickstart"])
    assert any("mirror stable channel names" in line for line in payload["python_sdk"]["notes"])
    assert any("SDK-only shortcuts" in line for line in payload["python_sdk"]["notes"])
    assert payload["readiness_controls"]["doctor_args"][0] == "--require-channel <name>"
    assert "required_not_ready" in payload["readiness_controls"]["summary_fields"]
    assert payload["external_project_usage"]["copy_files_required"] is False
    assert payload["external_project_usage"]["preferred_interface"] == "agent-reach collect --json"
    assert payload["codex_runtime_policy"]["default_interface"] == "agent-reach collect --json"
    assert "Do not copy" in payload["codex_runtime_policy"]["no_copy_rule"]
    request_scale_policy = payload["codex_runtime_policy"]["request_scale_policy"]
    assert request_scale_policy["single_collect"]["pattern"] == "single normalized collect or read"
    assert request_scale_policy["bounded_multi_source"]["pattern"] == "caller-chosen small multi-source collection"
    assert request_scale_policy["large_scale_research"]["explicit_opt_in"] is True
    assert any("does not choose request scale" in item for item in request_scale_policy["rules"])
    assert any("default `--limit 20`" in item for item in request_scale_policy["rules"])
    assert payload["codex_runtime_policy"]["large_scale_research"]["pattern"] == "bounded fan-out with normalized JSON handoff"
    assert any("hacker_news" in command for command in payload["verification_commands"])
    assert any("mcp_registry" in command for command in payload["verification_commands"])
    assert any(command.startswith("agent-reach collect ") for command in payload["verification_commands"])
    assert any("--profile runtime-minimal" in command for command in payload["verification_commands"])


def test_export_runtime_minimal_omits_bootstrap_payloads():
    payload = export_codex_integration(profile="runtime-minimal")

    assert payload["client"] == "codex"
    assert payload["profile"] == "runtime-minimal"
    assert "channels" not in payload
    assert "plugin_manifest_inline" not in payload
    assert "mcp_config_inline" not in payload
    assert payload["positioning"] == ["integration_helper", "runtime_policy"]
    assert "github" in payload["channel_names"]
    assert payload["skill"]["names"] == [
        "agent-reach",
        "agent-reach-shape-brief",
        "agent-reach-orchestrate",
        "agent-reach-propose-improvements",
        "agent-reach-maintain-proposals",
        "agent-reach-maintain-release",
    ]
    assert payload["codex_runtime_policy"]["default_interface"] == "agent-reach collect --json"
    assert any("--item-text-mode snippet" in command for command in payload["verification_commands"])
    assert any("runtime-minimal omits full channel contracts" in note for note in payload["notes"])


def test_export_tool_install_omits_dead_paths(tmp_path):
    fake_repo_root = tmp_path / "site-packages"
    fake_repo_root.mkdir(parents=True)

    with patch("agent_reach.integrations.codex._repo_root", return_value=fake_repo_root), patch(
        "agent_reach.integrations.codex._current_working_dir",
        return_value=tmp_path / "consumer-project",
    ):
        payload = export_codex_integration()

    assert payload["execution_context"] == "tool_install"
    assert payload["profile"] == "full"
    assert payload["plugin_manifest"] is None
    assert payload["mcp_config"] is None
    assert payload["recommended_docs"] == []
    assert payload["plugin_manifest_inline"]["name"] == "agent-reach"
    assert payload["plugin_manifest_inline"]["skills"] == payload["skill"]["source"]
    assert payload["plugin_manifest_inline"]["mcpServers"] == "../.mcp.json"
    assert payload["mcp_config_inline"]["mcpServers"]["exa"]["url"] == "https://mcp.exa.ai/mcp"
    assert payload["skill"]["names"] == [
        "agent-reach",
        "agent-reach-shape-brief",
        "agent-reach-orchestrate",
        "agent-reach-propose-improvements",
        "agent-reach-maintain-proposals",
        "agent-reach-maintain-release",
    ]
    plugin_destination = Path(payload["suggested_destinations"]["plugin_manifest"])
    mcp_destination = Path(payload["suggested_destinations"]["mcp_config"])
    assert plugin_destination.parts[-2:] == (".codex-plugin", "plugin.json")
    assert mcp_destination.name == ".mcp.json"
    assert payload["documentation_summary"]
    assert any("latest fork build" in item for item in payload["documentation_summary"])
    assert any("ledger validate" in item for item in payload["documentation_summary"])
    assert any("--require-channel" in item for item in payload["documentation_summary"])
    assert any("YouTube collection exposes" in item for item in payload["documentation_summary"])
    assert any("probe_attention" in item for item in payload["documentation_summary"])
    assert any("validate-only" in item for item in payload["documentation_summary"])
    assert payload["inline_payload_notes"]
    assert payload["readiness_controls"]["summary_fields"][-1] == "probe_attention"
    assert payload["external_project_usage"]["github_actions"]["uses"].startswith("iwachacha/Agent-Reach/")
    assert any("agent-reach[crawl4ai]" in note for note in payload["external_project_usage"]["github_actions"]["notes"])
    assert payload["codex_runtime_policy"]["large_scale_research"]["recommended_limits"]["discovery"] == 10
    assert any("required_not_ready" in item for item in payload["codex_runtime_policy"]["decision_order"])
    assert any("probe_attention" in item for item in payload["codex_runtime_policy"]["decision_order"])
    assert any("authenticated-but-unprobed" in item for item in payload["codex_runtime_policy"]["failure_policy"])
