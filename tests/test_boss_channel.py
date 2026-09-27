# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel.

Boss hires directly and uses the CDP debugging port to reuse the logged-in real Chrome (headless is a restricted area, code 36 risk control).
check() only performs read-only detection: boss-agent-cli is installed or not → the CDP port is unreachable → whether it is reusable
zhipin tab → Whether there is a login cookie in the browser (wt2) → Whether the tabs stop at the anti-crawling security verification page.
Each branch returns (status, message) independently and never triggers the browser to start (no side effects).

Note that `boss status` only verifies the local session.enc and does not mean that the CDP browser has logged in - Layer 4
The browser itself (Storage.getCookies) shall prevail.
"""

import base64
import hashlib
import json
from unittest.mock import patch

from agent_reach.channels import boss as boss_mod
from agent_reach.channels.boss import BossChannel
from agent_reach.probe import ProbeResult


def _ok_probe():
    return ProbeResult("ok", output="1.18.0")


# --- can_handle ---

def test_can_handle_matches_zhipin_hosts():
    ch = BossChannel()
    for url in [
        "https://www.zhipin.com/job_detail/abc.html",
        "https://zhipin.com/web/geek/job?query=\u5927\u6a21\u578b",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() four branches ---

def test_check_off_when_cli_missing():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("missing")):
        status, message = ch.check()
    assert status == "off"
    assert "boss-agent-cli" in message
    assert "agent-reach install --system --channels=boss" in message
    assert ch.active_backend is None


def test_check_error_when_cli_broken():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("broken")):
        status, message = ch.check()
    assert status == "error"
    assert ch.active_backend is None


def test_check_off_when_cdp_unreachable():
    ch = BossChannel()
    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", return_value=None
    ):
        status, message = ch.check()
    assert status == "off"
    assert "9222" in message
    assert ch.active_backend is None


def test_chrome_launch_command_is_portable_and_loopback_only():
    mac = boss_mod._chrome_launch_command("Darwin")
    linux = boss_mod._chrome_launch_command("Linux")
    windows = boss_mod._chrome_launch_command("Windows")

    assert mac.startswith('open -na "Google Chrome" --args ')
    assert linux.startswith("google-chrome ")
    assert windows.startswith("Start-Process chrome.exe -ArgumentList ")
    for command in (mac, linux, windows):
        assert "--remote-debugging-address=127.0.0.1" in command
        assert "--remote-debugging-port=9222" in command
        assert "boss-chrome-profile" in command
        assert "https://www.zhipin.com/web/geek/job" in command


def test_check_warn_when_no_zhipin_page():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://example.com"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ), patch.object(boss_mod, "_cdp_zhipin_login_cookie", return_value=None):
        status, message = ch.check()
    assert status == "warn"
    assert ch.active_backend is None


def test_check_warn_when_ready():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://www.zhipin.com/web/geek/job"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ), patch.object(boss_mod, "_cdp_zhipin_login_cookie", return_value=True):
        status, message = ch.check()
    assert status == "warn"
    assert "boss-agent-cli #403-#407" in message
    assert "boss --cdp-url http://localhost:9222 login --cdp" in message
    assert "--browser-source existing-browser" in message
    assert "code 37 = TOKEN_REFRESH_FAILED" not in message
    assert "wt2" in message
    # Ready path: check() must mark the actual service backend (base contract, doctor --json is no longer constant null)
    assert ch.active_backend == ch.backends[0]


def test_check_warn_when_cookie_probe_fails():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://www.zhipin.com/web/geek/job"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ), patch.object(boss_mod, "_cdp_zhipin_login_cookie", return_value=None):
        status, message = ch.check()
    assert status == "warn"
    assert "login status unknown" in message
    # The link is ready (port is open + there is a tab), only the login status is unknown → still marked as a service backend
    assert ch.active_backend == ch.backends[0]


def test_check_warn_when_browser_not_logged_in():
    """There is no wt2 in the browser → it clearly indicates that you are not logged in, and that boss status only represents session.enc."""
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [{"type": "page", "url": "https://www.zhipin.com/web/geek/job"}]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ), patch.object(boss_mod, "_cdp_zhipin_login_cookie", return_value=False):
        status, message = ch.check()
    assert status == "warn"
    assert "AUTH_EXPIRED" in message
    assert "session.enc" in message
    assert "boss --cdp-url http://localhost:9222 login --cdp" in message
    assert ch.active_backend is None


def test_check_warn_when_stuck_on_security_check():
    ch = BossChannel()

    def fake_cdp(path):
        if path == "/json/version":
            return {"Browser": "Chrome"}
        return [
            {
                "type": "page",
                "url": "https://www.zhipin.com/web/common/security-check.html?seed=abc",
            }
        ]

    with patch.object(boss_mod, "probe_command", return_value=_ok_probe()), patch.object(
        boss_mod, "_cdp_json", side_effect=fake_cdp
    ), patch.object(boss_mod, "_cdp_zhipin_login_cookie", return_value=True):
        status, message = ch.check()
    assert status == "warn"
    assert "security verification" in message
    assert "does not mean that you are not logged in" in message
    assert "boss status" in message
    assert "wt2" in message
    assert ch.active_backend is None


def test_cdp_cookie_probe_returns_none_without_ws_url():
    with patch.object(boss_mod, "_cdp_json", return_value={"Browser": "Chrome"}):
        assert boss_mod._cdp_zhipin_login_cookie() is None


def test_check_clears_stale_active_backend():
    ch = BossChannel()
    ch.active_backend = "stale"
    with patch.object(boss_mod, "probe_command", return_value=ProbeResult("missing")):
        ch.check()
    assert ch.active_backend is None


# --- WebSocket client for _cdp_zhipin_login_cookie (doctor read-only detection wt2) ---

# Fixed urandom → Fixed Sec-WebSocket-Key so accept can be precalculated
_FIXED_KEY16 = b"\x01" * 16
_FIXED_KEY = base64.b64encode(_FIXED_KEY16).decode()
_FIXED_ACCEPT = base64.b64encode(
    hashlib.sha1((_FIXED_KEY + boss_mod._WS_ACCEPT_GUID).encode()).digest()
).decode()


def _ws_frame(payload: dict) -> bytes:
    """Constructs a server→client unmasked text frame."""
    body = json.dumps(payload).encode("utf-8")
    n = len(body)
    header = bytes([0x81])
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += bytes([126]) + n.to_bytes(2, "big")
    else:
        header += bytes([127]) + n.to_bytes(8, "big")
    return header + body


def _handshake(status_line: bytes) -> bytes:
    return (
        status_line
        + b"\r\nSec-WebSocket-Accept: "
        + _FIXED_ACCEPT.encode()
        + b"\r\n\r\n"
    )


class _FakeSock:
    """The fake socket that spits out the preset byte stream in sequence and records the sendall content."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.sent = b""

    def settimeout(self, *_a):
        pass

    def sendall(self, data):
        self.sent += data

    def recv(self, _n):
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _run_ws_probe(monkeypatch, chunks, ws_url="ws://127.0.0.1:9222/devtools/browser/abc"):
    """Run _cdp_zhipin_login_cookie with a fake socket and return (result, fake socket)."""
    sock = _FakeSock(chunks)
    monkeypatch.setattr(boss_mod.os, "urandom", lambda n: _FIXED_KEY16)
    monkeypatch.setattr(boss_mod.socket, "create_connection", lambda *a, **k: sock)
    monkeypatch.setattr(
        boss_mod, "_cdp_json", lambda path: {"webSocketDebuggerUrl": ws_url}
    )
    return boss_mod._cdp_zhipin_login_cookie(), sock


_WT2_RESULT = _ws_frame(
    {"id": 1, "result": {"cookies": [{"name": "wt2", "domain": ".zhipin.com"}]}}
)


def test_ws_probe_event_frame_before_response(monkeypatch):
    """#1: The event frame (without id) arrives before the response frame, the response with id==1 should still be read and wt2 identified."""
    event = _ws_frame({"method": "Storage.cookiesChanged", "params": {}})
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), event + _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_accepts_empty_reason_phrase(monkeypatch):
    """#2: The RFC legal empty reason phrase 'HTTP/1.1 101' (no trailing spaces) should be accepted."""
    chunks = [_handshake(b"HTTP/1.1 101"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_rejects_bogus_1019(monkeypatch):
    """#2: Pseudocode 1019 (including the ' 101 ' substring) should not be considered a successful upgrade."""
    chunks = [_handshake(b"HTTP/1.1 1019 Weird"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is None


def test_ws_probe_ipv6_host_header_bracketed(monkeypatch):
    """#3: IPv6 loopback webSocketDebuggerUrl, the Host header must have square brackets."""
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), _WT2_RESULT]
    result, sock = _run_ws_probe(monkeypatch, chunks, ws_url="ws://[::1]:9222/devtools/browser/x")
    assert result is True
    assert b"Host: [::1]:9222\r\n" in sock.sent
