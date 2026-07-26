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

# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"


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
    p_install.add_argument("--safe", action="store_true",
                           help="Safe mode: skip automatic system changes, show what's needed instead")
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
                                 "xhs-cookies",
                                 "feishu-app-id", "feishu-app-secret", "feishu-chat-id",
                                 "feishu-webhook-url", "feishu-webhook-secret"],
                        help="What to configure (omit if using --from-browser)")
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument("--from-browser", metavar="BROWSER",
                        choices=["chrome", "firefox", "edge", "brave", "opera"],
                        help="Auto-extract ALL platform cookies from browser (chrome/firefox/edge/brave/opera)")

    # ── notify ──
    p_notify = sub.add_parser("notify", help="Send notifications via configured integrations")
    p_notify_sub = p_notify.add_subparsers(dest="notify_target", help="Notification target")
    p_feishu = p_notify_sub.add_parser("feishu", help="Send a Feishu card message")
    p_feishu.add_argument("--title", default="Agent Reach", help="Card title")
    p_feishu.add_argument("--text", default="", help="Card body (Markdown)")
    p_feishu.add_argument("--template", default="blue",
                          choices=["blue", "wathet", "turquoise", "green", "yellow",
                                   "orange", "red", "carmine", "violet", "purple",
                                   "indigo", "grey"],
                          help="Card header color")
    p_feishu.add_argument("--test", action="store_true",
                          help="Send a test message using current Feishu config")

    # ── daily-run ──
    p_daily = sub.add_parser("daily-run", help="Daily stock skill: audit, verdict, push")
    p_daily_sub = p_daily.add_subparsers(dest="daily_action", help="Daily-run action")
    p_dr_eval = p_daily_sub.add_parser("evaluate", help="Audit + verdict + quality gate (JSON)")
    p_dr_eval.add_argument("--input", "-i", required=True, help="Snapshot JSON file")
    p_dr_eval.add_argument("--with-doctor", action="store_true",
                           help="Include agent-reach doctor channel status in audit")
    p_dr_push = p_daily_sub.add_parser("push", help="Evaluate snapshot and push Feishu card")
    p_dr_push.add_argument("--input", "-i", required=True, help="Snapshot JSON file")
    p_dr_push.add_argument("--title", default="", help="Feishu card title")
    p_dr_push.add_argument("--template", default="", help="Feishu card color template")
    p_dr_push.add_argument("--with-doctor", action="store_true",
                           help="Include agent-reach doctor channel status in audit")
    p_dr_push.add_argument("--dry-run", action="store_true",
                           help="Evaluate only, do not send Feishu message")
    p_dr_fetch = p_daily_sub.add_parser("fetch", help="Enrich snapshot via AKShare (optional)")
    p_dr_fetch.add_argument("--code", required=True, help="A-share code e.g. 688008")
    p_dr_fetch.add_argument("--input", "-i", default="", help="Optional base snapshot JSON to merge")
    p_dr_fetch.add_argument("--output", "-o", default="", help="Write enriched snapshot to file")
    p_dr_verify = p_daily_sub.add_parser("verify", help="Compare baseline vs current snapshot")
    p_dr_verify.add_argument("--baseline", "-b", required=True, help="Baseline snapshot/report JSON")
    p_dr_verify.add_argument("--current", "-c", required=True, help="Current snapshot JSON")
    p_dr_verify.add_argument("--push", action="store_true", help="Push verification card to Feishu")
    p_dr_bt = p_daily_sub.add_parser("backtest", help="Run MSS threshold backtest on history JSON")
    p_dr_bt.add_argument("--input", "-i", required=True, help="History JSON array (date,mss,return,...)")
    p_dr_opt = p_daily_sub.add_parser("optimize", help="Grid search MSS thresholds/weights")
    p_dr_opt.add_argument("--input", "-i", required=True, help="History JSON (with optional factor fields)")
    p_dr_opt.add_argument(
        "--objective",
        default="excess_return",
        choices=["excess_return", "total_return", "win_rate", "sharpe_proxy"],
        help="Optimization objective",
    )
    p_dr_opt.add_argument("--save", action="store_true",
                          help="Write best params to ~/.agent-reach/daily_run_settings.json")
    p_dr_opt.add_argument("--push", action="store_true", help="Push optimization summary to Feishu")
    p_dr_plugins = p_daily_sub.add_parser("plugins", help="List or run expert plugins")
    p_dr_plugins.add_argument("plugins_action", nargs="?", choices=["list", "run"], default="list")
    p_dr_plugins.add_argument("--input", "-i", default="", help="Snapshot JSON for plugins run")
    p_dr_plugins.add_argument("--names", default="", help="Comma-separated plugin names")
    p_dr_morning = p_daily_sub.add_parser("morning", help="One-click: experts → evaluate → Feishu push")
    p_dr_morning.add_argument("--input", "-i", required=True, help="Morning snapshot JSON")
    p_dr_morning.add_argument("--code", default="", help="Optional A-share code for AKShare enrich")
    p_dr_morning.add_argument("--fetch", action="store_true", help="AKShare enrich when --code set")
    p_dr_morning.add_argument("--with-doctor", action="store_true", help="Include doctor in audit")
    p_dr_morning.add_argument("--dry-run", action="store_true", help="Do not push Feishu cards")
    p_dr_morning.add_argument("--no-start-notify", action="store_true", help="Skip start notification")
    p_dr_morning.add_argument("--save-baseline", action="store_true",
                              help="Save snapshot to ~/.agent-reach/daily_run/last_morning.json")
    p_dr_morning.add_argument("--title", default="", help="Feishu report title")
    p_dr_morning.add_argument("--names", default="", help="Comma-separated expert plugin names")
    p_dr_close = p_daily_sub.add_parser("close", help="One-click: verify morning vs close → Feishu")
    p_dr_close.add_argument("--input", "-i", required=True, help="Close/EOD snapshot JSON")
    p_dr_close.add_argument("--baseline", "-b", default="",
                            help="Morning baseline JSON (default: last_morning.json)")
    p_dr_close.add_argument("--dry-run", action="store_true", help="Do not push Feishu")
    p_dr_close.add_argument("--title", default="", help="Feishu verification title")
    p_dr_close.add_argument("--with-experts", action="store_true",
                            help="Run expert plugins on EOD snapshot before verify")
    p_dr_intraday = p_daily_sub.add_parser(
        "intraday",
        help="Intraday scan (S1-S10) + optional trade eval (T1-T5) with lookback MSS",
    )
    p_dr_intraday.add_argument("--input", "-i", default="", help="Snapshot JSON for scan/trade")
    p_dr_intraday.add_argument("--scan", action="store_true", help="Record one data collection scan")
    p_dr_intraday.add_argument("--trade", action="store_true", help="Evaluate trade after scan (or alone)")
    p_dr_intraday.add_argument("--status", action="store_true", help="Show today's intraday state")
    p_dr_intraday.add_argument("--reset", action="store_true", help="Reset today's intraday state")
    p_dr_intraday.add_argument("--with-doctor", action="store_true", help="Include doctor in audit")
    p_dr_intraday.add_argument("--dry-run", action="store_true", help="Do not push Feishu")
    p_dr_intraday.add_argument("--title", default="", help="Feishu card title")
    p_dr_intraday.add_argument("--names", default="", help="Comma-separated expert plugin names")
    p_dr_intraday.add_argument(
        "--expected-return",
        type=float,
        default=None,
        help="Expected return pct for friction check (e.g. 0.012 = 1.2%%)",
    )
    p_dr_build = p_daily_sub.add_parser(
        "build-snapshot",
        help="Auto-build snapshot from portfolio config + live quotes",
    )
    p_dr_build.add_argument(
        "--portfolio", "-p", default="",
        help="Portfolio JSON (default: ~/.agent-reach/daily_run/portfolio.json)",
    )
    p_dr_build.add_argument(
        "--output", "-o", default="",
        help="Write snapshot JSON (default: stdout or last_snapshot.json with --save)",
    )
    p_dr_build.add_argument("--save", action="store_true",
                            help="Save to ~/.agent-reach/daily_run/last_snapshot.json")
    p_dr_build.add_argument(
        "--report-type",
        default="intraday",
        choices=["premarket", "intraday", "close"],
        help="Snapshot report type",
    )
    p_dr_build.add_argument("--code", default="", help="Override primary stock code")
    p_dr_build.add_argument("--no-enrich", action="store_true",
                            help="Skip live quote fetch (use portfolio static prices)")
    p_dr_sched = p_daily_sub.add_parser("schedule", help="Cron schedule for morning/intraday/close")
    p_dr_sched.add_argument(
        "schedule_action",
        nargs="?",
        choices=["print", "install", "run"],
        default="print",
        help="print crontab | install crontab | run job now",
    )
    p_dr_sched.add_argument(
        "job_name",
        nargs="?",
        default="",
        help="Job for schedule run (e.g. schedule run intraday)",
    )
    p_dr_sched.add_argument(
        "--job",
        default="",
        choices=["morning", "intraday", "close", "weekly", "forecast"],
        help="Job for schedule run (alternative to positional job_name)",
    )
    p_dr_sched.add_argument("--dry-run", action="store_true",
                            help="Print crontab block without installing (install action)")
    p_dr_hot = p_daily_sub.add_parser("hot-news", help="Self-hosted 60s API for hot news")
    p_dr_hot_sub = p_dr_hot.add_subparsers(dest="hot_news_action", required=True)
    p_dr_hot_install = p_dr_hot_sub.add_parser("install", help="Deploy local 60s (native Node by default)")
    p_dr_hot_install.add_argument(
        "--mode",
        default="native",
        choices=["native", "docker", "auto"],
        help="Deploy mode: native Node.js (default), docker, or auto",
    )
    p_dr_hot_install.add_argument("--force", action="store_true",
                                  help="Recreate process/container")
    p_dr_hot_install.add_argument("--skip-deploy", action="store_true",
                                  help="Only merge settings; do not start 60s")
    p_dr_hot_install.add_argument("--skip-docker", action="store_true",
                                  help=argparse.SUPPRESS)  # backward compat → skip-deploy
    p_dr_hot_install.add_argument("--no-pull", action="store_true",
                                  help="Skip git pull / docker pull before run")
    p_dr_hot_install.add_argument("--no-reboot-cron", action="store_true",
                                  help="Do not install @reboot crontab auto-start")
    p_dr_hot_sub.add_parser("install-reboot", help="Install @reboot crontab for 60s auto-start")
    p_dr_hot_sub.add_parser("print-reboot-cron", help="Print @reboot crontab block")
    p_dr_hot_stop = p_dr_hot_sub.add_parser("stop", help="Stop local 60s (native and/or docker)")
    p_dr_hot_stop.add_argument("--remove", action="store_true",
                               help="Remove vendor dir (native) or container (docker)")
    p_dr_hot_stop.add_argument("--mode", default="",
                               choices=["", "native", "docker", "auto"],
                               help="Stop only selected deploy mode")
    p_daily_sub.add_parser("sample", help="Print example snapshot JSON to stdout")

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
                      help="Transcription provider (default: auto = groq → openai fallback)")
    p_tr.add_argument("-o", "--output", default=None,
                      help="Write transcript to a file instead of stdout")

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
    elif args.command == "notify":
        _cmd_notify(args)
    elif args.command == "daily-run":
        _cmd_daily_run(args)
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
    OPENCLI_ONLY_CHANNELS = {"opencli", "facebook", "instagram"}
    COOKIE_CHANNELS = {"twitter", "xueqiu", "bilibili"}

    requested_channels = set()
    if args.channels:
        raw = [c.strip().lower() for c in args.channels.split(",") if c.strip()]
        if "all" in raw:
            requested_channels = set(CHANNEL_INSTALLERS.keys()) | {"xueqiu", "linkedin"}
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

    server_skipped_opencli_channels = set()
    if env == "server" and requested_channels:
        # OpenCLI rides a real desktop Chrome session — useless headless
        server_skipped_opencli_channels = requested_channels & OPENCLI_ONLY_CHANNELS
        requested_channels -= server_skipped_opencli_channels

    # Apply explicit flags
    if args.proxy:
        if dry_run:
            print(f"[dry-run] Would save network proxy")
        else:
            config.set("proxy", args.proxy)
            config.set("bilibili_proxy", args.proxy)  # legacy key
            print(f"✅ 代理已保存（Agent 访问受限网络时使用）")

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

    if server_skipped_opencli_channels:
        print()
        print("  -- OpenCLI 需要桌面环境 + Chrome，服务器环境跳过："
              f"{', '.join(sorted(server_skipped_opencli_channels))}")

    # ── Install optional channels (only if --channels specified) ──
    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        ran_installers = set()
        for ch_name in sorted(requested_channels):
            installer = CHANNEL_INSTALLERS.get(ch_name)
            if installer and installer not in ran_installers:
                installer()
                ran_installers.add(installer)

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
        print("Tip: 部分平台对服务器 IP 有风控。")
        print("   Reddit 必须登录态（rdt-cli + Cookie，见 doctor 提示），中国大陆网络还需代理。")
        print("   保存代理供 Agent 使用：agent-reach configure proxy http://user:pass@ip:port")
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
            print("   agent-reach install --channels=twitter,xiaohongshu,reddit,facebook,instagram,...")
            print("   agent-reach install --channels=all  (install everything)")

        # Star reminder
        print()
        print("如果 Agent Reach 帮到了你，给个 Star 让更多人发现它吧：")
        print("   https://github.com/Panniantong/Agent-Reach")
        print("   只需一秒，对独立开发者意义很大。谢谢！")
    else:
        print()
        print("Dry run complete. No changes were made.")


def _install_skill(force: bool = True):
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
            status = _copy_skill_dir(target)
            if status:
                platform_name = "Agent" if ".agents" in skill_dir else "OpenClaw" if "openclaw" in skill_dir else "Claude Code"
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

    # NOTE: twitter-cli, xiaoyuzhou, xhs-cli etc. are optional.
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
    """Set up XiaoHongShu — backend depends on environment.

    Desktop: OpenCLI (reuses the browser session, zero config).
    Server: xiaohongshu-mcp guide (self-contained headless browser + QR
    login; we don't manage long-running services, so guide only).
    xhs-cli is no longer installed by default — upstream unmaintained
    since 2026-03; existing installs keep working as a fallback backend.
    """
    import shutil

    print("Setting up XiaoHongShu...")
    if _detect_environment() == "server":
        print("  服务器环境推荐 xiaohongshu-mcp（自带无头浏览器，扫码登录）：")
        print("    1. 下载 binary：https://github.com/xpzouying/xiaohongshu-mcp/releases")
        print("       （建议放到 ~/.agent-reach/tools/ 下）")
        print("    2. 启动服务（首次运行会下载约 150MB 浏览器，请等待完成）")
        print("    3. 扫码登录后接入：mcporter config add xiaohongshu http://localhost:18060/mcp")
        print("    4. 验证：agent-reach doctor")
        return

    _install_opencli_deps()
    if shutil.which("xhs"):
        print("  ✅ 检测到存量 xhs-cli，将作为备选后端继续可用")


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
        return

    if not shutil.which("npm"):
        print("  [!]  OpenCLI requires Node.js ≥ 20. Install Node first:")
        print("       https://nodejs.org  （或 brew install node）")
        return

    try:
        subprocess.run(
            ["npm", "install", "-g", OPENCLI_PACKAGE],
            capture_output=True, encoding="utf-8", errors="replace", timeout=300,
        )
    except Exception:
        pass

    st = opencli_status()
    if st.installed and not st.broken:
        print("  ✅ OpenCLI installed")
        print("  最后一步（必须手动，Chrome 安全限制）：安装浏览器扩展")
        print(f"    1. 打开 {OPENCLI_EXTENSION_URL}")
        print("    2. 点「添加至 Chrome」")
        print("    3. 运行 `opencli doctor` 验证连接")
    else:
        print(f"  [!]  OpenCLI install failed. Run: npm install -g {OPENCLI_PACKAGE}")


def _install_reddit_deps():
    """Set up Reddit — desktop prefers OpenCLI, rdt-cli for servers/legacy.

    No zero-config path exists (anonymous .json blocked, official API
    approval-gated since 2025-11) — every backend needs a logged-in session.
    """
    if _detect_environment() != "server":
        _install_opencli_deps()
        print("  Reddit 走 OpenCLI（浏览器里登录过 reddit.com 即可用）")
        import shutil
        if shutil.which("rdt"):
            print("  ✅ 检测到存量 rdt-cli，将作为备选后端继续可用")
        return

    _install_rdt_cli()


def _install_rdt_cli():
    """Install rdt-cli (pinned git source — PyPI lags upstream)."""
    import shutil
    import subprocess

    print("Setting up Reddit (rdt-cli)...")
    if shutil.which("rdt"):
        print("  ✅ rdt-cli already installed")
        return
    for tool, cmd in [
        ("pipx", ["pipx", "install", _RDT_GIT_SOURCE]),
        ("uv", ["uv", "tool", "install", "--from", _RDT_GIT_SOURCE, "rdt-cli"]),
    ]:
        if shutil.which(tool):
            try:
                subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=120)
                if shutil.which("rdt"):
                    print("  ✅ rdt-cli installed")
                    return
            except Exception:
                pass
    print(f"  [!]  rdt-cli install failed. Run: pipx install '{_RDT_GIT_SOURCE}'")


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
        config.set("groq_api_key", value)
        print(f"✅ Groq key configured!")

    elif args.key == "openai-key":
        config.set("openai_api_key", value)
        print(f"✅ OpenAI key configured!")

    elif args.key == "feishu-app-id":
        config.set("feishu_app_id", value.strip())
        print("✅ Feishu App ID configured!")

    elif args.key == "feishu-app-secret":
        config.set("feishu_app_secret", value.strip())
        print("✅ Feishu App Secret configured!")

    elif args.key == "feishu-chat-id":
        config.set("feishu_chat_id", value.strip())
        print("✅ Feishu chat_id configured!")
        print("   请确保机器人已加入目标群聊。")

    elif args.key == "feishu-webhook-url":
        config.set("feishu_webhook_url", value.strip())
        print("✅ Feishu webhook URL configured!")

    elif args.key == "feishu-webhook-secret":
        config.set("feishu_webhook_secret", value.strip())
        print("✅ Feishu webhook secret configured!")


def _cmd_notify(args):
    """Send outbound notifications."""
    from agent_reach.config import Config
    from agent_reach.integrations.feishu import FeishuError, send_card

    if args.notify_target != "feishu":
        print("Usage: agent-reach notify feishu [--test] [--title TITLE] [--text TEXT]")
        sys.exit(1)

    config = Config()
    title = args.title
    text = args.text
    if args.test:
        title = "✅ Agent Reach · 飞书推送测试"
        text = (
            "飞书通知集成已配置成功。\n\n"
            "- 模式：App Bot API 或 Webhook\n"
            "- 命令：`agent-reach notify feishu --test`\n"
            "- 文档：daily_run_skill 早盘/盘中/收盘简报将自动推送"
        )

    if not text:
        print("Missing --text (or use --test)")
        sys.exit(1)

    try:
        result = send_card(config, title, text, template=args.template)
    except FeishuError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    print("✅ Feishu message sent!")
    if isinstance(result, dict):
        data = result.get("data") or {}
        message_id = data.get("message_id")
        if message_id:
            print(f"   message_id: {message_id}")


def _cmd_daily_run(args):
    """Daily-run skill pipeline: audit, verdict, optional Feishu push."""
    import json
    from pathlib import Path

    from agent_reach.daily_run.pipeline import evaluate_snapshot, push_report, render_markdown

    if args.daily_action == "sample":
        sample = {
            "as_of": "2026-07-08T03:30:00+00:00",
            "report_type": "premarket",
            "code": "688008",
            "name": "澜起科技",
            "price": 255.87,
            "reference_price": 253.20,
            "ma20": 260.0,
            "position_20d": 0.55,
            "volume_ratio": 1.2,
            "mss_breakdown": {"fx": 35, "flow": 48, "global": 38, "sentiment": 50},
            "mss_range": [40, 52],
            "sources": {
                "quote": {"summary": "新浪财经 255.87 +1.05%"},
                "flow": {"summary": "北向净流入 12.36 亿"},
                "sentiment": {"summary": "雪球 DDR5 景气讨论"},
            },
            "structured_review_complete": True,
            "macro_summary": "预测 MSS 区间 [40, 52]",
            "portfolio": {"cash_ratio": 0.61, "total": 91938},
        }
        print(json.dumps(sample, ensure_ascii=False, indent=2))
        return

    if args.daily_action == "fetch":
        from agent_reach.daily_run.akshare_adapter import AKShareError, enrich_snapshot

        base: dict = {}
        if args.input:
            p = Path(args.input)
            if p.exists():
                base = json.loads(p.read_text(encoding="utf-8"))
        try:
            merged = enrich_snapshot(base, args.code)
        except AKShareError as exc:
            print(f"❌ {exc}")
            sys.exit(1)
        out = json.dumps(merged, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(out + "\n", encoding="utf-8")
            print(f"✅ Wrote enriched snapshot to {args.output}")
        else:
            print(out)
        return

    if args.daily_action == "verify":
        from agent_reach.config import Config
        from agent_reach.daily_run.settings import load_settings
        from agent_reach.daily_run.verify import render_verify_markdown, verify_snapshots
        from agent_reach.integrations.feishu import FeishuError, send_card

        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        current = json.loads(Path(args.current).read_text(encoding="utf-8"))
        result = verify_snapshots(baseline, current, load_settings())
        md = render_verify_markdown(result)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        print("\n--- Markdown ---\n")
        print(md)
        if args.push:
            title = f"🧠 收盘验证 · {result.name or result.code or '大盘'}"
            try:
                tpl = load_settings().get("report", {}).get("feishu_template_verify", "purple")
                send_card(Config(), title, md, template=tpl)
                print("\n✅ Verification report pushed to Feishu")
            except FeishuError as exc:
                print(f"\n❌ Feishu push failed: {exc}")
                sys.exit(1)
        return

    if args.daily_action == "backtest":
        from agent_reach.daily_run.backtest import render_backtest_markdown, run_mss_backtest
        from agent_reach.daily_run.settings import load_settings

        history = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(history, list):
            print("❌ backtest input must be a JSON array")
            sys.exit(1)
        cfg = load_settings().get("backtest", {})
        result = run_mss_backtest(
            history,
            macro_veto=float(cfg.get("macro_veto", 40)),
            aggressive_entry=float(cfg.get("aggressive_entry", 50)),
            initial_capital=float(cfg.get("default_initial_capital", 100000)),
            commission_rate=float(cfg.get("commission_rate", 0.0015)),
        )
        print(json.dumps({"metrics": result.metrics.to_dict(), "trades": result.trades}, ensure_ascii=False, indent=2))
        print("\n--- Markdown ---\n")
        print(render_backtest_markdown(result))
        return

    if args.daily_action == "optimize":
        from agent_reach.config import Config
        from agent_reach.daily_run.optimizer import (
            grid_search_optimize,
            render_optimize_markdown,
            save_optimized_settings,
        )
        from agent_reach.daily_run.settings import load_settings
        from agent_reach.integrations.feishu import FeishuError, send_card

        history = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(history, list):
            print("❌ optimize input must be a JSON array")
            sys.exit(1)
        settings = load_settings()
        result = grid_search_optimize(history, settings, objective=args.objective)
        payload = {
            "objective": result.objective,
            "best_score": result.best_score,
            "best_params": result.best_params,
            "metrics": result.metrics,
            "trials": result.trials,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        md = render_optimize_markdown(result)
        print("\n--- Markdown ---\n")
        print(md)
        if args.save:
            out = save_optimized_settings(result, settings)
            print(f"\n✅ Saved optimized settings to {out}")
        if args.push:
            try:
                send_card(
                    Config(),
                    "🎯 MSS 参数优化结果",
                    md,
                    template="green",
                )
                print("\n✅ Optimization report pushed to Feishu")
            except FeishuError as exc:
                print(f"\n❌ Feishu push failed: {exc}")
                sys.exit(1)
        return

    if args.daily_action == "plugins":
        from agent_reach.daily_run.plugins.loader import list_plugins, run_experts
        from agent_reach.daily_run.pipeline import evaluate_snapshot, render_markdown
        from agent_reach.daily_run.settings import load_settings

        if args.plugins_action == "list":
            print(json.dumps(list_plugins(), ensure_ascii=False, indent=2))
            return
        if not args.input:
            print("Usage: agent-reach daily-run plugins run -i snapshot.json [--names macro,technical]")
            sys.exit(1)
        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        names = [n.strip() for n in args.names.split(",") if n.strip()] or None
        enriched = run_experts(snapshot, load_settings(), names=names)
        evaluation = evaluate_snapshot(enriched)
        print(json.dumps(
            {
                "expert_results": enriched.get("expert_results"),
                "mss_final": enriched.get("mss_final"),
                "verdict": evaluation["verdict"].to_dict(),
                "markdown_preview": render_markdown(evaluation["report"]),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return

    if args.daily_action == "morning":
        from agent_reach.config import Config
        from agent_reach.daily_run.akshare_adapter import AKShareError, enrich_snapshot
        from agent_reach.daily_run.settings import load_settings
        from agent_reach.daily_run.workflows import run_morning, save_morning_baseline

        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if args.code and args.fetch:
            try:
                snapshot = enrich_snapshot(snapshot, args.code)
            except AKShareError as exc:
                print(f"⚠️ AKShare fetch skipped: {exc}")

        doctor_channels = None
        if args.with_doctor:
            from agent_reach.doctor import check_all
            doctor_channels = check_all(Config())

        names = [n.strip() for n in args.names.split(",") if n.strip()] or None
        try:
            result = run_morning(
                snapshot,
                settings=load_settings(),
                doctor_channels=doctor_channels,
                plugin_names=names,
                push=not args.dry_run,
                start_notify=not args.no_start_notify,
                title=args.title or None,
                config=Config(),
            )
        except RuntimeError as exc:
            print(f"❌ {exc}")
            sys.exit(1)

        if args.save_baseline:
            path = save_morning_baseline(result["snapshot"])
            print(f"✅ Baseline saved to {path}")

        report = result["evaluation"]["report"]
        print(f"结论：{report.get('verdict')}（{report.get('confidence')}） MSS={report.get('mss_final')}")
        print(f"步骤：{' → '.join(result['steps'])}")
        if args.dry_run:
            print("\n--- Markdown Preview ---\n")
            print(result["markdown"])
        else:
            print("✅ Morning report pushed to Feishu")
            feishu = result.get("feishu") or {}
            data = feishu.get("data") or {}
            if data.get("message_id"):
                print(f"   message_id: {data['message_id']}")
        return

    if args.daily_action == "close":
        from agent_reach.config import Config
        from agent_reach.daily_run.intraday import load_state
        from agent_reach.daily_run.plugins.loader import run_experts
        from agent_reach.daily_run.settings import load_settings
        from agent_reach.daily_run.snapshot_builder import load_portfolio
        from agent_reach.daily_run.workflows import (
            load_morning_baseline,
            prepare_close_run,
            run_close,
        )

        current = json.loads(Path(args.input).read_text(encoding="utf-8"))
        settings = load_settings()
        if args.with_experts:
            current = run_experts(current, settings)

        if args.baseline:
            baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        else:
            try:
                baseline = load_morning_baseline()
            except FileNotFoundError as exc:
                print(f"❌ {exc}")
                sys.exit(1)

        portfolio = load_portfolio()
        state = load_state()
        prepared = prepare_close_run(
            current,
            baseline,
            portfolio,
            settings=settings,
            scans=state.scans,
            trades=state.trades,
        )

        result = run_close(
            prepared["snapshot"],
            baseline,
            settings=settings,
            push=not args.dry_run,
            title=args.title or None,
            config=Config(),
            intraday_scans=state.scans,
            intraday_trades=state.trades,
            watchlist_adjust=prepared["watchlist_adjust"],
            code_review=prepared["code_review"],
            verify_dict=prepared.get("verify"),
        )
        result["code_review"] = prepared["code_review"]
        result["watchlist_adjust"] = prepared["watchlist_adjust"]
        result["prepare_steps"] = prepared["steps"]
        print(json.dumps(result["verify"], ensure_ascii=False, indent=2))
        if prepared["steps"]:
            print(f"预处理：{' → '.join(prepared['steps'])}")
        print("\n--- Markdown ---\n")
        print(result["markdown"])
        if not args.dry_run:
            print("\n✅ Close verification pushed to Feishu")
        return

    if args.daily_action == "intraday":
        from agent_reach.config import Config
        from agent_reach.daily_run.intraday import (
            evaluate_trade,
            load_state,
            record_scan,
            reset_state,
            run_intraday,
        )
        from agent_reach.daily_run.settings import load_settings

        settings = load_settings()

        if args.reset:
            reset_state()
            print("✅ Intraday state reset for today")
            return

        if args.status:
            state = load_state()
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return

        if not args.input:
            print("Usage: agent-reach daily-run intraday -i snapshot.json [--scan|--trade]")
            sys.exit(1)

        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        doctor_channels = None
        if args.with_doctor:
            from agent_reach.doctor import check_all
            doctor_channels = check_all(Config())

        names = [n.strip() for n in args.names.split(",") if n.strip()] or None
        do_scan = args.scan or not args.trade
        do_trade = args.trade

        if do_scan and do_trade:
            try:
                result = run_intraday(
                    snapshot,
                    settings=settings,
                    doctor_channels=doctor_channels,
                    plugin_names=names,
                    push=not args.dry_run,
                    trade=True,
                    title=args.title or None,
                    config=Config(),
                    expected_return_pct=args.expected_return,
                )
            except RuntimeError as exc:
                print(f"❌ {exc}")
                sys.exit(1)
            scan = result["scan"]["scan"]
            trade = result["trade"]["decision"]
            print(f"扫描 {scan['scan_id']}：MSS={scan['mss_final']} · {scan['verdict']}")
            print(f"调仓 {trade['trade_id']}：{trade['action']} · Lookback MSS={trade['lookback_mss']}")
            print(f"步骤：{' → '.join(result['steps'])}")
            if args.dry_run:
                print("\n--- Markdown ---\n")
                print(result["scan"]["markdown"])
                print("\n--- Trade ---\n")
                print(result["trade"]["markdown"])
            else:
                print("✅ Intraday report pushed to Feishu")
            return

        if do_scan:
            try:
                result = record_scan(
                    snapshot,
                    settings=settings,
                    doctor_channels=doctor_channels,
                    plugin_names=names,
                )
            except RuntimeError as exc:
                print(f"❌ {exc}")
                sys.exit(1)
            scan = result["scan"]
            print(f"✅ {scan['scan_id']} recorded · MSS={scan['mss_final']} · Lookback={result['lookback_mss']}")
            if not args.dry_run:
                from agent_reach.integrations.feishu import send_card
                tpl = settings.get("report", {}).get("feishu_template_intraday", "blue")
                name = scan.get("name") or scan.get("code") or "大盘"
                send_card(
                    Config(),
                    args.title or f"📊 盘中 {scan['scan_id']} · {name}",
                    result["markdown"],
                    template=tpl,
                )
                print("✅ Scan pushed to Feishu")
            else:
                print("\n--- Markdown ---\n")
                print(result["markdown"])
            return

        try:
            result = evaluate_trade(
                snapshot,
                settings=settings,
                doctor_channels=doctor_channels,
                plugin_names=names,
                expected_return_pct=args.expected_return,
            )
        except RuntimeError as exc:
            print(f"❌ {exc}")
            sys.exit(1)
        trade = result["decision"]
        print(f"✅ {trade['trade_id']} · {trade['action']} · Lookback MSS={trade['lookback_mss']}")
        print(f"   {trade['reasoning']}")
        if not args.dry_run:
            from agent_reach.integrations.feishu import send_card
            tpl = settings.get("report", {}).get("feishu_template_intraday", "blue")
            send_card(
                Config(),
                args.title or f"⚡ 调仓 {trade['trade_id']}",
                result["markdown"],
                template=tpl,
            )
            print("✅ Trade evaluation pushed to Feishu")
        else:
            print("\n--- Markdown ---\n")
            print(result["markdown"])
        return

    if args.daily_action == "build-snapshot":
        from agent_reach.config import Config
        from agent_reach.daily_run.snapshot_builder import build_snapshot, load_portfolio

        portfolio_path = Path(args.portfolio) if args.portfolio else None
        portfolio = load_portfolio(portfolio_path) if portfolio_path else load_portfolio()
        snap = build_snapshot(
            portfolio,
            report_type=args.report_type,
            primary_code=args.code or None,
            config=Config(),
            enrich=not args.no_enrich,
        )
        out_text = json.dumps(snap, ensure_ascii=False, indent=2)
        if args.save or args.output:
            out_path = Path(args.output) if args.output else (
                Path.home() / ".agent-reach" / "daily_run" / "last_snapshot.json"
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out_text + "\n", encoding="utf-8")
            print(f"✅ Snapshot written to {out_path}")
            print(f"   code={snap.get('code')} price={snap.get('price')} holdings={len(snap.get('portfolio', {}).get('holdings', []))}")
        else:
            print(out_text)
        return

    if args.daily_action == "schedule":
        from agent_reach.config import Config
        from agent_reach.daily_run.schedule import install_crontab, render_crontab_block, run_scheduled

        if args.schedule_action == "print":
            print(render_crontab_block())
            return

        if args.schedule_action == "install":
            try:
                block = install_crontab(dry_run=args.dry_run)
            except RuntimeError as exc:
                print(f"⚠️ {exc}")
                sys.exit(0 if "crontab.txt" in str(exc) else 1)
            if args.dry_run:
                print(block)
            else:
                print("✅ Crontab installed (Asia/Shanghai, local wrapper)")
                print(f"   logs: ~/.agent-reach/daily_run/logs/cron-*.log")
                print(render_crontab_block())
            return

        if args.schedule_action == "run":
            job = args.job or args.job_name or "intraday"
            if job not in ("morning", "intraday", "close", "weekly", "forecast"):
                print("❌ job must be morning, intraday, close, weekly, or forecast")
                sys.exit(1)
            try:
                result = run_scheduled(job, push=not args.dry_run, config=Config())
            except Exception as exc:
                print(f"❌ Schedule run failed: {exc}")
                sys.exit(1)
            job_result = result.get("result") or {}
            print(f"✅ Scheduled job '{job}' completed")
            print(f"   snapshot: {result.get('snapshot_path')}")
            if job == "morning":
                report = (job_result.get("evaluation") or {}).get("report") or {}
                print(f"   verdict={report.get('verdict')} MSS={report.get('mss_final')}")
            elif job == "intraday":
                scan = (job_result.get("scan") or {}).get("scan") or {}
                print(f"   {scan.get('scan_id')} MSS={scan.get('mss_final')} · {scan.get('verdict')}")
            elif job == "close":
                verify = job_result.get("verify") or {}
                print(f"   summary: {verify.get('summary', '')[:80]}")
            elif job == "weekly":
                wr = job_result.get("report") or {}
                pnl = wr.get("weekly_pnl")
                print(f"   weekly_pnl={pnl} holdings={len(wr.get('holdings') or [])}")
            elif job == "forecast":
                fc = job_result.get("forecast") or {}
                print(f"   forecast {fc.get('week_start')}–{fc.get('week_end')} symbols={len(fc.get('symbols') or {})}")
                print(f"   path: {result.get('forecast_path') or job_result.get('forecast_path')}")
            if not args.dry_run:
                print("   Feishu push sent")
            return

        print("Usage: agent-reach daily-run schedule {print|install|run} [--job morning|intraday|close|weekly|forecast]")
        sys.exit(1)

    if args.daily_action == "hot-news":
        import json as _json

        from agent_reach.daily_run.hot_news_deploy import (
            install_60s_local,
            install_reboot_crontab,
            render_reboot_crontab_block,
            status_60s,
            stop_60s,
        )

        action = args.hot_news_action
        if action == "install":
            skip_deploy = args.skip_deploy or getattr(args, "skip_docker", False)
            result = install_60s_local(
                mode=args.mode,
                pull=not args.no_pull,
                force=args.force,
                skip_deploy=skip_deploy,
                install_reboot_cron=not args.no_reboot_cron,
            )
            print(_json.dumps(result, ensure_ascii=False, indent=2))
            if result.get("ok"):
                print(f"\n✅ 60s hot-news ready ({result.get('active_base_url') or result.get('local_base_url')})")
                if result.get("web_url"):
                    print(f"   Web 面板: {result['web_url']}  （8787 为 API JSON，请打开 Web 面板阅读）")
                if result.get("settings_path"):
                    print(f"   settings: {result['settings_path']}")
                if result.get("reboot_cron_installed"):
                    print("   @reboot 自启: 已安装（重启后自动拉起 60s）")
                elif result.get("reboot_cron_message"):
                    print(f"   @reboot 自启: 未安装（{result['reboot_cron_message']}）")
            else:
                print(f"\n⚠️ {result.get('message', '60s install incomplete')}")
                sys.exit(1 if not result.get("active_base_url") else 0)
            return

        if action == "install-reboot":
            try:
                install_reboot_crontab()
            except RuntimeError as exc:
                print(f"⚠️ {exc}")
                sys.exit(1)
            print("✅ @reboot 自启已安装（重启后约 30s 自动拉起 60s + Web 面板）")
            print(render_reboot_crontab_block())
            return

        if action == "print-reboot-cron":
            print(render_reboot_crontab_block())
            return

        if action == "status":
            print(_json.dumps(status_60s(), ensure_ascii=False, indent=2))
            return

        if action == "stop":
            mode = args.mode or None
            ok, msg = stop_60s(remove=args.remove, mode=mode or None)
            if ok:
                print(f"✅ {msg}")
            else:
                print(f"❌ {msg}")
                sys.exit(1)
            return

        print("Usage: agent-reach daily-run hot-news {install|status|stop}")
        sys.exit(1)

    if args.daily_action not in ("evaluate", "push"):
        print("Usage: agent-reach daily-run {morning|close|intraday|build-snapshot|schedule|hot-news|evaluate|push|fetch|verify|backtest|optimize|plugins|sample} ...")
        sys.exit(1)

    path = Path(args.input)
    if not path.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    doctor_channels = None
    if getattr(args, "with_doctor", False):
        from agent_reach.config import Config
        from agent_reach.doctor import check_all
        doctor_channels = check_all(Config())

    evaluation = evaluate_snapshot(snapshot, doctor_channels=doctor_channels)
    audit = evaluation["audit"]
    gate = evaluation["gate"]
    report = evaluation["report"]

    if args.daily_action == "evaluate":
        payload = {
            "audit": {
                "passed": audit.passed,
                "issues": audit.issues,
                "warnings": audit.warnings,
                "summary": audit.summary(),
            },
            "verdict": evaluation["verdict"].to_dict(),
            "gate": {
                "passed": gate.passed,
                "missing_fields": gate.missing_fields,
                "warnings": gate.warnings,
                "summary": gate.summary(),
            },
            "report": report,
            "markdown_preview": render_markdown(report),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.exit(0 if audit.passed and gate.passed else 1)

    # push
    print(f"审计：{audit.summary()}")
    print(f"门禁：{gate.summary()}")
    print(f"结论：{report.get('verdict')}（{report.get('confidence')}） MSS={report.get('mss_final')}")

    if args.dry_run:
        print("\n--- Markdown Preview ---\n")
        print(render_markdown(report))
        sys.exit(0 if audit.passed and gate.passed else 1)

    try:
        result = push_report(
            evaluation,
            title=args.title or None,
            template=args.template or None,
        )
    except Exception as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    print("✅ Feishu daily-run report sent!")
    if isinstance(result, dict):
        data = result.get("data") or {}
        message_id = data.get("message_id")
        if message_id:
            print(f"   message_id: {message_id}")


def _cmd_transcribe(args):
    """Transcribe a URL or local audio file via Whisper (Groq → OpenAI fallback)."""
    from pathlib import Path

    from agent_reach.transcribe import TranscribeError, transcribe

    try:
        text = transcribe(args.source, provider=args.provider)
    except TranscribeError as e:
        print(f"❌ {e}")
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
        # No Docker - write to a local file for manual import.
        # Create with 0o600 atomically so the file is never world-readable
        # between open() and a follow-up chmod() (same pattern Config.save()
        # uses in config.py).
        import os
        import stat

        from agent_reach.utils.paths import make_private_dir

        cookie_dir = make_private_dir(os.path.expanduser("~/.agent-reach"))
        cookie_path = cookie_dir / "xhs-cookies.json"
        try:
            fd = os.open(
                str(cookie_path),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,  # 0o600
            )
            if os.name != "nt":
                os.chmod(cookie_path, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(cookies_json)
        except OSError:
            # Windows / unsupported flags — fall back to plain open + chmod.
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookies_json)
            try:
                os.chmod(cookie_path, 0o600)
            except OSError:
                pass
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


def _cmd_doctor(args=None):
    from agent_reach.config import Config
    from agent_reach.doctor import check_all, check_integrations, format_report
    try:
        from rich import print as rprint
    except ImportError:
        rprint = print
    config = Config()
    results = check_all(config)
    integrations = check_integrations(config)

    if args is not None and getattr(args, "json", False):
        payload = {"channels": results, "integrations": integrations}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    rprint(format_report(results))

    # Auto-install skill if not already present (fixes #154)
    _install_skill(force=False)


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
    print("【信息】Reddit — 必须登录态（无零配置路径）。桌面推荐 OpenCLI；或 rdt-cli：")
    print(f"  安装：pipx install '{_RDT_GIT_SOURCE}'")
    print("  然后运行：rdt login（需先在浏览器登录 reddit.com）")
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

    r, l = parse(remote), parse(local)
    if r is None or l is None:
        return remote != local  # unparseable — fall back to old behavior
    return r > l


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
        if latest and _is_newer_version(latest, __version__):
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
        print("  更新（一句话发给 Agent 即可完整更新）：")
        print("    帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md")


if __name__ == "__main__":
    main()
