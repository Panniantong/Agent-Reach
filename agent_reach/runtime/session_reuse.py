"""Site-scoped local session reuse. Source browsers are read-only and never cloned.

The user removed the dedicated-only policy. Use existing connected browsers,
then saved Reach state, before requesting a human login. No password/keychain API.
"""
from __future__ import annotations

import json
import time

from agent_reach.utils.paths import PrivatePathError, read_small_text_no_follow

from . import bridge, browser, cdp, state
from .browser_binding import wait_lock
from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError


def _cookies(rows, domains) -> list:
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("name") or "value" not in row:
            continue
        if not any(cdp.domain_matches(str(row.get("domain", "")), domain) for domain in domains):
            continue
        expires = row.get("expires", row.get("expirationDate", -1))
        if not isinstance(expires, (int, float)) or (0 < expires <= time.time()):
            continue
        cookie = {k: row[k] for k in ("name", "value", "domain", "path", "secure", "httpOnly") if k in row}
        cookie["expires"] = expires
        same = {"no_restriction": "None", "lax": "Lax", "strict": "Strict",
                "None": "None", "Lax": "Lax", "Strict": "Strict"}.get(str(row.get("sameSite", "")))
        if same:
            cookie["sameSite"] = same
        out.append(cookie)
    return out


def profiles() -> list:
    return [{"id": context, "dedicated": context == browser.bound_context()}
            for context in browser.connected_contexts()]


def use(profile: str) -> dict:
    if profile == browser.bound_context() or profile not in browser.connected_contexts():
        raise ReachError(NEED_SETUP, "Choose a connected local browser profile from browser profiles")
    def select(data):
        data["local_browser_source"] = profile
        data["session_reuse"] = {name: record for name, record in data.get("session_reuse", {}).items()
                                 if record.get("blocked") or record.get("source") == "manual"}
    state.mutate(select)
    return {"source_profile": profile, "scope": "requested site only", "source_changed": False}


def _source_cookies(channel: str, domains) -> tuple[list, str]:
    from agent_reach.backends.opencli import export_site_cookies
    try:
        contexts = [p["id"] for p in profiles() if not p["dedicated"]]
    except ReachError as exc:
        if exc.code != NEED_SETUP:
            raise
        # Native CLI sessions remain usable when optional OpenCLI/source
        # discovery is absent or incompatible. Account ambiguity below still
        # requires a choice rather than silently using another account.
        contexts = []
    preferred = state.load().get("local_browser_source")
    if preferred:
        contexts = [preferred] if preferred in contexts else []
    found = []
    for context in contexts:
        try:
            cookies = _cookies([c for domain in domains for c in export_site_cookies(context, domain)], domains)
        except ReachError:
            continue  # a disconnected source must not prevent use of saved Reach login
        if cookies:
            found.append((cookies, context))
    if len(found) > 1:
        raise ReachError(NEED_SETUP, "Several local browsers have cookies for this site; choose which account to reuse",
                         hint="Run agent-reach browser profiles, then browser use ID. No account was copied.")
    if found:
        return found[0]
    # Older Reach versions stored the user's login in a per-site owned snapshot.
    source = state.root() / "sessions" / (channel + "-cloak") / "profile" / "reach-session.json"
    try:
        data = json.loads(read_small_text_no_follow(source, max_bytes=2 * 1024 * 1024) or "{}")
        cookies = _cookies(data.get("cookies", []), domains)
    except (OSError, ValueError, PrivatePathError):
        cookies = []
    return cookies, "saved-reach-session" if cookies else "saved-profile"


def prepare(channel: str, *, force: bool = False) -> dict:
    """Reuse an imported site session until explicitly refreshed; verify access separately."""
    from .manage import _channel, site_domains
    ch = _channel(channel)
    if not ch.login_url:
        return {"source": "not_required", "copied_cookies": 0}
    # One copy per site at a time; queries of other sites keep running.
    with wait_lock(f"session:{channel}"):
        browser.ensure_running()
        record = state.load().get("session_reuse", {}).get(channel, {})
        if not force and (record.get("blocked") or record.get("source") == "manual"
                          or (record.get("cookie_snapshot") == 1 and record.get("copied_cookies", 0) > 0)):
            return record
        cookies, source = _source_cookies(channel, site_domains(ch))
        # Source discovery tolerates a disconnected optional Bridge for native
        # CLI sessions. A browser-backed action still needs it before recording
        # discovery as a successful (possibly empty) site snapshot.
        bridge.require_running()
        if force and not cookies:
            # An explicit import that found no login must not report success.
            raise ReachError(NEED_SETUP, "No local browser login was found for this site; nothing was copied",
                             hint=f"Run agent-reach browser profiles to check the source browser, or agent-reach login {channel}.")
        if cookies:
            current = cdp.call("Storage.getCookies")
            if current is None:
                raise ReachError(UPSTREAM_BROKEN, "Could not inspect the saved site session; the original browser is unchanged")
            previous = _cookies(current.get("cookies", []), site_domains(ch))
            def key(cookie):
                return cookie.get("name"), cookie.get("domain"), cookie.get("path", "/")
            incoming = {key(c) for c in cookies}
            # The source is a site snapshot, not an overlay onto another account.
            # Expire destination-only cookies (including stale UI preferences),
            # preserving all other sites and every cookie supplied by the source.
            stale = [{**c, "value": "", "expires": 1} for c in previous if key(c) not in incoming]
            if cdp.call("Storage.setCookies", {"cookies": stale + cookies}) is None:
                old = {key(c) for c in previous}
                rollback = [{**c, "value": "", "expires": 1} for c in cookies if key(c) not in old] + previous
                cdp.call("Storage.setCookies", {"cookies": rollback})
                raise ReachError(UPSTREAM_BROKEN, "Could not apply the local site session; saved state retained and the original browser is unchanged")
            browser.save_session()
        result = {"source": source, "copied_cookies": len(cookies), "at": state.now(),
                  "verified": False, "source_changed": False, "cookie_snapshot": 1}
        state.mutate(lambda data: data.setdefault("session_reuse", {}).__setitem__(channel, result))
        return result
