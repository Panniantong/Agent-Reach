# -*- coding: utf-8 -*-
"""CLI for the Windows/Codex Agent Reach fork."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from agent_reach import __version__
from agent_reach.batch import BatchPlanError, render_batch_text, run_batch_plan
from agent_reach.candidates import (
    CandidatePlanError,
    build_candidates_payload,
    render_candidates_text,
)
from agent_reach.client import AgentReachClient
from agent_reach.config import normalize_searxng_base_url
from agent_reach.ledger import (
    append_result_json,
    default_run_id,
    merge_ledger_inputs,
    save_collection_result,
    validate_ledger_input,
)
from agent_reach.results import CollectionResult
from agent_reach.schemas import SCHEMA_VERSION, utc_timestamp
from agent_reach.scout import (
    BUDGETS,
    PRESETS,
    QUALITY_PROFILES,
    ScoutPlanError,
    build_scout_plan,
    render_scout_text,
)
from agent_reach.utils.commands import ensure_command_on_path, find_command
from agent_reach.utils.paths import (
    get_mcporter_config_path,
    render_mcporter_command,
    render_ytdlp_fix_command,
)

CORE_CHANNELS = (
    "web",
    "exa_search",
    "github",
    "hatena_bookmark",
    "bluesky",
    "qiita",
    "youtube",
    "rss",
)
OPTIONAL_CHANNELS = ("reddit", "twitter")
ALL_OPTIONAL_CHANNELS = set(OPTIONAL_CHANNELS)

EXA_SERVER_URL = "https://mcp.exa.ai/mcp"
UPSTREAM_REPO = "Panniantong/Agent-Reach"


def _ensure_utf8_console() -> None:
    """Best-effort UTF-8 stdout/stderr on Windows terminals."""

    if sys.platform != "win32" or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _configure_logging(verbose: bool = False) -> None:
    """Keep loguru quiet unless verbose output is explicitly requested."""

    from loguru import logger

    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="INFO")


def _print_json(payload: object) -> None:
    """Render a stable JSON payload."""

    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-reach",
        description="Windows-first research tooling for Codex and compatible agents",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"Agent Reach v{__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    p_install = sub.add_parser("install", help="Install and configure the supported research stack")
    p_install.add_argument(
        "--env",
        choices=["local", "server", "auto"],
        default="auto",
        help="Environment classification for messaging only",
    )
    p_install.add_argument(
        "--safe",
        action="store_true",
        help="Show the Windows commands that would be run without changing anything",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the install plan without changing anything",
    )
    p_install.add_argument(
        "--channels",
        default="",
        help="Comma-separated optional channels to install (reddit,twitter,all)",
    )
    p_install.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable install plan. Requires --dry-run or --safe",
    )

    p_configure = sub.add_parser("configure", help="Save credentials or import them from a browser")
    p_configure.add_argument(
        "key",
        nargs="?",
        choices=[
            "github-token",
            "searxng-base-url",
            "twitter-cookies",
        ],
        help="Configuration key to set",
    )
    p_configure.add_argument("value", nargs="*", help="Value to store")
    p_configure.add_argument(
        "--from-browser",
        metavar="BROWSER",
        choices=["chrome", "firefox", "edge", "brave", "opera"],
        help="Import Twitter cookies from a local browser",
    )

    p_doctor = sub.add_parser("doctor", help="Check supported channel availability")
    p_doctor.add_argument("--json", action="store_true", help="Print machine-readable diagnostics")
    p_doctor.add_argument(
        "--probe",
        action="store_true",
        help="Run lightweight live probes after readiness checks",
    )
    p_doctor.add_argument(
        "--exit-policy",
        choices=["core", "all"],
        default="core",
        help="Exit-code policy: core ignores optional setup gaps, all preserves strict all-channel readiness",
    )

    p_collect = sub.add_parser("collect", help="Run a read-only collection operation")
    p_collect.add_argument("--channel", required=True, help="Stable channel name")
    p_collect.add_argument("--operation", required=True, help="Supported operation for the channel")
    p_collect.add_argument("--input", required=True, help="Input value such as a URL, repo, or query")
    p_collect.add_argument("--limit", type=int, help="Optional item limit for search/read operations")
    p_collect.add_argument("--page-size", type=int, help="Optional per-request page size for operations that support pagination")
    p_collect.add_argument("--max-pages", type=int, help="Optional request-count guardrail for operations that support pagination")
    p_collect.add_argument("--cursor", help="Optional backend continuation token for cursor-based operations")
    p_collect.add_argument("--page", type=int, help="Optional starting page number for page-based operations")
    p_collect.add_argument("--since", help="Optional lower time boundary for operations that support it")
    p_collect.add_argument("--until", help="Optional upper time boundary for operations that support it")
    p_collect.add_argument("--json", action="store_true", help="Print machine-readable collection output")
    p_collect.add_argument(
        "--max-text-chars",
        type=int,
        help="Show text snippets up to N characters in text mode only",
    )
    p_collect.add_argument(
        "--save",
        help="Append the raw CollectionResult envelope to an evidence ledger JSONL file",
    )
    p_collect.add_argument(
        "--run-id",
        help="Evidence ledger run ID. Defaults to AGENT_REACH_RUN_ID or a UTC timestamp",
    )
    p_collect.add_argument(
        "--intent",
        help="Optional evidence ledger intent label. Requires --save",
    )
    p_collect.add_argument(
        "--query-id",
        help="Optional evidence ledger query ID. Requires --save",
    )
    p_collect.add_argument(
        "--source-role",
        help="Optional evidence ledger source role label. Requires --save",
    )
    p_collect.add_argument(
        "--body-mode",
        choices=["none", "snippet", "full"],
        help="Control high-volume body storage for qiita search. Defaults to full",
    )
    p_collect.add_argument(
        "--query",
        help="Channel-specific query string for crawl4ai crawl",
    )

    p_plan = sub.add_parser("plan", help="Build lightweight plans from evidence ledgers")
    plan_sub = p_plan.add_subparsers(dest="plan_command", help="Planning commands")
    p_candidates = plan_sub.add_parser(
        "candidates",
        help="Return deduped candidates for follow-up reads",
    )
    p_candidates.add_argument("--input", required=True, help="Evidence ledger JSONL input path")
    p_candidates.add_argument(
        "--by",
        choices=["url", "id"],
        default="url",
        help="Dedupe mode. Defaults to URL, then falls back to source + id",
    )
    p_candidates.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum candidates to return",
    )
    p_candidates.add_argument("--json", action="store_true", help="Print machine-readable output")
    p_candidates.add_argument(
        "--summary-only",
        action="store_true",
        help="Return summary counts without candidate bodies",
    )
    p_candidates.add_argument(
        "--fields",
        help="Comma-separated candidate fields to include in output",
    )

    p_scout = sub.add_parser("scout", help="Build a plan-only capability snapshot")
    p_scout.add_argument("--topic", required=True, help="Topic echo for the calling workflow")
    p_scout.add_argument("--budget", choices=BUDGETS, default="auto", help="Research budget hint")
    p_scout.add_argument(
        "--quality",
        choices=QUALITY_PROFILES,
        default="precision",
        help="Quality profile hint",
    )
    p_scout.add_argument("--preset", choices=PRESETS, help="Optional source-pack seed")
    p_scout.add_argument(
        "--plan-only",
        action="store_true",
        help="Build the plan without running network collection",
    )
    p_scout.add_argument("--json", action="store_true", help="Print machine-readable scout output")

    p_batch = sub.add_parser("batch", help="Run a bounded batch collection plan")
    p_batch.add_argument("--plan", required=True, help="Research plan JSON path")
    batch_save_group = p_batch.add_mutually_exclusive_group(required=True)
    batch_save_group.add_argument("--save", help="Evidence ledger JSONL output path")
    batch_save_group.add_argument("--save-dir", help="Directory for sharded evidence ledger JSONL outputs")
    p_batch.add_argument(
        "--shard-by",
        choices=["channel", "operation", "channel-operation"],
        help="Shard key for --save-dir outputs. Defaults to channel",
    )
    p_batch.add_argument("--concurrency", type=int, default=1, help="Maximum concurrent collections")
    p_batch.add_argument("--resume", action="store_true", help="Skip queries already saved in the ledger")
    p_batch.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Emit checkpoint summaries after this many completed queries",
    )
    p_batch.add_argument(
        "--quality",
        choices=QUALITY_PROFILES,
        help="Override the plan quality profile hint",
    )
    p_batch.add_argument("--json", action="store_true", help="Print machine-readable batch output")

    p_channels = sub.add_parser("channels", help="Show the stable channel registry")
    p_channels.add_argument("name", nargs="?", help="Optional stable channel name to inspect")
    p_channels.add_argument("--json", action="store_true", help="Print machine-readable channel data")

    p_export = sub.add_parser(
        "export-integration",
        help="Export non-mutating integration data for downstream clients",
    )
    p_export.add_argument("--client", choices=["codex"], required=True, help="Target client")
    p_export.add_argument(
        "--format",
        choices=["text", "json", "powershell"],
        default="text",
        help="Output format for the integration export",
    )

    p_ledger = sub.add_parser("ledger", help="Manage evidence ledger files")
    ledger_sub = p_ledger.add_subparsers(dest="ledger_command", help="Ledger commands")
    p_ledger_merge = ledger_sub.add_parser("merge", help="Merge a ledger file or shard directory into one JSONL file")
    p_ledger_merge.add_argument("--input", required=True, help="Ledger input file or directory")
    p_ledger_merge.add_argument("--output", required=True, help="Merged ledger JSONL output path")
    p_ledger_merge.add_argument("--json", action="store_true", help="Print machine-readable merge output")
    p_ledger_validate = ledger_sub.add_parser("validate", help="Validate a ledger file or shard directory")
    p_ledger_validate.add_argument("--input", required=True, help="Ledger input file or directory")
    p_ledger_validate.add_argument("--json", action="store_true", help="Print machine-readable validation output")
    p_ledger_append = ledger_sub.add_parser("append", help="Append a CollectionResult JSON file to a ledger")
    p_ledger_append.add_argument("--input", required=True, help="CollectionResult JSON input file")
    p_ledger_append.add_argument("--output", required=True, help="Evidence ledger JSONL output path")
    p_ledger_append.add_argument("--run-id", help="Evidence ledger run ID. Defaults to AGENT_REACH_RUN_ID or a UTC timestamp")
    p_ledger_append.add_argument("--intent", help="Optional evidence ledger intent label")
    p_ledger_append.add_argument("--query-id", help="Optional evidence ledger query ID")
    p_ledger_append.add_argument("--source-role", help="Optional evidence ledger source role label")
    p_ledger_append.add_argument("--json", action="store_true", help="Print machine-readable append output")

    p_uninstall = sub.add_parser("uninstall", help="Remove local Agent Reach state and skill files")
    p_uninstall.add_argument("--dry-run", action="store_true", help="Preview what would be removed")
    p_uninstall.add_argument(
        "--keep-config",
        action="store_true",
        help="Remove skill files only and keep ~/.agent-reach",
    )

    p_skill = sub.add_parser("skill", help="Install or remove the bundled skill files")
    skill_group = p_skill.add_mutually_exclusive_group(required=True)
    skill_group.add_argument("--install", action="store_true", help="Install the bundled skill")
    skill_group.add_argument("--uninstall", action="store_true", help="Remove the bundled skill")

    p_check_update = sub.add_parser("check-update", help="Check the upstream project for new releases")
    p_check_update.add_argument("--json", action="store_true", help="Print machine-readable update data")

    sub.add_parser("version", help="Show the current Agent Reach version")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ensure_utf8_console()

    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "version":
        print(f"Agent Reach v{__version__}")
        return 0
    if args.command == "install":
        return _cmd_install(args)
    if args.command == "configure":
        return _cmd_configure(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "collect":
        return _cmd_collect(args)
    if args.command == "plan":
        return _cmd_plan(args)
    if args.command == "scout":
        return _cmd_scout(args)
    if args.command == "batch":
        return _cmd_batch(args)
    if args.command == "ledger":
        return _cmd_ledger(args)
    if args.command == "channels":
        return _cmd_channels(args)
    if args.command == "export-integration":
        return _cmd_export_integration(args)
    if args.command == "uninstall":
        return _cmd_uninstall(args)
    if args.command == "skill":
        return _cmd_skill(args)
    if args.command == "check-update":
        return _cmd_check_update(args)
    return 0


def _parse_requested_channels(raw: str) -> List[str]:
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not items:
        return []
    if "all" in items:
        return list(OPTIONAL_CHANNELS)

    invalid = [item for item in items if item not in ALL_OPTIONAL_CHANNELS]
    if invalid:
        supported = ", ".join(list(OPTIONAL_CHANNELS) + ["all"])
        raise SystemExit(f"Unsupported channel(s): {', '.join(invalid)}. Supported values: {supported}")
    return items


def _build_install_plan_payload(
    env: str,
    requested_channels: Sequence[str],
    dry_run: bool = False,
    safe: bool = False,
) -> dict:
    from agent_reach.integrations.codex import export_codex_integration

    integration = export_codex_integration()
    mode = "dry-run" if dry_run else "safe"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "install",
        "mode": mode,
        "environment": env,
        "platform": sys.platform,
        "core_channels": list(CORE_CHANNELS),
        "optional_channels_requested": list(requested_channels),
        "commands": _manual_install_commands(requested_channels),
        "skill_targets": [str(root / "agent-reach") for root in _candidate_skill_roots()],
        "execution_context": integration["execution_context"],
        "plugin_manifest": integration["plugin_manifest"],
        "plugin_manifest_inline": integration["plugin_manifest_inline"],
        "mcp_config": integration["mcp_config"],
        "mcp_config_inline": integration["mcp_config_inline"],
        "suggested_destinations": integration["suggested_destinations"],
        "safe": safe,
        "dry_run": dry_run,
    }


def _cmd_install(args) -> int:
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report

    if args.json and not (args.safe or args.dry_run):
        raise SystemExit("install --json is only supported with --dry-run or --safe")

    config = Config()
    requested_channels = _parse_requested_channels(args.channels)
    env = args.env if args.env != "auto" else _detect_environment()

    if args.safe or args.dry_run:
        if args.json:
            _print_json(
                _build_install_plan_payload(
                    env,
                    requested_channels,
                    dry_run=bool(args.dry_run),
                    safe=bool(args.safe),
                )
            )
        else:
            _print_install_plan(requested_channels, dry_run=args.dry_run)
        return 0

    print()
    print("Agent Reach Installer")
    print("========================================")
    print(f"Environment: {env}")
    print(f"Core channels: {', '.join(CORE_CHANNELS)}")
    print(f"Optional channels requested: {', '.join(requested_channels) if requested_channels else 'none'}")
    print()

    failures: List[str] = []

    if sys.platform != "win32":
        print("This fork only automates Windows installs. Use --safe to see the required commands.")
        failures.append("windows")
    else:
        if not _ensure_gh_cli():
            failures.append("gh")
        if not _ensure_ytdlp():
            failures.append("yt-dlp")
        if not _ensure_nodejs():
            failures.append("nodejs")

    if not _ensure_mcporter():
        failures.append("mcporter")
    elif not _ensure_exa_config():
        failures.append("exa")

    if not _ensure_ytdlp_js_runtime():
        failures.append("yt-dlp-js-runtime")

    if "reddit" in requested_channels and not _install_reddit_deps():
        failures.append("rdt-cli")

    if "twitter" in requested_channels and not _install_twitter_deps():
        failures.append("twitter-cli")

    installed_paths = _install_skill()
    print()
    if installed_paths:
        print("Installed skill targets:")
        for path in installed_paths:
            print(f"  {path}")

    print()
    print("Health check:")
    print(format_report(check_all(config)))

    if "twitter" in requested_channels:
        print()
        print("Next step for Twitter/X:")
        print('  agent-reach configure twitter-cookies "auth_token=...; ct0=..."')
        print("  Or: agent-reach configure --from-browser chrome")

    if failures:
        print()
        print("Some steps still need attention:")
        for item in failures:
            print(f"  - {item}")
        print("Run `agent-reach install --safe` to print the exact Windows commands again.")
        return 1

    print()
    print("Install complete.")
    return 0


def _print_install_plan(requested_channels: Sequence[str], dry_run: bool = False) -> None:
    prefix = "[dry-run] Would run:" if dry_run else "Manual Windows commands:"
    commands = _manual_install_commands(requested_channels)
    print(prefix)
    for command in commands:
        print(f"  {command}")
    if dry_run:
        print()
        print("Dry run complete. No changes were made.")


def _manual_install_commands(requested_channels: Sequence[str]) -> List[str]:
    commands: List[str] = []
    if not find_command("gh"):
        commands.append(
            "winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements"
        )
    if not find_command("yt-dlp"):
        commands.append(
            "winget install --id yt-dlp.yt-dlp -e --accept-package-agreements --accept-source-agreements"
        )
    if not (shutil.which("node") and shutil.which("npm")):
        commands.append(
            "winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements"
        )
    if not find_command("mcporter"):
        commands.append("npm install -g mcporter")
    if not _has_exa_config():
        commands.append(render_mcporter_command(f"config add exa {EXA_SERVER_URL}"))
    if not _ytdlp_js_runtime_ready():
        commands.append(render_ytdlp_fix_command())
    if "reddit" in requested_channels and not find_command("rdt"):
        commands.append("uv tool install rdt-cli")
    if "twitter" in requested_channels and not find_command("twitter"):
        commands.append("uv tool install twitter-cli")
    commands.append("agent-reach skill --install")
    return commands


def _detect_environment() -> str:
    if sys.platform == "win32":
        return "local"
    indicators = [
        os.environ.get("CI"),
        os.environ.get("GITHUB_ACTIONS"),
        os.environ.get("SSH_CONNECTION"),
    ]
    return "server" if any(indicators) else "local"


def _run(
    command: Sequence[str],
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
    )


def _ensure_gh_cli() -> bool:
    existing = ensure_command_on_path("gh")
    if existing:
        _ensure_local_bin_wrapper("gh", existing)
        print("  [OK] gh CLI already installed")
        return True
    print("  Installing gh CLI with winget...")
    return _winget_install("GitHub.cli", "gh")


def _ensure_ytdlp() -> bool:
    existing = ensure_command_on_path("yt-dlp")
    if existing:
        _ensure_local_bin_wrapper("yt-dlp", existing)
        print("  [OK] yt-dlp already installed")
        return True
    print("  Installing yt-dlp with winget...")
    return _winget_install("yt-dlp.yt-dlp", "yt-dlp")


def _ensure_nodejs() -> bool:
    if shutil.which("node") and shutil.which("npm"):
        print("  [OK] Node.js already installed")
        return True
    print("  Installing Node.js LTS with winget...")
    if not _winget_install("OpenJS.NodeJS.LTS", "node"):
        return False
    if shutil.which("node") and shutil.which("npm"):
        return True
    print("  [WARN] Node.js installed but npm is not visible in the current shell yet")
    return False


def _winget_install(package_id: str, command_name: str) -> bool:
    winget = shutil.which("winget")
    if not winget:
        print(f"  [WARN] winget is not available. Install {package_id} manually.")
        return False
    try:
        result = _run(
            [
                winget,
                "install",
                "--id",
                package_id,
                "-e",
                "--source",
                "winget",
                "--disable-interactivity",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            timeout=900,
        )
    except Exception as exc:
        print(f"  [WARN] winget install failed for {package_id}: {exc}")
        return False

    installed_path = ensure_command_on_path(command_name)
    if installed_path:
        _ensure_local_bin_wrapper(command_name, installed_path)
        print(f"  [OK] {command_name} is ready")
        return True

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    message = stderr or stdout or "unknown winget failure"
    print(f"  [WARN] {package_id} did not finish cleanly: {message[:200]}")
    return False


def _ensure_mcporter() -> bool:
    if find_command("mcporter"):
        print("  [OK] mcporter already installed")
        return True
    npm = shutil.which("npm")
    if not npm:
        print("  [WARN] npm is missing, so mcporter cannot be installed")
        return False
    print("  Installing mcporter with npm...")
    try:
        _run([npm, "install", "-g", "mcporter"], timeout=600)
    except Exception as exc:
        print(f"  [WARN] mcporter install failed: {exc}")
        return False
    if find_command("mcporter"):
        print("  [OK] mcporter is ready")
        return True
    print("  [WARN] mcporter is still missing after npm install")
    return False


def _has_exa_config() -> bool:
    command = _mcporter_command()
    if not command:
        return False
    try:
        result = _run([*command, "config", "list"], timeout=30)
    except Exception:
        return False
    return "exa" in (result.stdout or "").lower()


def _ensure_exa_config() -> bool:
    command = _mcporter_command(create_dir=True)
    if not command:
        print("  [WARN] mcporter is missing, so Exa cannot be configured")
        return False
    if _has_exa_config():
        print("  [OK] Exa MCP already configured")
        return True
    print("  Configuring Exa MCP...")
    try:
        _run([*command, "config", "add", "exa", EXA_SERVER_URL], timeout=60)
    except Exception as exc:
        print(f"  [WARN] Exa configuration failed: {exc}")
        return False
    if _has_exa_config():
        print("  [OK] Exa MCP configured")
        return True
    print("  [WARN] Exa MCP is still not configured")
    return False


def _ytdlp_js_runtime_ready() -> bool:
    from agent_reach.utils.paths import get_ytdlp_config_path
    from agent_reach.utils.text import read_utf8_text

    if not ensure_command_on_path("yt-dlp"):
        return False
    if shutil.which("deno"):
        return True
    if not shutil.which("node"):
        return False

    config_path = get_ytdlp_config_path()
    if not config_path.exists():
        return False
    return "--js-runtimes" in read_utf8_text(config_path)


def _ensure_ytdlp_js_runtime() -> bool:
    from agent_reach.utils.paths import get_ytdlp_config_path, render_ytdlp_fix_command

    if _ytdlp_js_runtime_ready():
        print("  [OK] yt-dlp JS runtime already configured")
        return True

    if not ensure_command_on_path("yt-dlp"):
        print("  [WARN] yt-dlp is missing, so the JS runtime could not be configured")
        return False
    if not shutil.which("node") and not shutil.which("deno"):
        print("  [WARN] No JS runtime found for yt-dlp")
        return False
    if shutil.which("deno"):
        print("  [OK] Deno is available for yt-dlp")
        return True

    config_path = get_ytdlp_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        if "--js-runtimes node" not in existing:
            prefix = "" if not existing or existing.endswith("\n") else "\n"
            config_path.write_text(f"{existing}{prefix}--js-runtimes node\n", encoding="utf-8")
        print(f"  [OK] Added Node.js runtime to {config_path}")
        return True
    except Exception as exc:
        print(f"  [WARN] Could not update yt-dlp config: {exc}")
        print(render_ytdlp_fix_command())
        return False


def _install_twitter_deps() -> bool:
    if find_command("twitter"):
        print("  [OK] twitter-cli already installed")
        return True
    uv = shutil.which("uv")
    if not uv:
        print("  [WARN] uv is missing, so twitter-cli cannot be installed automatically")
        return False
    print("  Installing twitter-cli with uv tool...")
    try:
        _run([uv, "tool", "install", "twitter-cli"], timeout=600)
    except Exception as exc:
        print(f"  [WARN] twitter-cli install failed: {exc}")
        return False
    if find_command("twitter"):
        print("  [OK] twitter-cli is ready")
        return True
    print("  [WARN] twitter-cli is still missing after uv tool install")
    return False


def _install_reddit_deps() -> bool:
    if find_command("rdt"):
        print("  [OK] rdt-cli already installed")
        return True
    uv = shutil.which("uv")
    if not uv:
        print("  [WARN] uv is missing, so rdt-cli cannot be installed automatically")
        return False
    print("  Installing rdt-cli with uv tool...")
    try:
        _run([uv, "tool", "install", "rdt-cli"], timeout=600)
    except Exception as exc:
        print(f"  [WARN] rdt-cli install failed: {exc}")
        return False
    if find_command("rdt"):
        print("  [OK] rdt-cli is ready")
        return True
    print("  [WARN] rdt-cli is still missing after uv tool install")
    return False


def _mcporter_command(create_dir: bool = False) -> List[str]:
    mcporter = find_command("mcporter")
    if not mcporter:
        return []

    config_path = get_mcporter_config_path()
    if create_dir:
        config_path.parent.mkdir(parents=True, exist_ok=True)
    return [mcporter, "--config", str(config_path)]


def _ensure_local_bin_wrapper(command_name: str, executable_path: str) -> None:
    """Create a small shim under ~/.local/bin for newly-installed tools."""

    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    wrapper = local_bin / f"{command_name}.cmd"
    try:
        if str(Path(executable_path).resolve()).lower() == str(wrapper.resolve()).lower():
            return
    except Exception:
        pass
    try:
        wrapper.write_text(
            "@echo off\n"
            f"\"{executable_path}\" %*\n",
            encoding="utf-8",
        )
    except OSError:
        return


def _candidate_skill_roots() -> List[Path]:
    roots: List[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home) / "skills")
    roots.append(Path.home() / ".codex" / "skills")
    roots.append(Path.home() / ".agents" / "skills")

    deduped: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            deduped.append(root)
            seen.add(key)
    return deduped


def _install_skill() -> List[Path]:
    source_dir = Path(__file__).resolve().parent / "skill"
    installed_paths: List[Path] = []

    existing_roots = [root for root in _candidate_skill_roots() if root.exists()]
    if not existing_roots:
        existing_roots = [_candidate_skill_roots()[0]]

    for root in existing_roots:
        target = root / "agent-reach"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source_dir, target)
        installed_paths.append(target)

    return installed_paths


def _uninstall_skill() -> List[Path]:
    removed: List[Path] = []
    for root in _candidate_skill_roots():
        target = root / "agent-reach"
        if target.exists():
            shutil.rmtree(target)
            removed.append(target)
    return removed


def _cmd_skill(args) -> int:
    if args.install:
        installed = _install_skill()
        if installed:
            for path in installed:
                print(f"Installed skill: {path}")
        else:
            print("No skill targets were written.")
    elif args.uninstall:
        removed = _uninstall_skill()
        if removed:
            for path in removed:
                print(f"Removed skill: {path}")
        else:
            print("No skill installations found.")
    return 0


def _cmd_configure(args) -> int:
    from agent_reach.config import Config

    config = Config()

    if args.from_browser:
        _configure_from_browser(args.from_browser, config)
        return 0

    if not args.key:
        raise SystemExit("configure requires either a key or --from-browser")

    value = " ".join(args.value).strip()
    if args.key == "github-token":
        if not value:
            raise SystemExit("github-token requires a value")
        config.set("github_token", value)
        print("Saved github_token to config.")
        gh = ensure_command_on_path("gh")
        if gh:
            try:
                result = subprocess.run(
                    [gh, "auth", "login", "--with-token"],
                    input=value + "\n",
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )
                if result.returncode == 0:
                    print("Logged gh CLI in with the provided token.")
                else:
                    print("gh auth login did not complete cleanly. You can retry with `gh auth login`.")
            except Exception as exc:
                print(f"Could not update gh auth automatically: {exc}")
        return 0

    if args.key == "searxng-base-url":
        if not value:
            raise SystemExit("searxng-base-url requires a value")
        normalized = normalize_searxng_base_url(value)
        config.set("searxng_base_url", normalized)
        print(f"Saved searxng_base_url to config: {normalized}")
        return 0

    if args.key == "twitter-cookies":
        if not value:
            raise SystemExit("twitter-cookies requires a cookie header string or two values")
        auth_token, ct0 = _parse_twitter_cookie_input(value)
        config.set("twitter_auth_token", auth_token)
        config.set("twitter_ct0", ct0)
        _persist_twitter_env(auth_token, ct0)
        print("Saved Twitter/X cookies to config.")
        print("Verify with: twitter status")
        return 0

    raise SystemExit(f"Unsupported configure key: {args.key}")


def _parse_twitter_cookie_input(raw: str) -> Tuple[str, str]:
    raw = raw.strip()
    if not raw:
        raise SystemExit("Twitter cookie input is empty")

    if "auth_token=" in raw or "ct0=" in raw:
        parts = {}
        for item in raw.split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()
        auth_token = parts.get("auth_token")
        ct0 = parts.get("ct0")
        if auth_token and ct0:
            return auth_token, ct0
        raise SystemExit("Twitter cookie header must include both auth_token and ct0")

    values = raw.split()
    if len(values) == 2:
        return values[0], values[1]
    raise SystemExit("Provide either `auth_token=...; ct0=...` or `AUTH_TOKEN CT0`")


def _configure_from_browser(browser: str, config) -> None:
    try:
        from agent_reach.cookie_extract import extract_all
    except Exception as exc:
        raise SystemExit(f"Browser import support is unavailable: {exc}")

    try:
        extracted = extract_all(browser)
    except Exception as exc:
        raise SystemExit(str(exc))

    twitter = extracted.get("twitter") or {}
    auth_token = twitter.get("auth_token")
    ct0 = twitter.get("ct0")
    if not auth_token or not ct0:
        raise SystemExit(f"No Twitter/X cookies were found in {browser}")

    config.set("twitter_auth_token", auth_token)
    config.set("twitter_ct0", ct0)
    _persist_twitter_env(auth_token, ct0)
    print(f"Imported Twitter/X cookies from {browser}.")
    print("Verify with: twitter status")


def _persist_twitter_env(auth_token: str, ct0: str) -> None:
    """Persist Twitter credentials for twitter-cli across future shells."""

    os.environ["TWITTER_AUTH_TOKEN"] = auth_token
    os.environ["TWITTER_CT0"] = ct0
    os.environ["AUTH_TOKEN"] = auth_token
    os.environ["CT0"] = ct0

    if sys.platform != "win32":
        return

    for key, value in (
        ("TWITTER_AUTH_TOKEN", auth_token),
        ("TWITTER_CT0", ct0),
        ("AUTH_TOKEN", auth_token),
        ("CT0", ct0),
    ):
        try:
            subprocess.run(
                ["setx", key, value],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except Exception:
            pass


def _cmd_doctor(args) -> int:
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, doctor_exit_code, format_report, make_doctor_payload

    config = Config()
    results = check_all(config, probe=args.probe)
    if args.json:
        _print_json(make_doctor_payload(results, probe=args.probe, exit_policy=args.exit_policy))
    else:
        print(format_report(results, probe=args.probe, exit_policy=args.exit_policy))
    return doctor_exit_code(results, exit_policy=args.exit_policy)


def _compact_text_snippet(text: str | None, max_chars: int | None) -> str | None:
    if max_chars is None or not text:
        return None
    snippet = " ".join(text.split())
    if not snippet:
        return None
    if len(snippet) > max_chars:
        return f"{snippet[:max_chars]}..."
    return snippet


def _render_collect_text(payload: CollectionResult, max_text_chars: int | None = None) -> str:
    lines = [
        "Agent Reach Collection",
        "========================================",
        f"Channel: {payload['channel']}",
        f"Operation: {payload['operation']}",
        f"OK: {'yes' if payload['ok'] else 'no'}",
    ]
    if payload["ok"]:
        lines.append(f"Items: {len(payload['items'])}")
        for item in payload["items"][:5]:
            title = item.get("title") or item.get("id")
            url = item.get("url") or ""
            lines.append(f"  - {title} {url}".rstrip())
            snippet = _compact_text_snippet(item.get("text"), max_text_chars)
            if snippet:
                lines.append(f"    {snippet}")
    else:
        error = payload["error"]
        code = error["code"] if error else "unknown"
        message = error["message"] if error else ""
        lines.append(f"Error: {code} - {message}".rstrip())
    return "\n".join(lines)


def _cmd_collect(args) -> int:
    if args.max_text_chars is not None and args.max_text_chars < 1:
        print("max-text-chars must be greater than or equal to 1", file=sys.stderr)
        return 2
    annotations = [args.intent, args.query_id, args.source_role]
    if any(value is not None for value in annotations) and not args.save:
        print("intent, query-id, and source-role require --save", file=sys.stderr)
        return 2
    if args.body_mode and (args.channel != "qiita" or args.operation != "search"):
        print("body-mode is only supported for qiita search", file=sys.stderr)
        return 2
    if args.query and (args.channel != "crawl4ai" or args.operation != "crawl"):
        print("query is only supported for crawl4ai crawl", file=sys.stderr)
        return 2
    if args.channel == "crawl4ai" and args.operation == "crawl" and not args.query:
        print("crawl4ai crawl requires --query", file=sys.stderr)
        return 2

    client = AgentReachClient()
    collect_kwargs = {}
    if args.limit is not None:
        collect_kwargs["limit"] = args.limit
    if args.body_mode is not None:
        collect_kwargs["body_mode"] = args.body_mode
    if args.query is not None:
        collect_kwargs["crawl_query"] = args.query
    if args.page_size is not None:
        collect_kwargs["page_size"] = args.page_size
    if args.max_pages is not None:
        collect_kwargs["max_pages"] = args.max_pages
    if args.cursor is not None:
        collect_kwargs["cursor"] = args.cursor
    if args.page is not None:
        collect_kwargs["page"] = args.page
    if args.since is not None:
        collect_kwargs["since"] = args.since
    if args.until is not None:
        collect_kwargs["until"] = args.until
    payload = client.collect(args.channel, args.operation, args.input, **collect_kwargs)
    if args.json:
        _print_json(payload)
    else:
        print(_render_collect_text(payload, max_text_chars=args.max_text_chars))

    if args.save:
        try:
            save_collection_result(
                args.save,
                payload,
                run_id=args.run_id or default_run_id(),
                input_value=args.input,
                intent=args.intent,
                query_id=args.query_id,
                source_role=args.source_role,
            )
        except (OSError, TypeError, ValueError) as exc:
            print(f"Could not save evidence ledger: {exc}", file=sys.stderr)
            return 1

    if payload["ok"]:
        return 0
    error = payload["error"]
    if error and error["code"] in {"unknown_channel", "unsupported_operation", "invalid_input", "unsupported_option"}:
        return 2
    return 1


def _cmd_plan(args) -> int:
    if args.plan_command == "candidates":
        return _cmd_plan_candidates(args)
    print("plan requires a subcommand", file=sys.stderr)
    return 2


def _cmd_plan_candidates(args) -> int:
    if args.limit < 1:
        print("limit must be greater than or equal to 1", file=sys.stderr)
        return 2
    try:
        payload = build_candidates_payload(
            args.input,
            by=args.by,
            limit=args.limit,
            summary_only=args.summary_only,
            fields=args.fields,
        )
    except CandidatePlanError as exc:
        if args.json:
            _print_json(_candidate_error_payload(args, str(exc)))
            return 2
        print(f"Could not plan candidates: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(render_candidates_text(payload))
    return 0


def _candidate_error_payload(args, message: str) -> dict:
    fields = None
    if args.fields is not None:
        fields = [item.strip() for item in args.fields.split(",") if item.strip()]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "plan candidates",
        "ok": False,
        "input": args.input,
        "by": args.by,
        "limit": args.limit,
        "summary_only": bool(args.summary_only),
        "fields": fields,
        "candidates": [],
        "error": {
            "code": "candidate_plan_error",
            "message": message,
        },
    }


def _cmd_scout(args) -> int:
    if not args.plan_only:
        print("scout currently requires --plan-only", file=sys.stderr)
        return 2
    try:
        payload = build_scout_plan(
            args.topic,
            budget=args.budget,
            quality=args.quality,
            preset=args.preset,
        )
    except ScoutPlanError as exc:
        print(f"Could not build scout plan: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json(payload)
    else:
        print(render_scout_text(payload))
    return 0


def _cmd_batch(args) -> int:
    if args.shard_by and not args.save_dir:
        print("shard-by is only supported with --save-dir", file=sys.stderr)
        return 2
    try:
        payload, exit_code = run_batch_plan(
            args.plan,
            save_path=args.save,
            save_dir=args.save_dir,
            shard_by=args.shard_by or "channel",
            concurrency=args.concurrency,
            resume=args.resume,
            checkpoint_every=args.checkpoint_every,
            quality=args.quality,
        )
    except BatchPlanError as exc:
        print(f"Could not run batch plan: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json(payload)
    else:
        print(render_batch_text(payload))
    return exit_code


def _cmd_ledger(args) -> int:
    if args.ledger_command == "merge":
        return _cmd_ledger_merge(args)
    if args.ledger_command == "validate":
        return _cmd_ledger_validate(args)
    if args.ledger_command == "append":
        return _cmd_ledger_append(args)
    print("ledger requires a subcommand", file=sys.stderr)
    return 2


def _cmd_ledger_merge(args) -> int:
    try:
        payload = merge_ledger_inputs(args.input, args.output)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Could not merge ledgers: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json(payload)
    else:
        print(
            "\n".join(
                [
                    "Agent Reach Ledger Merge",
                    "========================================",
                    f"Input: {payload['input']}",
                    f"Output: {payload['output']}",
                    f"Files merged: {payload['files_merged']}",
                    f"Records written: {payload['records_written']}",
                ]
            )
        )
    return 0


def _cmd_ledger_validate(args) -> int:
    try:
        payload = validate_ledger_input(args.input)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Could not validate ledger: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json(payload)
    else:
        print(
            "\n".join(
                [
                    "Agent Reach Ledger Validate",
                    "========================================",
                    f"Input: {payload['input']}",
                    f"Valid: {'yes' if payload['valid'] else 'no'}",
                    f"Files checked: {payload['files_checked']}",
                    f"Records: {payload['records']}",
                    f"Collection results: {payload['collection_results']}",
                    f"Items seen: {payload['items_seen']}",
                    f"Invalid lines: {payload['invalid_lines']}",
                    f"Invalid records: {payload['invalid_records']}",
                    f"Large text fields: {len(payload['large_text_fields'])}",
                ]
            )
        )
    return 0 if payload["valid"] else 1


def _cmd_ledger_append(args) -> int:
    try:
        payload = append_result_json(
            args.input,
            args.output,
            run_id=args.run_id or default_run_id(),
            intent=args.intent,
            query_id=args.query_id,
            source_role=args.source_role,
        )
    except FileNotFoundError as exc:
        print(f"Could not append ledger: {exc}", file=sys.stderr)
        return 2
    except (OSError, TypeError, ValueError) as exc:
        print(f"Could not append ledger: {exc}", file=sys.stderr)
        return 1
    if args.json:
        _print_json(payload)
    else:
        print(
            "\n".join(
                [
                    "Agent Reach Ledger Append",
                    "========================================",
                    f"Input: {payload['input']}",
                    f"Output: {payload['output']}",
                    f"Channel: {payload['channel']}",
                    f"Operation: {payload['operation']}",
                    f"OK: {'yes' if payload['ok'] else 'no'}",
                    f"Items: {payload['count']}",
                ]
            )
        )
    return 0


def _render_channels_text(contracts: Sequence[dict]) -> str:
    lines = [
        "Agent Reach Channels",
        "========================================",
        "",
    ]
    for contract in contracts:
        tier = "core" if contract["tier"] == 0 else "optional"
        lines.append(f"{contract['name']} ({tier})")
        lines.append(f"  {contract['description']}")
        lines.append(f"  backends: {', '.join(contract['backends']) or 'none'}")
        lines.append(
            f"  auth: {contract['auth_kind']} | entrypoint: {contract['entrypoint_kind']}"
        )
        if contract.get("operations"):
            lines.append(f"  operations: {', '.join(contract['operations'])}")
        operation_contracts = contract.get("operation_contracts") or {}
        for operation in contract.get("operations") or []:
            details = operation_contracts.get(operation) or {}
            option_names = [option.get("name") for option in details.get("options", []) if option.get("name")]
            option_suffix = f" | options: {', '.join(option_names)}" if option_names else ""
            lines.append(
                "  "
                f"- {operation}: input={details.get('input_kind', 'text')} "
                f"| limit={'yes' if details.get('accepts_limit', False) else 'no'}"
                f"{option_suffix}"
            )
        probe_line = f"  probe: {'yes' if contract['supports_probe'] else 'no'}"
        if contract.get("supports_probe"):
            coverage = contract.get("probe_coverage") or "full"
            probe_operations = contract.get("probe_operations") or []
            probe_line += f" | coverage: {coverage}"
            if probe_operations:
                probe_line += f" | probe ops: {', '.join(probe_operations)}"
        lines.append(probe_line)
        if contract["required_commands"]:
            lines.append(f"  commands: {', '.join(contract['required_commands'])}")
        if contract["host_patterns"]:
            lines.append(f"  hosts: {', '.join(contract['host_patterns'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _cmd_channels(args) -> int:
    from agent_reach.channels import get_all_channel_contracts, get_channel_contract

    if args.name:
        contract = get_channel_contract(args.name)
        if contract is None:
            print(f"Unknown channel: {args.name}", file=sys.stderr)
            return 2
        if args.json:
            _print_json(
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at": utc_timestamp(),
                    "channel": contract,
                }
            )
        else:
            print(_render_channels_text([contract]))
        return 0

    contracts = get_all_channel_contracts()
    if args.json:
        _print_json(
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at": utc_timestamp(),
                "channels": contracts,
            }
        )
    else:
        print(_render_channels_text(contracts))
    return 0


def _cmd_export_integration(args) -> int:
    from agent_reach.integrations.codex import (
        export_codex_integration,
        render_codex_integration_powershell,
        render_codex_integration_text,
    )

    payload = export_codex_integration()
    if args.format == "json":
        _print_json(payload)
    elif args.format == "powershell":
        print(render_codex_integration_powershell(payload))
    else:
        print(render_codex_integration_text(payload))
    return 0


def _cmd_uninstall(args) -> int:
    from agent_reach.config import Config

    config_path = Config.CONFIG_FILE
    config_dir = Config.CONFIG_DIR
    skill_paths = [root / "agent-reach" for root in _candidate_skill_roots()]

    if args.dry_run:
        print("Dry-run uninstall plan:")
        if not args.keep_config:
            print(f"  Remove config dir: {config_dir}")
        for path in skill_paths:
            if path.exists():
                print(f"  Remove skill: {path}")
        print("  Remove Exa MCP entry if mcporter is installed")
        return 0

    removed_any = False
    if not args.keep_config and config_dir.exists():
        shutil.rmtree(config_dir)
        print(f"Removed config dir: {config_dir}")
        removed_any = True
    elif not args.keep_config and config_path.exists():
        config_path.unlink(missing_ok=True)

    for path in skill_paths:
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed skill: {path}")
            removed_any = True

    mcporter = find_command("mcporter")
    if mcporter:
        try:
            result = _run([*_mcporter_command(create_dir=True), "config", "list"], timeout=30)
            if "exa" in (result.stdout or "").lower():
                _run([*_mcporter_command(create_dir=True), "config", "remove", "exa"], timeout=30)
                print("Removed mcporter Exa entry")
                removed_any = True
        except Exception:
            pass

    if not removed_any:
        print("Nothing to remove.")
        return 0

    print()
    print("Optional tool cleanup:")
    print("  winget uninstall --id GitHub.cli -e")
    print("  winget uninstall --id yt-dlp.yt-dlp -e")
    print("  npm uninstall -g mcporter")
    print("  uv tool uninstall rdt-cli")
    print("  uv tool uninstall twitter-cli")
    return 0


def _import_requests():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"urllib3 .* doesn't match a supported version!",
        )
        import requests

    return requests


def _classify_update_error(exc) -> str:
    requests = _import_requests()

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        text = str(exc).lower()
        markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
            "dns",
        ]
        if any(marker in text for marker in markers):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"


def _classify_github_response_error(resp) -> Optional[str]:
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
        except Exception:
            message = ""
        if "rate limit" in message:
            return "rate_limit"
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None


def _update_error_text(kind: str) -> str:
    mapping = {
        "timeout": "request timed out",
        "dns": "DNS resolution failed",
        "rate_limit": "GitHub API rate limit reached",
        "connection": "connection failed",
        "server_error": "GitHub returned a server error",
        "http": "HTTP request failed",
        "unknown": "unknown error",
    }
    return mapping.get(kind, "unknown error")


def _github_get_with_retry(url: str, timeout: int = 10, retries: int = 3, sleeper=time.sleep):
    requests = _import_requests()

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, _classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err = _classify_github_response_error(response)
        if err in {"rate_limit", "server_error"}:
            if attempt >= retries:
                return None, err, attempt
            delay = 2 ** (attempt - 1)
            retry_after = response.headers.get("Retry-After")
            if err == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return response, None, attempt

    return None, "unknown", retries


def _build_update_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_timestamp(),
        "command": "check-update",
        "current_version": __version__,
        "upstream_repo": UPSTREAM_REPO,
        "status": "error",
    }
    release_url = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest"
    commit_url = f"https://api.github.com/repos/{UPSTREAM_REPO}/commits/main"

    response, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        payload.update(
            {
                "status": "error",
                "error": _update_error_text(err),
                "error_kind": err,
                "attempts": attempts,
            }
        )
        return payload

    if response is not None and response.status_code == 200:
        release_payload = response.json()
        latest = release_payload.get("tag_name", "").lstrip("v")
        payload["latest_version"] = latest or __version__
        if latest and latest != __version__:
            payload["status"] = "update_available"
            body = release_payload.get("body", "").strip()
            payload["release_notes_preview"] = body.splitlines()[:20] if body else []
        else:
            payload["status"] = "up_to_date"
        return payload

    response, err, attempts = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err:
        payload.update(
            {
                "status": "error",
                "error": _update_error_text(err),
                "error_kind": err,
                "attempts": attempts,
            }
        )
        return payload

    if response is not None and response.status_code == 200:
        commit_payload = response.json()
        payload.update(
            {
                "status": "unknown",
                "latest_main_commit": {
                    "sha": commit_payload.get("sha", "")[:7],
                    "date": commit_payload.get("commit", {})
                    .get("committer", {})
                    .get("date", "")[:10],
                    "message": commit_payload.get("commit", {}).get("message", "").splitlines()[0],
                },
            }
        )
        return payload

    payload.update(
        {
            "status": "error",
            "error": f"GitHub returned HTTP {response.status_code if response is not None else 'unknown'}",
            "error_kind": "http",
        }
    )
    return payload


def _render_update_payload(payload: dict) -> str:
    lines = [f"Current version: v{payload['current_version']}"]
    status = payload["status"]

    if status == "error":
        attempts = payload.get("attempts")
        detail = payload.get("error", "unknown error")
        if attempts:
            lines.append(f"[WARN] Could not check releases: {detail} after {attempts} attempt(s)")
        else:
            lines.append(f"[WARN] Could not check releases: {detail}")
        return "\n".join(lines)

    if status == "update_available":
        lines.append(f"Update available: v{payload.get('latest_version', 'unknown')}")
        notes = payload.get("release_notes_preview", [])
        if notes:
            lines.append("")
            for line in notes:
                lines.append(f"  {line}")
        return "\n".join(lines)

    if status == "up_to_date":
        lines.append("Already up to date.")
        return "\n".join(lines)

    if status == "unknown":
        commit = payload.get("latest_main_commit", {})
        lines.append(
            "Latest main commit: "
            f"{commit.get('sha', '')} ({commit.get('date', '')}) {commit.get('message', '')}"
        )
        return "\n".join(lines)

    lines.append("[WARN] Unknown update status")
    return "\n".join(lines)


def _cmd_check_update(args) -> int:
    payload = _build_update_payload()
    if args.json:
        _print_json(payload)
    else:
        print(_render_update_payload(payload))
    return 1 if payload["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
