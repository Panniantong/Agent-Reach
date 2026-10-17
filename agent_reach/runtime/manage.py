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
from pathlib import Path
from typing import Any, Dict, List, Optional
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


def uses_cloak(ch) -> bool:
    """Derive the primary browser backend from the channel's action declarations."""
    return any(a.backends and a.backends[0][0] == "cloakbrowser" for a in ch.actions)


def fingerprint(channel: str) -> str:
    """Invalidate checks when this build, channel dependencies, source, or network changes."""
    from agent_reach.config import Config

    from .browser_binding import profile_for

    data = state.load()
    cfg = Config(read_only=True)
    ch = _channel(channel)
    relevant = set(ch.prereqs) | set(ch.tools) | set(channel_tools(ch))
    relevant.update(name for action in ch.actions for name, _ in action.backends)
    value = [__version__, channel, profile_for(channel),
             os.environ.get("REACH_CLOAK_PROXY") or cfg.get("proxy"),
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
            and (check.get("codes", {}).get(name) != "RATE_LIMITED"
                 or state.age_seconds(evidence[name].get("at")) < 3600)}


def fresh_check(channel: str, check: Optional[dict]) -> bool:
    return bool(fresh_actions(channel, check))


def channel_tools(ch) -> List[str]:
    """Everything `add` installs for the channel, prerequisites first."""
    if uses_cloak(ch):
        return ["cloakbrowser"]
    names = list(ch.prereqs) + (["chrome"] if _uses_browser(ch) else []) + list(ch.tools)
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
                    "elapsed_ms": out["meta"]["elapsed_ms"],
                    "error": err and {"code": err["code"], "message": err["message"]},
                    "item_count": len(out["items"]), "attempts": out["meta"]["attempts"],
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
                previous = data["checks"].get(ch.name, {}).get("actions", {})
                evidence = {r["action"]: {"backend": r["backend"], "at": state.now(),
                                           "item_count": r["item_count"], "fingerprint": signatures[ch.name]}
                            for r in results if r["channel"] == ch.name}
                data["checks"][ch.name] = {"at": state.now(), "actions": actions, "codes": failed,
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
    if uses_cloak(ch):
        from agent_reach.backends.cloak import status
        backend = status(ch.name)
        from .browser_binding import profile_for
        fallbacks = [{"backend": "opencli", "installed": tools.present("opencli"),
                      "configured": bool(profile_for(ch.name)), "logged_in": None}]
        if ch.name == "boss":
            fallbacks.append({"backend": "boss-agent-cli", "installed": tools.present("boss-agent-cli"),
                              "configured": None, "logged_in": None})
        available = (backend["installed"] and backend["configured"] or
                     any(b["installed"] and b["configured"] for b in fallbacks))
        result: dict[str, Any] = {"status": "unverified" if available else "needs_setup",
                "problems": [] if available else ["No configured channel backend"],
                "backends": [backend, *fallbacks],
                "hint": f"agent-reach cloak status {ch.name}; agent-reach check {ch.name} --search"}
        check = data["checks"].get(ch.name)
        actions = fresh_actions(ch.name, check)
        query = next((a.name for a in ch.actions if a.name in ("search", "jobs")), None)
        if result["status"] == "unverified" and query in actions:
            failed = [a for a, ok in actions.items() if not ok]
            result.update(checked_at=check["at"], verified_actions=[a for a, ok in actions.items() if ok])
            codes = [check.get("codes", {}).get(a) for a in failed]
            result["status"] = ("needs_login" if codes and all(c == "NEED_LOGIN" for c in codes)
                                else "cooldown" if codes and all(c == "RATE_LIMITED" for c in codes)
                                else "needs_user_action" if codes and all(c == "PLATFORM_BLOCKED" for c in codes)
                                else "broken" if failed else "search_ready" if check.get("scope") == "search" else "ready")
        failures = (data.get("setup_failures", {}).get(ch.name, {}),
                    data.get("cooldowns", {}).get(ch.name, {}))
        for failure in sorted(failures, key=lambda item: item.get("at", "")):
            age = state.age_seconds(failure.get("at"))
            ttl = 3600 if failure.get("code") == "RATE_LIMITED" else 600
            if (failure.get("code") in {"RATE_LIMITED", "UPSTREAM_BROKEN"} and age < ttl
                    and (not check or check.get("at", "") <= failure["at"])):
                result = {**result,
                          "status": "cooldown" if failure["code"] == "RATE_LIMITED" else "broken",
                          "problems": [failure.get("message") or "Channel setup failed"],
                          "retry_after_seconds": max(0, int(ttl - age))}
        return result
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
    for ch in _channels():
        check = data["checks"].get(ch.name)
        current = fresh_actions(ch.name, check)
        channels.append({"channel": ch.name, "level": ch.level, **channel_status(ch, data),
                         "regressed": regressed({**check, "actions": current}) if check and current else False})
    return {"version": __version__, "channels": channels, "tools": tools.recorded()}


# ── add / remove ──

def _install_channel(ch, *, allow_upgrade: bool = False) -> List[dict]:
    if uses_cloak(ch):
        from agent_reach.backends.cloak import setup
        return [setup()]
    installed = [tools.ensure(t, allow_upgrade=allow_upgrade) for t in channel_tools(ch)]
    ch.on_add()
    return installed


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "。")) else text + "."


def _next_step(ch) -> Optional[str]:
    """Installation never opens a browser or assumes an existing session expired."""
    if uses_cloak(ch):
        return (f"Run agent-reach ensure {ch.name} to reuse an authorized existing session. "
                f"If login is needed, use agent-reach cloak login {ch.name} and continue with ensure.")
    if ch.login_url or ch.login_argv:
        return f"Reuse existing login first: agent-reach login {ch.name}. This inspects connection options without opening a browser."
    return " ".join(_sentence(p) for p in ch.setup_problems()) or None


def add(name: str, *, allow_upgrade: bool = False) -> dict:
    """Install whatever the channel needs (prerequisites included), add it, describe existing-session reuse."""
    ch = _channel(name)
    installed = _install_channel(ch, allow_upgrade=allow_upgrade)
    def save_channel(data):
        data["channels"][name] = {"added_at": state.now()}
        data["removed_defaults"] = [n for n in data["removed_defaults"] if n != name]
    state.mutate(save_channel)
    return {"channel": name, "added": True, "tools": installed, "next": _next_step(ch)}


def _needed_tools(data: dict) -> set:
    return tools.closure(t for c in _channels() if is_added(c, data)
                         for t in (channel_tools(c) + (list(c.tools) + list(c.prereqs) if uses_cloak(c) else [])))


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
    data["channels"].pop(name, None)
    data["checks"].pop(name, None)
    if ch.level == "default" and name not in data["removed_defaults"]:
        data["removed_defaults"].append(name)
    state.save(data)
    ch.on_remove()
    if ch.session:
        clear_session(ch.session)
    if ch.logout_keys:
        from agent_reach.config import Config

        cfg = Config()
        for key in ch.logout_keys:
            if cfg.get(key):
                cfg.delete(key)
    cookies, browser_deleted, warnings = 0, False, []
    from .browser_binding import profile_for, unbind_profile
    existing = ch.name == "boss" or ("opencli" in ch.tools and profile_for(ch.name) != "dedicated")
    if "opencli" in ch.tools:
        unbind_profile(ch.name)
    if _uses_browser(ch) and not existing:
        others = [c for c in _channels() if c.name != name and _uses_browser(c) and is_added(c, data)]
        try:
            if others:
                if browser.profile_dir().is_dir():
                    cookies = browser.clear_site(site_domains(ch))
            else:
                browser_deleted = browser.delete_profile()
        except ReachError as err:
            warnings.append(err.message)
    return {"channel": name, "removed": was_added, "removed_tools": _prune(data),
            "cleared_cookies": cookies, "browser_deleted": browser_deleted, "warnings": warnings}


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
    _remove(real)  # old instructions are replaced, not merged
    _write_copy(real, text)
    return real


def _write_copy(target: Path, text: str) -> None:
    from importlib.resources import files

    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(text, encoding="utf-8")
    references = target / "references"
    references.mkdir(exist_ok=True)
    for source in files("agent_reach").joinpath("skill").joinpath("references").iterdir():
        if source.is_file() and source.name.endswith(".md"):
            (references / source.name).write_text(source.read_text("utf-8"), encoding="utf-8")


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
        shutil.rmtree(target)
    skills_dir.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(skill_dir(), target_is_directory=True)
        return "link", None
    except (OSError, NotImplementedError):
        # Windows without symlink rights: fall back to a copy that update refreshes.
        _write_copy(target, text)
        return "copy", None


def _remove_native_old_copies() -> List[str]:
    """Our old real copies in folders of AIs that now read ~/.agents/skills (so they don't see two)."""
    removed = []
    for _, skills in native_agents().values():
        target = skills / SKILL_NAME
        if _is_our_copy(target):
            shutil.rmtree(target)
            removed.append(str(target))
    return removed


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
    data["skill"]["links"] = links
    state.save(data)
    return {**skill_status(), "not_linked": not_linked, "removed_old_copies": _remove_native_old_copies()}


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
    """Real copy, recorded links/copies, and our links/old copies in every known skills folder."""
    found: List[Path] = []
    for rec in state.load()["skill"]["links"]:
        p = Path(rec["path"])
        if _links_to_real(p) or _is_our_copy(p):
            found.append(p)
    known = [skills for _, skills in linked_agents().values()] + [skills for _, skills in native_agents().values()]
    for skills in known:
        p = skills / SKILL_NAME
        if _links_to_real(p) or _is_our_copy(p):
            found.append(p)
    real = skill_dir()
    if real.exists() or real.is_symlink():
        found.append(real)
    return list(dict.fromkeys(found))


# ── setup / migrate ──

def migrate() -> dict:
    """First run after an older Agent Reach: create state, keep credentials, suggest channels."""
    from agent_reach.config import Config

    cfg = Config(read_only=True)
    hints = []
    for cmd, channel in (("bili", "bilibili"), ("opencli", "xiaohongshu"), ("boss", "boss"), ("mcporter", "linkedin")):
        if shutil.which(cmd):
            hints.append(channel)
    if cfg.get("xueqiu_cookie"):
        hints.append("xueqiu")
    defaults = {c.name for c in _channels() if c.level == "default"}
    data = state.load()
    data["migrated_from"] = "1.5"
    state.save(data)
    return {
        "migrated": True,
        "kept": "~/.agent-reach/config.yaml (keys and cookies unchanged)",
        "suggested_channels": sorted(set(hints) - defaults),
        "note": "Your own global tools were not removed. Old logins can be copied with `agent-reach login <channel> --import-existing`.",
    }


def _optional_entry(c) -> dict:
    """What the user must do for an optional channel; installs happen by themselves."""
    needs = (["login"] if (c.login_url or c.login_argv) else []) + ([c.needs_key] if c.needs_key else [])
    return {"channel": c.name, "level": c.level, "add": f"agent-reach add {c.name}", "needs": needs}


def setup() -> dict:
    """Add the default channels (except ones the user removed) and place the skill."""
    migration = migrate() if not state.exists() and (state.root() / "config.yaml").exists() else None
    if not state.exists():
        state.save(state.load())
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
    mcp = None
    if (home_dir() / ".cursor").is_dir():
        from . import mcp_registration

        try:
            mcp = mcp_registration.install()
        except ReachError as err:
            mcp = {"agent": "cursor", "installed": False, "reason": err.message}
    return {
        "version": __version__,
        "default_channels": added,
        "skill": skill,
        "optional_channels": optional,
        "logins": [{"channel": c.name, "command": f"agent-reach login {c.name}"} for c in defaults if _has_login(c)],
        "migration": migration,
        "mcp": mcp,
    }


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
    return {"version": __version__, "tools": synced, "problems": problems, "removed_tools": _prune(state.load()),
            "dropped_channels": dropped, "user_actions": actions, "skill": place_skill(), "migration": migration}


def update(check_only: bool = False) -> dict:
    """Upgrade Agent Reach when a release is newer, then upgrade every added channel's tools."""
    info = update_check()
    if check_only:
        return info
    method = install_method()
    if info["update_available"] and method != "editable":
        cmd = upgrade_command(info["latest"])
        if method != "uv":
            raise ReachError(
                NEED_SETUP, "this copy of Agent Reach was not installed with uv, so it cannot update itself",
                hint=f"Reinstall once with uv: `{' '.join(cmd)}`, then remove the old copy "
                     "(e.g. `pipx uninstall agent-reach` or `pip uninstall agent-reach`).",
            )
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
            synced = json.loads(out.stdout.strip().splitlines()[-1]).get("result") or {}
        except (ValueError, IndexError):
            synced = {"raw": out.stdout[-500:]}
        return {**info, "upgraded": True, "method": method, "sync": synced,
                "user_actions": synced.get("user_actions", [])}
    synced = sync()
    return {**info, "upgraded": False, "method": method, "sync": synced, "user_actions": synced["user_actions"]}


# ── uninstall ──

_OWNED = ("config.yaml", "state.json", "mcporter.json", "sessions", "browser",
          "update-check.json", "update-check.started")


def uninstall(dry_run: bool = False) -> dict:
    from . import browser, mcp_registration

    root = state.root()
    mcp = mcp_registration.uninstall(dry_run=dry_run)
    targets = _skill_uninstall_targets()  # before state.json goes: it records the links
    targets += [root / n for n in _OWNED]
    targets += [tools.tool_dir(n) for n in tools.TOOLS] + [tools.npm_global_dir(), root / "tools" / "xiaoyuzhou"]
    targets = [t for t in targets if t.exists() or t.is_symlink()]
    globals_ = tools.uninstall_global_owned(dry_run=True)
    if not dry_run:
        browser.stop()
        tools.uninstall_global_owned(dry_run=False)
        for t in targets:
            _remove(t)
        for d in (root / "tools", root):
            try:
                d.rmdir()
            except OSError:
                pass
    removing = {str(t) for t in targets} | {str(root / "tools")}
    kept = sorted(str(p) for p in root.iterdir() if str(p) not in removing) if root.exists() else []
    return {"dry_run": dry_run, "removed": [str(t) for t in targets], "global_tools_removed": globals_,
            "kept_unrecognized": kept, "remove_program": UNINSTALL_PROGRAM, "mcp": mcp}


# ── configure ──

CONFIG_KEYS = {"groq-key": "groq_api_key", "openai-key": "openai_api_key", "proxy": "proxy", "github-token": "github_token",
               "model-key": "model_api_key", "model-base-url": "model_base_url", "model-name": "model_name"}


def configure(key: str, value: str) -> dict:
    from agent_reach.config import Config

    if key not in CONFIG_KEYS:
        raise ReachError(BAD_INPUT, f"unknown key: {key}; valid: {', '.join(CONFIG_KEYS)}")
    if not value:
        raise ReachError(BAD_INPUT, "empty value")
    Config().set(CONFIG_KEYS[key], value)
    return {"key": key, "saved": True}
