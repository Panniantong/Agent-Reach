# -*- coding: utf-8 -*-
"""CLI for the Windows/Codex Agent Reach fork."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from agent_reach import __version__
from agent_reach.utils.commands import ensure_command_on_path, find_command
from agent_reach.utils.paths import (
    get_mcporter_config_path,
    render_mcporter_command,
    render_ytdlp_fix_command,
)

CORE_CHANNELS = ("web", "exa_search", "github", "youtube", "rss")
OPTIONAL_CHANNELS = ("twitter",)
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
        help="Comma-separated optional channels to install (twitter,all)",
    )

    p_configure = sub.add_parser("configure", help="Save credentials or import them from a browser")
    p_configure.add_argument(
        "key",
        nargs="?",
        choices=["github-token", "twitter-cookies"],
        help="Configuration key to set",
    )
    p_configure.add_argument("value", nargs="*", help="Value to store")
    p_configure.add_argument(
        "--from-browser",
        metavar="BROWSER",
        choices=["chrome", "firefox", "edge", "brave", "opera"],
        help="Import Twitter cookies from a local browser",
    )

    sub.add_parser("doctor", help="Check supported channel availability")

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

    sub.add_parser("check-update", help="Check the upstream project for new releases")
    sub.add_parser("watch", help="Health check plus update check for scheduled runs")
    sub.add_parser("version", help="Show the current Agent Reach version")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    _ensure_utf8_console()

    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        raise SystemExit(0)

    if args.command == "version":
        print(f"Agent Reach v{__version__}")
        raise SystemExit(0)
    if args.command == "install":
        _cmd_install(args)
    elif args.command == "configure":
        _cmd_configure(args)
    elif args.command == "doctor":
        _cmd_doctor()
    elif args.command == "uninstall":
        _cmd_uninstall(args)
    elif args.command == "skill":
        _cmd_skill(args)
    elif args.command == "check-update":
        _cmd_check_update()
    elif args.command == "watch":
        _cmd_watch()


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


def _cmd_install(args) -> None:
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report

    config = Config()
    requested_channels = _parse_requested_channels(args.channels)
    env = args.env if args.env != "auto" else _detect_environment()

    print()
    print("Agent Reach Installer")
    print("========================================")
    print(f"Environment: {env}")
    print(f"Core channels: {', '.join(CORE_CHANNELS)}")
    print(f"Optional channels requested: {', '.join(requested_channels) if requested_channels else 'none'}")
    print()

    if args.safe or args.dry_run:
        _print_install_plan(requested_channels, dry_run=args.dry_run)
        return

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
    else:
        print()
        print("Install complete.")


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
        # Best-effort only. The tool can still be used via its discovered absolute path.
        return


def _candidate_skill_roots() -> List[Path]:
    roots: List[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home) / "skills")
    roots.append(Path.home() / ".codex" / "skills")
    roots.append(Path.home() / ".agents" / "skills")

    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        roots.append(Path(openclaw_home) / ".openclaw" / "skills")

    roots.append(Path.home() / ".openclaw" / "skills")
    roots.append(Path.home() / ".claude" / "skills")

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


def _cmd_skill(args) -> None:
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


def _cmd_configure(args) -> None:
    from agent_reach.config import Config

    config = Config()

    if args.from_browser:
        _configure_from_browser(args.from_browser, config)
        return

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
        return

    if args.key == "twitter-cookies":
        if not value:
            raise SystemExit("twitter-cookies requires a cookie header string or two values")
        auth_token, ct0 = _parse_twitter_cookie_input(value)
        config.set("twitter_auth_token", auth_token)
        config.set("twitter_ct0", ct0)
        _persist_twitter_env(auth_token, ct0)
        print("Saved Twitter/X cookies to config.")
        print("Verify with: twitter status")
        return

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


def _cmd_doctor() -> None:
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report

    config = Config()
    print(format_report(check_all(config)))


def _cmd_uninstall(args) -> None:
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
        return

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
        return

    print()
    print("Optional tool cleanup:")
    print("  winget uninstall --id GitHub.cli -e")
    print("  winget uninstall --id yt-dlp.yt-dlp -e")
    print("  npm uninstall -g mcporter")
    print("  uv tool uninstall twitter-cli")


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


def _cmd_check_update():
    print(f"Current version: v{__version__}")
    release_url = f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest"
    commit_url = f"https://api.github.com/repos/{UPSTREAM_REPO}/commits/main"

    response, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"[WARN] Could not check releases: {_update_error_text(err)} after {attempts} attempt(s)")
        return "error"

    if response.status_code == 200:
        payload = response.json()
        latest = payload.get("tag_name", "").lstrip("v")
        if latest and latest != __version__:
            print(f"Update available: v{latest}")
            body = payload.get("body", "").strip()
            if body:
                print()
                for line in body.splitlines()[:20]:
                    print(f"  {line}")
            return "update_available"
        print("Already up to date.")
        return "up_to_date"

    response, err, attempts = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err:
        print(f"[WARN] Could not check the latest main commit: {_update_error_text(err)}")
        return "error"

    if response.status_code == 200:
        payload = response.json()
        sha = payload.get("sha", "")[:7]
        date = payload.get("commit", {}).get("committer", {}).get("date", "")[:10]
        message = payload.get("commit", {}).get("message", "").splitlines()[0]
        print(f"Latest main commit: {sha} ({date}) {message}")
        return "unknown"

    print(f"[WARN] GitHub returned HTTP {response.status_code}")
    return "error"


def _cmd_watch() -> None:
    from agent_reach.config import Config
    from agent_reach.doctor import check_all

    results = check_all(Config())
    issues = [
        f"{item['name']}: {item['message']}"
        for item in results.values()
        if item["status"] != "ok"
    ]

    update_status = _cmd_check_update()
    if not issues and update_status != "update_available":
        print("Agent Reach: all monitored channels look healthy")
        return

    print()
    print("Agent Reach Watch")
    print("========================================")
    for issue in issues:
        print(f"  {issue}")


if __name__ == "__main__":
    main()
