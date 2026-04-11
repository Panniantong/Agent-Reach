# -*- coding: utf-8 -*-
"""Codex-oriented integration exports for Agent Reach."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_reach import __version__
from agent_reach.channels import get_all_channel_contracts
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp

EXA_SERVER_URL = "https://mcp.exa.ai/mcp"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _packaged_skill_source() -> Path:
    return Path(__file__).resolve().parents[1] / "skill"


def _current_working_dir() -> Path:
    return Path.cwd()


def _candidate_skill_roots() -> list[Path]:
    roots: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home) / "skills")
    roots.append(Path.home() / ".codex" / "skills")
    roots.append(Path.home() / ".agents" / "skills")
    return roots


def _required_commands(channels: list[dict]) -> list[str]:
    commands = set()
    for channel in channels:
        commands.update(channel.get("required_commands", []))
    return sorted(commands)


def _mcp_snippet() -> dict[str, Any]:
    return {
        "mcpServers": {
            "exa": {
                "type": "http",
                "url": EXA_SERVER_URL,
            }
        }
    }


def _artifact_paths(repo_root: Path) -> dict[str, Path]:
    return {
        "plugin_manifest": repo_root / ".codex-plugin" / "plugin.json",
        "mcp_config": repo_root / ".mcp.json",
        "docs_codex_integration": repo_root / "docs" / "codex-integration.md",
        "docs_codex_compatibility": repo_root / "docs" / "codex-compatibility.md",
        "docs_downstream_usage": repo_root / "docs" / "downstream-usage.md",
        "docs_python_sdk": repo_root / "docs" / "python-sdk.md",
        "docs_field_research_improvements": repo_root / "docs" / "field-research-improvements-2026-04-10.md",
        "docs_agent_reach_nexus_concept": repo_root / "docs" / "agent-reach-nexus-concept.md",
    }


def _execution_context(repo_root: Path) -> str:
    paths = _artifact_paths(repo_root)
    if paths["plugin_manifest"].exists() and paths["mcp_config"].exists():
        return "checkout"
    return "tool_install"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _existing_path(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _recommended_docs(repo_root: Path) -> list[str]:
    docs = [
        _artifact_paths(repo_root)["docs_codex_integration"],
        _artifact_paths(repo_root)["docs_codex_compatibility"],
        _artifact_paths(repo_root)["docs_downstream_usage"],
        _artifact_paths(repo_root)["docs_python_sdk"],
        _artifact_paths(repo_root)["docs_field_research_improvements"],
        _artifact_paths(repo_root)["docs_agent_reach_nexus_concept"],
    ]
    return [str(path) for path in docs if path.exists()]


def _suggested_destinations(execution_context: str, repo_root: Path) -> dict[str, str]:
    base_dir = repo_root if execution_context == "checkout" else _current_working_dir()
    return {
        "plugin_manifest": str(base_dir / ".codex-plugin" / "plugin.json"),
        "mcp_config": str(base_dir / ".mcp.json"),
    }


def _default_plugin_manifest(skill_source: str, mcp_config_path: str) -> dict[str, Any]:
    return {
        "name": "agent-reach",
        "version": __version__,
        "description": "Windows-first research integration substrate for Codex and similar agents.",
        "author": {
            "name": "Neo Reid",
        },
        "license": "MIT",
        "keywords": [
            "codex",
            "windows",
            "research",
            "mcp",
            "diagnostics",
            "integration",
        ],
        "skills": skill_source,
        "mcpServers": mcp_config_path,
        "interface": {
            "displayName": "Agent Reach",
            "shortDescription": "Windows/Codex research integration substrate",
            "longDescription": (
                "Bootstraps, documents, diagnoses, and exposes thin read-only collection "
                "for downstream Codex workflows on Windows."
            ),
            "developerName": "Neo Reid",
            "category": "Developer Tools",
            "capabilities": [
                "Readiness",
                "Registry",
                "Collection",
            ],
            "defaultPrompt": [
                "Show me which research channels are ready on this Windows machine.",
                "Export the Codex integration settings for Agent Reach.",
                "List the supported channels and their setup requirements.",
                (
                    "Run a read-only collection using the live channel contract, including web, Exa, "
                    "GitHub, Hatena Bookmark, Bluesky, Qiita, YouTube, RSS, SearXNG, Crawl4AI, "
                    "Hacker News, MCP Registry, Reddit, or optional Twitter/X."
                ),
            ],
            "brandColor": "#0F766E",
        },
    }


def _tool_install_plugin_mcp_reference() -> str:
    """Return the MCP reference expected after writing to the suggested Codex paths."""

    return "../.mcp.json"


def _plugin_manifest_inline(
    repo_root: Path,
    execution_context: str,
    skill_source: str,
) -> dict[str, Any]:
    payload = _read_json(_artifact_paths(repo_root)["plugin_manifest"])
    if payload is not None and execution_context == "checkout":
        return payload
    mcp_reference = (
        _tool_install_plugin_mcp_reference()
        if execution_context == "tool_install"
        else "../.mcp.json"
    )
    return _default_plugin_manifest(skill_source, mcp_reference)


def _mcp_config_inline(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(_artifact_paths(repo_root)["mcp_config"])
    return payload if payload is not None else _mcp_snippet()


def _documentation_summary() -> list[str]:
    return [
        "Use `agent-reach collect --json` as the primary external interface in arbitrary projects.",
        "Inspect `agent-reach channels --json` operation contracts before choosing per-channel options such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` downstream.",
        "Add `--save .agent-reach/evidence.jsonl` when a research run needs an auditable raw CollectionResult ledger.",
        "Use `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json` before treating saved evidence as a CI artifact.",
        "Use `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json` to add a successful conditional collection captured without `--save`.",
        "Use `agent-reach plan candidates --input .agent-reach/evidence.jsonl --json` for no-model URL or ID dedupe before follow-up reads.",
        "`doctor --json` defaults to core exit policy: tier 0 channels affect the exit code, while optional setup gaps are listed under `summary.advisory_not_ready`.",
        "Treat `extras.source_hints`, `extras.media_references`, and web extraction hygiene metadata as diagnostics only, not ranking or trust scores.",
        "YouTube collection exposes video metadata, subtitle/caption availability, thumbnail references, and normalized linked media references, not video binary analysis.",
        "Use `agent-reach channels --json`, `doctor --json`, and `doctor --json --probe` for discovery and diagnostics.",
        "Tool installs expose the CLI. Import `AgentReachClient` only after installing Agent Reach into the caller Python environment.",
        "If `plugin_manifest` or `mcp_config` is null, write the inline payloads to the suggested destinations instead.",
    ]


def _inline_payload_notes() -> list[str]:
    return [
        "Write `plugin_manifest_inline` to `suggested_destinations.plugin_manifest` and `mcp_config_inline` to `suggested_destinations.mcp_config`.",
        "`plugin_manifest_inline.mcpServers` is a relative reference that resolves after both inline payloads are written to the suggested Codex paths.",
    ]


def _external_project_usage() -> dict[str, Any]:
    """Describe the no-copy downstream integration paths."""

    return {
        "copy_files_required": False,
        "preferred_interface": "agent-reach collect --json",
        "codex_global_install": {
            "commands": [
                "uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git",
                "agent-reach skill --install",
                "agent-reach doctor --json --probe",
            ],
            "notes": [
                "The skill install writes to the user's Codex skill home, not to the downstream project.",
                "Downstream projects do not need `.codex-plugin`, `.mcp.json`, or `agent_reach/skill` files when using the CLI.",
            ],
        },
        "github_actions": {
            "uses": "iwachacha/Agent-Reach/.github/actions/setup-agent-reach@main",
            "notes": [
                "Use the composite action to install the CLI in the workflow without vendoring Agent Reach files.",
                "Pin `uses` to a tag or commit for reproducible automation.",
                "Install `agent-reach[crawl4ai]` plus `python -m playwright install chromium` in jobs that need browser-backed reads.",
                "Keep scheduling, ranking, summarization, state, and Discord publishing in the downstream project.",
            ],
        },
        "discord_bot": {
            "recommended_pattern": "subprocess collector",
            "notes": [
                "Call `agent-reach collect --json` per source and map `items` into the bot's normalized item type.",
                "Use `--save .agent-reach/evidence.jsonl` when the bot or CI job needs a raw evidence artifact.",
                "Use `agent-reach plan candidates` when the bot or CI job wants a no-model dedupe pass before deeper reads.",
                "Use source hints and web hygiene fields only as diagnostics; keep scoring and posting policy in the bot.",
                "Treat optional channels as capability surfaces; gate them with `channels --json`, `doctor --json`, and `doctor --json --probe` when reliability matters.",
                "Validate saved evidence with `agent-reach ledger validate --json` before downstream ingestion.",
            ],
        },
    }


def _codex_runtime_policy() -> dict[str, Any]:
    """Give Codex a compact, explicit operating policy for arbitrary projects."""

    return {
        "default_interface": "agent-reach collect --json",
        "no_copy_rule": (
            "Use the globally installed CLI and skill. Do not copy `.codex-plugin`, `.mcp.json`, "
            "or Agent Reach source files into a downstream repository unless the user explicitly asks for repo-local artifacts."
        ),
        "decision_order": [
            "If readiness is unknown, run `agent-reach channels --json` and `agent-reach doctor --json` first.",
            "Read `doctor.summary.blocking_not_ready` and `doctor.summary.advisory_not_ready`; use `--exit-policy all` only when every optional channel must be ready.",
            "Inspect the live channel contract and let the calling workflow choose channels for the user's task.",
            "Inspect `operation_contracts` and let the calling workflow choose bounded pagination or time-window inputs such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` when a channel supports them.",
            "Use specialist channels such as `github`, `qiita`, `bluesky`, `rss`, `youtube`, `hatena_bookmark`, `hacker_news`, `mcp_registry`, `reddit`, `searxng`, or `crawl4ai` only when the caller's task and readiness checks support them.",
            "Use Twitter/X only when optional credentials and `doctor --json --probe` show the required operation is ready.",
            "Treat `source_hints`, `media_references`, `text_length`, `link_count`, and `extraction_warning` as diagnostic metadata only.",
            "Keep ranking, summarization, scheduling, Discord publishing, and state in the downstream project.",
        ],
        "large_scale_research": {
            "pattern": "bounded fan-out with normalized JSON handoff",
            "steps": [
                "Start with 2-4 broad discovery queries at small limits such as 5-10.",
                "Inspect `channels --json` operation contracts and choose any page, cursor, or time-window options downstream instead of relying on a fixed Agent Reach route.",
                "Append raw collection envelopes with `--save .agent-reach/evidence.jsonl` when traceability matters.",
                "Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by url --limit 20 --json` for no-model dedupe.",
                "Apply downstream ranking, summarization, and selection before deeper reads.",
                "Fan out `web read` only for selected high-signal URLs.",
                "Inspect web extraction warnings and source hints as non-authoritative diagnostics.",
                "Persist raw `CollectionResult` JSONL ledgers as artifacts when running in CI.",
                "Treat per-channel failures as partial results unless the user asked for strict completeness.",
            ],
            "recommended_limits": {
                "discovery": 10,
                "source_specific_search": 20,
                "deep_reads_per_round": 10,
            },
        },
        "failure_policy": [
            "Do not fall back to backend-specific CLIs unless debugging a failed Agent Reach operation.",
            "If `doctor --json` marks an optional channel warn, continue with ready channels unless that channel is essential.",
            "For optional or credential/runtime-gated channels, report operation-level readiness and the JSON error envelope separately.",
            "For Twitter/X, authenticated-but-unprobed `warn` means collection may work but operation readiness is unverified until `doctor --json --probe`.",
        ],
    }


def export_codex_integration() -> dict[str, Any]:
    """Return the stable integration payload for Codex on Windows."""

    repo_root = _repo_root()
    execution_context = _execution_context(repo_root)
    artifact_paths = _artifact_paths(repo_root)
    channels = get_all_channel_contracts()
    skill_source = str(_packaged_skill_source())
    suggested_destinations = _suggested_destinations(execution_context, repo_root)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "client": "codex",
        "platform": "windows",
        "execution_context": execution_context,
        "positioning": [
            "bootstrapper",
            "channel_registry",
            "readiness_layer",
            "integration_helper",
        ],
        "channels": channels,
        "required_commands": _required_commands(channels),
        "skill": {
            "source": skill_source,
            "targets": [str(root / "agent-reach") for root in _candidate_skill_roots()],
        },
        "plugin_manifest": _existing_path(artifact_paths["plugin_manifest"]),
        "plugin_manifest_inline": _plugin_manifest_inline(
            repo_root,
            execution_context,
            skill_source,
        ),
        "mcp_config": _existing_path(artifact_paths["mcp_config"]),
        "mcp_config_inline": _mcp_config_inline(repo_root),
        "suggested_destinations": suggested_destinations,
        "inline_payload_notes": _inline_payload_notes(),
        "mcp_snippet": _mcp_snippet(),
        "external_project_usage": _external_project_usage(),
        "codex_runtime_policy": _codex_runtime_policy(),
        "verification_commands": [
            "agent-reach channels --json",
            "agent-reach doctor --json",
            "agent-reach doctor --json --probe",
            'agent-reach collect --channel github --operation read --input "openai/openai-python" --json',
            'agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json',
            'agent-reach collect --channel web --operation read --input "https://example.com" --json',
            'agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json',
            'agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 3 --json',
            "agent-reach export-integration --client codex --format json",
        ],
        "python_sdk": {
            "availability": "project_env_only",
            "import": "from agent_reach import AgentReachClient",
            "install_examples": [
                "uv pip install -e C:\\path\\to\\Agent-Reach",
                "uv pip install C:\\path\\to\\dist\\agent_reach-<version>-py3-none-any.whl",
            ],
            "quickstart": [
                "from agent_reach import AgentReachClient",
                "client = AgentReachClient()",
                'client.github.read("openai/openai-python")',
                'client.collect("github", "search", "agent reach", limit=5, page_size=2, max_pages=2)',
            ],
            "notes": [
                "uv tool install exposes the agent-reach CLI, not a general Python import in arbitrary projects.",
            ],
        },
        "recommended_docs": _recommended_docs(repo_root),
        "documentation_summary": _documentation_summary(),
    }


def render_codex_integration_text(payload: dict[str, Any]) -> str:
    """Render a human-readable integration summary."""

    lines = [
        "Agent Reach integration export for Codex on Windows",
        "========================================",
        "",
        f"Execution context: {payload['execution_context']}",
        "Positioning:",
        "  bootstrapper, channel registry, readiness layer, integration helper",
        "",
    ]
    if payload["plugin_manifest"]:
        lines.append(f"Plugin manifest: {payload['plugin_manifest']}")
    else:
        lines.append("Plugin manifest: not bundled in this tool install")
        lines.append(f"Suggested destination: {payload['suggested_destinations']['plugin_manifest']}")
    if payload["mcp_config"]:
        lines.append(f"MCP config: {payload['mcp_config']}")
    else:
        lines.append("MCP config: not bundled in this tool install")
        lines.append(f"Suggested destination: {payload['suggested_destinations']['mcp_config']}")
    lines.append(f"Skill source: {payload['skill']['source']}")
    lines.append("Skill targets:")
    for target in payload["skill"]["targets"]:
        lines.append(f"  {target}")

    if payload["recommended_docs"]:
        lines.extend(["", "Recommended docs:"])
        for path in payload["recommended_docs"]:
            lines.append(f"  {path}")
    else:
        lines.extend(["", "Documentation summary:"])
        for line in payload["documentation_summary"]:
            lines.append(f"  {line}")

    lines.extend(["", "Inline payload notes:"])
    for line in payload["inline_payload_notes"]:
        lines.append(f"  {line}")

    lines.extend(["", "Python SDK:"])
    lines.append(f"  availability: {payload['python_sdk']['availability']}")
    for line in payload["python_sdk"]["notes"]:
        lines.append(f"  {line}")

    lines.extend(["", "External project usage:"])
    lines.append(
        "  copy files required: "
        f"{'yes' if payload['external_project_usage']['copy_files_required'] else 'no'}"
    )
    lines.append(f"  preferred interface: {payload['external_project_usage']['preferred_interface']}")
    lines.append(f"  Codex default interface: {payload['codex_runtime_policy']['default_interface']}")
    lines.append(f"  no-copy rule: {payload['codex_runtime_policy']['no_copy_rule']}")

    lines.extend(["", "Required commands:"])
    for command in payload["required_commands"]:
        lines.append(f"  {command}")

    lines.extend(["", "Verification commands:"])
    for command in payload["verification_commands"]:
        lines.append(f"  {command}")
    return "\n".join(lines)


def render_codex_integration_powershell(payload: dict[str, Any]) -> str:
    """Render a PowerShell-oriented export snippet."""

    skill_targets = ",\n".join(f'  "{target}"' for target in payload["skill"]["targets"])
    plugin_manifest_json = json.dumps(payload["plugin_manifest_inline"], indent=2, ensure_ascii=False)
    mcp_config_json = json.dumps(payload["mcp_config_inline"], indent=2, ensure_ascii=False)
    plugin_manifest_path = payload["plugin_manifest"] or payload["suggested_destinations"]["plugin_manifest"]
    mcp_config_path = payload["mcp_config"] or payload["suggested_destinations"]["mcp_config"]
    return "\n".join(
        [
            "# Agent Reach integration export for Codex on Windows",
            f'$executionContext = "{payload["execution_context"]}"',
            f'$pluginManifestPath = "{plugin_manifest_path}"',
            f'$mcpConfigPath = "{mcp_config_path}"',
            f'$skillSource = "{payload["skill"]["source"]}"',
            "$skillTargets = @(",
            skill_targets,
            ")",
            "",
            "# Write these inline payloads if the file paths above do not exist yet.",
            "$pluginManifestJson = @'",
            plugin_manifest_json,
            "'@",
            "",
            "$mcpConfigJson = @'",
            mcp_config_json,
            "'@",
            "",
            "# Verification commands",
            "agent-reach channels --json",
            "agent-reach doctor --json",
            "agent-reach doctor --json --probe",
            'agent-reach collect --channel github --operation read --input "openai/openai-python" --json',
            'agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json',
        ]
    )
