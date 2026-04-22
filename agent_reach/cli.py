# -*- coding: utf-8 -*-
"""
Agent Reach CLI — installer, doctor, and configuration tool.

Usage:
    agent-reach install --env=auto
    agent-reach doctor
    agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy"
    agent-reach setup
"""

import sys
import argparse
import json
import os
import time

from agent_reach import __version__


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
                           help="Residential proxy for Reddit/Bilibili (http://user:pass@ip:port)")
    p_install.add_argument("--safe", action="store_true",
                           help="Safe mode: skip automatic system changes, show what's needed instead")
    p_install.add_argument("--dry-run", action="store_true",
                           help="Show what would be done without making any changes")
    p_install.add_argument("--channels", default="",
                           help="Comma-separated optional channels to install "
                                "(twitter,weibo,wechat,xiaoyuzhou,xueqiu,xiaohongshu,"
                                "reddit,bilibili,douyin,linkedin,all)")

    # ── configure ──
    p_conf = sub.add_parser("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument("key", nargs="?", default=None,
                        choices=["proxy", "github-token", "groq-key",
                                 "twitter-cookies", "youtube-cookies",
                                 "xhs-cookies"],
                        help="What to configure (omit if using --from-browser)")
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument("--from-browser", metavar="BROWSER",
                        choices=["chrome", "firefox", "edge", "brave", "opera"],
                        help="Auto-extract ALL platform cookies from browser (chrome/firefox/edge/brave/opera)")

    # ── doctor ──
    sub.add_parser("doctor", help="Check platform availability")

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
    sub.add_parser("check-update", help="Check for new versions and changes")

    # ── watch ──
    sub.add_parser("watch", help="Quick health check + update check (for scheduled tasks)")

    # ── version ──
    sub.add_parser("version", help="Show version")

    args = parser.parse_args()

    # Suppress loguru noise unless --verbose
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"Agent Reach v{__version__}")
        sys.exit(0)

    if args.command == "doctor":
        _cmd_doctor()
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


# ── Command handlers ────────────────────────────────


def _cmd_install(args):
    """One-shot deterministic installer."""
    import os
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report

    safe_mode = args.safe
    dry_run = args.dry_run

    config = Config()
    print()
    print("Agent Reach Installer")
    print("=" * 40)

    # Ensure tools directory exists (for upstream tool repos)
    tools_dir = os.path.expanduser("~/.agent-reach/tools")
    os.makedirs(tools_dir, exist_ok=True)

    if dry_run:
        print("DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("SAFE MODE — skipping automatic system changes")
        print()

    # ── Parse --channels ──
    CHANNEL_INSTALLERS = {
        "twitter":     _install_twitter_deps,
        "weibo":       _install_weibo_deps,
        "wechat":      _install_wechat_deps,
        "xiaoyuzhou":  _install_xiaoyuzhou_deps,
        "xiaohongshu": _install_xhs_deps,
        "reddit":      _install_reddit_deps,
        "bilibili":    _install_bili_deps,
        # xueqiu: cookie-only, no install step
        # douyin/linkedin: manual setup, no auto-install
    }
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili"}

    requested_channels = set()
    if args.channels:
        raw = [c.strip().lower() for c in args.channels.split(",") if c.strip()]
        if "all" in raw:
            requested_channels = set(CHANNEL_INSTALLERS.keys()) | {"xueqiu", "douyin", "linkedin"}
        else:
            requested_channels = set(raw)

    # Auto-detect environment
    env = args.env
    if env == "auto":
        env = _detect_environment()

    if env == "server":
        print(f"Environment: Server/VPS (auto-detected)")
    else:
        print(f"Environment: Local computer (auto-detected)")

    # Apply explicit flags
    if args.proxy:
        if dry_run:
            print(f"[dry-run] Would configure proxy for Bilibili")
        else:
            config.set("bilibili_proxy", args.proxy)
            print(f"✅ Proxy configured for Bilibili")

    # ── Install core system dependencies (lightweight, always) ──
    print()
    if dry_run:
        _install_system_deps_dryrun()
    elif safe_mode:
        _install_system_deps_safe()
    else:
        _install_system_deps()

    # ── mcporter (for Exa search) ──
    print()
    if dry_run:
        print("[dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        _install_mcporter_safe()
    else:
        _install_mcporter()

    # ── Install optional channels (only if --channels specified) ──
    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        for ch_name in sorted(requested_channels):
            installer = CHANNEL_INSTALLERS.get(ch_name)
            if installer:
                installer()

    if requested_channels and dry_run:
        print()
        print(f"[dry-run] Would install optional channels: {', '.join(sorted(requested_channels))}")

    # ── Auto-import cookies (only if cookie-needing channels are requested) ──
    needs_cookies = bool(requested_channels & COOKIE_CHANNELS)
    if env == "local" and needs_cookies and not safe_mode and not dry_run:
        print()
        print("Importing cookies from browser...")
        print("  (macOS may ask for your login password to access the Keychain — this is normal,")
        print("   it only happens once during install. Enter your password or click 'Allow'.)")
        try:
            from agent_reach.cookie_extract import configure_from_browser
            results = configure_from_browser("chrome", config)
            found = False
            for platform, success, message in results:
                if success:
                    print(f"  ✅ {platform}: {message}")
                    found = True
            if not found:
                results = configure_from_browser("firefox", config)
                for platform, success, message in results:
                    if success:
                        print(f"  ✅ {platform}: {message}")
                        found = True
            if not found:
                print("  -- No cookies found (normal if you haven't logged into these sites)")
        except Exception:
            print("  -- Could not read browser cookies (browser might be open or password was denied)")
    elif env == "local" and needs_cookies and dry_run:
        print()
        print("[dry-run] Would try to import cookies from Chrome/Firefox")

    # Environment-specific advice
    if env == "server":
        print()
        print("Tip: Bilibili may block server IPs.")
        print("   Reddit: rdt-cli works without proxy (pipx install rdt-cli).")
        print("   For Bilibili full access: agent-reach configure proxy http://user:pass@ip:port")
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

        # ── Install agent skill ──
        _install_skill()

        print(f"✅ Installation complete! {ok}/{total} channels active.")

        if not requested_channels:
            # First install — hint about optional channels
            print()
            print("More channels available! Use --channels to install:")
            print("   agent-reach install --channels=twitter,weibo,xiaohongshu,...")
            print("   agent-reach install --channels=all  (install everything)")

        # Star reminder
        print()
        print("如果 Agent Reach 帮到了你，给个 Star 让更多人发现它吧：")
        print("   https://github.com/Panniantong/Agent-Reach")
        print("   只需一秒，对独立开发者意义很大。谢谢！")
    else:
        print()
        print("Dry run complete. No changes were made.")


def _install_skill():
    """Install Agent Reach as an agent skill (OpenClaw / Claude Code / .agents)."""
    import os
    import shutil
    import importlib.resources

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

    def _copy_skill_dir(target: str) -> bool:
        """Copy entire skill directory (locale-specific SKILL.md + references/)."""
        try:
            # Clear existing installation
            if os.path.exists(target):
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

            return True
        except Exception as e:
            print(f"  Warning: Could not install skill: {e}")
            return False

    # Determine skill install path (priority: .agents > openclaw > claude)
    skill_dirs = [
        os.path.expanduser("~/.agents/skills"),      # Generic agents (priority)
        os.path.expanduser("~/.openclaw/skills"),    # OpenClaw
        os.path.expanduser("~/.claude/skills"),      # Claude Code (if exists)
    ]

    # Insert OPENCLAW_HOME path at the beginning if environment variable is set
    openclaw_home = os.environ.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(0, os.path.join(openclaw_home, ".openclaw", "skills"))

    installed = False
    for skill_dir in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "agent-reach")
            if _copy_skill_dir(target):
                platform_name = "Agent" if ".agents" in skill_dir else "OpenClaw" if "openclaw" in skill_dir else "Claude Code"
                print(f"Skill installed for {platform_name}: {target}")
                installed = True

    if not installed:
        # No known skill directory found — create for .agents by default
        target = os.path.expanduser("~/.agents/skills/agent-reach")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if _copy_skill_dir(target):
            print(f"Skill installed: {target}")
        else:
            print("  -- Could not install agent skill (optional)")
            print("  -- Tip: install OpenClaw, Claude Code, or create ~/.agents/skills/ manually")


def _uninstall_skill():
    """Remove SKILL.md from all known agent skill directories."""
    import shutil

    skill_dirs = [
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
        _install_skill()
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
    """Install system-level dependencies: gh CLI, Node.js (for mcporter)."""
    import shutil
    import subprocess
    import platform
    import tempfile

    print("Checking system dependencies...")

    # ── gh CLI ──
    if shutil.which("gh"):
        print("  ✅ gh CLI already installed")
    else:
        print("  Installing gh CLI...")
        os_type = platform.system().lower()
        if os_type == "linux":
            try:
                # Official GitHub apt source setup without invoking a shell.
                keyring_path = "/usr/share/keyrings/githubcli-archive-keyring.gpg"
                list_path = "/etc/apt/sources.list.d/github-cli.list"
                arch = subprocess.run(
                    ["dpkg", "--print-architecture"],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                ).stdout.strip() or "amd64"
                subprocess.run(
                    ["curl", "-fsSL", "https://cli.github.com/packages/githubcli-archive-keyring.gpg", "-o", keyring_path],
                    capture_output=True, timeout=60,
                )
                repo_line = (
                    f"deb [arch={arch} signed-by={keyring_path}] "
                    "https://cli.github.com/packages stable main\n"
                )
                with open(list_path, "w", encoding="utf-8") as f:
                    f.write(repo_line)
                subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=60)
                subprocess.run(["apt-get", "install", "-y", "-qq", "gh"], capture_output=True, timeout=60)
                if shutil.which("gh"):
                    print("  ✅ gh CLI installed")
                else:
                    print("  [!]  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
            except Exception:
                print("  [!]  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
        elif os_type == "darwin":
            if shutil.which("brew"):
                try:
                    subprocess.run(["brew", "install", "gh"], capture_output=True, timeout=120)
                    if shutil.which("gh"):
                        print("  ✅ gh CLI installed")
                    else:
                        print("  [!]  gh CLI install failed. Try: brew install gh")
                except Exception:
                    print("  [!]  gh CLI install failed. Try: brew install gh")
            else:
                print("  [!]  gh CLI not found. Install: https://cli.github.com")
        else:
            print("  [!]  gh CLI not found. Install: https://cli.github.com")

    # ── Node.js (needed for mcporter) ──
    if shutil.which("node") and shutil.which("npm"):
        print("  ✅ Node.js already installed")
    else:
        print("  Installing Node.js...")
        try:
            # Use NodeSource setup script without invoking a shell pipeline.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".sh") as tf:
                script_path = tf.name
            subprocess.run(
                ["curl", "-fsSL", "https://deb.nodesource.com/setup_22.x", "-o", script_path],
                capture_output=True, timeout=60,
            )
            subprocess.run(
                ["bash", script_path],
                capture_output=True, timeout=120,
            )
            try:
                os.unlink(script_path)
            except Exception:
                pass
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "nodejs"],
                capture_output=True, timeout=120,
            )
            if shutil.which("node"):
                print("  ✅ Node.js installed")
            else:
                print("  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")
        except Exception:
            print("  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")

    # ── undici (proxy support for Node.js fetch) ──
    npm_cmd = shutil.which("npm")
    if npm_cmd:
        npm_root = subprocess.run([npm_cmd, "root", "-g"], capture_output=True, encoding="utf-8", errors="replace", timeout=5).stdout.strip()
        undici_path = os.path.join(npm_root, "undici", "index.js") if npm_root else ""
        if os.path.exists(undici_path):
            print("  ✅ undici already installed (Node.js proxy support)")
        else:
            try:
                subprocess.run([npm_cmd, "install", "-g", "undici"], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
                print("  ✅ undici installed (Node.js proxy support)")
            except Exception:
                print("  -- undici install failed (optional — may not work behind proxies)")

    # ── yt-dlp JS runtime config (YouTube requires external JS runtime) ──
    if shutil.which("node"):
        ytdlp_config_dir = os.path.expanduser("~/.config/yt-dlp")
        ytdlp_config = os.path.join(ytdlp_config_dir, "config")
        needs_config = True
        if os.path.exists(ytdlp_config):
            with open(ytdlp_config, "r") as f:
                if "--js-runtimes" in f.read():
                    needs_config = False
                    print("  ✅ yt-dlp JS runtime already configured")
        if needs_config:
            try:
                os.makedirs(ytdlp_config_dir, exist_ok=True)
                with open(ytdlp_config, "a") as f:
                    f.write("--js-runtimes node\n")
                print("  ✅ yt-dlp configured to use Node.js as JS runtime (YouTube)")
            except Exception:
                print("  -- Could not configure yt-dlp JS runtime (YouTube may not work)")

    # NOTE: twitter-cli, weibo, xiaoyuzhou, wechat, xhs-cli etc. are optional.
    # They are installed via --channels flag, not here.
    # See CHANNEL_INSTALLERS in _cmd_install().


def _install_xiaoyuzhou_deps():
    """Install Xiaoyuzhou podcast transcription script."""
    import shutil
    from agent_reach.config import Config

    config = Config()
    print("Setting up Xiaoyuzhou podcast transcription...")

    tools_dir = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou")
    script_dst = os.path.join(tools_dir, "transcribe.sh")

    if os.path.isfile(script_dst):
        print("  ✅ Xiaoyuzhou transcription script already installed")
    else:
        # Copy script from package
        script_src = os.path.join(os.path.dirname(__file__), "scripts", "transcribe_xiaoyuzhou.sh")
        if os.path.isfile(script_src):
            try:
                os.makedirs(tools_dir, exist_ok=True)
                import shutil as _shutil
                _shutil.copy2(script_src, script_dst)
                os.chmod(script_dst, 0o755)
                print("  ✅ Xiaoyuzhou transcription script installed")
            except Exception as e:
                print(f"  [!]  Failed to install script: {e}")
        else:
            print("  [!]  Script source not found in package")

    # Check ffmpeg
    if shutil.which("ffmpeg"):
        print("  ✅ ffmpeg available")
    else:
        print("  -- ffmpeg not found. Install: apt install -y ffmpeg (or brew install ffmpeg)")

    # Check GROQ_API_KEY
    has_key = bool(os.environ.get("GROQ_API_KEY")) or bool(config.get("groq_api_key"))
    if has_key:
        print("  ✅ Groq API key configured")
    else:
        print("  -- Groq API key not set. Get free key at https://console.groq.com")
        print("     Then run: agent-reach configure groq-key gsk_xxxxx")


def _install_twitter_deps():
    """Install twitter-cli for Twitter search + timeline."""
    import shutil
    import subprocess

    print("Setting up Twitter (twitter-cli)...")
    if shutil.which("twitter"):
        print("  ✅ twitter-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "twitter-cli"]),
                      ("uv", ["uv", "tool", "install", "twitter-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("twitter"):
                    print("  ✅ twitter-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  twitter-cli install failed. Run: pipx install twitter-cli")


def _install_xhs_deps():
    """Install xhs-cli (xiaohongshu-cli) for XiaoHongShu."""
    import shutil
    import subprocess

    print("Setting up XiaoHongShu (xhs-cli)...")
    if shutil.which("xhs"):
        print("  ✅ xhs-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "xiaohongshu-cli"]),
                      ("uv", ["uv", "tool", "install", "xiaohongshu-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("xhs"):
                    print("  ✅ xhs-cli installed (run `xhs login` to authenticate)")
                    return
            except Exception:
                pass
    print("  [!]  xhs-cli install failed. Run: pipx install xiaohongshu-cli")


def _install_reddit_deps():
    """Install rdt-cli for Reddit search + reading."""
    import shutil
    import subprocess

    print("Setting up Reddit (rdt-cli)...")
    if shutil.which("rdt"):
        print("  ✅ rdt-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "rdt-cli"]),
                      ("uv", ["uv", "tool", "install", "rdt-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("rdt"):
                    print("  ✅ rdt-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  rdt-cli install failed. Run: pipx install rdt-cli")


def _install_bili_deps():
    """Install bili-cli for Bilibili hot/rank/search."""
    import shutil
    import subprocess

    print("Setting up Bilibili (bili-cli)...")
    if shutil.which("bili"):
        print("  ✅ bili-cli already installed")
        return
    for tool, cmd in [("pipx", ["pipx", "install", "bilibili-cli"]),
                      ("uv", ["uv", "tool", "install", "bilibili-cli"])]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("bili"):
                    print("  ✅ bili-cli installed")
                    return
            except Exception:
                pass
    print("  [!]  bili-cli install failed. Run: pipx install bilibili-cli")


def _install_weibo_deps():
    """Install Weibo MCP server (Panniantong fork with visitor passport auth)."""
    import shutil
    import subprocess

    print("Setting up Weibo MCP server...")

    # Check if already installed and working
    mcporter = shutil.which("mcporter")
    if mcporter:
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "weibo" in r.stdout:
                print("  ✅ Weibo MCP already configured")
                return
        except Exception:
            pass

    # Install from our fork (has visitor passport auth fix)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "git+https://github.com/Panniantong/mcp-server-weibo.git"],
            check=True, timeout=120
        )
        print("  ✅ mcp-server-weibo installed (Panniantong fork)")
    except Exception as e:
        print(f"  [!]  mcp-server-weibo install failed: {e}")
        return

    # Register with mcporter
    if mcporter:
        try:
            subprocess.run(
                [mcporter, "config", "add", "weibo", "--command", "mcp-server-weibo"],
                check=True, capture_output=True, timeout=10
            )
            print("  ✅ Weibo MCP registered with mcporter")
        except Exception:
            print("  [!]  mcporter config add failed. Run manually: mcporter config add weibo --command 'mcp-server-weibo'")
    else:
        print("  -- mcporter not found, skipping MCP registration. Install mcporter first, then run: mcporter config add weibo --command 'mcp-server-weibo'")


def _install_wechat_deps():
    """Install WeChat article reading and search dependencies."""
    import subprocess

    print("Setting up WeChat article tools...")

    # Check if already installed
    has_camoufox = False
    has_miku = False
    try:
        import camoufox  # noqa: F401
        has_camoufox = True
    except ImportError:
        pass
    try:
        import miku_ai  # noqa: F401
        has_miku = True
    except ImportError:
        pass

    # Install Python packages
    if has_camoufox and has_miku:
        print("  ✅ WeChat Python packages already installed")
    else:
        pkgs = []
        if not has_camoufox:
            pkgs.extend(["camoufox[geoip]", "markdownify", "beautifulsoup4", "httpx"])
        if not has_miku:
            pkgs.append("miku_ai")
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q"] + pkgs
            subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
            # Verify
            ok = True
            try:
                import importlib
                if not has_camoufox:
                    importlib.import_module("camoufox")
                if not has_miku:
                    importlib.import_module("miku_ai")
            except ImportError:
                ok = False
            if ok:
                print(f"  ✅ WeChat Python packages installed ({', '.join(pkgs)})")
            else:
                print(f"  [!]  Some WeChat packages failed to install. Try: pip install {' '.join(pkgs)}")
        except Exception:
            print(f"  [!]  WeChat packages install failed. Try: pip install {' '.join(pkgs)}")

    # Clone wechat-article-for-ai tool
    tools_dir = os.path.expanduser("~/.agent-reach/tools")
    wechat_dir = os.path.join(tools_dir, "wechat-article-for-ai")
    if os.path.isfile(os.path.join(wechat_dir, "main.py")):
        print("  ✅ wechat-article-for-ai tool already installed")
    else:
        try:
            os.makedirs(tools_dir, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1",
                 "https://github.com/Panniantong/wechat-article-for-ai.git", wechat_dir],
                capture_output=True, encoding="utf-8", errors="replace", timeout=60,
            )
            if os.path.isfile(os.path.join(wechat_dir, "main.py")):
                print("  ✅ wechat-article-for-ai tool installed")
            else:
                print("  [!]  wechat-article-for-ai clone failed. Try: git clone https://github.com/Panniantong/wechat-article-for-ai.git " + wechat_dir)
        except Exception:
            print("  [!]  wechat-article-for-ai clone failed. Try: git clone https://github.com/Panniantong/wechat-article-for-ai.git " + wechat_dir)


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
        found = any(shutil.which(b) for b in binaries)
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
        ("gh CLI", ["gh"], "apt install gh / brew install gh"),
        ("Node.js", ["node"], "curl NodeSource setup | bash + apt install nodejs"),
    ]

    for label, binaries, method in checks:
        found = any(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label}: already installed, skip")
        else:
            print(f"  {label}: would install via: {method}")



def _install_mcporter():
    """Install mcporter and configure Exa search."""
    import shutil
    import subprocess

    print("Setting up mcporter (search backend)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
    else:
        # Check for npm/npx
        if not shutil.which("npm") and not shutil.which("npx"):
            print("  [!]  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/ or: curl -fsSL https://fnm.vercel.app/install | bash")
            return
        try:
            subprocess.run(
                ["npm", "install", "-g", "mcporter"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=120,
            )
            if shutil.which("mcporter"):
                print("  ✅ mcporter installed")
            else:
                print("  [X] mcporter install failed. Retry: npm install -g mcporter (check network/timeout), or try: npx mcporter@latest list")
                return
        except Exception as e:
            print(f"  [X] mcporter install failed: {e}")
            return

    # Configure Exa MCP (free, no key needed)
    try:
        r = subprocess.run(
            ["mcporter", "config", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=5
        )
        if "exa" not in r.stdout:
            subprocess.run(
                ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=10,
            )
            print("  ✅ Exa search configured (free, no API key needed)")
        else:
            print("  ✅ Exa search already configured")
    except Exception:
        print("  [!]  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp")

    # NOTE: xhs-cli is now optional, installed via --channels=xiaohongshu


def _install_mcporter_safe():
    """Safe mode: check mcporter status, print instructions."""
    import shutil

    print("Checking mcporter (safe mode)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp")
    else:
        print("  -- mcporter not installed")
        print("  To install: npm install -g mcporter")
        print("  Then configure Exa: mcporter config add exa https://mcp.exa.ai/mcp")


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


def _cmd_configure(args):
    """Set a config value and test it, or auto-extract from browser."""
    import shutil
    from agent_reach.config import Config

    config = Config()

    # ── Auto-extract from browser ──
    if args.from_browser:
        from agent_reach.cookie_extract import configure_from_browser

        browser = args.from_browser
        print(f"Extracting cookies from {browser}...")
        print()

        results = configure_from_browser(browser, config)

        found_any = False
        for platform, success, message in results:
            if success:
                print(f"  ✅ {platform}: {message}")
                found_any = True
            else:
                print(f"  -- {platform}: {message}")

        print()
        if found_any:
            print("✅ Cookies configured! Run `agent-reach doctor` to see updated status.")
        else:
            print(f"No cookies found. Make sure you're logged into the platforms in {browser}.")
        return

    # ── Manual configure ──
    if not args.key:
        print("Usage: agent-reach configure <key> <value>")
        print("   or: agent-reach configure --from-browser chrome")
        return

    value = " ".join(args.value) if args.value else ""
    if not value:
        print(f"Missing value for {args.key}")
        return

    if args.key == "proxy":
        config.set("bilibili_proxy", value)
        print(f"✅ Proxy configured for Bilibili!")
        print("  Note: Reddit 已改为通过 rdt-cli 访问，无需代理。")

    elif args.key == "twitter-cookies":
        # Accept two formats:
        # 1. auth_token ct0 (two separate values)
        # 2. Full cookie header string: "auth_token=xxx; ct0=yyy; ..."
        auth_token, ct0 = _parse_twitter_cookie_input(value)

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)

            # Sync credentials to twitter-cli env
            print("✅ Twitter cookies configured!")

            print("Testing Twitter access...", end=" ")
            try:
                import subprocess
                twitter_bin = shutil.which("twitter")
                if not twitter_bin:
                    print("[!] twitter-cli not installed. Run: pipx install twitter-cli")
                else:
                    import os
                    env = os.environ.copy()
                    env["TWITTER_AUTH_TOKEN"] = auth_token
                    env["TWITTER_CT0"] = ct0
                    result = subprocess.run(
                        [twitter_bin, "status"],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                        env=env,
                    )
                    output = (result.stdout or "") + (result.stderr or "")
                    if "ok: true" in output:
                        print("✅ Twitter access works!")
                    else:
                        print("[!] Auth check failed (cookies might be wrong)")
            except Exception as e:
                print(f"[X] Failed: {e}")
        else:
            print("[X] Could not find auth_token and ct0 in your input.")
            print("   Accepted formats:")
            print("   1. agent-reach configure twitter-cookies AUTH_TOKEN CT0")
            print('   2. agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy; ..."')

    elif args.key == "youtube-cookies":
        config.set("youtube_cookies_from", value)
        print(f"✅ YouTube cookie source configured: {value}")
        print("   yt-dlp will use cookies from this browser for age-restricted/member videos.")

    elif args.key == "xhs-cookies":
        _configure_xhs_cookies(value)

    elif args.key == "github-token":
        config.set("github_token", value)
        print(f"✅ GitHub token configured!")

    elif args.key == "groq-key":
        cleaned = value.strip()
        if not _looks_like_groq_key(cleaned):
            print("[X] Groq API keys start with 'gsk_'. The value you provided does not.")
            print("   Tip: Groq Console (https://console.groq.com) issues keys prefixed 'gsk_'.")
            print("   If you pasted a key from OpenAI (sk-...) or another vendor, it won't work")
            print("   against Groq's Whisper endpoint used for Xiaoyuzhou transcription.")
            return
        config.set("groq_api_key", cleaned)
        print(f"✅ Groq key configured!")


def _looks_like_groq_key(value: str) -> bool:
    """Best-effort check that ``value`` looks like a Groq console API key."""
    return bool(value) and value.startswith("gsk_")


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


def _configure_xhs_cookies(value):
    """Import cookies into xiaohongshu-mcp Docker container.

    Accepts two formats:
    1. Cookie-Editor JSON export (array of cookie objects)
    2. Header String: "name1=value1; name2=value2; ..."

    The xiaohongshu-mcp container stores cookies at $COOKIES_PATH
    (default: /app/data/cookies.json or cookies.json in workdir).
    Format: JSON array of {name, value, domain, path, expires, httpOnly, secure, sameSite}.
    """
    import json
    import shutil
    import subprocess

    value = value.strip()
    if not value:
        print("[X] Missing cookie value.")
        print("   Usage: agent-reach configure xhs-cookies '<cookie JSON or header string>'")
        return

    # Detect format and parse
    cookies_json = None

    # Try JSON format first (Cookie-Editor JSON export)
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list) and parsed:
                # Validate it looks like cookie objects
                first = parsed[0]
                if isinstance(first, dict) and "name" in first and "value" in first:
                    cookies_json = json.dumps(parsed)
                    print(f"  Parsed {len(parsed)} cookies from JSON format")
                else:
                    print("[X] JSON array doesn't contain cookie objects (need name/value fields)")
                    return
            else:
                print("[X] Empty or invalid JSON array")
                return
        except json.JSONDecodeError as e:
            print(f"[X] Invalid JSON: {e}")
            return

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
            return

    if not cookies_json:
        print("[X] Could not parse cookies. Accepted formats:")
        print('   1. JSON array: \'[{"name":"x","value":"y","domain":".xiaohongshu.com",...}]\'')
        print('   2. Header String: "key1=val1; key2=val2; ..."')
        return

    # Find the container
    docker = shutil.which("docker")
    if not docker:
        # No Docker - write to a local file for manual import
        cookie_path = os.path.expanduser("~/.agent-reach/xhs-cookies.json")
        with open(cookie_path, "w") as f:
            f.write(cookies_json)
        os.chmod(cookie_path, 0o600)
        print(f"  Cookies saved to {cookie_path}")
        print("  Docker not found. Copy manually:")
        print(f"  docker cp {cookie_path} xiaohongshu-mcp:/app/data/cookies.json")
        return

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
            return
    except Exception as e:
        print(f"[X] Could not check Docker: {e}")
        return

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
        os.unlink(tmp_path)

        if result.returncode != 0:
            print(f"[X] Failed to copy cookies: {result.stderr}")
            return

        print(f"✅ Cookies written to {container_name}:{cookie_path_in_container}")
        # Restart container so it reloads cookies from disk
        print("  Restarting container to reload cookies...", end=" ", flush=True)
        try:
            subprocess.run(
                [docker, "restart", container_name],
                capture_output=True, encoding="utf-8", timeout=30,
            )
            print("done")
        except Exception as e:
            print(f"\n  [!] Could not restart container: {e}")
            print(f"  Restart manually: docker restart {container_name}")
    except Exception as e:
        print(f"[X] Failed to write cookies: {e}")
        return

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


def _cmd_uninstall(args):
    """Remove all Agent Reach config, tokens, and skill files."""
    import shutil
    import subprocess

    dry_run = args.dry_run
    keep_config = args.keep_config

    print()
    print("Agent Reach Uninstaller")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be removed (no changes)")
        print()

    removed_any = False

    # ── 1. Config directory (~/.agent-reach/) ──
    config_dir = os.path.expanduser("~/.agent-reach")
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

    # ── 2. Skill files ──
    skill_dirs = [
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
                    shutil.rmtree(skill_path)
                    print(f"  Removed {platform_name} skill: {skill_path}")
                    removed_any = True
                except Exception as e:
                    print(f"  Could not remove {skill_path}: {e}")

    # ── 3. mcporter MCP entries ──
    if shutil.which("mcporter"):
        for mcp_name in ("exa", "xiaohongshu"):
            try:
                r = subprocess.run(
                    ["mcporter", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=10
                )
                if mcp_name in r.stdout:
                    if dry_run:
                        print(f"[dry-run] Would remove mcporter entry: {mcp_name}")
                    else:
                        subprocess.run(
                            ["mcporter", "config", "remove", mcp_name],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                        )
                        print(f"  Removed mcporter entry: {mcp_name}")
                        removed_any = True
            except Exception:
                pass

    # ── 4. Summary and optional steps ──
    print()
    if dry_run:
        print("Dry run complete. No changes were made.")
        print("Run without --dry-run to actually remove the above.")
    else:
        if removed_any:
            print("Agent Reach data removed.")
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


def _cmd_doctor():
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report
    try:
        from rich import print as rprint
    except ImportError:
        rprint = print
    config = Config()
    results = check_all(config)
    rprint(format_report(results))

    # Auto-install skill if not already present (fixes #154)
    _install_skill()


def _cmd_setup():
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
        print("  然后：mcporter config add exa https://mcp.exa.ai/mcp")
        print()
    else:
        try:
            r = subprocess.run(
                ["mcporter", "config", "list"], capture_output=True, encoding="utf-8", errors="replace", timeout=10
            )
            if "exa" in r.stdout.lower():
                print("  当前状态: ✅ 已配置")
            else:
                print("  当前状态: -- 未配置")
                setup_now = input("  现在自动配置 Exa 吗？[Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_r = subprocess.run(
                        ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                        capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                    )
                    if add_r.returncode == 0:
                        print("  ✅ Exa 已配置")
                    else:
                        print("  [!] 自动配置失败，请手动执行：")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp")
        except Exception:
            print("  [!] 无法检查 Exa 配置，请手动执行：")
            print("     mcporter config add exa https://mcp.exa.ai/mcp")
        print()

    # Step 2: GitHub token
    print("【可选】GitHub Token — 提高 API 限额")
    print("  无 token: 60 次/小时 | 有 token: 5000 次/小时")
    print("  获取: https://github.com/settings/tokens (无需任何权限)")
    current = config.get("github_token")
    if current:
        print(f"  当前状态: ✅ 已配置")
    else:
        key = input("  GITHUB_TOKEN (回车跳过): ").strip()
        if key:
            config.set("github_token", key)
            print("  ✅ GitHub API 已提升至 5000 次/小时！")
        else:
            print("  跳过。公开 API 也能用")
    print()

    # Step 3: Reddit — rdt-cli
    print("【信息】Reddit — 通过 rdt-cli 搜索和阅读，无需配置")
    print("  安装：pipx install rdt-cli")
    print()

    # Step 4: Groq (Whisper)
    print("【可选】Groq API — 视频无字幕时的语音转文字")
    print("  免费额度，注册: https://console.groq.com")
    current = config.get("groq_api_key")
    if current:
        print(f"  当前状态: ✅ 已配置")
    else:
        key = input("  GROQ_API_KEY (回车跳过): ").strip()
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

        if latest and latest != __version__:
            print(f"最新版本: v{latest} ← 有更新！")
            if body:
                print()
                print("更新内容：")
                # Show first 20 lines of release notes
                for line in body.strip().split("\n")[:20]:
                    print(f"  {line}")
            print()
            print("更新命令:")
            print("  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
            return "update_available"
        print(f"✅ 已是最新版本")
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
        print("更新命令:")
        print("  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
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
    from agent_reach.config import Config
    from agent_reach.doctor import check_all
    from agent_reach import __version__

    config = Config()
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
        if latest and latest != __version__:
            update_available = True
            new_version = latest
            release_body = data.get("body", "")

    # Output
    if not issues and not update_available:
        print(f"Agent Reach: 全部正常 ({ok}/{total} 渠道可用，v{__version__} 已是最新)")
        return

    print(f"Agent Reach 监控报告")
    print(f"=" * 40)
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
        print(f"  更新: pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")


if __name__ == "__main__":
    main()
