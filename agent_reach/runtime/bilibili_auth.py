"""Live Bilibili authentication and resumable, user-confirmed QR login.

Only the managed native session is reused automatically. QR keys and cookies
stay in owner-only files; the JSON contract exposes an image path, never secrets.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

from agent_reach.utils.paths import (
    atomic_write_private_text,
    ensure_no_symlink_path,
    home_dir,
    read_small_text_no_follow,
)

from . import state
from .browser_binding import wait_lock
from .clock import Clock
from .result import (
    NEED_LOGIN,
    NEED_SETUP,
    PLATFORM_BLOCKED,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
)
from .run import run_cmd
from .sessions import session_dir, sessions_root

NAV = "https://api.bilibili.com/x/web-interface/nav"
GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
QR_TTL = 180
COOKIE_FIELDS = {"SESSDATA": "sessdata", "bili_jct": "bili_jct",
                 "DedeUserID": "dedeuserid", "buvid3": "buvid3", "buvid4": "buvid4"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}


def _remaining(budget):
    remaining = budget.remaining() if isinstance(budget, Clock) else budget
    if remaining <= 0:
        raise ReachError(TIMEOUT, "Bilibili authentication exceeded its time budget")
    return remaining


def _files(create=False):
    root = session_dir("bili-cli") if create else sessions_root() / "bili-cli"
    return root / ".bilibili-cli" / "credential.json", root / "login-qr.json", root / "login-qr.png"


def _read(path):
    try:
        value = json.loads(read_small_text_no_follow(path, max_bytes=64 * 1024) or "{}")
    except (ValueError, FileNotFoundError):
        return {}
    return value if isinstance(value, dict) else {}


def _rate_limited():
    state.mutate(lambda data: data.setdefault("cooldowns", {}).__setitem__(
        "bilibili", {"code": RATE_LIMITED, "message": "Bilibili authentication is rate limited", "at": state.now()}))
    raise ReachError(RATE_LIMITED, "Bilibili authentication is rate limited")


def _request(url, timeout, *, params=None, credential=None):
    from .dispatch import cooldown
    limited = cooldown("bilibili")
    if limited:
        raise ReachError(RATE_LIMITED, limited["message"],
                         hint=f"Wait {limited['retry_after_seconds']} seconds before retrying Bilibili.")
    cookies = {key: credential[field] for key, field in COOKIE_FIELDS.items()
               if credential and isinstance(credential.get(field), str) and credential[field]}
    try:
        response = requests.get(url, params=params, cookies=cookies, headers=HEADERS,
                                timeout=_remaining(timeout), allow_redirects=False)
    except requests.Timeout:
        raise ReachError(TIMEOUT, "Bilibili authentication request timed out") from None
    except requests.RequestException:
        # Request exceptions may embed the QR token or response cookies.
        raise ReachError(UPSTREAM_BROKEN, "Bilibili authentication network request failed") from None
    if response.status_code == 429:
        _rate_limited()
    if response.status_code in (403, 412):
        raise ReachError(PLATFORM_BLOCKED, "Bilibili requires verification on its official page")
    if response.status_code != 200:
        raise ReachError(UPSTREAM_BROKEN, f"Bilibili authentication HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili authentication returned invalid JSON") from None
    if not isinstance(body, dict):
        raise ReachError(UPSTREAM_BROKEN, "Bilibili authentication returned an invalid object")
    code = body.get("code")
    if code in (-101, -111):
        raise ReachError(NEED_LOGIN, "Bilibili session is missing or expired")
    if code in (-352, -412):
        raise ReachError(PLATFORM_BLOCKED, "Bilibili requires verification on its official page")
    if code in (-509, -799):
        _rate_limited()
    if code != 0 or not isinstance(body.get("data"), dict):
        raise ReachError(UPSTREAM_BROKEN, "Bilibili authentication returned an unexpected response")
    _remaining(timeout)
    return body["data"], response


def _valid(credential, timeout):
    if not isinstance(credential.get("sessdata"), str) or not credential["sessdata"].strip():
        return False
    try:
        data, _ = _request(NAV, timeout, credential=credential)
    except ReachError as exc:
        if exc.code == NEED_LOGIN:
            return False
        raise
    if not isinstance(data.get("isLogin"), bool):
        raise ReachError(UPSTREAM_BROKEN, "Bilibili did not report its login state")
    return data["isLogin"]


def status(timeout=20):
    """Validate live; never infer authentication from file presence or cached flags."""
    timeout = timeout if isinstance(timeout, Clock) else Clock(timeout)
    credential = _read(_files()[0])
    valid = _valid(credential, timeout)
    return {"logged_in": valid, "verified": True, "status": "authenticated" if valid else "needs_login"}


def _save(credential):
    # Called only after a live validation; replace neither account nor files on failure.
    credential = {field: credential.get(field, "") for field in (*COOKIE_FIELDS.values(), "ac_time_value")}
    credential["saved_at"] = time.time()
    atomic_write_private_text(_files(create=True)[0], json.dumps(credential))
    state.mutate(lambda data: data.setdefault("session_reuse", {}).__setitem__(
        "bilibili", {"source": "manual", "verified": True, "at": state.now()}))


def import_existing(timeout=20):
    """Explicit one-time import of the native CLI's local session, validated first."""
    timeout = Clock(timeout)
    with wait_lock("bilibili-auth", wait=_remaining(timeout)):
        candidate = _read(home_dir() / ".bilibili-cli" / "credential.json")
        if not _valid(candidate, timeout):
            raise ReachError(NEED_LOGIN, "The native Bilibili session could not be validated")
        _remaining(timeout)
        _save(candidate)
        _clear_qr()
        return {"logged_in": True, "verified": True, "status": "authenticated", "source": "native-import"}


def _public_qr(pending):
    return {"logged_in": False, "verified": True, "status": "waiting_for_scan",
            "qr_path": str(_files()[2].absolute()), "expires_at": pending["expires_at"],
            "poll_command": "agent-reach login bilibili --poll",
            "next": "Show qr_path as an image in this conversation. The user must scan with the Bilibili app and confirm; then poll and retry the original action."}


def _clear_qr():
    for path in _files()[1:]:
        ensure_no_symlink_path(path)
        path.unlink(missing_ok=True)


def _render_qr(url, path, timeout):
    from .tools import resolve
    executable = resolve("bili")
    if not executable:
        raise ReachError(NEED_SETUP, "Install the Bilibili channel before requesting a QR image")
    python = Path(executable).with_name("python.exe" if os.name == "nt" else "python")
    ensure_no_symlink_path(path)
    # The URL/token is stdin, never a command-line argument or log message.
    script = "import sys,qrcode; qrcode.make(sys.stdin.read()).save(sys.argv[1])"
    try:
        run_cmd([str(python), "-c", script, str(path)], input_data=url, timeout=_remaining(timeout),
                label="Bilibili QR image")
    except ReachError as exc:
        if exc.code == TIMEOUT:
            raise
        raise ReachError(UPSTREAM_BROKEN, "Could not render the Bilibili QR image") from None
    except Exception:
        raise ReachError(UPSTREAM_BROKEN, "Could not render the Bilibili QR image") from None
    if os.name != "nt":
        path.chmod(0o600)


def _start_qr(timeout):
    _, pending_file, image_file = _files(create=True)
    pending = _read(pending_file)
    expires = pending.get("expires_at")
    if (isinstance(expires, (int, float)) and expires > time.time()
            and pending.get("qrcode_key") and image_file.is_file()):
        ensure_no_symlink_path(image_file)
        return _public_qr(pending)
    data, _ = _request(GENERATE, timeout)
    url, key = data.get("url"), data.get("qrcode_key")
    if not isinstance(url, str) or not isinstance(key, str) or not key:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili did not return a QR login token")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"passport.bilibili.com", "account.bilibili.com"} or parsed.username:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned an unexpected QR login destination")
    _clear_qr()
    _render_qr(url, image_file, timeout)
    _remaining(timeout)
    pending = {"qrcode_key": key, "expires_at": time.time() + QR_TTL}
    atomic_write_private_text(pending_file, json.dumps(pending))
    return _public_qr(pending)


def _poll(timeout):
    pending = _read(_files()[1])
    expires = pending.get("expires_at")
    if not isinstance(expires, (int, float)) or not pending.get("qrcode_key"):
        _clear_qr()
        return {"logged_in": False, "verified": True, "status": "expired",
                "next": "Run agent-reach login bilibili to obtain a new QR image."}
    # A user may have confirmed before expiry while the agent was busy. Ask the
    # server once even after the local display TTL; do not discard a completed login.
    data, response = _request(POLL, timeout, params={"qrcode_key": pending["qrcode_key"]})
    code = data.get("code")
    if code in (86101, 86090):
        result = _public_qr(pending)
        result["status"] = "waiting_for_scan" if code == 86101 else "waiting_for_confirmation"
        return result
    if code == 86038:
        _clear_qr()
        return {"logged_in": False, "verified": True, "status": "expired",
                "next": "Run agent-reach login bilibili to obtain a new QR image."}
    if code != 0:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned an unexpected QR polling state")
    cookies = response.cookies.get_dict()
    # Support both current Set-Cookie and older redirect-query credentials.
    redirect = data.get("url") or ""
    if not isinstance(redirect, str):
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned an invalid QR redirect")
    query = parse_qs(urlsplit(redirect).query)
    for key in COOKIE_FIELDS:
        if not cookies.get(key) and query.get(key):
            cookies[key] = query[key][0]
    credential = {field: cookies.get(key, "") for key, field in COOKIE_FIELDS.items()}
    credential["ac_time_value"] = data.get("refresh_token") or ""
    if not _valid(credential, timeout):
        raise ReachError(NEED_LOGIN, "QR confirmation did not produce a valid Bilibili session")
    _remaining(timeout)
    _save(credential)
    _clear_qr()
    return {"logged_in": True, "verified": True, "status": "authenticated"}


def login(timeout=20, *, poll=False, check=False):
    """One bounded step; reuse a verified session, otherwise present/poll one QR."""
    timeout = Clock(timeout)
    with wait_lock("bilibili-auth", wait=_remaining(timeout)):
        current = status(timeout)
        if current["logged_in"] or check:
            return current
        return _poll(timeout) if poll else _start_qr(timeout)


def require_login(timeout=20):
    result = login(timeout)
    if not result["logged_in"]:
        raise ReachError(NEED_LOGIN, "Bilibili session is missing or expired; user login is required",
                         hint=result["next"], details={"login": result})
