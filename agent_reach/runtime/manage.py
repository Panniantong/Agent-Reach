"""Management commands: setup, add, remove, update, doctor, skill, uninstall, configure.

Each public function returns a plain dict `result` or raises ReachError; the CLI
wraps it in {schema_version, ok, action, result, error}.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from agent_reach import __version__
from agent_reach.utils.paths import home_dir

from . import state, tools, update_notice
from .result import BAD_INPUT, NEED_SETUP, UPSTREAM_BROKEN, ReachError

REPO = update_notice.REPO
CHECK_FRESH_SECONDS = 24 * 3600

#: Machine prerequisites a channel may list in `prereqs` (keys of tools.TOOLS).
#: `add` installs them when the machine has none, without an admin password.
PREREQS = ("node", "uv", "ffmpeg", "chrome")


def _channels():
    from .cli import unified_channels

    return unified_channels()


def _channel(name: str):
    ch = next((c for c in _channels() if c.name == name), None)
    if ch is None:
        valid = ", ".join(c.name for c in _channels())
        raise ReachError(BAD_INPUT, f"unknown channel: {name}; valid: {valid}")
    return ch


def is_added(ch, data: Optional[dict] = None) -> bool:
    data = data or state.load()
    if ch.name in data["channels"]:
        return True
    return ch.level == "default" and ch.name not in data["removed_defaults"]


def _uses_browser(ch) -> bool:
    return bool(ch.login_url)




@lru_cache(maxsize=1)
def code_signature() -> str:
    """A candidate with the same version must not inherit another build's passes."""
    root = Path(__file__).parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "api" not in path.relative_to(root).parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def fingerprint(channel: str) -> str:
    """Invalidate checks when this build, channel dependencies, source, or network changes."""
    from agent_reach.config import Config

    from .browser_binding import profile_for

    data = state.load()
    cfg = Config(read_only=True)
    ch = _channel(channel)
    relevant = set(ch.prereqs) | set(ch.tools) | set(channel_tools(ch))
    relevant.update(name for action in ch.actions for name, _ in action.backends)
    session_revision = data.get("session_revisions", {}).get(channel)
    value = [__version__, code_signature(), channel, profile_for(channel),
             cfg.get("proxy"), session_revision,
             {k: data["tools"].get(k, {}).get("version") for k in sorted(relevant)}]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def fresh_actions(channel: str, check: Optional[dict]) -> dict[str, bool]:
    """Keep each action's evidence independent when another action is checked later."""
    if not check:
        return {}
    evidence = check.get("evidence", {})
    signature = fingerprint(channel)
    return {name: passed for name, passed in check.get("actions", {}).items()
            if evidence.get(name, {}).get("fingerprint") == signature
            and state.age_seconds(evidence[name].get("at")) < CHECK_FRESH_SECONDS
            and (not passed or evidence[name].get("verified", True))
            and (check.get("codes", {}).get(name) != "RATE_LIMITED"
                 or state.age_seconds(evidence[name].get("at")) < 3600)}


def fresh_check(channel: str, check: Optional[dict]) -> bool:
    return bool(fresh_actions(channel, check))


def channel_tools(ch) -> List[str]:
    """Everything `add` installs for the channel, prerequisites first."""
    names = (["node", "opencli", "chrome"] if _uses_browser(ch) else []) + list(ch.prereqs) + list(ch.tools)
    return list(dict.fromkeys(names))


def site_domains(ch) -> List[str]:
    """Cookie domains of the channel's site in the Agent Reach browser."""
    if getattr(ch, "domains", ()):
        return list(ch.domains)
    host = (urlparse(ch.login_url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return [host] if host else []


def _has_login(ch) -> bool:
    return bool(ch.login_url or ch.login_argv or ch.logout_keys)


def browser_login_next(ch) -> str:
    """The single sentence for the user after the login page opened in the Agent Reach browser."""
    from agent_reach.channels.base import Channel

    needs_sync = bool(ch.session) or type(ch).sync_login is not Channel.sync_login
    if needs_sync:
        return (f"The user logs in to {ch.name} in the Agent Reach browser window that just opened; "
                f"then run `agent-reach login {ch.name} --sync`.")
    return f"The user logs in to {ch.name} in the Agent Reach browser window that just opened; then retry the action."

# ── checks ──

def run_checks(names: Optional[List[str]] = None, timeout: float = 60.0, search_only: bool = False) -> dict:
    """Live-test the added channels (or the named ones); persist results in state."""
    from .dispatch import run_action

    selected = _channels()
    if names:
        unknown = set(names) - {c.name for c in selected}
        if unknown:
            raise ReachError(BAD_INPUT, f"unknown channel(s): {', '.join(sorted(unknown))}")
        selected = [c for c in selected if c.name in names]
    else:
        data = state.load()
        selected = [c for c in selected if is_added(c, data)]
    import math
    if not math.isfinite(timeout) or timeout <= 0:
        raise ReachError(BAD_INPUT, "timeout must be finite and positive")
    results = []
    for ch in selected:
        for action in ch.actions:
            if action.live_test is None or (search_only and action.name not in {"search", "jobs"}):
                continue
            # Search acceptance exercises the same route as an agent command, once.
            backends = [(None, None)] if search_only else action.backends
            for label, _ in backends:
                out = run_action(ch, action.name, dict(action.live_test), timeout=timeout, only_backend=label)
                label = out.get("backend") or label or (out["meta"]["attempts"][-1]["backend"] if out["meta"]["attempts"] else None)
                passed = bool(out["ok"] and out["items"])
                err = out["error"] or (None if passed else {"code": "EMPTY", "message": "succeeded but returned no items"})
                results.append({
                    "channel": ch.name, "action": action.name, "backend": label, "passed": passed,
                    "verified": bool(passed and out["items"]),
                    "elapsed_ms": out["meta"]["elapsed_ms"],
                    "error": err and {"code": err["code"], "message": err["message"]},
                    "item_count": len(out["items"]), "attempts": out["meta"]["attempts"],
                    "access": out["meta"].get("access"),
                })
                if err and err["code"] in {"PLATFORM_BLOCKED", "RATE_LIMITED", "NEED_LOGIN"}:
                    break
    by_action: Dict[tuple, bool] = {}
    codes: Dict[tuple, str] = {}
    for r in results:
        key = (r["channel"], r["action"])
        by_action[key] = by_action.get(key, False) or r["passed"]
        if not r["passed"] and key not in codes:
            codes[key] = r["error"]["code"]
    signatures = {ch.name: fingerprint(ch.name) for ch in selected}
    def save_checks(data):
        for ch in selected:
            actions = {a: ok for (c, a), ok in by_action.items() if c == ch.name}
            if actions:
                failed = {a: codes[(ch.name, a)] for a, ok in actions.items() if not ok}
                old = data["checks"].get(ch.name, {})
                previous = old.get("actions", {})
                evidence = dict(old.get("evidence", {}))
                for action in actions:
                    matches = [r for r in results if r["channel"] == ch.name and r["action"] == action]
                    best = next((r for r in matches if r["verified"]), next((r for r in matches if r["passed"]), matches[-1]))
                    evidence[action] = {"backend": best["backend"], "at": state.now(),
                                        "item_count": best["item_count"], "verified": best["verified"],
                                        "fingerprint": signatures[ch.name], "access": best.get("access")}
                data["checks"][ch.name] = {"at": state.now(), "actions": {**previous, **actions},
                                           "codes": {**{a: code for a, code in old.get("codes", {}).items() if a not in actions}, **failed},
                                           "previous": previous, "scope": "search" if search_only else "all",
                                           "evidence": evidence}
    state.mutate(save_checks)
    return {"ok": bool(results) and all(by_action.values()), "scope": "search" if search_only else "all", "results": results}


def regressed(check: Optional[dict]) -> bool:
    """An action passed in the previous check and fails in the latest one."""
    if not check:
        return False
    previous = check.get("previous", {})
    return any(previous.get(a) and not ok for a, ok in check.get("actions", {}).items())


def channel_status(ch, data: dict) -> dict:
    if not is_added(ch, data):
        return {"status": "not_added", "problems": [], "hint": f"agent-reach add {ch.name}"}
    problems = [f"{t} not installed: run `agent-reach add {ch.name}`" for t in channel_tools(ch) if not tools.present(t)]
    problems += ch.setup_problems()
    if problems:
        return {"status": "needs_setup", "problems": problems}
    check = data["checks"].get(ch.name)
    actions = fresh_actions(ch.name, check)
    query = next((a.name for a in ch.actions if a.name in ("search", "jobs")), None)
    if actions and (check.get("scope") != "search" or query in actions):
        failed = [a for a, ok in actions.items() if not ok]
        if failed:
            codes = check.get("codes", {})
            if all(codes.get(a) == "NEED_LOGIN" for a in failed):
                return {"status": "needs_login", "problems": [f"needs login for: {', '.join(failed)}"],
                        "hint": f"agent-reach login {ch.name}", "checked_at": check["at"]}
            if all(codes.get(a) == "RATE_LIMITED" for a in failed):
                return {"status": "cooldown", "problems": [f"rate limited: {', '.join(failed)}"],
                        "checked_at": check["at"]}
            if all(codes.get(a) == "PLATFORM_BLOCKED" for a in failed):
                return {"status": "needs_user_action", "problems": [f"platform verification: {', '.join(failed)}"],
                        "checked_at": check["at"]}
            return {"status": "broken", "problems": [f"live check failed: {', '.join(failed)}"], "checked_at": check["at"]}
        return {"status": "search_ready" if check.get("scope") == "search" else "ready", "problems": [],
                "checked_at": check["at"], "verified_actions": list(actions)}
    return {"status": "unverified", "problems": [], "hint": f"agent-reach check {ch.name}"}


def doctor() -> dict:
    """Status of every channel from local state only (no network); `check` runs the live tests."""
    data = state.load()
    channels = []
    registered = _channels()
    for ch in registered:
        check = data["checks"].get(ch.name)
        current = fresh_actions(ch.name, check)
        channels.append({"channel": ch.name, "level": ch.level, **channel_status(ch, data),
                         "regressed": regressed({**check, "actions": current}) if check and current else False})
    from .onboarding import capability_summary

    return {"version": __version__, "channels": channels, "tools": tools.recorded(),
            "capability_summary": capability_summary(registered, channels)}


# ── add / remove ──

def _install_channel(ch, *, allow_upgrade: bool = False) -> List[dict]:
    installed = [tools.ensure(t, allow_upgrade=allow_upgrade) for t in channel_tools(ch)]
    if _uses_browser(ch):
        from . import browser
        from .browser_binding import exclusive_browser
        with exclusive_browser():  # setup may restart the browser; let running queries finish first
            browser.setup()
    ch.on_add()
    return installed


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "。")) else text + "."


def _next_step(ch) -> Optional[str]:
    """Tools are prepared; actual access decides whether login is needed."""
    if ch.login_url or ch.login_argv:
        return ("Use existing public tools when they cover the task. "
                f"If access requires login, run agent-reach login {ch.name} "
                "to open the shared dedicated browser or native login flow.")
    return " ".join(_sentence(p) for p in ch.setup_problems()) or None


def add(name: str, *, allow_upgrade: bool = False) -> dict:
    """Install whatever the channel needs (prerequisites included), add it, describe existing-session reuse."""
    ch = _channel(name)
    previously_added = is_added(ch)
    installed = _install_channel(ch, allow_upgrade=allow_upgrade)
    def save_channel(data):
        if not previously_added:
            data.setdefault("session_reuse", {}).pop(name, None)
        data["channels"][name] = {"added_at": state.now()}
        data["removed_defaults"] = [n for n in data["removed_defaults"] if n != name]
    state.mutate(save_channel)
    from .onboarding import capability_summary

    current = {"channel": name, **channel_status(ch, state.load())}
    return {"channel": name, "added": True, "tools": installed, "next": _next_step(ch),
            "capability_summary": capability_summary([ch], [current])}


def _needed_tools(data: dict) -> set:
    added = [c for c in _channels() if is_added(c, data)]
    needed = tools.closure(t for c in added for t in channel_tools(c))
    if any(_uses_browser(c) for c in added):
        needed.add("cloakbrowser")
    return needed


def _prune(data: dict) -> List[str]:
    """Remove our tools no added channel uses."""
    return tools.prune(_needed_tools(data))


def remove(name: str) -> dict:
    """Remove a channel (defaults too) and everything only it used."""
    from . import browser
    from .sessions import clear_session

    ch = _channel(name)
    data = state.load()
    was_added = is_added(ch, data)
    if not was_added:
        return {"channel": name, "removed": False, "removed_tools": [], "cleared_cookies": 0,
                "browser_deleted": False, "warnings": []}
    # Keep the registration and its tools until required login cleanup succeeds.
    cookies = browser.clear_site(site_domains(ch)) if _uses_browser(ch) else 0
    ch.on_remove()
    legacy_profile = state.root() / "sessions" / (name + "-cloak")
    if state.owned_path(legacy_profile) and legacy_profile.exists():
        _remove(legacy_profile)
    if ch.session:
        clear_session(ch.session)
    if ch.logout_keys:
        from agent_reach.config import Config

        cfg = Config()
        for key in ch.logout_keys:
            if cfg.get(key):
                cfg.delete(key)
    def forget(saved):
        saved["channels"].pop(name, None)
        saved.setdefault("session_reuse", {})[name] = {"blocked": True, "at": state.now()}
        saved["checks"].pop(name, None)
        if ch.level == "default" and name not in saved["removed_defaults"]:
            saved["removed_defaults"].append(name)
        for key in ("reuse_sources", "setup_failures", "backend_health", "cooldowns"):
            saved.get(key, {}).pop(name, None)
        saved.setdefault("session_revisions", {})[name] = state.now()
    state.mutate(forget)
    return {"channel": name, "removed": True, "removed_tools": _prune(state.load()),
            "cleared_cookies": cookies, "browser_deleted": False, "warnings": []}


# ── skill (the agent-facing instructions) ──
#
# One real copy in ~/.agents/skills/agent-reach (read natively by Codex, OpenCode,
# Cline, Warp, Zed). AIs that do not read that folder get a symlink in their own
# skills folder, but only when their config folder exists. Source for the folders:
# the vercel-labs/skills supported-agents table.

SKILL_NAME = "agent-reach"


def _openclaw_home() -> Path:
    oc = os.environ.get("OPENCLAW_HOME")
    return (Path(oc) if oc else home_dir()) / ".openclaw"


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else home_dir() / ".config"


def linked_agents() -> Dict[str, tuple]:
    """AIs that need a link: name -> (config folder that proves it is installed, its skills folder)."""
    home = home_dir()
    return {
        "claude-code": (home / ".claude", home / ".claude" / "skills"),
        "openclaw": (_openclaw_home(), _openclaw_home() / "skills"),
        "hermes": (home / ".hermes", home / ".hermes" / "skills"),
        "cursor": (home / ".cursor", home / ".cursor" / "skills"),
        "gemini-cli": (home / ".gemini", home / ".gemini" / "skills"),
        "github-copilot": (home / ".copilot", home / ".copilot" / "skills"),
        "windsurf": (home / ".codeium" / "windsurf", home / ".codeium" / "windsurf" / "skills"),
    }


def native_agents() -> Dict[str, tuple]:
    """AIs that read ~/.agents/skills themselves: name -> (config folder, their own old skills folder)."""
    home = home_dir()
    return {
        "codex": (home / ".codex", home / ".codex" / "skills"),
        "opencode": (_config_home() / "opencode", _config_home() / "opencode" / "skills"),
    }


def skill_dir() -> Path:
    return home_dir() / ".agents" / "skills" / SKILL_NAME


def _skill_lang() -> str:
    for var in ("AGENT_REACH_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "").strip().lower()
        if v.startswith("en"):
            return "en"
    return "zh"


def render_skill(lang: Optional[str] = None) -> str:
    from importlib.resources import files

    lang = lang or _skill_lang()
    template = files("agent_reach").joinpath("skill").joinpath("SKILL_en.md" if lang == "en" else "SKILL.md").read_text("utf-8")
    labels = {"default": "default", "optional": "optional", "experimental": "experimental"}
    rows = ["| channel | level | actions | login |", "|---|---|---|---|"]
    for ch in _channels():
        login = f"`agent-reach login {ch.name}`" if _has_login(ch) else "-"
        if ch.name == "reddit":
            login = "浏览器路径按需" if lang == "zh" else "Browser path only, if required"
        rows.append(f"| {ch.name} | {labels[ch.level]} | {', '.join(a.name for a in ch.actions)} | {login} |")
    return template.replace("{{CHANNEL_TABLE}}", "\n".join(rows)).replace("{{VERSION}}", __version__)


def _is_our_copy(path: Path) -> bool:
    """A real folder holding our SKILL.md (frontmatter `name: agent-reach`)."""
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        lines = (path / "SKILL.md").read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, _, value = line.partition(":")
        if key.strip() == "name":
            return value.strip().strip("'\"") == SKILL_NAME
    return False


def _links_to_real(path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        return Path(os.path.realpath(path)) == Path(os.path.realpath(skill_dir()))
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _write_real_copy(text: str) -> Path:
    real = skill_dir()
    if (real / "SKILL.md").exists() and not _is_our_copy(real):
        raise ReachError(BAD_INPUT, "A different skill already occupies the Reach instruction path; left untouched")
    _write_copy(real, text)
    return real


def _write_copy(target: Path, text: str) -> None:
    from importlib.resources import files

    from agent_reach.utils.paths import atomic_write_private_text, ensure_no_symlink_path
    ensure_no_symlink_path(target, "skill directory")
    target.mkdir(parents=True, exist_ok=True)
    atomic_write_private_text(target / "SKILL.md", text)
    written = [str(target / "SKILL.md")]
    references = target / "references"
    ensure_no_symlink_path(references, "skill references")
    references.mkdir(exist_ok=True)
    for source in files("agent_reach").joinpath("skill").joinpath("references").iterdir():
        if source.is_file() and source.name.endswith(".md"):
            atomic_write_private_text(references / source.name, source.read_text("utf-8"))
            written.append(str(references / source.name))
    state.mutate(lambda data: data["skill"].setdefault("files", {}).update({str(target): written}))


def _link_into(skills_dir: Path, text: str) -> tuple:
    """Make `<skills_dir>/agent-reach` point at the real copy.

    Returns (kind, reason): kind is "link" | "copy" | None (left alone; reason says why).
    Our own old real copy is replaced; anything else already there is left untouched.
    """
    target = skills_dir / SKILL_NAME
    if _links_to_real(target):
        return "link", None
    if target.is_symlink():
        return None, f"a symlink to {os.readlink(target)} is already there"
    if target.exists():
        if not _is_our_copy(target):
            return None, "a different skill named agent-reach is already there"
        _write_copy(target, text)
        return "copy", None
    skills_dir.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(skill_dir(), target_is_directory=True)
        return "link", None
    except (OSError, NotImplementedError):
        # Windows without symlink rights: fall back to a copy that update refreshes.
        _write_copy(target, text)
        return "copy", None


def _agent_for(skills_dir: Path) -> str:
    return next((name for name, (_, d) in linked_agents().items() if d == skills_dir), "custom")


def place_skill() -> dict:
    """Write the real copy, link every detected AI, refresh recorded links/copies."""
    text = render_skill()
    _write_real_copy(text)
    data = state.load()
    targets: Dict[Path, str] = {}
    for name, (config, skills) in linked_agents().items():
        if config.is_dir():
            targets[skills] = name
    for rec in data["skill"]["links"]:
        parent = Path(rec["path"]).parent
        if parent.is_dir():
            targets.setdefault(parent, rec.get("agent", "custom"))
    links, not_linked = [], []
    for skills, agent in targets.items():
        target = skills / SKILL_NAME
        kind, reason = _link_into(skills, text)
        if kind:
            links.append({"agent": agent, "path": str(target), "kind": kind})
        else:
            not_linked.append({"agent": agent, "path": str(target), "reason": reason})
    state.mutate(lambda saved: saved["skill"].update(links=links))
    return {**skill_status(), "not_linked": not_linked, "removed_old_copies": []}


def skill_status() -> dict:
    real = skill_dir()
    recorded = state.load()["skill"]["links"]
    links = [r for r in recorded
             if _links_to_real(Path(r["path"])) or (r["kind"] == "copy" and _is_our_copy(Path(r["path"])))]
    installed = (real / "SKILL.md").is_file()
    agents = []
    if installed:
        agents = [name for name, (config, _) in native_agents().items() if config.is_dir()]
        agents += [r["agent"] for r in links if r["agent"] not in agents and r["agent"] != "custom"]
    return {"path": str(real / "SKILL.md"), "installed": installed, "agents": agents,
            "links": [r["path"] for r in links if r["kind"] == "link"],
            "copies": [r["path"] for r in links if r["kind"] == "copy"]}


def link_skill(skills_dir: str) -> dict:
    """Link the skill into the skills folder of an AI that is not in the table."""
    target_dir = Path(skills_dir).expanduser()
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    if target_dir.name == SKILL_NAME:
        raise ReachError(BAD_INPUT, f"give the skills folder, not the {SKILL_NAME} folder inside it",
                         hint=f"agent-reach skill link {target_dir.parent}")
    if os.path.realpath(target_dir) == os.path.realpath(skill_dir().parent):
        return skill_status()
    text = render_skill()
    if not (skill_dir() / "SKILL.md").is_file():
        _write_real_copy(text)
    kind, reason = _link_into(target_dir, text)
    if kind is None:
        raise ReachError(BAD_INPUT, f"{target_dir / SKILL_NAME}: {reason}; left it untouched",
                         hint="Ask the user to move it away, then run this again.")
    data = state.load()
    path = str(target_dir / SKILL_NAME)
    data["skill"]["links"] = [r for r in data["skill"]["links"] if r["path"] != path]
    data["skill"]["links"].append({"agent": _agent_for(target_dir), "path": path, "kind": kind})
    state.save(data)
    return skill_status()


def _skill_uninstall_targets() -> List[Path]:
    """Only recorded files and still-matching shortcuts; preserve user additions."""
    data = state.load()["skill"]
    found = []
    for rec in data["links"]:
        path = Path(rec["path"])
        if rec["kind"] == "link" and _links_to_real(path):
            found.append(path)
    for folder, files in data.get("files", {}).items():
        base = Path(folder)
        if base.is_symlink():
            continue
        for name in files:
            path = Path(name)
            if path.is_relative_to(base) and not any(p.is_symlink() for p in path.parents if p != base.parent):
                found.append(path)
    return list(dict.fromkeys(found))


# ── setup / migrate ──

#: 1.5 config keys and CLI tools that show which channels the user relied on.
_LEGACY_KEYS = {"twitter_auth_token": "twitter", "twitter_ct0": "twitter", "xueqiu_cookie": "xueqiu",
                "xhs_cookie": "xiaohongshu"}
_LEGACY_COMMANDS = {"twitter": "twitter", "xhs": "xiaohongshu", "opencli": "xiaohongshu", "rdt": "reddit",
                    "bili": "bilibili", "boss": "boss"}
#: 1.5 channels that 1.6 no longer has; the report says what replaces them.
RETIRED_CHANNELS = ("rss", "exa_search")


def migrate() -> dict:
    """First run after an older Agent Reach: create state, keep credentials, suggest channels.

    The result is kept in state so the first install report can explain the upgrade even
    when another process (the new uv copy) renders it.
    """
    from agent_reach.config import Config

    cfg = Config(read_only=True)
    hints = {ch for key, ch in _LEGACY_KEYS.items() if cfg.get(key)}
    hints |= {ch for cmd, ch in _LEGACY_COMMANDS.items() if shutil.which(cmd)}
    defaults = {c.name for c in _channels() if c.level == "default"}
    result = {
        "migrated": True,
        "kept": "~/.agent-reach/config.yaml (keys and cookies unchanged)",
        "suggested_channels": sorted(hints - defaults),
        "retired_channels": list(RETIRED_CHANNELS),
        "note": "Your own global tools were not removed. Browser login must be completed by the user in the Reach dedicated window.",
    }
    data = state.load()
    data["migrated_from"] = "1.5"
    data["migration"] = result
    state.save(data)
    return result


def _cleanup_old_copies() -> dict:
    """From the uv install, remove 1.5 copies (pipx / ~/.agent-reach-venv) so they cannot shadow it."""
    if install_method() != "uv":
        return {"removed": [], "failed": []}
    from . import legacy
    return legacy.remove()


def _old_copy_actions(old: dict) -> List[str]:
    from . import legacy
    return [f"An old Agent Reach copy could not be removed ({i['path']}); run `{legacy.manual_command(i)}`."
            for i in old["failed"]]


def _optional_entry(c) -> dict:
    """What the user must do for an optional channel; installs happen by themselves."""
    needs = (["login_if_required"] if (c.login_url or c.login_argv) else []) + ([c.needs_key] if c.needs_key else [])
    return {"channel": c.name, "level": c.level, "add": f"agent-reach add {c.name}", "needs": needs}


def setup() -> dict:
    """Add the default channels (except ones the user removed) and place the skill."""
    if not state.exists() and (state.root() / "config.yaml").exists():
        migrate()
    if not state.exists():
        state.save(state.load())
    saved_migration = state.load()
    migration = None if saved_migration.get("migration_reported") else saved_migration.get("migration")
    old_copies = _cleanup_old_copies()
    user_actions = _retired_mcp_notice() + _old_copy_actions(old_copies)
    if state.load()["tools"].get("mcporter", {}).get("owner") == tools.OURS:
        tools.remove_private("mcporter")  # retired LinkedIn MCP transport, only our private copy
    state.mutate(lambda saved: [saved.pop(key, None) for key in ("reuse_sources", "ask_pending", "pending")])
    skill = place_skill()
    data = state.load()
    defaults = [c for c in _channels() if c.level == "default" and is_added(c, data)]
    added = []
    for ch in defaults:
        try:
            added.append({"channel": ch.name, "ok": True, "tools": _install_channel(ch)})
        except ReachError as err:
            added.append({"channel": ch.name, "ok": False, "tools": [],
                          "error": {"code": err.code, "message": err.message, "hint": err.hint}})
    optional = [_optional_entry(c) for c in _channels() if not is_added(c, data)]
    from .onboarding import capability_summary, installation_report

    registered = _channels()
    current = [{"channel": c.name, **channel_status(c, state.load())} for c in registered]
    result = {
        "version": __version__,
        "user_actions": user_actions,
        "default_channels": added,
        "skill": skill,
        "optional_channels": optional,
        "logins": [{"channel": c.name, "command": f"agent-reach login {c.name}",
                    "when": "only_if_required"} for c in defaults if _has_login(c)],
        "capability_summary": capability_summary(registered, current),
        "migration": migration,
        "old_copies": old_copies,
    }
    from agent_reach.utils.paths import PrivatePathError, atomic_write_private_text

    markdown = installation_report(result)
    report = {"markdown": markdown, "path": None}
    try:
        state.remember_path(state.root() / "installation-report.md", "installation receipt")
        report["path"] = str(atomic_write_private_text(state.root() / "installation-report.md", markdown))
    except (OSError, PrivatePathError):
        # The receipt remains in stdout even if its local copy cannot be saved.
        report["write_error"] = "安装报告未能保存；完整表格仍在 installation_report.markdown。"
    result["installation_report"] = report
    if migration:
        state.mutate(lambda saved: saved.__setitem__("migration_reported", True))
    return result


def _retired_mcp_notice() -> list:
    """Read the old ledger only; never edit another application's configuration."""
    if state.load().get("mcp"):
        return ["An older Reach build registered an MCP server. Remove the agent-reach entry in your AI application's MCP settings; Reach no longer edits those settings."]
    return []


# ── update ──

def update_check() -> dict:
    """Live check of the latest release; also refreshes the background notice cache."""
    try:
        rel = update_notice.fetch_latest(timeout=15)
    except Exception as exc:  # noqa: BLE001
        raise ReachError(UPSTREAM_BROKEN, f"could not reach GitHub: {exc}") from None
    try:
        update_notice.write_cache(rel)
    except OSError:
        pass
    return {
        "current": __version__,
        "latest": rel["latest"],
        "update_available": update_notice.version_tuple(rel["latest"]) > update_notice.version_tuple(__version__),
        "notes": rel["notes"],
    }


def install_method() -> str:
    """How this copy of Agent Reach was installed: uv | editable | other."""
    try:
        from importlib.metadata import distribution

        direct = distribution("agent-reach").read_text("direct_url.json") or "{}"
        if json.loads(direct).get("dir_info", {}).get("editable"):
            return "editable"
    except Exception:  # noqa: BLE001
        pass
    if (Path(sys.prefix) / "uv-receipt.toml").is_file():
        return "uv"
    return "other"


def _source(version: str) -> str:
    return f"https://github.com/{REPO}/archive/refs/tags/v{version}.zip"


def upgrade_command(version: str) -> List[str]:
    return ["uv", "tool", "install", "--force", _source(version)]


UNINSTALL_PROGRAM = "uv tool uninstall agent-reach"


def _ordered_tools(names) -> List[str]:
    """Tools plus what they need, dependencies first, each once."""
    out: List[str] = []

    def visit(n: str) -> None:
        if n in out or n not in tools.TOOLS:
            return
        for d in tools.TOOLS[n].needs:
            visit(d)
        out.append(n)

    for n in names:
        visit(n)
    return out


def sync() -> dict:
    """Bring every added channel's tools to their latest allowed version, prune unused
    tools, drop channels this version no longer has, refresh the skill.

    `user_actions` are plain sentences for what the user must do now.
    """
    migration = migrate() if not state.exists() else None
    data = state.load()
    known = {c.name for c in _channels()}
    dropped = sorted(set(data["channels"]) - known)
    for n in dropped:
        data["channels"].pop(n, None)
        data["checks"].pop(n, None)
    data["removed_defaults"] = [n for n in data["removed_defaults"] if n in known]
    state.save(data)
    actions = [f"The {n} channel is no longer part of Agent Reach and was removed." for n in dropped]
    added = [c for c in _channels() if is_added(c, data)]
    synced, problems, failed = [], [], set()
    for t in _ordered_tools(t for c in added for t in channel_tools(c)):
        try:
            synced.append(tools.ensure(t, upgrade=True))
        except ReachError as err:
            failed.add(t)
            problems.append({"tool": t, "code": err.code, "message": err.message, "hint": err.hint})
    for c in added:
        bad = [t for t in channel_tools(c) if t in failed]
        if bad:
            hint = next((p["hint"] for p in problems if p["tool"] in bad and p.get("hint")), None)
            actions.append(_sentence(f"{c.name} could not update {', '.join(bad)}" + (f": {hint}" if hint else "")))
            continue
        try:
            c.on_add()
        except ReachError as err:
            actions.append(_sentence(f"{c.name}: {err.hint or err.message}"))
        actions += [_sentence(f"{c.name}: {p}") for p in c.setup_problems()]
        check = data["checks"].get(c.name) or {}
        previous = check.get("previous") or {}
        expired = [a for a, code in (check.get("codes") or {}).items() if code == "NEED_LOGIN" and previous.get(a)]
        if expired:
            actions.append(f"The user needs to log in to {c.name} again: run `agent-reach login {c.name}`.")
    old_copies = _cleanup_old_copies()
    actions += _old_copy_actions(old_copies)
    return {"version": __version__, "tools": synced, "problems": problems, "removed_tools": _prune(state.load()),
            "dropped_channels": dropped, "user_actions": actions, "skill": place_skill(), "migration": migration,
            "old_copies": old_copies}


def _move_to_uv(info: dict) -> dict:
    """This copy was installed with pip/pipx (1.5 style). Install the release with uv, let the
    new copy set itself up (it removes known old copies), then remove this copy too."""
    fresh = not state.exists()
    if fresh and (state.root() / "config.yaml").exists():
        migrate()  # recorded in state; the new copy's install report explains the upgrade
    uv = tools.resolve("uv")
    if not uv:
        tools.ensure("uv")
        uv = tools.resolve("uv")
    if not uv:
        raise ReachError(NEED_SETUP, "uv could not be installed",
                         hint="Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    newest = update_notice.version_tuple(info["latest"]) >= update_notice.version_tuple(__version__)
    cmd = upgrade_command(info["latest"] if newest else __version__)
    proc = subprocess.run([uv, *cmd[1:]], capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        raise ReachError(UPSTREAM_BROKEN, f"upgrade failed: {proc.stderr.strip()[-300:]}",
                         hint=f"Run manually: {' '.join(cmd)}")
    bin_dir = subprocess.run([uv, "tool", "dir", "--bin"], capture_output=True, text=True, timeout=60).stdout.strip()
    exe = Path(bin_dir) / ("agent-reach.exe" if os.name == "nt" else "agent-reach")
    child = [str(exe), "setup"] if fresh else [str(exe), "update", "--sync-only"]
    out = subprocess.run(child, capture_output=True, text=True, timeout=1800)
    try:
        result = json.loads(out.stdout.strip().split("\n")[-1]).get("result") or {}
    except (ValueError, IndexError):
        result = {"raw": out.stdout[-500:]}
    actions = list(result.get("user_actions") or [])
    package = Path(__file__).resolve().parents[1]
    if package.exists():  # a copy the new one does not know about (pip --user, conda, ...)
        gone = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "agent-reach"],
                              capture_output=True, timeout=120).returncode == 0
        if not gone:
            actions.append(f"Remove the old Agent Reach copy: `{sys.executable} -m pip uninstall agent-reach`.")
    found = shutil.which("agent-reach")
    if not found or os.path.realpath(found) != os.path.realpath(exe):
        actions.append("Open a new terminal so `agent-reach` runs the new version; if it still does not, "
                       f"run `{uv} tool update-shell`.")
    return {**info, "upgraded": True, "method": "moved_to_uv", "sync": result,
            "installation_report": result.get("installation_report"), "user_actions": actions}


def update(check_only: bool = False) -> dict:
    """Upgrade Agent Reach when a release is newer, then upgrade every added channel's tools."""
    info = update_check()
    if check_only:
        return info
    method = install_method()
    if method == "other":
        return _move_to_uv(info)
    if info["update_available"] and method != "editable":
        cmd = upgrade_command(info["latest"])
        run = [tools.resolve("uv") or cmd[0], *cmd[1:]]
        try:
            proc = subprocess.run(run, capture_output=True, text=True, timeout=900)
        except FileNotFoundError:
            raise ReachError(NEED_SETUP, "uv is not on PATH",
                             hint="Install uv: https://docs.astral.sh/uv/getting-started/installation/") from None
        if proc.returncode != 0:
            raise ReachError(UPSTREAM_BROKEN, f"upgrade failed: {proc.stderr.strip()[-300:]}",
                             hint=f"Run manually: {' '.join(cmd)}")
        exe = shutil.which("agent-reach") or sys.argv[0]
        out = subprocess.run([exe, "update", "--sync-only"], capture_output=True, text=True, timeout=1800)
        try:
            synced = json.loads(out.stdout.strip().split("\n")[-1]).get("result") or {}
        except (ValueError, IndexError):
            synced = {"raw": out.stdout[-500:]}
        return {**info, "upgraded": True, "method": method, "sync": synced,
                "user_actions": synced.get("user_actions", [])}
    synced = sync()
    return {**info, "upgraded": False, "method": method, "sync": synced, "user_actions": synced["user_actions"]}


# ── uninstall ──


def uninstall(dry_run: bool = False) -> dict:
    from . import browser

    root = state.root()
    targets = _skill_uninstall_targets()  # before state.json goes: it records the links
    data = state.load()
    for name in data.get("owned_paths", {}):
        path = root / name
        if name and ".." not in Path(name).parts and path.is_relative_to(root) and not Path(name).is_absolute():
            targets.append(path)
    targets += [tools.tool_dir(n) for n, entry in data["tools"].items()
                if entry.get("owner") == tools.OURS and entry.get("scope") == "private"
                and tools._SAFE_NAME.fullmatch(n)]
    targets = [t for t in targets if t.exists() or t.is_symlink()]
    globals_ = tools.uninstall_global_owned(dry_run=True)
    if not dry_run:
        if state.owned_path(browser.browser_root()) or browser._load_state().get("backend"):
            if not browser.stop():
                raise ReachError(UPSTREAM_BROKEN, "The dedicated browser could not close; uninstall stopped before deleting its files")
        tools.uninstall_global_owned(dry_run=False)
        # Children first; directory entries do not authorize deleting unrecorded siblings.
        for t in sorted(set(targets), key=lambda p: len(p.parts), reverse=True):
            from agent_reach.utils.paths import ensure_no_symlink_path
            ensure_no_symlink_path(t.parent, "uninstall parent")
            _remove(t)
        for folder in data.get("skill", {}).get("files", {}):
            for directory in (Path(folder) / "references", Path(folder)):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        for d in (root / "tools", root):
            try:
                d.rmdir()
            except OSError:
                pass
    removing = {str(t) for t in targets} | {str(root / "tools")}
    kept = sorted(str(p) for p in root.iterdir() if str(p) not in removing) if root.exists() else []
    return {"dry_run": dry_run, "removed": [str(t) for t in targets], "global_tools_removed": globals_,
            "kept_unrecognized": kept, "remove_program": UNINSTALL_PROGRAM}


# ── configure ──

CONFIG_KEYS = {"groq-key": "groq_api_key", "openai-key": "openai_api_key", "proxy": "proxy", "github-token": "github_token",
}


def configure(key: str, value: str) -> dict:
    from agent_reach.config import Config

    if key not in CONFIG_KEYS:
        raise ReachError(BAD_INPUT, f"unknown key: {key}; valid: {', '.join(CONFIG_KEYS)}")
    if not value:
        raise ReachError(BAD_INPUT, "empty value")
    Config().set(CONFIG_KEYS[key], value)
    return {"key": key, "saved": True}
