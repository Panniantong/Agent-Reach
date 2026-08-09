# -*- coding: utf-8 -*-
"""
Agent Reach CLI — installer, doctor, and configuration tool.

Usage:
    agent-reach install --env=auto
    agent-reach doctor
    agent-reach configure twitter-cookies
    agent-reach setup
"""

import argparse
import json
import os
import sys
import time

from agent_reach import __version__

# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"
_MAX_CONFIGURE_VALUE_CHARS = 1024 * 1024
_SENSITIVE_CONFIG_KEYS = {
    "proxy",
    "github-token",
    "groq-key",
    "openai-key",
    "twitter-cookies",
    "xhs-cookies",
}


def _ensure_utf8_console():
    """Best-effort Windows console UTF-8 setup for CLI runtime only."""
    if sys.platform != "win32":
        return
    # Avoid interfering with pytest/captured streams.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        # Do not crash CLI just because encoding patch failed.
        pass


def _configure_logging(verbose: bool = False):
    """Suppress loguru output unless --verbose is set."""
    from loguru import logger
    logger.remove()  # Remove default stderr handler
    if verbose:
        logger.add(sys.stderr, level="INFO")


def main():
    _ensure_utf8_console()

    parser = argparse.ArgumentParser(
        prog="agent-reach",
        description="Give your AI Agent eyes to see the entire internet",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"Agent Reach v{__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── setup ──
    sub.add_parser("setup", help="Interactive configuration wizard")

    # ── install ──
    p_install = sub.add_parser("install", help="One-shot installer with flags")
    p_install.add_argument("--env", choices=["local", "server", "auto"], default="auto",
                           help="Environment: local, server, or auto-detect")
    p_install.add_argument("--proxy", default="",
                           help="Network proxy saved for agents to export as HTTP(S)_PROXY "
                                "in restricted networks (http://user:pass@ip:port)")
    install_mode = p_install.add_mutually_exclusive_group()
    install_mode.add_argument(
        "--system",
        action="store_true",
        help="Explicitly allow system dependency, global tool, config, and skill installation",
    )
    install_mode.add_argument(
        "--safe",
        action="store_true",
        help="Safe check-only mode (default; retained for compatibility)",
    )
    p_install.add_argument("--dry-run", action="store_true",
                           help="Show what would be done without making any changes")
    p_install.add_argument("--channels", default="",
                           help="Comma-separated optional channels to install "
                                "(twitter,xiaoyuzhou,xueqiu,xiaohongshu,"
                                "reddit,facebook,instagram,bilibili,linkedin,all)")

    # ── configure ──
    p_conf = sub.add_parser("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument("key", nargs="?", default=None,
                        choices=["proxy", "github-token", "groq-key", "openai-key",
                                 "twitter-cookies", "youtube-cookies",
                                 "xhs-cookies"],
                        help="What to configure (omit if using --from-browser)")
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument(
        "--stdin",
        dest="read_stdin",
        action="store_true",
        help="Read the value from stdin instead of exposing it in process arguments",
    )
    p_conf.add_argument("--from-browser", metavar="BROWSER",
                        choices=["chrome", "firefox", "edge", "brave", "opera"],
                        help="Extract cookies for one explicitly selected platform")
    p_conf.add_argument(
        "--platform",
        choices=["twitter", "xiaohongshu", "bilibili", "xueqiu"],
        help="Platform to import (required with --from-browser)",
    )
    p_conf.add_argument(
        "--profile",
        help="Exact browser profile; a missing profile fails instead of falling back",
    )
    p_conf.add_argument(
        "--sync-legacy-twitter",
        action="store_true",
        help="With twitter-cookies, also write legacy xfetch/bird credential files",
    )

    # ── doctor ──
    p_doctor = sub.add_parser("doctor", help="Check platform availability")
    p_doctor.add_argument("--json", action="store_true",
                          help="Output machine-readable JSON instead of the text report")

    # ── uninstall ──
    p_uninstall = sub.add_parser("uninstall", help="Remove all Agent Reach config, tokens, and skill files")
    p_uninstall.add_argument("--dry-run", action="store_true",
                             help="Show what would be removed without making any changes")
    p_uninstall.add_argument("--keep-config", action="store_true",
                             help="Remove skill files only, keep ~/.agent-reach/ config and tokens")

    # ── skill ──
    p_skill = sub.add_parser("skill", help="Manage agent skill registration")
    p_skill_group = p_skill.add_mutually_exclusive_group(required=True)
    p_skill_group.add_argument("--install", action="store_true",
                               help="Install SKILL.md to agent skill directories")
    p_skill_group.add_argument("--uninstall", action="store_true",
                               help="Remove SKILL.md from agent skill directories")

    # ── format ──
    p_format = sub.add_parser("format", help="Clean and format platform API output")
    p_format.add_argument("platform", choices=["xhs"], help="Platform to format (xhs)")

    # ── check-update ──
    # ── transcribe ──
    p_tr = sub.add_parser("transcribe", help="Transcribe a URL or local audio file (Whisper via Groq/OpenAI)")
    p_tr.add_argument("source", help="Audio/video URL or local file path")
    p_tr.add_argument("--provider", choices=["auto", "groq", "openai"], default="auto",
                      help="Transcription provider (default: first configured provider)")
    p_tr.add_argument(
        "--allow-provider-fallback",
        action="store_true",
        help=(
            "With --provider auto, allow sending audio to the next "
            "configured provider after a failure"
        ),
    )
    p_tr.add_argument("-o", "--output", default=None,
                      help="Write transcript to a file instead of stdout")

    sub.add_parser("check-update", help="Check for new versions and changes")

    # ── watch ──
    sub.add_parser("watch", help="Quick health check + update check (for scheduled tasks)")

    # ── version ──
    sub.add_parser("version", help="Show version")

    args = parser.parse_args()

    if args.command == "configure" and args.from_browser:
        if args.read_stdin:
            p_conf.error("--stdin cannot be combined with --from-browser")
        if not args.platform:
            p_conf.error("--platform is required with --from-browser")
        manual_keys = {
            "twitter": "twitter-cookies",
            "xiaohongshu": "xhs-cookies",
        }
        if args.platform in manual_keys:
            p_conf.error(
                f"{args.platform} requires Cookie-Editor export; use "
                f"`agent-reach configure {manual_keys[args.platform]} ...`"
            )
        if args.profile and args.from_browser not in {"chrome", "edge", "brave"}:
            p_conf.error(
                "--profile is supported only for Chrome/Edge/Brave"
            )
        if args.sync_legacy_twitter:
            p_conf.error("--sync-legacy-twitter is only valid with twitter-cookies")
    elif args.command == "configure":
        if args.read_stdin and args.value:
            p_conf.error("--stdin cannot be combined with a positional value")
        if args.read_stdin and not args.key:
            p_conf.error("--stdin requires a configure key")
        if args.profile or args.platform:
            p_conf.error("--platform/--profile require --from-browser")
        if args.sync_legacy_twitter and args.key != "twitter-cookies":
            p_conf.error("--sync-legacy-twitter is only valid with twitter-cookies")

    if (
        args.command == "transcribe"
        and args.allow_provider_fallback
        and args.provider != "auto"
    ):
        p_tr.error("--allow-provider-fallback requires --provider auto")

    # Suppress loguru noise unless --verbose
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"Agent Reach v{__version__}")
        sys.exit(0)

    if args.command == "doctor":
        _cmd_doctor(args)
    elif args.command == "check-update":
        _cmd_check_update()
    elif args.command == "watch":
        _cmd_watch()
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "install":
        _cmd_install(args)
    elif args.command == "configure":
        _cmd_configure(args)
    elif args.command == "uninstall":
        _cmd_uninstall(args)
    elif args.command == "skill":
        _cmd_skill(args)
    elif args.command == "format":
        _cmd_format(args)
    elif args.command == "transcribe":
        _cmd_transcribe(args)


# ── Command handlers ────────────────────────────────


def _cmd_install(args):
    """One-shot deterministic installer."""
    import os

    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report

    safe_mode = getattr(args, "safe", False) or not getattr(args, "system", False)
    dry_run = args.dry_run

    # Validate channel names before constructing config or changing the system.
    CHANNEL_INSTALLERS = {
        "twitter":     _install_twitter_deps,
        "xiaoyuzhou":  _install_xiaoyuzhou_deps,
        "xiaohongshu": _install_xhs_deps,
        "reddit":      _install_reddit_deps,
        "facebook":    _install_opencli_deps,
        "instagram":   _install_opencli_deps,
        "bilibili":    _install_bili_deps,
        "opencli":     _install_opencli_deps,  # cross-channel backend, desktop only
        # xueqiu: cookie-only, no install step
        # linkedin: manual setup, no auto-install
    }
    supported_channels = set(CHANNEL_INSTALLERS) | {"xueqiu", "linkedin"}
    raw_channels = [
        channel.strip().lower()
        for channel in args.channels.split(",")
        if channel.strip()
    ]
    unknown_channels = set(raw_channels) - supported_channels - {"all"}
    if unknown_channels:
        supported = ", ".join(sorted(supported_channels | {"all"}))
        unknown = ", ".join(sorted(unknown_channels))
        print(
            f"agent-reach install: error: unknown channel(s): {unknown}. "
            f"Supported: {supported}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if "all" in raw_channels:
        requested_channels = supported_channels
    else:
        requested_channels = set(raw_channels)

    config = Config(read_only=dry_run or safe_mode)
    print()
    print("Agent Reach Installer")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("SAFE MODE — skipping automatic system changes")
        print()

    # Only a real installation may create persistent directories.
    if not dry_run and not safe_mode:
        tools_dir = os.path.expanduser("~/.agent-reach/tools")
        os.makedirs(tools_dir, exist_ok=True)

    OPENCLI_ONLY_CHANNELS = {"opencli", "facebook", "instagram"}
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili", "xiaohongshu"}

    # Auto-detect environment
    env = args.env
    if env == "auto":
        env = _detect_environment()

    if env == "server":
        print("Environment: Server/VPS (auto-detected)")
    else:
        print("Environment: Local computer (auto-detected)")

    server_skipped_opencli_channels = set()
    if env == "server" and requested_channels:
        # OpenCLI rides a real desktop Chrome session — useless headless
        server_skipped_opencli_channels = requested_channels & OPENCLI_ONLY_CHANNELS
        requested_channels -= server_skipped_opencli_channels

    # Apply explicit flags
    if args.proxy:
        if dry_run or safe_mode:
            mode = "dry-run" if dry_run else "safe"
            print(f"[{mode}] Would save network proxy")
        else:
            config.set("proxy", args.proxy)
            config.set("bilibili_proxy", args.proxy)  # legacy key
            print("✅ 代理已保存（Agent 访问受限网络时使用）")

    # ── Install core system dependencies (lightweight, always) ──
    print()
    core_install_ok = True
    if dry_run:
        _install_system_deps_dryrun()
    elif safe_mode:
        _install_system_deps_safe()
    else:
        core_install_ok = _install_system_deps() is not False

    # ── mcporter (for Exa search) ──
    print()
    if dry_run:
        print("[dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        _install_mcporter_safe()
    else:
        core_install_ok = (_install_mcporter() is not False) and core_install_ok

    if server_skipped_opencli_channels:
        print()
        print("  -- OpenCLI 需要桌面环境 + Chrome，服务器环境跳过："
              f"{', '.join(sorted(server_skipped_opencli_channels))}")

    # ── Install optional channels (only if --channels specified) ──
    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        ran_installers = set()
        optional_install_ok = True
        for ch_name in sorted(requested_channels):
            installer = CHANNEL_INSTALLERS.get(ch_name)
            if installer and installer not in ran_installers:
                optional_install_ok = (
                    installer() is not False
                ) and optional_install_ok
                ran_installers.add(installer)
    else:
        optional_install_ok = True

    if requested_channels and dry_run:
        print()
        print(f"[dry-run] Would install optional channels: {', '.join(sorted(requested_channels))}")

    # ── Cookie setup (explicit only — install never reads browser credentials) ──
    needs_cookies = bool(requested_channels & COOKIE_CHANNELS)
    if env == "local" and needs_cookies and not dry_run:
        print()
        print("Cookie login is never read automatically.")
        print("Run only the platform command you intend to authorize:")
        for channel in sorted(requested_channels & COOKIE_CHANNELS):
            if channel == "twitter":
                print("  agent-reach configure twitter-cookies")
            elif channel == "xiaohongshu":
                print("  agent-reach configure xhs-cookies")
            else:
                print(
                    "  agent-reach configure --from-browser chrome "
                    f"--platform {channel}"
                )
    elif env == "local" and needs_cookies and dry_run:
        print()
        print("[dry-run] Cookie import remains explicit; install will not read a browser")

    # Environment-specific advice
    if env == "server":
        print()
        print("Tip: 部分平台对服务器 IP 有风控。")
        print("   Reddit 必须登录态（rdt-cli + Cookie，见 doctor 提示），中国大陆网络还需代理。")
        print("   保存代理供 Agent 使用：agent-reach configure proxy（隐藏输入）")
        print("   Cheap option: https://www.webshare.io ($1/month)")

    # Test channels
    if not dry_run:
        print()
        print("Testing channels...")
        results = check_all(config)
        ok = sum(1 for r in results.values() if r["status"] == "ok")
        total = len(results)

        # Final status
        print()
        print(format_report(results))
        print()

        if safe_mode:
            print(
                "Safe mode check complete. No changes were made. "
                f"{ok}/{total} channels active."
            )
        else:
            # ── Install agent skill ──
            skill_install_ok = _install_skill() is not False
            install_ok = (
                core_install_ok and optional_install_ok and skill_install_ok
            )

            if install_ok:
                print(f"Installation complete. {ok}/{total} channels active.")
            else:
                print(
                    "Installation incomplete: one or more requested "
                    f"steps failed. {ok}/{total} channels active."
                )

            if not requested_channels:
                # First install — hint about optional channels
                print()
                print("More channels available! Use --channels to install:")
                print("   agent-reach install --system --channels=twitter,xiaohongshu,reddit,facebook,instagram,...")
                print("   agent-reach install --system --channels=all  (install everything)")

            # Star reminder
            print()
            print("如果 Agent Reach 帮到了你，给个 Star 让更多人发现它吧：")
            print("   https://github.com/Panniantong/Agent-Reach")
            print("   只需一秒，对独立开发者意义很大。谢谢！")
            if not install_ok:
                raise SystemExit(1)
    else:
        print()
        print("Dry run complete. No changes were made.")


def _resolve_hermes_home() -> tuple[str, bool]:
    """Return a safe Hermes home and whether it was explicitly selected."""
    raw = os.environ.get("HERMES_HOME", "").strip()
    if raw:
        expanded = os.path.expanduser(os.path.expandvars(raw))
        if os.path.isabs(expanded):
            return expanded, True
    return os.path.expanduser("~/.hermes"), False


def _install_skill(force: bool = True):
    """Install Agent Reach as an agent skill for supported agent clients."""
    import importlib.resources
    import os
    import shutil

    def _is_english_locale(value: str) -> bool:
        normalized = value.strip().lower()
        return normalized.startswith("en") or normalized.startswith("english")

    def _skill_resource_name() -> str:
        locale_candidates = (
            os.environ.get("AGENT_REACH_LANG", ""),
            os.environ.get("LC_ALL", ""),
            os.environ.get("LC_MESSAGES", ""),
            os.environ.get("LANG", ""),
        )
        if any(_is_english_locale(candidate) for candidate in locale_candidates):
            return "SKILL_en.md"
        return "SKILL.md"

    def _read_skill_markdown(skill_pkg):
        resource_name = _skill_resource_name()
        try:
            return skill_pkg.joinpath(resource_name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return skill_pkg.joinpath("SKILL.md").read_text(encoding="utf-8")

    def _copy_skill_dir(target: str) -> str | None:
        """Copy entire skill directory (locale-specific SKILL.md + references/)."""
        try:
            if not force and os.path.exists(os.path.join(target, "SKILL.md")):
                return "preserved"

            # Clear existing installation. A symlinked skill dir (dotfiles
            # setups) breaks shutil.rmtree — unlink the link itself instead.
            if os.path.islink(target):
                os.unlink(target)
            elif os.path.exists(target):
                shutil.rmtree(target)
            os.makedirs(target, exist_ok=True)

            # Get skill directory from package (with fallback for editable installs)
            try:
                skill_pkg = importlib.resources.files("agent_reach").joinpath("skill")
                skill_md = _read_skill_markdown(skill_pkg)
            except Exception:
                from pathlib import Path
                skill_pkg = Path(__file__).resolve().parent / "skill"
                skill_md = _read_skill_markdown(skill_pkg)

            # Copy SKILL.md using the selected locale file
            with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(skill_md)

            # Copy references/ directory
            refs_pkg = skill_pkg.joinpath("references")
            refs_target = os.path.join(target, "references")
            os.makedirs(refs_target, exist_ok=True)

            for ref_file in refs_pkg.iterdir():
                name = ref_file.name if hasattr(ref_file, 'name') else str(ref_file).split('/')[-1]
                if name.endswith(".md"):
                    content = ref_file.read_text(encoding="utf-8") if hasattr(ref_file, 'read_text') else ref_file.read_text()
                    with open(os.path.join(refs_target, name), "w", encoding="utf-8") as f:
                        f.write(content)

            return "installed"
        except Exception as e:
            print(f"  Warning: Could not install skill: {e}")
            return None

    # Install into every known skill root that already exists. An explicitly
    # selected Hermes profile may not have created its skills directory yet,
    # so create that child directory only when the profile home itself exists.
    hermes_home, explicit_hermes_home = _resolve_hermes_home()
    hermes_skills = os.path.join(hermes_home, "skills")
    if explicit_hermes_home and os.path.isdir(hermes_home):
        try:
            os.makedirs(hermes_skills, exist_ok=True)
        except OSError as exc:
            print(f"  Warning: Could not prepare Hermes skill directory: {exc}")
    skill_dirs = [
        (hermes_skills, "Hermes"),
        (os.path.expanduser("~/.agents/skills"), "Agent"),
        (os.path.expanduser("~/.config/opencode/skills"), "OpenCode"),
        (os.path.expanduser("~/.openclaw/skills"), "OpenClaw"),
        (os.path.expanduser("~/.claude/skills"), "Claude Code"),
    ]

    # Insert OPENCLAW_HOME path at the beginning if environment variable is set
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills"), "OpenClaw"),
        )

    installed = False
    for skill_dir, platform_name in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "agent-reach")
            status = _copy_skill_dir(target)
            if status:
                if status == "preserved":
                    print(f"Skill already installed for {platform_name}, preserving existing files: {target}")
                else:
                    print(f"Skill installed for {platform_name}: {target}")
                installed = True

    if not installed:
        # No known skill directory found — create for .agents by default
        target = os.path.expanduser("~/.agents/skills/agent-reach")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        status = _copy_skill_dir(target)
        if status == "preserved":
            print(f"Skill already installed, preserving existing files: {target}")
        elif status == "installed":
            print(f"Skill installed: {target}")
            installed = True
        else:
            print("  -- Could not install agent skill (optional)")
            print(
                "  -- Tip: install OpenCode, OpenClaw, Claude Code, "
                "or create ~/.agents/skills/ manually"
            )
    return installed


def _uninstall_skill():
    """Remove SKILL.md from all known agent skill directories."""
    import shutil

    hermes_home, _ = _resolve_hermes_home()
    hermes_skill = os.path.join(hermes_home, "skills", "agent-reach")
    skill_dirs = [
        (hermes_skill, "Hermes"),
        ("~/.config/opencode/skills/agent-reach", "OpenCode"),
        ("~/.openclaw/skills/agent-reach", "OpenClaw"),
        ("~/.claude/skills/agent-reach", "Claude Code"),
        ("~/.agents/skills/agent-reach", "Agent"),
    ]

    # Also check OPENCLAW_HOME
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills", "agent-reach"), "OpenClaw"),
        )

    removed = False
    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            try:
                if os.path.islink(skill_path):
                    os.unlink(skill_path)
                else:
                    shutil.rmtree(skill_path)
                print(f"  Removed {platform_name} skill: {skill_path}")
                removed = True
            except Exception as e:
                print(f"  Could not remove {skill_path}: {e}")

    if not removed:
        print("  No skill installations found.")


def _cmd_skill(args):
    """Manage agent skill registration."""
    if args.install:
        if not _install_skill():
            raise SystemExit(1)
    elif args.uninstall:
        _uninstall_skill()


def _cmd_format(args):
    """Clean and format platform API output from stdin."""
    import json
    import sys

    if args.platform == "xhs":
        from agent_reach.channels.xiaohongshu import format_xhs_result

        raw = sys.stdin.read().strip()
        if not raw:
            print("Error: no input on stdin", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

        cleaned = format_xhs_result(data)
        print(json.dumps(cleaned, ensure_ascii=False, indent=2))


def _install_system_deps():
    """Install system dependencies through an existing OS package manager."""
    import platform
    import shutil
    import subprocess

    print("Checking system dependencies...")

    gh_installed = bool(shutil.which("gh"))
    node_installed = bool(shutil.which("node") and shutil.which("npm"))

    if gh_installed:
        print("  ✅ gh CLI already installed")
    if node_installed:
        print("  ✅ Node.js already installed")

    missing_labels = []
    if not gh_installed:
        missing_labels.append("gh CLI")
    if not node_installed:
        missing_labels.append("Node.js")
    system_install_ok = not missing_labels

    os_type = platform.system().lower()
    if missing_labels and os_type == "linux":
        apt_get = shutil.which("apt-get")
        if not apt_get:
            system_install_ok = False
            print(
                "  [!]  Missing system dependencies: "
                f"{', '.join(missing_labels)}. apt-get is not available; "
                "install them manually."
            )
        else:
            packages = []
            if not gh_installed:
                packages.append("gh")
            if not node_installed:
                packages.extend(("nodejs", "npm"))
            print(f"  Installing {', '.join(missing_labels)} with apt-get...")
            try:
                update_result = subprocess.run(
                    [apt_get, "update", "-qq"],
                    capture_output=True,
                    timeout=120,
                )
                if update_result.returncode != 0:
                    system_install_ok = False
                    print(
                        "  [!]  apt-get update failed; no packages were installed."
                    )
                else:
                    install_result = subprocess.run(
                        [apt_get, "install", "-y", "-qq", *packages],
                        capture_output=True,
                        timeout=180,
                    )
                    if install_result.returncode == 0:
                        system_install_ok = True
                        print(
                            "  ✅ Installed with apt-get: "
                            f"{', '.join(missing_labels)}"
                        )
                    else:
                        system_install_ok = False
                        print(
                            "  [!]  apt-get install failed for: "
                            f"{', '.join(missing_labels)}"
                        )
            except (OSError, subprocess.TimeoutExpired):
                system_install_ok = False
                print(
                    "  [!]  apt-get failed for: "
                    f"{', '.join(missing_labels)}"
                )
    elif missing_labels and os_type == "darwin":
        brew = shutil.which("brew")
        if not brew:
            system_install_ok = False
            print(
                "  [!]  Missing system dependencies: "
                f"{', '.join(missing_labels)}. Homebrew is not available; "
                "install them manually."
            )
        else:
            system_install_ok = True
            brew_packages = []
            if not gh_installed:
                brew_packages.append(("gh", "gh CLI"))
            if not node_installed:
                brew_packages.append(("node", "Node.js"))
            for package, label in brew_packages:
                print(f"  Installing {label} with Homebrew...")
                try:
                    undici_result = subprocess.run(
                        [brew, "install", package],
                        capture_output=True,
                        timeout=180,
                    )
                    if undici_result.returncode == 0:
                        print(f"  ✅ {label} installed")
                    else:
                        system_install_ok = False
                        print(f"  [!]  {label} install failed")
                except (OSError, subprocess.TimeoutExpired):
                    system_install_ok = False
                    print(f"  [!]  {label} install failed")
    elif missing_labels:
        system_install_ok = False
        print(
            "  [!]  Missing system dependencies: "
            f"{', '.join(missing_labels)}. Install them manually."
        )

    # ── undici (proxy support for Node.js fetch) ──
    npm_cmd = shutil.which("npm")
    if npm_cmd:
        try:
            npm_root_result = subprocess.run(
                [npm_cmd, "root", "-g"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            npm_root_result = None

        if npm_root_result is None or npm_root_result.returncode != 0:
            print(
                "  -- Could not inspect global npm packages; "
                "skipping optional undici install"
            )
        else:
            npm_root = npm_root_result.stdout.strip()
            undici_path = (
                os.path.join(npm_root, "undici", "index.js")
                if npm_root
                else ""
            )
            if os.path.exists(undici_path):
                print("  ✅ undici already installed (Node.js proxy support)")
            else:
                try:
                    result = subprocess.run(
                        [npm_cmd, "install", "-g", "undici"],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=60,
                    )
                    if result.returncode == 0:
                        print("  ✅ undici installed (Node.js proxy support)")
                    else:
                        print(
                            "  -- undici install failed "
                            "(optional — may not work behind proxies)"
                        )
                except (OSError, subprocess.TimeoutExpired):
                    print(
                        "  -- undici install failed "
                        "(optional — may not work behind proxies)"
                    )

    # ── yt-dlp JS runtime config (YouTube requires external JS runtime) ──
    if shutil.which("deno"):
        print("  ✅ yt-dlp can use the installed Deno JS runtime")
    elif shutil.which("node"):
        from agent_reach.channels.youtube import (
            _JS_RUNTIMES_SUPPORTED_FROM,
            _parse_ytdlp_version,
        )
        from agent_reach.utils.paths import (
            PrivatePathError,
            atomic_write_private_text,
            get_ytdlp_config_path,
            read_small_text_no_follow,
        )

        ytdlp_cmd = shutil.which("yt-dlp")
        installed_version = None
        if ytdlp_cmd:
            try:
                version_result = subprocess.run(
                    [ytdlp_cmd, "--version"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if version_result.returncode == 0:
                    installed_version = _parse_ytdlp_version(
                        version_result.stdout.strip()
                    )
            except (OSError, subprocess.TimeoutExpired):
                installed_version = None

        if (
            installed_version is None
            or installed_version < _JS_RUNTIMES_SUPPORTED_FROM
        ):
            print(
                "  -- 未写入 yt-dlp JS runtime 配置：yt-dlp 缺失、过旧或"
                "版本无法确认。先升级：python -m pip install -U "
                '"yt-dlp[default]"'
            )
        else:
            ytdlp_config = get_ytdlp_config_path()
            try:
                existing_config = read_small_text_no_follow(
                    ytdlp_config,
                    max_bytes=1024 * 1024,
                )
                if (
                    existing_config is not None
                    and "--js-runtimes" in existing_config
                ):
                    print("  ✅ yt-dlp JS runtime already configured")
                else:
                    existing_config = existing_config or ""
                    separator = (
                        ""
                        if not existing_config
                        or existing_config.endswith(("\n", "\r"))
                        else "\n"
                    )
                    atomic_write_private_text(
                        ytdlp_config,
                        existing_config
                        + separator
                        + "--js-runtimes node\n",
                    )
                    print(
                        "  ✅ yt-dlp configured to use Node.js as JS runtime "
                        "(YouTube)"
                    )
            except (OSError, UnicodeError, ValueError, PrivatePathError):
                print(
                    "  -- Could not configure yt-dlp JS runtime "
                    "(YouTube may not work)"
                )

    # NOTE: twitter-cli, xiaoyuzhou, xhs-cli etc. are optional.
    # They are installed via --channels flag, not here.
    # See CHANNEL_INSTALLERS in _cmd_install().
    return system_install_ok


def _install_xiaoyuzhou_deps():
    """Install Xiaoyuzhou podcast transcription script."""
    import shutil

    from agent_reach.config import Config
    from agent_reach.utils.paths import PrivatePathError, atomic_write_private_text

    config = Config()
    print("Setting up Xiaoyuzhou podcast transcription...")

    tools_dir = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou")
    script_dst = os.path.join(tools_dir, "transcribe.sh")

    script_src = os.path.join(
        os.path.dirname(__file__),
        "scripts",
        "transcribe_xiaoyuzhou.sh",
    )
    script_ok = False
    if os.path.isfile(script_src):
        existed = os.path.isfile(script_dst)
        try:
            with open(script_src, encoding="utf-8") as source:
                script_text = source.read()
            atomic_write_private_text(script_dst, script_text)
            os.chmod(script_dst, 0o700)
            action = "updated" if existed else "installed"
            print(f"  ✅ Xiaoyuzhou transcription script {action}")
            script_ok = True
        except (OSError, UnicodeError, PrivatePathError) as exc:
            print(f"  [!]  Failed to install script: {exc}")
    else:
        print("  [!]  Script source not found in package")

    # Check ffmpeg
    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    if ffmpeg_ok:
        print("  ✅ ffmpeg available")
    else:
        print("  -- ffmpeg not found. Install: apt install -y ffmpeg (or brew install ffmpeg)")

    # Check GROQ_API_KEY
    has_key = bool(os.environ.get("GROQ_API_KEY")) or bool(config.get("groq_api_key"))
    if has_key:
        print("  ✅ Groq API key configured")
    else:
        print("  -- Groq API key not set. Get free key at https://console.groq.com")
        print("     Then run: agent-reach configure groq-key（隐藏输入）")
    return script_ok and ffmpeg_ok


def _install_twitter_deps():
    """Install twitter-cli for Twitter search + timeline."""
    import shutil
    import subprocess

    print("Setting up Twitter (twitter-cli)...")
    if shutil.which("twitter"):
        print("  ✅ twitter-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", "twitter-cli"]),
        ("uv", ["tool", "install", "twitter-cli"]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("twitter"):
                    print("  ✅ twitter-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print("  [!]  twitter-cli install failed. Run: pipx install twitter-cli")
    return False


def _install_xhs_deps():
    """Set up XiaoHongShu — backend depends on environment.

    Desktop: OpenCLI (reuses the browser session, zero config).
    Server: xiaohongshu-mcp guide with an explicit Cookie-Editor export;
    we don't manage long-running services, so guide only.
    xhs-cli is no longer installed by default — upstream unmaintained
    since 2026-03; existing installs keep working as a fallback backend.
    """
    import shutil

    print("Setting up XiaoHongShu...")
    if _detect_environment() == "server":
        print("  服务器环境推荐 xiaohongshu-mcp：")
        print("    1. 下载 binary：https://github.com/xpzouying/xiaohongshu-mcp/releases")
        print("       （建议放到 ~/.agent-reach/tools/ 下）")
        print("    2. 启动服务（首次运行会下载约 150MB 浏览器，请等待完成）")
        print("    3. 用 Cookie-Editor 从 xiaohongshu.com 明确导出 Cookie")
        print("       agent-reach configure xhs-cookies（粘贴到隐藏输入提示）")
        print("    4. 接入：mcporter config add xiaohongshu http://localhost:18060/mcp --scope home")
        print("    5. 验证：agent-reach doctor")
        return False

    opencli_ok = _install_opencli_deps()
    xhs_ok = bool(shutil.which("xhs"))
    if xhs_ok:
        print("  ✅ 检测到存量 xhs-cli，将作为备选后端继续可用")
    return opencli_ok or xhs_ok


def _install_opencli_deps():
    """Install OpenCLI — cross-platform backend riding the user's Chrome session.

    Desktop-only. The npm package installs automatically; the Chrome
    extension CANNOT be installed programmatically (Chrome security model),
    so we print a one-click guide instead.
    """
    import shutil
    import subprocess

    from agent_reach.backends import (
        OPENCLI_EXTENSION_URL,
        OPENCLI_PACKAGE,
        opencli_status,
        opencli_summary,
    )

    print("Setting up OpenCLI (browser-session backend, desktop only)...")
    st = opencli_status()
    if st.installed and not st.broken:
        print(f"  ✅ {opencli_summary(st)}")
        if not st.ready:
            print(f"  {st.hint}")
        return True

    npm_cmd = shutil.which("npm")
    if not npm_cmd:
        print("  [!]  OpenCLI requires Node.js ≥ 20. Install Node first:")
        print("       https://nodejs.org  （或 brew install node）")
        return False

    try:
        install_result = subprocess.run(
            [npm_cmd, "install", "-g", OPENCLI_PACKAGE],
            capture_output=True, encoding="utf-8", errors="replace", timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        install_result = None

    st = opencli_status()
    if (
        install_result is not None
        and install_result.returncode == 0
        and st.installed
        and not st.broken
    ):
        print("  ✅ OpenCLI installed")
        print("  最后一步（必须手动，Chrome 安全限制）：安装浏览器扩展")
        print(f"    1. 打开 {OPENCLI_EXTENSION_URL}")
        print("    2. 点「添加至 Chrome」")
        print("    3. 运行 `opencli doctor` 验证连接")
        return True
    else:
        print(f"  [!]  OpenCLI install failed. Run: npm install -g {OPENCLI_PACKAGE}")
        return False


def _install_reddit_deps():
    """Set up Reddit — desktop prefers OpenCLI, rdt-cli for servers/legacy.

    No zero-config path exists (anonymous .json blocked, official API
    approval-gated since 2025-11) — every backend needs a logged-in session.
    """
    if _detect_environment() != "server":
        installed = _install_opencli_deps()
        print("  Reddit 走 OpenCLI（浏览器里登录过 reddit.com 即可用）")
        import shutil
        if shutil.which("rdt"):
            print("  ✅ 检测到存量 rdt-cli，将作为备选后端继续可用")
        return installed

    return _install_rdt_cli()


def _install_rdt_cli():
    """Install rdt-cli (pinned git source — PyPI lags upstream)."""
    import shutil
    import subprocess

    print("Setting up Reddit (rdt-cli)...")
    if shutil.which("rdt"):
        print("  ✅ rdt-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", _RDT_GIT_SOURCE]),
        ("uv", ["tool", "install", "--from", _RDT_GIT_SOURCE, "rdt-cli"]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("rdt"):
                    print("  ✅ rdt-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print(f"  [!]  rdt-cli install failed. Run: pipx install '{_RDT_GIT_SOURCE}'")
    return False


def _install_bili_deps():
    """Install bili-cli for Bilibili hot/rank/search."""
    import shutil
    import subprocess

    print("Setting up Bilibili (bili-cli)...")
    if shutil.which("bili"):
        print("  ✅ bili-cli already installed")
        return True
    for tool, args in [
        ("pipx", ["install", "bilibili-cli"]),
        ("uv", ["tool", "install", "bilibili-cli"]),
    ]:
        tool_cmd = shutil.which(tool)
        if tool_cmd:
            try:
                result = subprocess.run(
                    [tool_cmd, *args], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=120,
                )
                if result.returncode == 0 and shutil.which("bili"):
                    print("  ✅ bili-cli installed")
                    return True
            except (OSError, subprocess.TimeoutExpired):
                pass
    print("  [!]  bili-cli install failed. Run: pipx install bilibili-cli")
    return False


def _install_system_deps_safe():
    """Safe mode: check what's installed, print instructions for what's missing."""
    import shutil

    print("Checking system dependencies (safe mode — no auto-install)...")

    deps = [
        ("gh", ["gh"], "GitHub CLI", "https://cli.github.com — or: apt install gh / brew install gh"),
        ("node", ["node", "npm"], "Node.js", "https://nodejs.org — or: apt install nodejs npm"),
    ]

    missing = []
    for name, binaries, label, install_hint in deps:
        found = all(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label} already installed")
        else:
            print(f"  -- {label} not found")
            missing.append((label, install_hint))

    if missing:
        print()
        print("  To install missing dependencies manually:")
        for label, hint in missing:
            print(f"    {label}: {hint}")
    else:
        print("  All system dependencies are installed!")


def _install_system_deps_dryrun():
    """Dry-run: just show what would be checked/installed."""
    import shutil

    print("[dry-run] System dependency check:")

    checks = [
        ("gh CLI", ["gh"], "apt-get install gh / brew install gh"),
        (
            "Node.js",
            ["node", "npm"],
            "apt-get install nodejs npm / brew install node",
        ),
    ]

    for label, binaries, method in checks:
        found = all(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label}: already installed, skip")
        else:
            print(f"  {label}: would install via: {method}")



def _install_mcporter():
    """Install mcporter and configure Exa search."""
    import shutil
    import subprocess

    print("Setting up mcporter (search backend)...")

    mcporter_cmd = shutil.which("mcporter")
    if mcporter_cmd:
        print("  ✅ mcporter already installed")
    else:
        npm_cmd = shutil.which("npm")
        if not npm_cmd:
            print("  [!]  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/")
            return False
        try:
            install_result = subprocess.run(
                [npm_cmd, "install", "-g", "mcporter"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            )
            mcporter_cmd = shutil.which("mcporter")
            if install_result.returncode == 0 and mcporter_cmd:
                print("  ✅ mcporter installed")
            else:
                print("  [X] mcporter install failed. Retry: npm install -g mcporter (check network/timeout), or try: npx mcporter@latest list")
                return False
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"  [X] mcporter install failed: {e}")
            return False

    # Configure Exa MCP (free, no key needed)
    try:
        from agent_reach.channels.mcporter import (
            McporterConfigError,
            configured_server_names,
        )

        r = subprocess.run(
            [mcporter_cmd, "config", "list", "--json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if r.returncode != 0:
            raise McporterConfigError("mcporter 配置查询失败")
        server_names = configured_server_names(r.stdout)
        if "exa" not in server_names:
            add_result = subprocess.run(
                [
                    mcporter_cmd,
                    "config",
                    "add",
                    "exa",
                    "https://mcp.exa.ai/mcp",
                    "--scope",
                    "home",
                ],
                capture_output=True, encoding="utf-8", errors="replace", timeout=10,
            )
            if add_result.returncode == 0:
                print("  ✅ Exa search configured (free, no API key needed)")
                return True
            else:
                print(
                    "  [!]  Could not configure Exa. Run manually: "
                    "mcporter config add exa https://mcp.exa.ai/mcp --scope home"
                )
                return False
        else:
            print("  ✅ Exa search already configured")
            return True
    except Exception:
        print("  [!]  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        return False

    # NOTE: xhs-cli is now optional, installed via --channels=xiaohongshu


def _install_mcporter_safe():
    """Safe mode: check mcporter status, print instructions."""
    import shutil

    print("Checking mcporter (safe mode)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp --scope home")
    else:
        print("  -- mcporter not installed")
        print("  To install: npm install -g mcporter")
        print("  Then configure Exa: mcporter config add exa https://mcp.exa.ai/mcp --scope home")


def _detect_environment():
    """Auto-detect if running on local computer or server."""
    import os

    # Check common server indicators
    indicators = 0

    # SSH session
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        indicators += 2

    # Docker / container
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        indicators += 2

    # No display (headless)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        indicators += 1

    # Cloud VM identifiers
    for cloud_file in ["/sys/hypervisor/uuid", "/sys/class/dmi/id/product_name"]:
        if os.path.exists(cloud_file):
            try:
                with open(cloud_file) as f:
                    content = f.read().lower()
                if any(x in content for x in ["amazon", "google", "microsoft", "digitalocean", "linode", "vultr", "hetzner"]):
                    indicators += 2
            except Exception:
                pass

    # systemd-detect-virt
    try:
        import subprocess
        result = subprocess.run(["systemd-detect-virt"], capture_output=True, encoding="utf-8", errors="replace", timeout=3)
        if result.returncode == 0 and result.stdout.strip() != "none":
            indicators += 1
    except Exception:
        pass

    return "server" if indicators >= 2 else "local"


def _read_configure_value(args) -> str:
    """Read one configure value without echoing secrets by default."""
    values = getattr(args, "value", None) or []
    if getattr(args, "read_stdin", False):
        try:
            value = sys.stdin.read(_MAX_CONFIGURE_VALUE_CHARS + 1)
        except OSError:
            print("Could not read configure value from stdin", file=sys.stderr)
            raise SystemExit(1) from None
        if len(value) > _MAX_CONFIGURE_VALUE_CHARS:
            print("Configure value exceeds the 1 MiB safety limit", file=sys.stderr)
            raise SystemExit(1)
        return value.rstrip("\r\n")

    if values:
        if getattr(args, "key", None) in _SENSITIVE_CONFIG_KEYS:
            print(
                "Warning: positional secrets are deprecated because shell history "
                "and process listings may expose them; omit the value for a hidden "
                "prompt or use --stdin.",
                file=sys.stderr,
            )
        return " ".join(values)

    try:
        interactive = bool(sys.stdin.isatty())
    except (AttributeError, OSError):
        interactive = False
    if not interactive:
        return ""

    import getpass

    try:
        return getpass.getpass(f"Value for {args.key}: ")
    except (EOFError, KeyboardInterrupt):
        print("Configure input cancelled", file=sys.stderr)
        raise SystemExit(1) from None


def _cmd_configure(args):
    """Set a config value and test it, or auto-extract from browser."""
    import shutil
    from typing import cast

    from agent_reach.config import Config

    config = Config()

    # ── Auto-extract from browser ──
    if args.from_browser:
        from agent_reach.cookie_extract import configure_from_browser

        browser = args.from_browser
        platform = "xhs" if args.platform == "xiaohongshu" else args.platform
        print(f"Extracting {args.platform} cookies from {browser}...")
        print()

        try:
            results = configure_from_browser(
                browser,
                config,
                platform=platform,
                profile=args.profile,
            )
        except ValueError as exc:
            from agent_reach.utils.text import scrub_url_credentials

            print(
                f"agent-reach configure: error: "
                f"{scrub_url_credentials(exc)}",
                file=sys.stderr,
            )
            raise SystemExit(2) from None

        found_any = False
        for result in results:
            if hasattr(result, "platform"):
                result_platform = result.platform
                success = result.success
                message = result.message
                targets = getattr(result, "targets", ())
            else:
                legacy_result = cast(tuple[str, bool, str], result)
                result_platform, success, message = legacy_result
                targets = ()
            if success:
                print(f"  ✅ {result_platform}: {message}")
                if targets:
                    print(f"     写入：{', '.join(targets)}")
                found_any = True
            else:
                print(f"  -- {result_platform}: {message}")

        print()
        if found_any:
            print("✅ Cookies configured! Run `agent-reach doctor` to see updated status.")
        else:
            print(f"No cookies found. Make sure you're logged into the platforms in {browser}.")
            raise SystemExit(1)
        return

    # ── Manual configure ──
    if not args.key:
        print("Usage: agent-reach configure <key> [--stdin]")
        print("   Omit the value to enter it through a hidden prompt.")
        print(
            "   or: agent-reach configure --from-browser chrome "
            "--platform xueqiu"
        )
        return

    value = _read_configure_value(args)
    if not value:
        print(f"Missing value for {args.key}")
        raise SystemExit(1)

    if args.key == "proxy":
        # Generic network proxy for restricted environments. Nothing reads
        # this key at runtime — agents read it back and export HTTP(S)_PROXY
        # before invoking upstream tools (see docs/install.md). The legacy
        # bilibili_proxy key is kept in sync for older configs.
        config.set("proxy", value)
        config.set("bilibili_proxy", value)
        print("✅ 代理已保存（供 Agent 在访问 Reddit/Twitter 等需要代理的网络时设置 HTTP_PROXY/HTTPS_PROXY）")
        print("  Note: B站走 bili-cli，国内网络无需代理。")

    elif args.key == "twitter-cookies":
        # Accept two formats:
        # 1. auth_token ct0 (two separate values)
        # 2. Full cookie header string: "auth_token=xxx; ct0=yyy; ..."
        auth_token, ct0 = _parse_twitter_cookie_input(value)

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)

            print("✅ Twitter cookies 已保存到 ~/.agent-reach/config.yaml")
            if getattr(args, "sync_legacy_twitter", False):
                from agent_reach.cookie_extract import (
                    _sync_bird_env,
                    _sync_xfetch_session,
                )

                legacy_results = (
                    (
                        "~/.config/xfetch/session.json",
                        _sync_xfetch_session(auth_token, ct0),
                    ),
                    (
                        "~/.config/bird/credentials.env",
                        _sync_bird_env(auth_token, ct0),
                    ),
                )
                for path, success in legacy_results:
                    outcome = "written" if success else "failed"
                    print(f"  {outcome}: {path}")
                if all(success for _, success in legacy_results):
                    print("  Legacy copies written successfully.")

            print(
                "  凭据未实时验证：不会执行 `twitter status`，因为上游在"
                "验证失败时会自动读取浏览器 Cookie。"
            )
            if not shutil.which("twitter"):
                print(
                    "  [!] twitter-cli 未安装。运行：pipx install twitter-cli"
                )
            else:
                print(
                    "  注意：独立 `twitter` 命令不会读取 Agent Reach 配置；"
                    "直接使用时需显式设置 TWITTER_AUTH_TOKEN/TWITTER_CT0。"
                )
        else:
            print("[X] Could not find auth_token and ct0 in your input.")
            print("   Run `agent-reach configure twitter-cookies` and paste either:")
            print("   1. AUTH_TOKEN and CT0 separated by whitespace")
            print("   2. A Cookie-Editor Header String")
            print("   For automation, pass the same value through --stdin.")
            raise SystemExit(1)

    elif args.key == "youtube-cookies":
        config.set("youtube_cookies_from", value)
        print(f"✅ YouTube cookie source configured: {value}")
        print("   yt-dlp will use cookies from this browser for age-restricted/member videos.")

    elif args.key == "xhs-cookies":
        if not _configure_xhs_cookies(value):
            raise SystemExit(1)

    elif args.key == "github-token":
        config.set("github_token", value)
        print("✅ GitHub token configured!")

    elif args.key == "groq-key":
        config.set("groq_api_key", value)
        print("✅ Groq key configured!")

    elif args.key == "openai-key":
        config.set("openai_api_key", value)
        print("✅ OpenAI key configured!")


def _cmd_transcribe(args):
    """Transcribe a URL or local audio file via an explicitly selected provider."""
    from pathlib import Path

    from agent_reach.transcribe import TranscribeError, transcribe
    from agent_reach.utils.text import scrub_url_credentials

    try:
        text = transcribe(
            args.source,
            provider=args.provider,
            allow_provider_fallback=getattr(
                args,
                "allow_provider_fallback",
                False,
            ),
        )
    except TranscribeError as e:
        print(f"❌ {scrub_url_credentials(e)}")
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"✅ Transcript written to {args.output}")
    else:
        print(text)


def _parse_twitter_cookie_input(value: str):
    """Parse Twitter cookie input from either separate values or a cookie header."""
    auth_token = None
    ct0 = None

    if "auth_token=" in value and "ct0=" in value:
        # Full cookie string — parse it.
        for part in value.replace(";", " ").split():
            if part.startswith("auth_token="):
                auth_token = part.split("=", 1)[1]
            elif part.startswith("ct0="):
                ct0 = part.split("=", 1)[1]
    elif len(value.split()) == 2 and "=" not in value:
        # Two separate values: AUTH_TOKEN CT0.
        parts = value.split()
        auth_token = parts[0]
        ct0 = parts[1]

    return auth_token, ct0


def _configure_xhs_cookies(value) -> bool:
    """Import cookies into xiaohongshu-mcp Docker container.

    Accepts two formats:
    1. Cookie-Editor JSON export (array of cookie objects)
    2. Header String: "name1=value1; name2=value2; ..."

    The xiaohongshu-mcp container stores cookies at $COOKIES_PATH
    (default: /app/data/cookies.json or cookies.json in workdir).
    Format: JSON array of {name, value, domain, path, expires, httpOnly, secure, sameSite}.
    """
    import json
    import os
    import shutil
    import subprocess

    value = value.strip()
    if not value:
        print("[X] Missing cookie value.")
        print("   Run `agent-reach configure xhs-cookies` and paste the Cookie-Editor export.")
        print("   For automation, pass the same value through --stdin.")
        return False

    # Detect format and parse
    cookies_json = None

    # Try JSON format first (Cookie-Editor JSON export)
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list) and parsed:
                from agent_reach.utils.url import domain_matches

                valid_cookies = []
                ignored_domains = 0
                ignored_invalid = 0
                for cookie in parsed:
                    if (
                        not isinstance(cookie, dict)
                        or not isinstance(cookie.get("name"), str)
                        or not cookie["name"]
                        or not isinstance(cookie.get("value"), str)
                    ):
                        ignored_invalid += 1
                        continue
                    if not domain_matches(
                        cookie.get("domain", ""),
                        "xiaohongshu.com",
                    ):
                        ignored_domains += 1
                        continue
                    valid_cookies.append(cookie)

                if ignored_domains:
                    print(
                        f"  [!] 已忽略 {ignored_domains} 个非 "
                        "xiaohongshu.com 域 Cookie"
                    )
                if ignored_invalid:
                    print(
                        f"  [!] 已忽略 {ignored_invalid} 个格式无效的 Cookie"
                    )
                if not valid_cookies:
                    print(
                        "[X] Cookie-Editor JSON 中没有有效的 "
                        "xiaohongshu.com 域 Cookie"
                    )
                    return False
                cookies_json = json.dumps(valid_cookies)
                print(
                    f"  Parsed {len(valid_cookies)} "
                    "xiaohongshu.com cookies from JSON format"
                )
            else:
                print("[X] Empty or invalid JSON array")
                return False
        except json.JSONDecodeError as e:
            print(f"[X] Invalid JSON: {e}")
            return False

    # Header String format: "key1=val1; key2=val2; ..."
    if cookies_json is None and "=" in value:
        cookies = []
        for part in value.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, val = part.split("=", 1)
            name = name.strip()
            val = val.strip()
            if name:
                cookies.append({
                    "name": name,
                    "value": val,
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                    "expires": -1,
                    "size": len(name) + len(val),
                    "httpOnly": False,
                    "secure": False,
                    "session": True,
                    "sameSite": "Lax",
                })
        if cookies:
            cookies_json = json.dumps(cookies)
            print(f"  Parsed {len(cookies)} cookies from Header String format")
        else:
            print("[X] Could not parse any cookies from input")
            return False

    if not cookies_json:
        print("[X] Could not parse cookies. Accepted formats:")
        print('   1. JSON array: \'[{"name":"x","value":"y","domain":".xiaohongshu.com",...}]\'')
        print('   2. Header String: "key1=val1; key2=val2; ..."')
        return False

    # Find the container
    docker = shutil.which("docker")
    if not docker:
        # No Docker - write to a local file for manual import.
        from agent_reach.utils.paths import (
            PrivatePathError,
            atomic_write_private_text,
            home_dir,
        )

        cookie_path = home_dir() / ".agent-reach" / "xhs-cookies.json"
        try:
            atomic_write_private_text(cookie_path, cookies_json)
        except (OSError, PrivatePathError) as exc:
            print(f"[X] Could not save cookies safely: {exc}")
            return False
        print(f"  Cookies saved to {cookie_path}")
        print("  Docker not found. Copy manually:")
        print(f"  docker cp {cookie_path} xiaohongshu-mcp:/app/data/cookies.json")
        return True

    # Check if xiaohongshu-mcp container is running
    try:
        result = subprocess.run(
            [docker, "ps", "--filter", "name=xiaohongshu-mcp", "--format", "{{.Names}}"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        container_name = result.stdout.strip()
        if not container_name:
            print("[X] xiaohongshu-mcp container is not running.")
            print("   Start it first:")
            print("   docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp")
            return False
    except Exception as e:
        print(f"[X] Could not check Docker: {e}")
        return False

    # Find the cookies path inside the container
    try:
        result = subprocess.run(
            [docker, "exec", container_name, "printenv", "COOKIES_PATH"],
            capture_output=True, encoding="utf-8", timeout=5,
        )
        cookie_path_in_container = result.stdout.strip()
        if not cookie_path_in_container:
            cookie_path_in_container = "/app/cookies.json"  # fallback: absolute path in workdir
    except Exception:
        cookie_path_in_container = "/app/cookies.json"

    # Write cookies into the container
    tmp_path = None
    try:
        # Write to temp file then docker cp
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(cookies_json)
            tmp_path = f.name

        result = subprocess.run(
            [docker, "cp", tmp_path, f"{container_name}:{cookie_path_in_container}"],
            capture_output=True, encoding="utf-8", timeout=10,
        )

        if result.returncode != 0:
            print(f"[X] Failed to copy cookies: {result.stderr}")
            return False

        print(f"✅ Cookies written to {container_name}:{cookie_path_in_container}")
        # Restart container so it reloads cookies from disk
        print("  Restarting container to reload cookies...", end=" ", flush=True)
        try:
            restart = subprocess.run(
                [docker, "restart", container_name],
                capture_output=True, encoding="utf-8", timeout=30,
            )
            if restart.returncode != 0:
                detail = (
                    (restart.stderr or "").strip()[:200]
                    or f"exit {restart.returncode}"
                )
                print(f"\n  [!] Could not restart container: {detail}")
                print(f"  Restart manually: docker restart {container_name}")
                return False
            print("done")
        except Exception as e:
            print(f"\n  [!] Could not restart container: {e}")
            print(f"  Restart manually: docker restart {container_name}")
            return False
    except Exception as e:
        print(f"[X] Failed to write cookies: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"  [!] Could not remove temporary cookie file: {e}")

    # Verify login status via mcporter
    mcporter = shutil.which("mcporter")
    if mcporter:
        print("  Verifying login status...", end=" ")
        try:
            result = subprocess.run(
                [mcporter, "call", "xiaohongshu.check_login_status()"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            )
            if "已登录" in result.stdout or "logged" in result.stdout.lower():
                print("✅ Login verified!")
            else:
                print("[!] Login check returned unexpected result:")
                print(f"  {result.stdout.strip()[:200]}")
                print("  Cookies were written but login might not be valid. Try fresh cookies.")
        except Exception as e:
            print(f"[!] Could not verify: {e}")
    else:
        print("  (mcporter not found, skipping verification)")
    return True


def _cmd_uninstall(args):
    """Remove all Agent Reach config, tokens, and skill files."""
    import shutil
    import subprocess

    from agent_reach.utils.paths import home_dir

    dry_run = args.dry_run
    keep_config = args.keep_config

    print()
    print("Agent Reach Uninstaller")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be removed (no changes)")
        print()

    removed_any = False
    mcporter_cleanup_skipped = False

    # ── 1. Config directory (~/.agent-reach/) ──
    config_dir = home_dir() / ".agent-reach"
    if not keep_config:
        if os.path.isdir(config_dir):
            if dry_run:
                print(f"[dry-run] Would remove config directory: {config_dir}")
                print("          (contains config.yaml with all tokens/cookies/API keys)")
            else:
                try:
                    shutil.rmtree(config_dir)
                    print(f"  Removed config directory: {config_dir}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {config_dir}: {e}")
        else:
            print(f"  Config directory not found (already clean): {config_dir}")
    else:
        print(f"  Skipping config directory (--keep-config): {config_dir}")

    # Opt-in legacy copies may be shared with upstream tools. Without a
    # provenance marker it would be unsafe to delete them automatically, so
    # surface every exact path that may still contain Twitter credentials.
    legacy_credential_paths = (
        home_dir() / ".config" / "xfetch" / "session.json",
        home_dir() / ".config" / "bird" / "credentials.env",
    )
    present_legacy_paths = [
        path for path in legacy_credential_paths if os.path.lexists(path)
    ]
    if present_legacy_paths:
        print("  [!] 检测到可选的 Twitter legacy 凭据副本；不会自动删除：")
        for path in present_legacy_paths:
            print(f"      {path}")
        print("      若确认不再被 xfetch/bird 使用，请手动删除。")

    # ── 2. Skill files ──
    hermes_home, _ = _resolve_hermes_home()
    hermes_skill = os.path.join(hermes_home, "skills", "agent-reach")
    skill_dirs = [
        (hermes_skill, "Hermes"),
        ("~/.config/opencode/skills/agent-reach", "OpenCode"),
        ("~/.openclaw/skills/agent-reach", "OpenClaw"),
        ("~/.claude/skills/agent-reach", "Claude Code"),
        ("~/.agents/skills/agent-reach", "Agent"),
    ]

    for skill_path_template, platform_name in skill_dirs:
        skill_path = os.path.expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            if dry_run:
                print(f"[dry-run] Would remove {platform_name} skill: {skill_path}")
            else:
                try:
                    if os.path.islink(skill_path):
                        os.unlink(skill_path)
                    else:
                        shutil.rmtree(skill_path)
                    print(f"  Removed {platform_name} skill: {skill_path}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {skill_path}: {e}")

    # ── 3. mcporter MCP entries ──
    if shutil.which("mcporter"):
        from agent_reach.channels.mcporter import (
            McporterConfigError,
            configured_server_names,
        )

        try:
            result = subprocess.run(
                [
                    "mcporter",
                    "config",
                    "list",
                    "--json",
                ],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode != 0:
                raise McporterConfigError("mcporter config query failed")
            server_names = configured_server_names(result.stdout)
        except (
            McporterConfigError,
            OSError,
            subprocess.TimeoutExpired,
        ):
            mcporter_cleanup_skipped = True
            print(
                "  [!] 无法安全核验 mcporter 配置来源；"
                "不会自动删除 exa/xiaohongshu 项。"
            )
        else:
            for mcp_name in ("exa", "xiaohongshu"):
                if mcp_name not in server_names:
                    continue
                mcporter_cleanup_skipped = True
                print(
                    f"  [!] mcporter entry {mcp_name} 来源无法证明由 "
                    "Agent Reach 管理；已保留。若确认不再需要，请手动移除。"
                )

    # ── 4. Summary and optional steps ──
    print()
    if dry_run:
        print("Dry run complete. No changes were made.")
        print("Run without --dry-run to actually remove the above.")
    else:
        if removed_any:
            print("Agent Reach data removed.")
        elif mcporter_cleanup_skipped:
            print("No proven Agent Reach-managed mcporter data was removed.")
        else:
            print("Nothing to remove — already clean.")

    print()
    print("Optional: remove the Agent Reach Python package itself:")
    print("  pip uninstall agent-reach")
    print()
    print("Optional: remove tools installed by Agent Reach:")
    print("  npm uninstall -g mcporter")
    print("  pipx uninstall twitter-cli")
    print("  npm uninstall -g undici")


def _cmd_doctor(args=None):
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report
    config = Config(read_only=True)
    results = check_all(config)

    if args is not None and getattr(args, "json", False):
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    report = format_report(results)
    try:
        from rich import print as rich_print
    except ImportError:
        print(report)
    else:
        rich_print(report)


def _cmd_setup():
    import getpass

    from agent_reach.config import Config

    config = Config()
    print()
    print("Agent Reach Setup")
    print("=" * 40)
    print()

    # Step 1: Exa (via mcporter, no API key required)
    import shutil
    import subprocess

    print("【推荐】全网搜索 — Exa（通过 mcporter）")
    print("  免费，无需 API Key")

    if not shutil.which("mcporter"):
        print("  当前状态: -- mcporter 未安装")
        print("  安装：npm install -g mcporter")
        print("  然后：mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        print()
    else:
        try:
            from agent_reach.channels.mcporter import (
                McporterConfigError,
                configured_server_names,
            )

            r = subprocess.run(
                ["mcporter", "config", "list", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if r.returncode != 0:
                raise McporterConfigError("mcporter 配置查询失败")
            if "exa" in configured_server_names(r.stdout):
                print("  当前状态: ✅ 已配置")
            else:
                print("  当前状态: -- 未配置")
                setup_now = input("  现在自动配置 Exa 吗？[Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_r = subprocess.run(
                        [
                            "mcporter",
                            "config",
                            "add",
                            "exa",
                            "https://mcp.exa.ai/mcp",
                            "--scope",
                            "home",
                        ],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                    )
                    if add_r.returncode == 0:
                        print("  ✅ Exa 已配置")
                    else:
                        print("  [!] 自动配置失败，请手动执行：")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        except Exception:
            print("  [!] 无法检查 Exa 配置，请手动执行：")
            print("     mcporter config add exa https://mcp.exa.ai/mcp --scope home")
        print()

    # Step 2: GitHub token
    print("【可选】GitHub Token — 提高 API 限额")
    print("  无 token: 60 次/小时 | 有 token: 5000 次/小时")
    print("  获取: https://github.com/settings/tokens (无需任何权限)")
    current = config.get("github_token")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        key = getpass.getpass("  GITHUB_TOKEN (回车跳过): ").strip()
        if key:
            config.set("github_token", key)
            print("  ✅ GitHub API 已提升至 5000 次/小时！")
        else:
            print("  跳过。公开 API 也能用")
    print()

    # Step 3: Reddit — rdt-cli
    print("【信息】Reddit — 必须登录态（无零配置路径）。桌面推荐 OpenCLI；或 rdt-cli：")
    print(f"  安装：pipx install '{_RDT_GIT_SOURCE}'")
    print("  然后运行：rdt login（需先在浏览器登录 reddit.com）")
    print()

    # Step 4: Groq (Whisper)
    print("【可选】Groq API — 视频无字幕时的语音转文字")
    print("  免费额度，注册: https://console.groq.com")
    current = config.get("groq_api_key")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        key = getpass.getpass("  GROQ_API_KEY (回车跳过): ").strip()
        if key:
            config.set("groq_api_key", key)
            print("  ✅ 语音转文字已开启！")
        else:
            print("  跳过")
    print()

    # Summary
    print("=" * 40)
    print(f"✅ 配置已保存到 {config.config_path}")
    print("运行 agent-reach doctor 查看完整状态")
    print()


def _classify_update_error(exc):
    """Classify update-check errors for user-friendly diagnostics."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        msg = str(exc).lower()
        dns_markers = [
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname",
            "getaddrinfo failed",
            "name resolution",
            "dns",
        ]
        if any(marker in msg for marker in dns_markers):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"


def _update_error_text(kind):
    """Map internal error kinds to user-facing text."""
    mapping = {
        "timeout": "网络超时",
        "dns": "DNS 解析失败",
        "rate_limit": "GitHub API 速率限制",
        "connection": "网络连接失败",
        "server_error": "GitHub 服务暂时不可用",
        "http": "HTTP 请求失败",
        "unknown": "未知网络错误",
    }
    return mapping.get(kind, "请求失败")


def _classify_github_response_error(resp):
    """Classify non-200 GitHub responses that merit special handling."""
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
            if "rate limit" in message:
                return "rate_limit"
        except Exception:
            pass
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None


def _github_get_with_retry(url, timeout=10, retries=3, sleeper=time.sleep):
    """GET GitHub API with retry/backoff and basic error classification."""
    import requests

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, _classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err_kind = _classify_github_response_error(resp)
        if err_kind in ("rate_limit", "server_error"):
            if attempt >= retries:
                return None, err_kind, attempt
            delay = 2 ** (attempt - 1)
            retry_after = resp.headers.get("Retry-After")
            if err_kind == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return resp, None, attempt

    return None, "unknown", retries


#: Full update = package + upstream tools + skill. The one-liner walks an
#: agent through all three (docs/update.md); bare pip only updates the package.
_UPDATE_INSTRUCTIONS = (
    "更新方式（推荐，复制这句话给你的 AI Agent，会完整更新本体+上游工具+skill）：\n"
    "  帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md\n"
    "仅更新本体（不含上游工具和 skill）：\n"
    "  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip"
)


def _is_newer_version(remote: str, local: str) -> bool:
    """True if remote is strictly newer than local (semantic compare).

    A plain != would tell users "update available" when their local build is
    AHEAD of the latest release (e.g. installed from main during a release
    window) — and walk them into a downgrade.
    """
    def parse(v):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except ValueError:
            return None

    remote_version, local_version = parse(remote), parse(local)
    if remote_version is None or local_version is None:
        return remote != local  # unparseable — fall back to old behavior
    return remote_version > local_version


def _cmd_check_update():
    """Check for newer versions on GitHub."""
    from agent_reach import __version__

    print(f"当前版本: v{__version__}")
    release_url = "https://api.github.com/repos/Panniantong/Agent-Reach/releases/latest"
    commit_url = "https://api.github.com/repos/Panniantong/Agent-Reach/commits/main"

    # Fetch latest release with retry/backoff.
    resp, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"[!] 无法检查更新（{_update_error_text(err)}，已重试 {attempts} 次）")
        return "error"

    if resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

        if latest and _is_newer_version(latest, __version__):
            print(f"最新版本: v{latest} ← 有更新！")
            if body:
                print()
                print("更新内容：")
                # Show first 20 lines of release notes
                for line in body.strip().split("\n")[:20]:
                    print(f"  {line}")
            print()
            print(_UPDATE_INSTRUCTIONS)
            return "update_available"
        print("✅ 已是最新版本")
        return "up_to_date"

    release_err = _classify_github_response_error(resp)
    if release_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    # No releases yet, fall back to latest main commit.
    resp2, err2, attempts2 = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err2:
        print(f"[!] 无法检查更新（{_update_error_text(err2)}，已重试 {attempts + attempts2} 次）")
        return "error"
    if resp2.status_code == 200:
        commit = resp2.json()
        sha = commit.get("sha", "")[:7]
        msg = commit.get("commit", {}).get("message", "").split("\n")[0]
        date = commit.get("commit", {}).get("committer", {}).get("date", "")[:10]
        print(f"最新提交: {sha} ({date}) {msg}")
        print()
        print(_UPDATE_INSTRUCTIONS)
        return "unknown"

    commit_err = _classify_github_response_error(resp2)
    if commit_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    print(f"[!] 无法检查更新（GitHub 返回 {resp2.status_code}）")
    return "error"


def _cmd_watch():
    """Quick health check + update check, designed for scheduled tasks.

    Only outputs problems. If everything is fine, outputs a single line.
    """
    from agent_reach import __version__
    from agent_reach.config import Config
    from agent_reach.doctor import check_all

    config = Config(read_only=True)
    issues = []

    # Check channels
    results = check_all(config)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Find broken channels (were working, now broken)
    for key, r in results.items():
        if r["status"] in ("off", "error"):
            issues.append(f"[X] {r['name']}：{r['message']}")
        elif r["status"] == "warn":
            issues.append(f"[!] {r['name']}：{r['message']}")

    # Check for updates
    update_available = False
    new_version = ""
    release_body = ""
    resp, err, _attempts = _github_get_with_retry(
        "https://api.github.com/repos/Panniantong/Agent-Reach/releases/latest",
        timeout=10,
        retries=2,
    )
    if not err and resp and resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        if latest and _is_newer_version(latest, __version__):
            update_available = True
            new_version = latest
            release_body = data.get("body", "")

    # Output
    if not issues and not update_available:
        print(f"Agent Reach: 全部正常 ({ok}/{total} 渠道可用，v{__version__} 已是最新)")
        return

    print("Agent Reach 监控报告")
    print("=" * 40)
    print(f"版本: v{__version__}  |  渠道: {ok}/{total}")

    if issues:
        print()
        for issue in issues:
            print(f"  {issue}")

    if update_available:
        print()
        print(f"新版本可用: v{new_version}")
        if release_body:
            for line in release_body.strip().split("\n")[:10]:
                print(f"    {line}")
        print("  更新（一句话发给 Agent 即可完整更新）：")
        print("    帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md")


if __name__ == "__main__":
    main()
