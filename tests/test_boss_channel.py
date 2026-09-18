# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel.

Boss Zhipin reuses a logged-in real Chrome session through the CDP debugging port; headless mode is avoided because of code 36 risk controls.
check() performs read-only probes only: boss-agent-cli installed → CDP port reachable → reusable
Zhipin tab → browser login cookie (wt2) present → tabs on anti-bot security-check pages.
Each branch returns (status, message) and never launches a browser.

`boss status` validates only local session.enc; it does not prove the CDP browser is logged in. Layer 4
uses the browser itself (Storage.getCookies) as the source of truth.
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
        "https://zhipin.com/web/geek/job?query=LLM",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() branches ---

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
    # Ready path: check() must mark the backend actually in service (base contract)
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
    assert "login state is unknown" in message
    # CDP is ready; unknown login state still leaves the backend marked as in service
    assert ch.active_backend == ch.backends[0]


def test_check_warn_when_browser_not_logged_in():
    """Missing wt2 must report browser logout and explain that boss status covers session.enc only."""
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
    assert "security-check" in message
    assert "independent of login state" in message
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


# --- _cdp_zhipin_login_cookie WebSocket client (read-only wt2 probe) ---

# Fixed urandom produces a deterministic Sec-WebSocket-Key and expected accept value
_FIXED_KEY16 = b"\x01" * 16
_FIXED_KEY = base64.b64encode(_FIXED_KEY16).decode()
_FIXED_ACCEPT = base64.b64encode(
    hashlib.sha1((_FIXED_KEY + boss_mod._WS_ACCEPT_GUID).encode()).digest()
).decode()


def _ws_frame(payload: dict) -> bytes:
    """Build an unmasked server-to-client text frame."""
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
    """Fake socket that returns predefined byte streams and records sendall data."""

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
    """Run _cdp_zhipin_login_cookie with a fake socket and return (result, socket)."""
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
    """#1: an event frame without id may arrive first; still read id==1 and detect wt2."""
    event = _ws_frame({"method": "Storage.cookiesChanged", "params": {}})
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), event + _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_accepts_empty_reason_phrase(monkeypatch):
    """#2: RFC-valid HTTP/1.1 101 with an empty reason phrase must be accepted."""
    chunks = [_handshake(b"HTTP/1.1 101"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_rejects_bogus_1019(monkeypatch):
    """#2: fake status 1019 must not be treated as a successful upgrade."""
    chunks = [_handshake(b"HTTP/1.1 1019 Weird"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is None


def test_ws_probe_ipv6_host_header_bracketed(monkeypatch):
    """#3: IPv6 loopback webSocketDebuggerUrl must use brackets in the Host header."""
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), _WT2_RESULT]
    result, sock = _run_ws_probe(monkeypatch, chunks, ws_url="ws://[::1]:9222/devtools/browser/x")
    assert result is True
    assert b"Host: [::1]:9222\r\n" in sock.sent
