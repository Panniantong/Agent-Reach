"""Unified entry for Agent Reach.

Agent commands:      <channel> <action>, read <url>, channels
Management commands: setup, add, remove, login, logout, browser, skill, doctor,
                     check, update, uninstall, configure, version

Everything prints one JSON object to stdout so agents never parse prose; logs
go to stderr. Exit code 0 = ok, 1 = error. Exceptions for humans: `help`, and
`--text` on doctor / check. `login` shows the upstream's interactive
output (QR codes, prompts) on stderr so stdout still carries only the JSON.

When a newer release is known (cached by a background check at most once a
day, never waited on), every JSON object carries meta.update = {current, latest, notes}.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, cast

from agent_reach.channels import get_all_channels
from agent_reach.channels.base import Action, Channel

from . import browser
from .dispatch import DEFAULT_TIMEOUT, find_action, run_action
from .result import (
    BAD_INPUT,
    DEFAULT_HINTS,
    NEED_SETUP,
    SCHEMA_VERSION,
    UPSTREAM_BROKEN,
    ReachError,
    envelope,
)
from .sessions import clear_session, has_login_state, import_legacy_state, session_env

_MANAGEMENT = (
    "setup", "add", "remove", "update", "doctor", "uninstall", "configure", "version",
)

HELP = """agent-reach — internet access for AI agents (all output is JSON)

For agents:
  agent-reach ask "一句话需求"             select, prepare, search, and summarize
  agent-reach channels                    list channels, actions, params
  agent-reach ensure CHANNEL              install/reuse/verify a channel; resumable
  agent-reach execute CHANNEL ACTION --params JSON  prepare and run one action
  agent-reach resume OPERATION_ID         continue after the user logs in
  agent-reach mcp                         stdio MCP server using the same runtime
  agent-reach mcp install cursor          register it in an existing Cursor profile
  agent-reach <channel> <action> [args]   e.g. agent-reach bilibili search python
  agent-reach read <url>                  read a link with the matching channel

For the user:
  agent-reach setup                       first run: install the default channels and the agent skill
  agent-reach add <channel>               add a channel; installs everything it needs, opens its login
  agent-reach remove <channel>            remove a channel (defaults too) and what only it used
  agent-reach login|logout <channel>      log in (the user does it) / forget the login
  agent-reach browser bind CHANNEL ID    bind an existing OpenCLI profile (IDs: opencli profile list)
  agent-reach browser unbind CHANNEL     forget binding without touching Chrome cookies
  agent-reach browser profiles           discover existing OpenCLI sessions
  agent-reach browser use ID              select a reusable default session
  agent-reach cloak setup                 install optional CloakBrowser runtime
  agent-reach cloak login CHANNEL         log in yourself, then close the Cloak window
  agent-reach cloak import CHANNEL --opencli-profile ID  explicitly copy site cookies
  agent-reach cloak status CHANNEL        inspect local CloakBrowser setup
  agent-reach ensure CHANNEL --reuse-profile ID  authorize site-scoped session import
  agent-reach ensure CHANNEL --forget-source     revoke that import grant
  agent-reach browser setup|status       explicit legacy dedicated browser
  agent-reach skill [link <skills-dir>]   where the agent skill is; link it for another AI
  agent-reach doctor [--text]             status of every channel and installed tool versions (no network)
  agent-reach check [channel] [--text]    live-test channels; --search tests search/jobs only
  agent-reach update [--check]            upgrade Agent Reach, every added channel's tools and the skill
  agent-reach configure <key> [value]     groq-key | openai-key | proxy | github-token | model-key | model-base-url | model-name
  agent-reach uninstall [--dry-run]       remove everything Agent Reach installed
"""


def unified_channels() -> List[Channel]:
    """Channels exposed on the command line."""
    return get_all_channels()


def _channel(name: str) -> Optional[Channel]:
    return next((ch for ch in unified_channels() if ch.name == name), None)


def _mgmt(action: str, fn, *args, **kwargs) -> int:
    """Run a management function and print {schema_version, ok, action, result, error}."""
    try:
        result, error = fn(*args, **kwargs), None
    except ReachError as err:
        result = None
        error = {"code": err.code, "message": err.message, "hint": err.hint or DEFAULT_HINTS.get(err.code, "")}
    return _emit({"schema_version": SCHEMA_VERSION, "ok": error is None, "action": action,
                  "result": result, "error": error})


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse that raises instead of printing usage and exiting."""

    def error(self, message: str):
        raise _ArgError(message)


#: Attach meta.update to JSON output (off for `update`, which reports versions itself).
_SHOW_NOTICE = True


def _emit(payload: dict) -> int:
    if _SHOW_NOTICE:
        from .update_notice import notice

        info = notice()
        if info:
            meta = payload.get("meta")
            payload["meta"] = {**(meta if isinstance(meta, dict) else {}), "update": info}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if payload.get("ok") else 1


def _usage(channel: Channel, action: Action) -> str:
    parts = ["agent-reach", channel.name, action.name]
    for p in action.params:
        parts.append(f"<{p.name}>" if p.required else f"[--{p.name} {p.name.upper()}]")
    return " ".join(parts)


def _bad_input(channel: Optional[str], action: Optional[str], message: str) -> int:
    return _emit(envelope(channel=channel, action=action, error=ReachError(BAD_INPUT, message)))


def _parse_action_args(action: Action, args: Sequence[str]) -> Dict[str, object]:
    parser = _Parser(prog=action.name, add_help=False)
    for p in action.params:
        if p.required:
            # Join extra words so an unquoted multi-word query still works.
            parser.add_argument(p.name, nargs="+" if p.type is str else None)
        else:
            parser.add_argument(f"--{p.name}", dest=p.name, default=None)
    parser.add_argument("--backend", choices=[b[0] for b in action.backends], default=None)
    parser.add_argument("--timeout", type=float, default=action.timeout or DEFAULT_TIMEOUT)
    ns = vars(parser.parse_args(list(args)))
    for p in action.params:
        if p.required and p.type is str and isinstance(ns.get(p.name), list):
            ns[p.name] = " ".join(ns[p.name])
    return ns


def _cmd_action(channel: Channel, args: Sequence[str]) -> int:
    if not args or args[0].startswith("-"):
        valid = ", ".join(a.name for a in channel.actions)
        return _bad_input(channel.name, None, f"missing action for {channel.name}; valid: {valid}")
    action = find_action(channel, args[0])
    if action is None:
        # Let run_action produce the standard unknown-action envelope.
        return _emit(run_action(channel, args[0], {}))
    try:
        ns = _parse_action_args(action, args[1:])
    except _ArgError as exc:
        return _bad_input(channel.name, action.name, f"{exc}; usage: {_usage(channel, action)}")
    timeout = cast(float, ns.pop("timeout"))
    backend = cast(Optional[str], ns.pop("backend"))
    return _emit(run_action(channel, action.name, ns, timeout=timeout, only_backend=backend))


def _cmd_read(args: Sequence[str]) -> int:
    parser = _Parser(prog="read", add_help=False)
    parser.add_argument("url")
    parser.add_argument("--backend", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, "read", f"{exc}; usage: agent-reach read <url>")
    readers = [ch for ch in unified_channels() if find_action(ch, "read")]
    specific = [ch for ch in readers if ch.name != "web"]
    target = next((ch for ch in specific if ch.can_handle(ns.url)), None)
    target = target or next((ch for ch in readers if ch.name == "web"), None)
    if target is None:
        return _bad_input(None, "read", "no channel can read this URL")
    return _emit(run_action(target, "read", {"target": ns.url}, timeout=ns.timeout, only_backend=ns.backend))


def _cmd_channels(_args: Sequence[str]) -> int:
    channels = []
    for ch in unified_channels():
        channels.append(
            {
                "name": ch.name,
                "description": ch.description,
                "level": ch.level,
                "login": _login_info(ch),
                "actions": [
                    {
                        "name": a.name,
                        "help": a.help,
                        "usage": _usage(ch, a),
                        "params": [
                            {
                                "name": p.name,
                                "help": p.help,
                                "required": p.required,
                                "type": p.type.__name__,
                                "default": p.default,
                            }
                            for p in a.params
                        ],
                        "backends": [label for label, _ in a.backends],
                    }
                    for a in ch.actions
                ],
            }
        )
    return _emit(
        {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "commands": {
                "read": "agent-reach read <url>  (picks the channel from the URL)",
                "action": "agent-reach <channel> <action> [args] [--timeout SECONDS]",
            },
            "channels": channels,
        }
    )


def _cmd_check(args: Sequence[str]) -> int:
    from . import manage

    parser = _Parser(prog="check", add_help=False)
    parser.add_argument("channels", nargs="*")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--search", action="store_true", help="Verify search/jobs through the normal route only")
    try:
        ns = parser.parse_args(list(args))
        out = manage.run_checks(ns.channels or None, timeout=ns.timeout, search_only=ns.search)
    except _ArgError as exc:
        return _bad_input(None, "check", str(exc))
    except ReachError as err:
        return _bad_input(None, "check", err.message)
    if ns.text:
        by_action: Dict[tuple, bool] = {}
        for r in out["results"]:
            mark = "PASS" if r["passed"] else "FAIL"
            why = "" if r["passed"] else f"  {r['error']['code']}: {r['error']['message']}"
            sys.stdout.write(f"{mark}  {r['channel']} {r['action']} [{r['backend']}] {r['elapsed_ms']}ms{why}\n")
            key = (r["channel"], r["action"])
            by_action[key] = by_action.get(key, False) or r["passed"]
        sys.stdout.write(f"\n{sum(by_action.values())}/{len(by_action)} actions working\n")
        return 0 if out["ok"] else 1
    return _emit({"schema_version": SCHEMA_VERSION, **out})


def _cmd_doctor(args: Sequence[str]) -> int:
    from . import manage

    parser = _Parser(prog="doctor", add_help=False)
    parser.add_argument("--text", action="store_true")
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, "doctor", str(exc))
    if not ns.text:
        return _mgmt("doctor", manage.doctor)
    result = manage.doctor()
    sys.stdout.write(f"Agent Reach {result['version']}\n\n")
    for c in result["channels"]:
        extra = "; ".join(c["problems"]) or c.get("hint", "")
        if c["regressed"]:
            extra = f"REGRESSED (worked at the previous check) {extra}"
        sys.stdout.write(f"{c['status']:<12} {c['channel']:<12} {c['level']:<13} {extra}\n")
    if result["tools"]:
        sys.stdout.write("\nTools\n")
        for t in result["tools"]:
            sys.stdout.write(f"{t['tool']:<16} {str(t.get('version') or '?'):<12} {t.get('owner', '')}\n")
    return 0


def _cmd_skill(args: Sequence[str]) -> int:
    from . import manage

    if not args:
        return _mgmt("skill", manage.skill_status)
    if args[0] != "link" or len(args) != 2:
        return _bad_input(None, "skill", "usage: agent-reach skill [link <skills-dir>]")
    return _mgmt("skill link", manage.link_skill, args[1])


def _cmd_management(head: str, args: Sequence[str]) -> int:
    from agent_reach import __version__

    from . import manage

    parser = _Parser(prog=head, add_help=False)
    if head in ("add", "remove"):
        parser.add_argument("channel")
        if head == "add":
            parser.add_argument("--allow-upgrade", action="store_true")
    elif head == "update":
        parser.add_argument("--check", action="store_true")
        parser.add_argument("--sync-only", action="store_true")
    elif head == "uninstall":
        parser.add_argument("--dry-run", action="store_true")
    elif head == "configure":
        parser.add_argument("key")
        parser.add_argument("value", nargs="?")
        parser.add_argument("--stdin", action="store_true")
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, head, str(exc))
    if head == "setup":
        return _mgmt(head, manage.setup)
    if head == "add":
        return _mgmt(head, manage.add, ns.channel, allow_upgrade=ns.allow_upgrade)
    if head == "remove":
        return _mgmt(head, manage.remove, ns.channel)
    if head == "update":
        if ns.sync_only:
            return _mgmt(head, manage.sync)
        return _mgmt(head, manage.update, check_only=ns.check)
    if head == "uninstall":
        return _mgmt(head, manage.uninstall, dry_run=ns.dry_run)
    if head == "configure":
        value = ns.value
        if ns.stdin:
            if sys.stdin.isatty() and ns.key.endswith("-key"):
                import getpass

                value = getpass.getpass(f"{ns.key}: ").strip()
            else:
                value = sys.stdin.read().strip()
        elif value is None and sys.stdin.isatty():
            import getpass

            value = getpass.getpass(f"{ns.key}: ").strip()
        return _mgmt(head, manage.configure, ns.key, value or "")
    return _mgmt(head, lambda: {"version": __version__, "install_method": manage.install_method()})


def _apply_saved_proxy() -> None:
    """Use the proxy saved by `configure proxy` unless the shell already sets one."""
    # Local browser/MCP endpoints must never be sent through the outbound proxy.
    bypass = list(dict.fromkeys(x.strip() for key in ("NO_PROXY", "no_proxy")
                               for x in os.environ.get(key, "").split(",") if x.strip()))
    for host in ("localhost", "127.0.0.1", "::1"):
        if host not in bypass:
            bypass.append(host)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(bypass)
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        return
    try:
        from agent_reach.config import Config

        proxy = Config(read_only=True).get("proxy")
    except Exception:  # noqa: BLE001
        return
    if proxy:
        os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"] = str(proxy)


def _login_info(ch: Channel):
    if ch.login_url:
        return {"via": "browser", "logged_in": None, "command": f"agent-reach login {ch.name}"}
    if ch.session:
        return {"via": "session", "logged_in": has_login_state(ch.session), "command": f"agent-reach login {ch.name}"}
    return None


def _login_channel(cmd: str, args: Sequence[str]):
    parser = _Parser(prog=cmd, add_help=False)
    parser.add_argument("channel")
    if cmd == "login":
        parser.add_argument("--import-existing", action="store_true")
        parser.add_argument("--sync", action="store_true")
        parser.add_argument("--new-browser", action="store_true", help="Explicitly open the persistent dedicated browser")
        parser.add_argument("--native", action="store_true", help="Explicitly run the native login flow; it may open a browser")
    ns = parser.parse_args(list(args))
    ch = _channel(ns.channel)
    if ch is None:
        raise _ArgError(f"unknown channel: {ns.channel}")
    if cmd == "logout" and not (ch.session or ch.logout_keys or "opencli" in ch.tools):
        hint = " Log out in the Agent Reach browser window instead." if ch.login_url else ""
        raise _ArgError(f"{ch.name} has no login state managed by Agent Reach.{hint}")
    if cmd == "login" and not (ch.session or ch.login_url):
        raise _ArgError(f"{ch.name} has no login managed by Agent Reach")
    return ch, ns


def _cmd_login(args: Sequence[str]) -> int:
    try:
        ch, ns = _login_channel("login", args)
    except _ArgError as exc:
        return _bad_input(None, "login", str(exc))
    if sum(bool(x) for x in (ns.sync, ns.new_browser, ns.native, ns.import_existing)) > 1:
        return _bad_input(ch.name, "login", "Choose only one login mode")
    from .onboarding import open_boss_browser, require_boss_cdp, session_plan
    if not (ns.sync or ns.new_browser or ns.native or ns.import_existing):
        return _mgmt("login", session_plan, ch)
    if ns.new_browser:
        if ch.name == "boss":
            return _mgmt("login", open_boss_browser)
        return _bad_input(ch.name, "login", "Use browser setup explicitly for OpenCLI, or login CHANNEL --native for a tool-owned login")
    if "opencli" in ch.tools:
        return _bad_input(ch.name, "login", "Log in inside the selected Chrome profile; Reach does not copy its cookies")
    if ch.name == "boss":
        try:
            endpoint = require_boss_cdp()
        except ReachError as err:
            return _emit(envelope(channel=ch.name, action="login", error=err))
    if ns.import_existing and ch.session:
        copied = import_legacy_state(ch.session, ch.legacy_state)
        if copied:
            return _emit(envelope(channel=ch.name, action="login", backend=ch.session,
                                  items=[{"imported": copied}]))
    try:
        synced = ch.sync_login()
    except ReachError as err:
        return _emit(envelope(channel=ch.name, action="login", error=err))
    if synced is not None:
        return _emit(envelope(channel=ch.name, action="login", backend="agent-reach-browser", items=[synced]))
    if not ch.login_argv:
        return _bad_input(ch.name, "login", f"{ch.name} has nothing to sync; just log in in the Agent Reach browser")
    from .tools import resolve

    exe = resolve(ch.login_argv[0])
    if not exe:
        return _emit(envelope(channel=ch.name, action="login", error=ReachError(
            NEED_SETUP, f"{ch.login_argv[0]} is not installed", hint=f"Run `agent-reach add {ch.name}` first.")))
    from .sessions import session_dir

    argv = [a.replace("{session}", str(session_dir(ch.session))) for a in ch.login_argv[1:]]
    if ch.name == "boss":
        argv[argv.index("--cdp-url") + 1] = endpoint
    env = dict(os.environ)
    if ch.session_home:
        env.update(session_env(ch.session))
    # Interactive: the user sees the QR code / prompts on stderr; stdout stays JSON.
    code = subprocess.call([exe, *argv], env=env, stdout=sys.stderr, stderr=sys.stderr)
    if code != 0 or not has_login_state(ch.session):
        return _emit(envelope(channel=ch.name, action="login",
                              error=ReachError(UPSTREAM_BROKEN, f"login did not complete (exit {code})")))
    return _emit(envelope(channel=ch.name, action="login", backend=ch.session, items=[{"logged_in": True}]))


def _cmd_logout(args: Sequence[str]) -> int:
    try:
        ch, _ = _login_channel("logout", args)
    except _ArgError as exc:
        return _bad_input(None, "logout", str(exc))
    from .manage import uses_cloak
    if uses_cloak(ch):
        from agent_reach.backends.cloak import logout
        try:
            result = logout(ch.name)
        except ReachError as err:
            return _emit(envelope(channel=ch.name, action="logout", error=err))
        return _emit(envelope(channel=ch.name, action="logout", backend="cloakbrowser",
                              items=[{**result, "browser_cookies_changed": False}]))
    if "opencli" in ch.tools:
        return _emit(envelope(channel=ch.name, action="logout", backend="opencli", items=[{
            "removed": False, "next": "Log out in Chrome yourself, or use agent-reach browser unbind " + ch.name,
            "browser_cookies_changed": False}]))
    removed = clear_session(ch.session) if ch.session else False
    if ch.logout_keys:
        from agent_reach.config import Config

        cfg = Config()
        for key in ch.logout_keys:
            if cfg.get(key):
                cfg.delete(key)
                removed = True
    return _emit(envelope(channel=ch.name, action="logout", backend=ch.session or "config", items=[{"removed": removed}]))


def _cmd_browser(args: Sequence[str]) -> int:
    parser = _Parser(prog="browser", add_help=False)
    parser.add_argument("op", choices=("setup", "status", "profiles", "use", "bind", "unbind", "repair-opencli"))
    parser.add_argument("channel", nargs="?")
    parser.add_argument("profile", nargs="?")
    parser.add_argument("--label")
    try:
        ns = parser.parse_args(list(args))
    except _ArgError as exc:
        return _bad_input(None, "browser", f"{exc}; usage: agent-reach browser setup|status")
    if ns.op == "profiles":
        from .onboarding import profiles
        return _mgmt("browser profiles", profiles)
    if ns.op == "use":
        from .onboarding import use_profile
        if not ns.channel:
            return _bad_input(None, "browser", "Usage: browser use CONTEXT_ID [--label NAME]")
        return _mgmt("browser use", use_profile, ns.channel, ns.label)
    if ns.op == "bind" and ns.channel == "boss":
        from .onboarding import bind_cdp
        return _mgmt("browser bind", bind_cdp, ns.profile)
    if ns.op == "repair-opencli":
        from .opencli_compat import repair
        return _mgmt("browser repair-opencli", repair)
    if ns.op in ("bind", "unbind"):
        from .browser_binding import bind_profile, unbind_profile
        ch = _channel(ns.channel)
        if ch is None or "opencli" not in ch.tools:
            return _bad_input(None, "browser", "Specify an OpenCLI channel")
        if ns.op == "bind" and not ns.profile:
            return _bad_input(None, "browser", "Usage: browser bind CHANNEL CONTEXT_ID|dedicated")
        item = bind_profile(ch.name, ns.profile) if ns.op == "bind" else unbind_profile(ch.name)
        return _emit(envelope(channel=ch.name, action="browser " + ns.op, backend="opencli", items=[item]))
    action = f"browser {ns.op}"
    try:
        item = browser.setup() if ns.op == "setup" else browser.status()
    except ReachError as err:
        return _emit(envelope(channel=None, action=action, error=err))
    return _emit(envelope(channel=None, action=action, backend="agent-reach-browser", items=[item]))


def _cmd_flow(head: str, args: Sequence[str]) -> int:
    from . import flow

    parser = _Parser(prog=head, add_help=False)
    if head == "resume":
        parser.add_argument("operation_id")
    else:
        parser.add_argument("channel")
        if head == "execute":
            parser.add_argument("channel_action")
            parser.add_argument("--params", required=True)
            parser.add_argument("--timeout", type=float, default=60.0)
        else:
            parser.add_argument("--action")
            parser.add_argument("--no-verify", action="store_true")
            parser.add_argument("--forget-source", action="store_true")
        parser.add_argument("--reuse-profile")
    try:
        ns = parser.parse_args(list(args))
        if head == "resume":
            from .ask import resume
            result = resume(ns.operation_id)
        elif head == "ensure":
            result = (flow.forget_source(ns.channel) if ns.forget_source else
                      flow.ensure(ns.channel, action=ns.action, source_profile=ns.reuse_profile,
                                  verify=not ns.no_verify))
        else:
            params = json.loads(ns.params)
            if not isinstance(params, dict):
                raise _ArgError("--params must be a JSON object")
            result = flow.execute(ns.channel, ns.channel_action, params, timeout=ns.timeout,
                                  source_profile=ns.reuse_profile)
    except (ValueError, _ArgError) as exc:
        return _bad_input(None, head, str(exc))
    except ReachError as err:
        return _emit(envelope(channel=None, action=head, error=err))
    return _emit({"schema_version": SCHEMA_VERSION, "action": head, **result})



def main(argv: Sequence[str]) -> int:
    global _SHOW_NOTICE

    if not argv or argv[0] in ("help", "-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    from . import tools, update_notice

    tools.extend_path()
    _SHOW_NOTICE = argv[0] != "update"
    if argv[0] not in ("update", "uninstall"):
        update_notice.maybe_refresh()
    _apply_saved_proxy()
    head, rest = argv[0], argv[1:]
    if head == "channels":
        return _cmd_channels(rest)
    if head == "ask":
        if not rest:
            return _bad_input(None, "ask", "usage: agent-reach ask <instruction>")
        from .ask import ask
        try:
            result = ask(" ".join(rest))
        except ReachError as err:
            return _emit(envelope(channel=None, action="ask", error=err))
        return _emit({"schema_version": SCHEMA_VERSION, "action": "ask", **result})
    if head in ("ensure", "execute", "resume"):
        return _cmd_flow(head, rest)
    if head == "mcp":
        if not rest:
            from agent_reach.mcp_server import serve
            return serve()
        from . import mcp_registration
        if rest == ["install", "cursor"]:
            return _mgmt("mcp install", mcp_registration.install)
        if rest == ["status"]:
            return _mgmt("mcp status", mcp_registration.status)
        if rest == ["uninstall", "cursor"]:
            return _mgmt("mcp uninstall", mcp_registration.uninstall)
        return _bad_input(None, "mcp", "usage: agent-reach mcp [install cursor|status|uninstall cursor]")
    if head == "check":
        return _cmd_check(rest)
    if head == "read":
        return _cmd_read(rest)
    if head == "login":
        return _cmd_login(rest)
    if head == "logout":
        return _cmd_logout(rest)
    if head == "cloak":
        return _cmd_cloak(rest)
    if head == "browser":
        return _cmd_browser(rest)
    if head == "doctor":
        return _cmd_doctor(rest)
    if head == "skill":
        return _cmd_skill(rest)
    if head in _MANAGEMENT:
        return _cmd_management(head, rest)
    channel = _channel(head)
    if channel is None:
        return _bad_input(None, head, f"unknown command or channel: {head}; run `agent-reach help`")
    return _cmd_action(channel, rest)


def _cmd_cloak(args):
    from agent_reach.backends import cloak
    parser = _Parser(prog="cloak", add_help=False)
    parser.add_argument("op", choices=("setup", "login", "import", "status", "logout"))
    parser.add_argument("channel", nargs="?", choices=tuple(cloak.DOMAINS))
    parser.add_argument("--state-file")
    parser.add_argument("--opencli-profile")
    try:
        ns = parser.parse_args(list(args))
        if ns.op != "setup" and not ns.channel:
            raise _ArgError("channel is required")
        if ns.op != "import" and (ns.state_file or ns.opencli_profile):
            raise _ArgError("import options require cloak import")
    except _ArgError as exc:
        return _bad_input(None, "cloak", str(exc))
    if ns.op == "setup":
        return _mgmt("cloak.setup", cloak.setup)
    if ns.op == "login":
        return _mgmt("cloak.login", cloak.login, ns.channel)
    if ns.op == "import":
        return _mgmt("cloak.import", cloak.import_login, ns.channel,
                     state_file=ns.state_file, opencli_profile=ns.opencli_profile)
    if ns.op == "logout":
        return _mgmt("cloak.logout", cloak.logout, ns.channel)
    return _mgmt("cloak.status", cloak.status, ns.channel)
