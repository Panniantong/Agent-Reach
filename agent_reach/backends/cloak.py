"""Opt-in, persistent CloakBrowser sessions and bounded subprocess calls."""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_reach.runtime.result import BAD_INPUT, NEED_SETUP, TIMEOUT, ReachError
from agent_reach.utils.paths import (
    atomic_write_private_text,
    ensure_no_symlink_path,
    make_private_dir,
)
from agent_reach.utils.url import domain_matches

DOMAINS = {"xiaohongshu": "xiaohongshu.com", "boss": "zhipin.com", "instagram": "instagram.com",
           "facebook": "facebook.com", "twitter": "x.com", "reddit": "reddit.com",
           "linkedin": "linkedin.com"}


def folder(channel):
    from agent_reach.runtime import state
    if channel not in DOMAINS:
        raise ReachError(BAD_INPUT, "Unsupported CloakBrowser channel")
    return state.root() / "sessions" / (channel + "-cloak")


def status(channel):
    from agent_reach.runtime.tools import resolve
    path = folder(channel)
    ensure_no_symlink_path(path, "CloakBrowser profile")
    ensure_no_symlink_path(path / "profile", "CloakBrowser profile")
    return {"backend": "cloakbrowser", "installed": bool(resolve("cloakbrowser")),
            "configured": (path / "configured.json").is_file(), "logged_in": None,
            "profile": str(path / "profile")}


def call(channel, action, *, timeout, profile_dir=None, **params):
    from agent_reach.config import Config
    from agent_reach.runtime.browser_binding import execution_lock
    from agent_reach.runtime.run import run_cmd
    from agent_reach.runtime.tools import resolve
    path = folder(channel)
    ensure_no_symlink_path(path, "CloakBrowser profile")
    ensure_no_symlink_path(path / "profile", "CloakBrowser profile")
    profile = Path(profile_dir) if profile_dir is not None else path / "profile"
    if profile_dir is not None and (profile.parent.parent != path or not profile.parent.name.startswith("stage-")):
        raise ReachError(BAD_INPUT, "Invalid staged CloakBrowser profile")
    ensure_no_symlink_path(profile, "CloakBrowser profile")
    exe = resolve("cloakbrowser")
    if not exe or (action not in {"import", "login"} and not status(channel)["configured"]):
        raise ReachError(NEED_SETUP, f"Run agent-reach cloak setup, then agent-reach cloak login {channel}")
    # This interpreter belongs to the tool's venv, not the Reach environment.
    python = Path(exe).parent / ("python.exe" if os.name == "nt" else "python")
    if not python.is_file():
        raise ReachError(NEED_SETUP, "CloakBrowser needs a Python venv installation; run agent-reach cloak setup")
    make_private_dir(path)
    request = {"channel": channel, "action": action, "profile": str(profile), **params}
    with execution_lock(str(profile)):
        out = run_cmd([str(python), "-m", "agent_reach.backends.cloak_worker", json.dumps(request)],
                      timeout=max(0.1, timeout - (12 if os.name == "nt" else 2)), env={
                          "PYTHONPATH": str(Path(__file__).parents[2]),
                          "CLOAKBROWSER_AUTO_UPDATE": "false",
                          "CLOAKBROWSER_CACHE_DIR": str(path.parents[1] / "cloak-binaries"),
                          "REACH_CLOAK_PROXY": os.environ.get("REACH_CLOAK_PROXY", str(Config(read_only=True).get("proxy") or "")),
                      })
    try:
        result = json.loads(out)
    except ValueError:
        raise ReachError("UPSTREAM_BROKEN", "CloakBrowser returned invalid JSON") from None
    if result.get("error"):
        raise ReachError(result["error"]["code"], result["error"]["message"])
    return result["items"]


def setup():
    from agent_reach.runtime import state, tools
    from agent_reach.runtime.run import run_cmd
    tools.ensure("cloakbrowser")
    exe = tools.resolve("cloakbrowser")
    if not exe:
        raise ReachError(NEED_SETUP, "CloakBrowser installation did not provide its executable")
    run_cmd([exe, "install"], timeout=600, env={"CLOAKBROWSER_AUTO_UPDATE": "false",
            "CLOAKBROWSER_CACHE_DIR": str(state.root() / "cloak-binaries")})
    return {"installed": True, "backend": "cloakbrowser", "opened_browser": False}


def login(channel):
    """User completes login in Cloak's own persistent browser, then closes it."""
    from agent_reach.runtime import state
    try:
        items = call(channel, "login", timeout=900)
    except ReachError as exc:
        if exc.code != TIMEOUT:
            raise
        raise ReachError(
            TIMEOUT,
            "Cloak login window closed after 15 minutes without a saved session. "
            "Ask the user whether to reopen it; do not retry automatically.",
            hint="The user must finish login and close the Cloak window to save the session. "
                 "Then run agent-reach ensure for this channel.",
        ) from None
    path = folder(channel)
    atomic_write_private_text(path / "configured.json", json.dumps({"source": "native login", "channel": channel}))
    saved = state.load()
    saved["checks"].pop(channel, None)
    state.save(saved)
    return {"backend": "cloakbrowser", "session_saved": True, "logged_in": None,
            "verification": items, "next": f"agent-reach {channel} search nasa --backend cloakbrowser" if channel == "instagram"
            else f"agent-reach {channel} search VLA --backend cloakbrowser"}


def scoped_cookies(channel, data):
    rows = data.get("cookies", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ReachError(BAD_INPUT, "Expected storage_state or a cookie array")
    cookies = []
    for c in rows:
        if not isinstance(c, dict) or not domain_matches(c.get("domain", ""), DOMAINS[channel]):
            continue
        if not all(isinstance(c.get(k), str) for k in ("name", "value", "domain", "path")):
            raise ReachError(BAD_INPUT, "Invalid cookie fields")
        item = {k: c[k] for k in ("name", "value", "domain", "path")}
        item.update(secure=bool(c.get("secure")), httpOnly=bool(c.get("httpOnly")))
        item["expires"] = c.get("expirationDate", c.get("expires", -1))
        same_site_value = c.get("sameSite")
        same_site = ({"no_restriction": "None", "lax": "Lax", "strict": "Strict",
                      "None": "None", "Lax": "Lax", "Strict": "Strict"}.get(same_site_value)
                     if isinstance(same_site_value, str) else None)
        # Missing is unspecified, not SameSite=None (which requires Secure).
        if same_site is not None:
            item["sameSite"] = same_site
        cookies.append(item)
    if not cookies:
        raise ReachError(BAD_INPUT, "No cookies for the selected site")
    return cookies


def import_login(channel, *, state_file=None, opencli_profile=None):
    """Explicit local import only. Cookie values never appear in stdout or argv."""
    import shutil
    import tempfile

    from agent_reach.runtime.browser_binding import execution_lock
    from agent_reach.runtime.run import run_cmd
    from agent_reach.runtime.tools import resolve
    from agent_reach.utils.paths import read_small_text_no_follow
    path = folder(channel)
    if bool(state_file) == bool(opencli_profile):
        raise ReachError(BAD_INPUT, "Choose exactly one of --state-file or --opencli-profile")
    make_private_dir(path)
    if state_file:
        try:
            data = json.loads(read_small_text_no_follow(Path(state_file), max_bytes=2 * 1024 * 1024) or "null")
        except (ValueError, OSError):
            raise ReachError(BAD_INPUT, "Cannot read cookie JSON") from None
    else:
        exe = resolve("opencli")
        if not exe:
            raise ReachError(NEED_SETUP, "OpenCLI is required only to import from Browser Bridge")
        from agent_reach.runtime.opencli_compat import package_root
        root = package_root()
        module = next((p for p in (root / "dist/src/browser/page.js", root / "browser/page.js")
                       if p.is_file()), None)
        if module is None:
            raise ReachError(NEED_SETUP, "Unsupported OpenCLI layout; use --state-file instead")
        script = (f"import {{Page}} from {json.dumps(module.as_uri())};"
                  f"const p=new Page('reach-cloak-import',undefined,{json.dumps(opencli_profile)});"
                  f"console.log(JSON.stringify(await p.getCookies({{domain:{json.dumps(DOMAINS[channel])}}}))); ")
        data = json.loads(run_cmd(["node", "--input-type=module", "-e", script], timeout=20))
    cookies = scoped_cookies(channel, data)
    from agent_reach.runtime import state
    fd, name = tempfile.mkstemp(prefix="import-", suffix=".json", dir=path)
    stage = Path(tempfile.mkdtemp(prefix="stage-", dir=path))
    backup = stage / "old-profile"
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cookies, f)
        items = call(channel, "import", timeout=60, profile_dir=stage / "profile", cookie_file=name)
        current = path / "profile"
        with execution_lock(str(current)):
            if current.exists():
                os.replace(current, backup)
            try:
                os.replace(stage / "profile", current)
            except OSError:
                if backup.exists() and not current.exists():
                    os.replace(backup, current)
                raise
        atomic_write_private_text(path / "configured.json", json.dumps({"source": "explicit import", "channel": channel}))
        state.mutate(lambda saved: saved["checks"].pop(channel, None))
        if backup.exists():
            shutil.rmtree(backup)
        return {"backend": "cloakbrowser", "imported_cookies": len(cookies), "verification": items,
                "profile": str(path / "profile"), "original_browser_changed": False}
    finally:
        Path(name).unlink(missing_ok=True)
        # A failed swap must leave its previous profile available for recovery.
        if not backup.exists():
            shutil.rmtree(stage, ignore_errors=True)


def logout(channel):
    import shutil

    from agent_reach.runtime.browser_binding import execution_lock
    path = folder(channel)
    ensure_no_symlink_path(path, "CloakBrowser profile")
    ensure_no_symlink_path(path / "profile", "CloakBrowser profile")
    with execution_lock(str(path / "profile")):
        if path.exists():
            shutil.rmtree(path)
    return {"removed": True, "backend": "cloakbrowser", "original_browser_changed": False}
