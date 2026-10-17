"""Resumable setup and execution shared by CLI and MCP.

The caller selects a channel and action. Reach handles its declared primary
backend, remembers an explicitly authorized login source, and records a real
query result. No password, cookie, or browser database is exposed here.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from . import manage, state, tools
from .browser_binding import execution_lock, profile_for
from .dispatch import find_action, run_action
from .result import BAD_INPUT, NEED_LOGIN, NEED_SETUP, PLATFORM_BLOCKED, RATE_LIMITED, ReachError


def _action(ch, name: Optional[str]):
    action = find_action(ch, name) if name else next(
        (a for a in ch.actions if a.name in ("search", "jobs")), ch.actions[0] if ch.actions else None
    )
    if action is None:
        raise ReachError(BAD_INPUT, f"{ch.name} has no action named {name}")
    return action


def _needs(channel: str, action: str, kind: str, message: str, **extra) -> dict:
    return {"ok": False, "status": "needs_user_action", "channel": channel, "action": action,
            "required_action": {"type": kind, "message": message, **extra}}


def _opencli_ready(channel: str, selected) -> bool:
    if not any(label == "opencli" for label, _ in selected.backends) or not tools.present("opencli"):
        return False
    from .onboarding import profiles

    source = profile_for(channel)
    return bool(source and source in {p["id"] for p in profiles()["profiles"]})


def _record(channel: str, action: str, out: dict) -> None:
    stamp = state.now()
    signature = manage.fingerprint(channel)
    def change(data):
        old = data["checks"].get(channel, {})
        actions = dict(old.get("actions", {}))
        actions[action] = bool(out["ok"] and out["items"])
        codes = dict(old.get("codes", {}))
        if actions[action]:
            codes.pop(action, None)
        else:
            codes[action] = (out.get("error") or {}).get("code", "EMPTY")
        evidence = dict(old.get("evidence", {}))
        evidence[action] = {"backend": out.get("backend"), "at": stamp,
                            "item_count": len(out["items"]), "fingerprint": signature}
        data["checks"][channel] = {"at": stamp, "actions": actions, "codes": codes,
                                     "previous": old.get("actions", {}), "scope": "search",
                                     "evidence": evidence}
        if codes.get(action) == RATE_LIMITED:
            data.setdefault("cooldowns", {})[channel] = {
                "code": RATE_LIMITED, "message": (out.get("error") or {}).get("message"), "at": stamp}
        elif actions[action]:
            data.setdefault("cooldowns", {}).pop(channel, None)
    state.mutate(change)


def prepare(channel: str, *, action: Optional[str] = None, source_profile: Optional[str] = None,
            install: bool = True) -> dict:
    """Idempotent local setup. A missing login always returns an explicit user step."""
    ch = manage._channel(channel)
    selected = _action(ch, action)
    primary = selected.backends[0][0] if selected.backends else None
    if not primary:
        raise ReachError(NEED_SETUP, f"{channel} {selected.name} has no backend")

    with execution_lock("prepare:" + channel):
        data = state.load()
        if source_profile:
            if primary != "cloakbrowser":
                raise ReachError(BAD_INPUT, "--reuse-profile applies to a CloakBrowser action")
            # An explicit flag grants only this site's import from this source.
            state.mutate(lambda saved: saved.setdefault("reuse_sources", {}).__setitem__(
                channel, {"profile": source_profile, "granted_at": state.now(), "scope": channel}))
            data = state.load()
        for failure in (data.get("setup_failures", {}).get(channel, {}),
                        data.get("cooldowns", {}).get(channel, {})):
            age = state.age_seconds(failure.get("at"))
            if failure.get("code") == RATE_LIMITED and age < 3600:
                return {"ok": False, "status": "cooldown", "channel": channel,
                        "action": selected.name, "retry_after_seconds": max(0, int(3600 - age)),
                        "error": {"code": RATE_LIMITED, "message": failure.get("message") or "Rate limited"}}
        if not manage.is_added(ch, data) or any(not tools.present(t) for t in manage.channel_tools(ch)):
            if not install:
                return _needs(channel, selected.name, "install", f"Run agent-reach ensure {channel}")
            manage.add(channel)
        if primary == "opencli":
            for tool in dict.fromkeys((*ch.prereqs, *ch.tools)):
                if not tools.present(tool):
                    if not install:
                        return _needs(channel, selected.name, "install", f"Install {tool}, then resume")
                    tools.ensure(tool)

        if primary == "cloakbrowser":
            from agent_reach.backends import cloak

            if cloak.status(channel)["configured"] and not source_profile:
                return {"ok": True, "status": "prepared", "channel": channel,
                        "action": selected.name, "backend": primary}
            grant = state.load().get("reuse_sources", {}).get(channel, {})
            if not grant and _opencli_ready(channel, selected):
                return {"ok": True, "status": "prepared", "channel": channel,
                        "action": selected.name, "backend": "opencli"}
            source = grant.get("profile")
            if source:
                failure = state.load().get("setup_failures", {}).get(channel, {})
                age = state.age_seconds(failure.get("at", ""))
                if (not source_profile and failure.get("profile") == source and
                        failure.get("code") == "UPSTREAM_BROKEN" and age < 600):
                    if _opencli_ready(channel, selected):
                        return {"ok": True, "status": "prepared", "channel": channel,
                                "action": selected.name, "backend": "opencli"}
                    return {"ok": False, "status": "failed",
                            "channel": channel, "action": selected.name,
                            "error": {"code": failure["code"], "message": failure.get("message", "Setup failed")}}
                from .onboarding import profiles

                connected = profiles()
                if source not in {p["id"] for p in connected["profiles"]}:
                    return _needs(channel, selected.name, "connect_browser",
                                  "Connect the selected Chrome profile's OpenCLI extension, then resume.",
                                  profile=source, discovery_error=connected.get("discovery_error"))
                try:
                    cloak.import_login(channel, opencli_profile=source)
                except ReachError as exc:
                    if exc.code in {RATE_LIMITED, "UPSTREAM_BROKEN"}:
                        code, message = exc.code, exc.message
                        state.mutate(lambda saved: saved.setdefault("setup_failures", {}).__setitem__(
                            channel, {"profile": source, "code": code, "message": message,
                                      "at": state.now()}))
                    if exc.code in {RATE_LIMITED, PLATFORM_BLOCKED}:
                        return {"ok": False, "status": "cooldown" if exc.code == RATE_LIMITED else "needs_user_action",
                                "channel": channel, "action": selected.name,
                                **({"retry_after_seconds": 3600} if exc.code == RATE_LIMITED else {}),
                                "error": {"code": exc.code, "message": exc.message},
                                **({"required_action": {"type": "platform_verification", "message": exc.message}}
                                   if exc.code == PLATFORM_BLOCKED else {})}
                    if exc.code == NEED_LOGIN:
                        return _needs(channel, selected.name, "login",
                                      f"Existing {channel} login needs renewal: {exc.message}. "
                                      "Log in in the authorized source browser or use Cloak's own login, then resume.")
                    if exc.code == "UPSTREAM_BROKEN" and _opencli_ready(channel, selected):
                        return {"ok": True, "status": "prepared", "channel": channel,
                                "action": selected.name, "backend": "opencli"}
                    return {"ok": False, "status": "failed", "channel": channel,
                            "action": selected.name, "error": {"code": exc.code, "message": exc.message}}
                state.mutate(lambda saved: saved.setdefault("setup_failures", {}).pop(channel, None))
                return {"ok": True, "status": "prepared", "channel": channel,
                        "action": selected.name, "backend": primary, "session_source": "authorized_profile"}
            return _needs(channel, selected.name, "login",
                          f"Log in yourself with agent-reach cloak login {channel}, then resume. "
                          "To reuse an existing Chrome login, run ensure with --reuse-profile ID.")

        if primary == "opencli":
            from .onboarding import profiles

            selected_profile = profile_for(channel)
            connected = profiles()
            if not selected_profile or selected_profile not in {p["id"] for p in connected["profiles"]}:
                return _needs(channel, selected.name, "connect_browser",
                              "Select a connected Chrome profile with agent-reach browser use ID, then resume.",
                              profiles=connected["profiles"])
        return {"ok": True, "status": "prepared", "channel": channel,
                "action": selected.name, "backend": primary}


def ensure(channel: str, *, action: Optional[str] = None, source_profile: Optional[str] = None,
           verify: bool = True, install: bool = True) -> dict:
    prepared = prepare(channel, action=action, source_profile=source_profile, install=install)
    if not prepared["ok"] or not verify:
        return prepared
    selected = _action(manage._channel(channel), prepared["action"])
    if selected.live_test is None:
        return {**prepared, "status": "prepared", "verified": False}
    out = run_action(manage._channel(channel), selected.name, dict(selected.live_test),
                     timeout=selected.timeout or 60)
    _record(channel, selected.name, out)
    if out["ok"] and out["items"]:
        return {**prepared, "status": "ready", "verified": True,
                "backend": out["backend"], "item_count": len(out["items"])}
    return _failure(channel, selected.name, out)


def _failure(channel: str, action: str, out: dict) -> dict:
    err = out.get("error") or {"code": "EMPTY", "message": "Query returned no items"}
    code = err["code"]
    if code in {NEED_LOGIN, PLATFORM_BLOCKED}:
        return _needs(channel, action, "platform_verification" if code == PLATFORM_BLOCKED else "login",
                      err["message"])
    return {"ok": False, "status": "cooldown" if code == RATE_LIMITED else "failed",
            "channel": channel, "action": action, "error": err, "attempts": out["meta"]["attempts"],
            **({"retry_after_seconds": 3600} if code == RATE_LIMITED else {})}


def execute(channel: str, action: str, params: dict[str, Any], *, timeout: float = 60,
            source_profile: Optional[str] = None, operation_id: Optional[str] = None) -> dict:
    if not isinstance(params, dict):
        raise ReachError(BAD_INPUT, "params must be an object")
    ch = manage._channel(channel)
    _action(ch, action)
    prepared = prepare(channel, action=action, source_profile=source_profile)
    if not prepared["ok"]:
        result = prepared
    else:
        out = run_action(ch, action, params, timeout=timeout)
        _record(channel, action, out)
        result = ({"ok": True, "status": "ready", "channel": channel, "action": action,
                   "backend": out["backend"], "items": out["items"], "meta": out["meta"]}
                  if out["ok"] else _failure(channel, action, out))
    if result["status"] == "needs_user_action":
        token = operation_id or "op_" + secrets.token_urlsafe(12)
        with execution_lock("pending:" + channel):
            def save_pending(data):
                pending = data.setdefault("pending", {})
                pending[token] = {"channel": channel, "action": action,
                                  "params": params, "timeout": timeout, "at": state.now()}
                for old in list(pending):
                    if state.age_seconds(pending[old].get("at", "")) > 7 * 86400:
                        pending.pop(old, None)
                while len(pending) > 32:
                    pending.pop(next(iter(pending)))
            state.mutate(save_pending)
        result["operation_id"] = token
    elif operation_id and result["status"] == "ready":
        with execution_lock("pending:" + channel):
            state.mutate(lambda data: data.setdefault("pending", {}).pop(operation_id, None))
    elif operation_id:
        result["operation_id"] = operation_id
    return result


def resume(operation_id: str) -> dict:
    pending = state.load().get("pending", {}).get(operation_id)
    if not pending:
        raise ReachError(BAD_INPUT, "Unknown or completed operation_id")
    result = execute(pending["channel"], pending["action"], pending["params"],
                     timeout=pending["timeout"], operation_id=operation_id)
    if (result.get("status") == "needs_user_action" and
            result.get("required_action", {}).get("type") == "login"):
        source = state.load().get("reuse_sources", {}).get(pending["channel"], {}).get("profile")
        if source:
            refreshed = prepare(pending["channel"], action=pending["action"], source_profile=source)
            if refreshed["ok"]:
                return execute(pending["channel"], pending["action"], pending["params"],
                               timeout=pending["timeout"], operation_id=operation_id)
            refreshed["operation_id"] = operation_id
            return refreshed
    return result


def forget_source(channel: str) -> dict:
    manage._channel(channel)
    with execution_lock("prepare:" + channel):
        removed = state.mutate(lambda data: data.setdefault("reuse_sources", {}).pop(channel, None) is not None)
    return {"ok": True, "status": "source_forget", "channel": channel, "source_grant_removed": removed,
            "existing_browser_and_cloak_sessions_changed": False}
