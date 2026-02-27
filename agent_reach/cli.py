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
    if not getattr(sys.stdout, "isatty", lambda: False)():
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
        description="👁️ Give your AI Agent eyes to see the entire internet",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"Agent Reach v{__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── read ──
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

    # ── configure ──
    p_conf = sub.add_parser("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument("key", nargs="?", default=None,
                        choices=["proxy", "github-token", "groq-key",
                                 "twitter-cookies", "youtube-cookies"],
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
    print("👁️  Agent Reach Installer")
    print("=" * 40)

    if dry_run:
        print("🔍 DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("🛡️  SAFE MODE — skipping automatic system changes")
        print()

    # Auto-detect environment
    env = args.env
    if env == "auto":
        env = _detect_environment()
    
    if env == "server":
        print(f"📡 Environment: Server/VPS (auto-detected)")
    else:
        print(f"💻 Environment: Local computer (auto-detected)")

    # Apply explicit flags
    if args.proxy:
        if dry_run:
            print(f"[dry-run] Would configure proxy for Reddit + Bilibili")
        else:
            config.set("reddit_proxy", args.proxy)
            config.set("bilibili_proxy", args.proxy)
            print(f"✅ Proxy configured for Reddit + Bilibili")

    # ── Install system dependencies ──
    print()
    if dry_run:
        _install_system_deps_dryrun()
    elif safe_mode:
        _install_system_deps_safe()
    else:
        _install_system_deps()

    # ── mcporter (for Exa search + XiaoHongShu) ──
    print()
    if dry_run:
        print("📦 [dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        _install_mcporter_safe()
    else:
        _install_mcporter()

    # Auto-import cookies on local computers
    if env == "local" and not safe_mode and not dry_run:
        print()
        print("🍪 Trying to import cookies from browser...")
        try:
            from agent_reach.cookie_extract import configure_from_browser
            results = configure_from_browser("chrome", config)
            found = False
            for platform, success, message in results:
                if success:
                    print(f"  ✅ {platform}: {message}")
                    found = True
            if not found:
                # Try firefox
                results = configure_from_browser("firefox", config)
                for platform, success, message in results:
                    if success:
                        print(f"  ✅ {platform}: {message}")
                        found = True
            if not found:
                print("  ⬜ No cookies found (normal if you haven't logged into these sites)")
        except Exception:
            print("  ⬜ Could not read browser cookies (browser might be open)")
    elif env == "local" and safe_mode:
        print()
        print("🍪 Skipped auto cookie import (safe mode).")
        print("   To import manually: agent-reach configure --from-browser chrome")
    elif env == "local" and dry_run:
        print()
        print("🍪 [dry-run] Would try to import cookies from Chrome/Firefox")

    # Environment-specific advice
    if env == "server":
        print()
        print("💡 Tip: Reddit and Bilibili block server IPs.")
        print("   Reddit search still works via Exa (free).")
        print("   For full access: agent-reach configure proxy http://user:pass@ip:port")
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

        if ok < total:
            print()
            print("🤖 Some channels are not active yet. If you're an AI Agent, try to fix them yourself — then run `agent-reach doctor` again.")
    else:
        print()
        print("🔍 Dry run complete. No changes were made.")


def _install_skill():
    """Install Agent Reach as an agent skill (OpenClaw / Claude Code)."""
    import os
    import importlib.resources

    # Determine skill install path
    skill_dirs = [
        os.path.expanduser("~/.openclaw/skills"),   # OpenClaw
        os.path.expanduser("~/.claude/skills"),      # Claude Code (if exists)
        os.path.expanduser("~/.agents/skills"),      # Generic agents
    ]

    installed = False
    for skill_dir in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "agent-reach")
            try:
                os.makedirs(target, exist_ok=True)
                # Read SKILL.md from package data
                skill_md = importlib.resources.files("agent_reach").joinpath("skill", "SKILL.md").read_text()
                with open(os.path.join(target, "SKILL.md"), "w") as f:
                    f.write(skill_md)
                platform_name = "OpenClaw" if "openclaw" in skill_dir else "Claude Code" if "claude" in skill_dir else "Agent"
                print(f"🧩 Skill installed for {platform_name}: {target}")
                installed = True
            except Exception:
                pass

    if not installed:
        # No known skill directory found — create for OpenClaw by default
        target = os.path.expanduser("~/.openclaw/skills/agent-reach")
        try:
            os.makedirs(target, exist_ok=True)
            skill_md = importlib.resources.files("agent_reach").joinpath("skill", "SKILL.md").read_text()
            with open(os.path.join(target, "SKILL.md"), "w") as f:
                f.write(skill_md)
            print(f"🧩 Skill installed: {target}")
        except Exception:
            print("  ⬜ Could not install agent skill (optional)")


def _install_system_deps():
    """Install system-level dependencies: gh CLI, Node.js (for mcporter)."""
    import shutil
    import subprocess
    import platform
    import tempfile

    print("🔧 Checking system dependencies...")

    # ── gh CLI ──
    if shutil.which("gh"):
        print("  ✅ gh CLI already installed")
    else:
        print("  📥 Installing gh CLI...")
        os_type = platform.system().lower()
        if os_type == "linux":
            try:
                # Official GitHub apt source setup without invoking a shell.
                keyring_path = "/usr/share/keyrings/githubcli-archive-keyring.gpg"
                list_path = "/etc/apt/sources.list.d/github-cli.list"
                arch = subprocess.run(
                    ["dpkg", "--print-architecture"],
                    capture_output=True, text=True, timeout=10,
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
                    print("  ⚠️  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
            except Exception:
                print("  ⚠️  gh CLI install failed. You can try: snap install gh, or download from https://github.com/cli/cli/releases")
        elif os_type == "darwin":
            if shutil.which("brew"):
                try:
                    subprocess.run(["brew", "install", "gh"], capture_output=True, timeout=120)
                    if shutil.which("gh"):
                        print("  ✅ gh CLI installed")
                    else:
                        print("  ⚠️  gh CLI install failed. Try: brew install gh")
                except Exception:
                    print("  ⚠️  gh CLI install failed. Try: brew install gh")
            else:
                print("  ⚠️  gh CLI not found. Install: https://cli.github.com")
        else:
            print("  ⚠️  gh CLI not found. Install: https://cli.github.com")

    # ── Node.js (needed for mcporter) ──
    if shutil.which("node") and shutil.which("npm"):
        print("  ✅ Node.js already installed")
    else:
        print("  📥 Installing Node.js...")
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
                print("  ⚠️  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")
        except Exception:
            print("  ⚠️  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, or download from https://nodejs.org")

    # ── xreach CLI (for Twitter search) ──
    if shutil.which("xreach"):
        print("  ✅ xreach CLI already installed")
    else:
        if shutil.which("npm"):
            try:
                subprocess.run(
                    ["npm", "install", "-g", "xreach-cli"],
                    capture_output=True, text=True, timeout=120,
                )
                if shutil.which("xreach"):
                    print("  ✅ xreach CLI installed (Twitter search + timeline)")
                else:
                    print("  ⬜ xreach CLI install failed (optional — Twitter reading still works via Jina)")
            except Exception:
                print("  ⬜ xreach CLI install failed (optional — Twitter reading still works via Jina)")
        else:
            print("  ⬜ xreach CLI requires Node.js (optional — Twitter reading still works via Jina)")

    # ── undici (proxy support for Node.js fetch) ──
    if shutil.which("npm"):
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=5).stdout.strip()
        undici_path = os.path.join(npm_root, "undici", "index.js") if npm_root else ""
        if os.path.exists(undici_path):
            print("  ✅ undici already installed (Node.js proxy support)")
        else:
            try:
                subprocess.run(["npm", "install", "-g", "undici"], capture_output=True, text=True, timeout=60)
                print("  ✅ undici installed (Node.js proxy support)")
            except Exception:
                print("  ⬜ undici install failed (optional — xreach may not work behind proxies)")

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
                print("  ⬜ Could not configure yt-dlp JS runtime (YouTube may not work)")


def _install_system_deps_safe():
    """Safe mode: check what's installed, print instructions for what's missing."""
    import shutil

    print("🔧 Checking system dependencies (safe mode — no auto-install)...")

    deps = [
        ("gh", ["gh"], "GitHub CLI", "https://cli.github.com — or: apt install gh / brew install gh"),
        ("node", ["node", "npm"], "Node.js", "https://nodejs.org — or: apt install nodejs npm"),
        ("xreach", ["xreach"], "xreach CLI (Twitter)", "npm install -g xreach-cli"),
    ]

    missing = []
    for name, binaries, label, install_hint in deps:
        found = any(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label} already installed")
        else:
            print(f"  ⬜ {label} not found")
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

    print("🔧 [dry-run] System dependency check:")

    checks = [
        ("gh CLI", ["gh"], "apt install gh / brew install gh"),
        ("Node.js", ["node"], "curl NodeSource setup | bash + apt install nodejs"),
        ("xreach CLI", ["xreach"], "npm install -g xreach-cli"),
    ]

    for label, binaries, method in checks:
        found = any(shutil.which(b) for b in binaries)
        if found:
            print(f"  ✅ {label}: already installed, skip")
        else:
            print(f"  📥 {label}: would install via: {method}")


def _install_mcporter():
    """Install mcporter and configure Exa + XiaoHongShu MCP servers."""
    import shutil
    import subprocess

    print("📦 Setting up mcporter (search + XiaoHongShu backend)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
    else:
        # Check for npm/npx
        if not shutil.which("npm") and not shutil.which("npx"):
            print("  ⚠️  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/ or: curl -fsSL https://fnm.vercel.app/install | bash")
            return
        try:
            subprocess.run(
                ["npm", "install", "-g", "mcporter"],
                capture_output=True, text=True, timeout=120,
            )
            if shutil.which("mcporter"):
                print("  ✅ mcporter installed")
            else:
                print("  ❌ mcporter install failed. Retry: npm install -g mcporter (check network/timeout), or try: npx mcporter@latest list")
                return
        except Exception as e:
            print(f"  ❌ mcporter install failed: {e}")
            return

    # Configure Exa MCP (free, no key needed)
    try:
        r = subprocess.run(
            ["mcporter", "config", "list"], capture_output=True, text=True, timeout=5
        )
        if "exa" not in r.stdout:
            subprocess.run(
                ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                capture_output=True, text=True, timeout=10,
            )
            print("  ✅ Exa search configured (free, no API key needed)")
        else:
            print("  ✅ Exa search already configured")
    except Exception:
        print("  ⚠️  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp")

    # Check XiaoHongShu MCP (only if server is running)
    try:
        r = subprocess.run(
            ["mcporter", "config", "list"], capture_output=True, text=True, timeout=5
        )
        if "xiaohongshu" in r.stdout:
            print("  ✅ XiaoHongShu MCP already configured")
        else:
            # Check if XHS MCP server is running on localhost:18060
            import requests
            try:
                requests.get("http://localhost:18060/", timeout=3)
                subprocess.run(
                    ["mcporter", "config", "add", "xiaohongshu", "http://localhost:18060/mcp"],
                    capture_output=True, text=True, timeout=10,
                )
                print("  ✅ XiaoHongShu MCP auto-detected and configured")
            except Exception:
                print("  ⬜ XiaoHongShu MCP not detected (optional)")
                print("     Install: docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp")
                print("     Then:    mcporter config add xiaohongshu http://localhost:18060/mcp")
                print("     Repo:    https://github.com/xpzouying/xiaohongshu-mcp")
    except Exception:
        pass


def _install_mcporter_safe():
    """Safe mode: check mcporter status, print instructions."""
    import shutil

    print("📦 Checking mcporter (safe mode)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp")
    else:
        print("  ⬜ mcporter not installed")
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
                content = open(cloud_file).read().lower()
                if any(x in content for x in ["amazon", "google", "microsoft", "digitalocean", "linode", "vultr", "hetzner"]):
                    indicators += 2
            except:
                pass

    # systemd-detect-virt
    try:
        import subprocess
        result = subprocess.run(["systemd-detect-virt"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and result.stdout.strip() != "none":
            indicators += 1
    except:
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
        print(f"🔍 Extracting cookies from {browser}...")
        print()

        results = configure_from_browser(browser, config)

        found_any = False
        for platform, success, message in results:
            if success:
                print(f"  ✅ {platform}: {message}")
                found_any = True
            else:
                print(f"  ⬜ {platform}: {message}")

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
        config.set("reddit_proxy", value)
        config.set("bilibili_proxy", value)
        print(f"✅ Proxy configured for Reddit + Bilibili!")

        # Auto-test
        print("Testing Reddit access...", end=" ")
        try:
            import requests
            resp = requests.get(
                "https://www.reddit.com/r/test.json?limit=1",
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                proxies={"http": value, "https": value},
                timeout=10,
            )
            if resp.status_code == 200:
                print("✅ Reddit works!")
            else:
                print(f"⚠️ Reddit returned {resp.status_code}")
        except Exception as e:
            print(f"❌ Failed: {e}")

    elif args.key == "twitter-cookies":
        # Accept two formats:
        # 1. auth_token ct0 (two separate values)
        # 2. Full cookie header string: "auth_token=xxx; ct0=yyy; ..."
        auth_token = None
        ct0 = None

        if "auth_token=" in value and "ct0=" in value:
            # Full cookie string — parse it
            for part in value.replace(";", " ").split():
                if part.startswith("auth_token="):
                    auth_token = part.split("=", 1)[1]
                elif part.startswith("ct0="):
                    ct0 = part.split("=", 1)[1]
        elif len(value.split()) == 2 and "=" not in value:
            # Two separate values: AUTH_TOKEN CT0
            parts = value.split()
            auth_token = parts[0]
            ct0 = parts[1]

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)
            print(f"✅ Twitter cookies configured!")

            print("Testing Twitter access...", end=" ")
            try:
                import subprocess
                xreach = shutil.which("xreach")
                if not xreach:
                    print("⚠️ xreach CLI not installed. Run: npm install -g xreach-cli")
                else:
                    import os
                    env = os.environ.copy()
                    env["AUTH_TOKEN"] = auth_token
                    env["CT0"] = ct0
                    result = subprocess.run(
                        [xreach, "search", "test", "-n", "1"],
                        capture_output=True, text=True, timeout=15,
                        env=env,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        print("✅ Twitter Advanced works!")
                    else:
                        print(f"⚠️ Test returned no results (cookies might be wrong)")
            except Exception as e:
                print(f"❌ Failed: {e}")
        else:
            print("❌ Could not find auth_token and ct0 in your input.")
            print("   Accepted formats:")
            print("   1. agent-reach configure twitter-cookies AUTH_TOKEN CT0")
            print('   2. agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy; ..."')

    elif args.key == "youtube-cookies":
        config.set("youtube_cookies_from", value)
        print(f"✅ YouTube cookie source configured: {value}")
        print("   yt-dlp will use cookies from this browser for age-restricted/member videos.")

    elif args.key == "github-token":
        config.set("github_token", value)
        print(f"✅ GitHub token configured!")

    elif args.key == "groq-key":
        config.set("groq_api_key", value)
        print(f"✅ Groq key configured!")


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
                    ["mcporter", "list"], capture_output=True, text=True, timeout=10
                )
                if mcp_name in r.stdout:
                    if dry_run:
                        print(f"[dry-run] Would remove mcporter entry: {mcp_name}")
                    else:
                        subprocess.run(
                            ["mcporter", "config", "remove", mcp_name],
                            capture_output=True, text=True, timeout=10,
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
    print("  npm uninstall -g xreach-cli")
    print("  npm uninstall -g undici")


def _cmd_doctor():
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, format_report
    config = Config()
    results = check_all(config)
    print(format_report(results))


def _cmd_setup():
    from agent_reach.config import Config

    config = Config()
    print()
    print("👁️  Agent Reach Setup")
    print("=" * 40)
    print()

    # Step 1: Exa (via mcporter, no API key required)
    import shutil
    import subprocess

    print("【推荐】全网搜索 — Exa（通过 mcporter）")
    print("  免费，无需 API Key")

    if not shutil.which("mcporter"):
        print("  当前状态: ⬜ mcporter 未安装")
        print("  安装：npm install -g mcporter")
        print("  然后：mcporter config add exa https://mcp.exa.ai/mcp")
        print()
    else:
        try:
            r = subprocess.run(
                ["mcporter", "config", "list"], capture_output=True, text=True, timeout=10
            )
            if "exa" in r.stdout.lower():
                print("  当前状态: ✅ 已配置")
            else:
                print("  当前状态: ⬜ 未配置")
                setup_now = input("  现在自动配置 Exa 吗？[Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_r = subprocess.run(
                        ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if add_r.returncode == 0:
                        print("  ✅ Exa 已配置")
                    else:
                        print("  ⚠️ 自动配置失败，请手动执行：")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp")
        except Exception:
            print("  ⚠️ 无法检查 Exa 配置，请手动执行：")
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
            print("  ℹ️  跳过。公开 API 也能用")
    print()

    # Step 3: Reddit proxy
    print("【可选】Reddit 代理 — 完整阅读 Reddit 帖子+评论")
    print("  Reddit 封锁很多 IP，需要 ISP 代理才能直接访问")
    print("  格式: http://用户名:密码@IP:端口")
    current = config.get("reddit_proxy")
    if current:
        print(f"  当前状态: ✅ 已配置")
    else:
        proxy = input("  REDDIT_PROXY (回车跳过): ").strip()
        if proxy:
            config.set("reddit_proxy", proxy)
            print("  ✅ Reddit 完整阅读已开启！")
        else:
            print("  ℹ️  跳过。仍可通过搜索获取 Reddit 内容")
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
            print("  ℹ️  跳过")
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

    print(f"📦 当前版本: v{__version__}")
    release_url = "https://api.github.com/repos/Panniantong/Agent-Reach/releases/latest"
    commit_url = "https://api.github.com/repos/Panniantong/Agent-Reach/commits/main"

    # Fetch latest release with retry/backoff.
    resp, err, attempts = _github_get_with_retry(release_url, timeout=10, retries=3)
    if err:
        print(f"⚠️ 无法检查更新（{_update_error_text(err)}，已重试 {attempts} 次）")
        return "error"

    if resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

        if latest and latest != __version__:
            print(f"🆕 最新版本: v{latest} ← 有更新！")
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
        print("⚠️ 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    # No releases yet, fall back to latest main commit.
    resp2, err2, attempts2 = _github_get_with_retry(commit_url, timeout=10, retries=2)
    if err2:
        print(f"⚠️ 无法检查更新（{_update_error_text(err2)}，已重试 {attempts + attempts2} 次）")
        return "error"
    if resp2.status_code == 200:
        commit = resp2.json()
        sha = commit.get("sha", "")[:7]
        msg = commit.get("commit", {}).get("message", "").split("\n")[0]
        date = commit.get("commit", {}).get("committer", {}).get("date", "")[:10]
        print(f"🔍 最新提交: {sha} ({date}) {msg}")
        print()
        print("更新命令:")
        print("  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
        return "unknown"

    commit_err = _classify_github_response_error(resp2)
    if commit_err == "rate_limit":
        print("⚠️ 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    print(f"⚠️ 无法检查更新（GitHub 返回 {resp2.status_code}）")
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
            issues.append(f"❌ {r['name']}：{r['message']}")
        elif r["status"] == "warn":
            issues.append(f"⚠️ {r['name']}：{r['message']}")

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
        print(f"👁️ Agent Reach: 全部正常 ({ok}/{total} 渠道可用，v{__version__} 已是最新)")
        return

    print(f"👁️ Agent Reach 监控报告")
    print(f"=" * 40)
    print(f"📦 版本: v{__version__}  |  渠道: {ok}/{total}")

    if issues:
        print()
        for issue in issues:
            print(f"  {issue}")

    if update_available:
        print()
        print(f"🆕 新版本可用: v{new_version}")
        if release_body:
            for line in release_body.strip().split("\n")[:10]:
                print(f"    {line}")
        print(f"  更新: pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")


if __name__ == "__main__":
    main()
