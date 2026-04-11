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
PACKAGED_SKILL_NAMES = (
    "agent-reach",
    "agent-reach-shape-brief",
    "agent-reach-orchestrate",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def packaged_skill_source() -> Path:
    return Path(__file__).resolve().parents[1] / "skills"


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


def _candidate_skill_targets() -> list[Path]:
    targets: list[Path] = []
    for root in _candidate_skill_roots():
        for skill_name in PACKAGED_SKILL_NAMES:
            targets.append(root / skill_name)
    return targets


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
        "docs_install": repo_root / "docs" / "install.md",
        "docs_codex_integration": repo_root / "docs" / "codex-integration.md",
        "docs_downstream_usage": repo_root / "docs" / "downstream-usage.md",
        "docs_python_sdk": repo_root / "docs" / "python-sdk.md",
        "docs_troubleshooting": repo_root / "docs" / "troubleshooting.md",
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
        _artifact_paths(repo_root)["docs_install"],
        _artifact_paths(repo_root)["docs_codex_integration"],
        _artifact_paths(repo_root)["docs_downstream_usage"],
        _artifact_paths(repo_root)["docs_python_sdk"],
        _artifact_paths(repo_root)["docs_troubleshooting"],
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
        "description": "Windows-first research integration and orchestration suite for Codex.",
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
            "shortDescription": "Windows/Codex research integration and orchestration",
            "longDescription": (
                "Bootstraps, documents, diagnoses, and exposes thin read-only collection "
                "plus in-session orchestration skills for downstream Codex research workflows on Windows."
            ),
            "developerName": "Neo Reid",
            "category": "Developer Tools",
            "capabilities": [
                "Readiness",
                "Registry",
                "Collection",
                "Orchestration",
            ],
            "defaultPrompt": [
                "Show me which research channels are ready on this Windows machine.",
                "Turn this rough research request into a structured Agent Reach brief.",
                "Take this rough research ask, decide whether one intake subagent is worth using, and start the Agent Reach investigation.",
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
        "Install the latest fork build from `git+https://github.com/iwachacha/Agent-Reach.git` or pin a commit/ref when reproducibility matters.",
        "`agent-reach skill --install` installs the bundled Codex skill suite: `agent-reach`, `agent-reach-shape-brief`, and `agent-reach-orchestrate`.",
        "Use `agent-reach collect --json` as the primary external interface in arbitrary projects.",
        "Let the calling workflow choose request scale, channels, pagination, ranking, summarization, and posting; Agent Reach exposes capabilities but does not choose scope for the caller.",
        "Use `agent-reach-shape-brief` to normalize vague requests into a fixed research brief before execution when the request is underspecified.",
        "Use `agent-reach-orchestrate` to move a rough or structured ask to actual Agent Reach collection start in the same session.",
        "For most rough asks, `agent-reach-orchestrate` is the default entrypoint; use `agent-reach-shape-brief` only when you want to stop before collection starts.",
        "Use at most one brief-shaping subagent per request, and only when intake ambiguity would materially change the research route.",
        "Inspect `agent-reach channels --json` operation contracts before choosing per-channel options such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` downstream.",
        "Add `--save .agent-reach/evidence.jsonl` when a research run needs an auditable raw CollectionResult ledger.",
        "Use `agent-reach schema collection-result --json` when downstream code needs a contract-testable CollectionResult schema.",
        "Use `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json` before treating saved evidence as a CI artifact.",
        "Use `agent-reach ledger validate --input .agent-reach/evidence.jsonl --require-metadata --json` only when missing intent, query_id, or source_role should fail automation.",
        "Use `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json` for neutral evidence health counts.",
        "Use `agent-reach ledger query --input .agent-reach/evidence.jsonl --filter \"channel == github\" --json` for lightweight filtering and field projection over saved evidence.",
        "Use `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json` to add a successful conditional collection captured without `--save`.",
        "Use `agent-reach batch --plan PLAN.json --validate-only --json` as a non-mutating preflight before any large-scale batch run.",
        "Use `agent-reach plan candidates --input .agent-reach/evidence.jsonl --json` for no-model URL or ID dedupe before follow-up reads; callers may choose `--by normalized_url`, `--by source_item_id`, `--by domain`, or `--by repo`.",
        "Use `doctor --json` for flat readiness diagnostics and pass `--require-channel`, `--require-channels`, or `--require-all` only when the caller wants readiness to affect the exit code.",
        "Read `doctor.summary.required_channels`, `doctor.summary.required_not_ready`, `doctor.summary.informational_not_ready`, and `doctor.summary.probe_attention` to apply caller-defined readiness policy downstream.",
        "Inspect `doctor.summary.probe_attention` when a channel supports only partial probe coverage or a probe run left operations unprobed.",
        "Treat `engagement`, `media_references`, `identifiers`, `extras.source_hints`, `error.category`, social time-window warnings, and page extraction hygiene metadata such as text_length, link_count, image_count, link_density, and extraction_warning as diagnostics only, not ranking or trust scores.",
        "YouTube collection exposes video metadata, subtitle/caption availability, thumbnail references, and normalized linked media references, not video binary analysis.",
        "Use `agent-reach channels --json`, `doctor --json`, and `doctor --json --probe` for discovery and diagnostics.",
        "Tool installs expose the CLI. Import `AgentReachClient` only after installing Agent Reach into the caller Python environment.",
        "If `plugin_manifest` or `mcp_config` is null, write the inline payloads to the suggested destinations instead.",
        "Use `agent-reach check-update --json` as an upstream release check; the latest upstream release can lag the latest fork commit.",
        "After pushing a custom ref, refresh a global install with `uv tool install --force git+<remote-url>@<ref>` and then rerun `agent-reach skill --install`.",
    ]


def _inline_payload_notes() -> list[str]:
    return [
        "Write `plugin_manifest_inline` to `suggested_destinations.plugin_manifest` and `mcp_config_inline` to `suggested_destinations.mcp_config`.",
        "`plugin_manifest_inline.mcpServers` is a relative reference that resolves after both inline payloads are written to the suggested Codex paths.",
    ]


def _readiness_controls() -> dict[str, Any]:
    return {
        "doctor_args": [
            "--require-channel <name>",
            "--require-channels <a,b>",
            "--require-all",
        ],
        "summary_fields": [
            "required_channels",
            "required_not_ready",
            "informational_not_ready",
            "probe_attention",
        ],
        "notes": [
            "Agent Reach does not impose a fixed required-channel set.",
            "Downstream tools choose which channels must be ready for a given run.",
            "Without `--require-*`, doctor stays in diagnostic-only mode and reports readiness without enforcing a caller policy.",
        ],
    }


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
                "The skill install writes the bundled skill suite to the user's Codex skill home, not to the downstream project.",
                "Downstream projects do not need `.codex-plugin`, `.mcp.json`, or `agent_reach/skills` files when using the CLI.",
                "After pushing a custom ref, refresh the global install with `uv tool install --force git+<remote-url>@<ref>` and rerun `agent-reach skill --install`.",
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
                "Treat channels as flat capability surfaces; gate the caller's chosen channels with `channels --json`, `doctor --json`, `doctor --json --probe`, and caller-selected `--require-*` flags when reliability matters.",
                "Validate saved evidence with `agent-reach ledger validate --json` before downstream ingestion.",
            ],
        },
}


def _request_scale_policy() -> dict[str, Any]:
    """Describe caller-controlled request sizing for downstream integrations."""

    return {
        "principle": (
            "Agent Reach exposes flexible collection capabilities. The calling workflow chooses "
            "scope, routes, channels, ranking, summarization, and posting."
        ),
        "rules": [
            "Agent Reach does not choose request scale, collection routes, source mix, ranking, summarization, or posting.",
            "Keep light requests light; do not auto-escalate a narrow ask into large-scale research.",
            "`collect --json` remains the default interface for thin downstream collection.",
            "`batch` and `scout` are explicit opt-in helpers, not the default route for everyday collection.",
            "`plan candidates` keeps its default `--limit 20`; raise it only when the caller explicitly wants a wider review set.",
            "Large-scale research is explicit opt-in and should be requested by the caller or host workflow.",
        ],
        "single_collect": {
            "intent": "narrow asks and lightweight verification",
            "pattern": "single normalized collect or read",
            "recommended_commands": [
                "Run one `agent-reach collect --json` command, or a very small caller-chosen set of collection commands.",
                "Do not reach for `batch`, `scout`, or evidence-ledger fan-out unless the caller explicitly asks for a broader run.",
            ],
        },
        "bounded_multi_source": {
            "intent": "small comparisons and targeted cross-checks",
            "pattern": "caller-chosen small multi-source collection",
            "recommended_commands": [
                "Use a small number of `collect --json` calls across ready channels that match the task.",
                "Choose pagination and time-window controls from the live operation contract only when the caller wants them.",
                "Use `batch` only if the caller explicitly wants a plan-driven run; it is not required for bounded multi-source work.",
            ],
        },
        "large_scale_research": {
            "intent": "explicit opt-in broad research runs",
            "pattern": "bounded fan-out with normalized JSON handoff",
            "explicit_opt_in": True,
            "steps": [
                "Start with 2-4 broad discovery queries at small limits such as 5-10.",
                "Inspect `channels --json` operation contracts and choose any page, cursor, or time-window options downstream instead of relying on a fixed Agent Reach route.",
                "Run `agent-reach batch --plan PLAN.json --validate-only --json` before executing a saved batch plan.",
                "Append raw collection envelopes with `--save .agent-reach/evidence.jsonl` when traceability matters.",
                "Run `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json` when downstream automation needs neutral artifact health counts.",
                "Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json` for no-model dedupe.",
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
    }


def _codex_runtime_policy() -> dict[str, Any]:
    """Give Codex a compact, explicit operating policy for arbitrary projects."""

    request_scale_policy = _request_scale_policy()
    return {
        "default_interface": "agent-reach collect --json",
        "no_copy_rule": (
            "Use the globally installed CLI and skill suite. Do not copy `.codex-plugin`, `.mcp.json`, "
            "or Agent Reach source files into a downstream repository unless the user explicitly asks for repo-local artifacts."
        ),
        "decision_order": [
            "If readiness is unknown, run `agent-reach channels --json` and `agent-reach doctor --json` first.",
            "Read `doctor.summary.required_not_ready`, `doctor.summary.informational_not_ready`, and `doctor.summary.probe_attention`; let the caller choose `--require-channel`, `--require-channels`, or `--require-all` for the run.",
            "Let the caller choose request scale first: keep narrow asks as `collect`, use bounded multi-source collection only when needed, and treat large-scale research as explicit opt-in.",
            "Inspect the live channel contract and let the calling workflow choose channels for the user's task.",
            "Inspect `operation_contracts` and let the calling workflow choose bounded pagination or time-window inputs such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` when a channel supports them.",
            "Use specialist channels such as `github`, `qiita`, `bluesky`, `rss`, `youtube`, `hatena_bookmark`, `hacker_news`, `mcp_registry`, `reddit`, `searxng`, or `crawl4ai` only when the caller's task and readiness checks support them.",
            "Use Twitter/X only when configured credentials and `doctor --json --probe` show the required operation is ready.",
            "Treat `source_hints`, `media_references`, `text_length`, `link_count`, `image_count`, `link_density`, and `extraction_warning` as diagnostic metadata only.",
            "Keep ranking, summarization, scheduling, Discord publishing, and state in the downstream project.",
        ],
        "request_scale_policy": request_scale_policy,
        "large_scale_research": request_scale_policy["large_scale_research"],
        "failure_policy": [
            "Do not fall back to backend-specific CLIs unless debugging a failed Agent Reach operation.",
            "If `doctor --json` marks a non-required channel warn or off, continue with ready channels unless the caller marked that channel as required.",
            "For credential or runtime-gated channels, report operation-level readiness and the JSON error envelope separately.",
            "Inspect `doctor.summary.probe_attention` before assuming probe coverage is complete for a channel.",
            "For Twitter/X, authenticated-but-unprobed `warn` means collection may work but operation readiness is unverified until `doctor --json --probe`.",
        ],
    }


def export_codex_integration() -> dict[str, Any]:
    """Return the stable integration payload for Codex on Windows."""

    repo_root = _repo_root()
    execution_context = _execution_context(repo_root)
    artifact_paths = _artifact_paths(repo_root)
    channels = get_all_channel_contracts()
    skill_source = str(packaged_skill_source())
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
            "names": list(PACKAGED_SKILL_NAMES),
            "targets": [str(path) for path in _candidate_skill_targets()],
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
        "readiness_controls": _readiness_controls(),
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
    lines.append("  request scale: caller chooses scope; large-scale research is explicit opt-in")
    lines.append("  default plan candidates limit: 20")

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
