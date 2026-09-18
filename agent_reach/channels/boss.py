# -*- coding: utf-8 -*-
"""Boss Zhipin — search jobs and retrieve full JDs through boss-agent-cli + a real Chrome session over CDP.

The backend is boss-agent-cli, which reuses a logged-in real Chrome instance through the CDP debugging port. Headless mode is intentionally avoided
because it can trigger code 36 account-risk controls, so check() performs only four layers of read-only probing and never instantiates BossClient or launches a browser.

Retrieval uses the public boss-agent-cli API (search_jobs + job_card_browser + browser_source="existing-browser").
See skill/references/career.md for usage. check() is responsible only for installation + CDP readiness +
whether the browser contains a login cookie; it never performs a search.

Two authentication stores must be distinguished during health checks. Both are required, but they authenticate different paths:

- `~/.boss-agent/auth/session.enc`(`boss status` / `status --live` validate only this store)
  1. is a hard prerequisite: `_get_browser()` unconditionally `get_token()`, if it cannot be read then `AuthRequired`, 
     do not delete it—the CDP search can fail before connecting to the browser;
  2. but it is **not the effective search credential**: after CDP connects to real Chrome it reuses `contexts[0]`; its cookies
     are injected only when there is no browser context, so they do not take effect for the normal existing-browser path;
  3. the httpx path (lower-risk operations: status/detail/cities/`job_card_httpx`) does use its
     cookies + stoken; code 37 `force_refresh()` also writes back to it.
- Browser cookies in the dedicated Chrome profile: in CDP mode, higher-risk operations such as search/greet
  actually carry these credentials.

Therefore, a valid session.enc plus a logged-out browser can make `boss status` report logged in while search returns
`AUTH_EXPIRED`. Layer 4 queries the CDP browser directly with Storage.getCookies, so browser state is authoritative.
"""

import base64
import hashlib
import json
import os
import platform
import socket
import struct
import urllib.request
from urllib.parse import urlparse

from agent_reach.probe import probe_command
from agent_reach.utils.url import host_matches

from .base import Channel

_CDP_URL = "http://localhost:9222"
_CDP_TIMEOUT = 5


def _chrome_launch_command(system: str | None = None) -> str:
    """Return a dedicated-profile Chrome command for the current OS."""
    system = system or platform.system()
    common = (
        "--remote-debugging-address=127.0.0.1 "
        "--remote-debugging-port=9222 "
    )
    url = '"https://www.zhipin.com/web/geek/job"'
    if system == "Darwin":
        return (
            'open -na "Google Chrome" --args '
            + common
            + '--user-data-dir="$HOME/.boss-chrome-profile" '
            + url
        )
    if system == "Windows":
        return (
            "Start-Process chrome.exe -ArgumentList "
            "'--remote-debugging-address=127.0.0.1',"
            "'--remote-debugging-port=9222',"
            '"--user-data-dir=$env:USERPROFILE\\.boss-chrome-profile",'
            "'https://www.zhipin.com/web/geek/job'"
        )
    return (
        "google-chrome "
        + common
        + '--user-data-dir="$HOME/.boss-chrome-profile" '
        + url
    )


def _cdp_json(path: str):
    """GET a local CDP endpoint with system proxies disabled. Return parsed JSON, or None on failure.

    CDP is bound only to loopback (127.0.0.1), so direct access is sufficient. An empty ProxyHandler explicitly bypasses any
    configured system/global proxy; sending localhost probes through a proxy is unnecessary and may be blocked. This is an intentional
    localhost-only assumption and must not be overridden by the configured proxy.
    """
    req = urllib.request.Request(f"{_CDP_URL}{path}", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=_CDP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _has_zhipin_page(pages) -> bool:
    """Return whether the CDP /json tab list contains a reusable zhipin.com tab, using exact hostname validation."""
    for page in pages or []:
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com"):
            return True
    return False


_SECURITY_CHECK_MARKERS = ("security-check", "zhipin-security", "_security_check")


def _security_check_blocks_all(pages) -> bool:
    """Return whether all existing Zhipin tabs are on anti-bot security-check pages rather than login pages."""
    zhipin_urls = [
        page.get("url", "")
        for page in (pages or [])
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com")
    ]
    if not zhipin_urls:
        return False
    return all(
        any(marker in url.lower() for marker in _SECURITY_CHECK_MARKERS)
        for url in zhipin_urls
    )


_WS_ACCEPT_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read_ws_text_frame(sock: socket.socket, initial: bytes = b""):
    """Read the next text frame and return (payload, leftover).

    leftover contains extra bytes received for later frames; the caller should pass it back as the next frame's initial
    buffer because one recv may contain multiple frames. Return (None, leftover) on a close frame or disconnect.
    Ignore ping/pong.
    """
    buf = initial
    while True:
        while len(buf) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        opcode = buf[0] & 0x0F
        length = buf[1] & 0x7F
        header_len = 2
        if length == 126:
            while len(buf) < header_len + 2:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">H", buf[header_len:header_len + 2])[0]
            header_len += 2
        elif length == 127:
            while len(buf) < header_len + 8:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">Q", buf[header_len:header_len + 8])[0]
            header_len += 8
        while len(buf) < header_len + length:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        payload = buf[header_len:header_len + length]
        buf = buf[header_len + length:]
        if opcode == 0x8:  # close
            return None, buf
        if opcode in (0x1, 0x2, 0x0):  # text / binary / continuation
            return payload, buf
        # Ignore ping (0x9), pong (0xA), etc. and continue to the next frame


def _send_ws_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytes([0x81])  # FIN + text
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", n)
    sock.sendall(header + mask + masked)


def _cdp_zhipin_login_cookie() -> bool | None:
    """Read-only probe for the zhipin.com login cookie (wt2) in the dedicated Chrome browser.

    True=present; False=absent (the browser is logged out and CDP search will return AUTH_EXPIRED);
    None=probe failed (for example, CDP WebSocket unreachable), so login state is unknown.
    This proves only that the browser profile contains a login cookie; it does not validate server-side cookie validity.
    """
    version = _cdp_json("/json/version")
    ws_url = (version or {}).get("webSocketDebuggerUrl")
    if not ws_url:
        return None
    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    try:
        with socket.create_connection((host, port), timeout=_CDP_TIMEOUT) as sock:
            sock.settimeout(_CDP_TIMEOUT)
            key = base64.b64encode(os.urandom(16)).decode()
            # IPv6 literals require brackets in the Host header (urlparse().hostname removes them)
            host_header = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            sock.sendall(handshake.encode())
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                response += chunk
            head, _, rest = response.partition(b"\r\n\r\n")
            status_line = head.split(b"\r\n", 1)[0]
            # Parse the status-code token exactly: accept "HTTP/1.1 101" (reason phrase may be empty), reject lookalikes such as 1019
            if status_line.split()[1:2] != [b"101"]:
                return None
            accept = base64.b64encode(
                hashlib.sha1((key + _WS_ACCEPT_GUID).encode()).digest()
            ).decode()
            if accept not in head.decode("latin-1"):
                return None
            _send_ws_text(sock, json.dumps({"id": 1, "method": "Storage.getCookies"}))
            # Chrome may send event frames first (without id); keep reading until the id==1 response arrives, with a limit to avoid infinite loops.
            # leftover carries extra bytes from the previous recv so multiple frames in one recv are not lost.
            buf = rest
            for _ in range(16):
                payload, buf = _read_ws_text_frame(sock, initial=buf)
                if payload is None:
                    return None
                data = json.loads(payload.decode("utf-8"))
                if data.get("id") != 1:
                    continue  # Skip event frames and continue reading
                if "result" not in data:
                    return None
                for cookie in data["result"].get("cookies", []):
                    if cookie.get("name") == "wt2" and "zhipin" in cookie.get("domain", ""):
                        return True
                return False
            return None
    except Exception:
        return None


class BossChannel(Channel):
    name = "boss"
    description = "Boss Zhipin job search and job descriptions"
    backends = ["boss-agent-cli (CDP)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    def check(self, config=None):
        self.active_backend = None

        # Layer 1: is boss-agent-cli installed?
        probe = probe_command("boss", ["--version"], timeout=10)
        if probe.status == "missing":
            return "off", (
                "boss-agent-cli is not installed. Obtain user approval first, then run:\n"
                "  agent-reach install --system --channels=boss\n"
                "After installation, the user must log in to zhipin.com manually in the dedicated Chrome profile."
            )
        if probe.status == "broken":
            return "error", (
                "The boss command exists but cannot execute—the installation is broken. Reinstall:\n"
                "  agent-reach install --system --channels=boss"
            )
        if not probe.ok:
            return "warn", f"boss command probe failed ({probe.status}); check the installation"

        # Layer 2: is the CDP port reachable?
        if _cdp_json("/json/version") is None:
            return "off", (
                "The CDP debugging port is unreachable. Start the dedicated debugging Chrome first:\n"
                f"  {_chrome_launch_command()}\n"
                "  Then have the user log in to zhipin.com manually in that window.\n"
                "Bind only to 127.0.0.1; any process that can reach port 9222 can fully control this Chrome instance."
            )

        # Layer 3: is there a reusable Boss Zhipin tab?
        pages = _cdp_json("/json")
        if pages is None:
            return "warn", "The CDP port is reachable, but /json tab enumeration failed"
        if not _has_zhipin_page(pages):
            return "warn", (
                "CDP is reachable but no existing zhipin.com tab was found (this does not prove the user is logged out; cookies may still exist, "
                "and boss-agent-cli can create a new tab). Prefer logging in to zhipin.com in Chrome first."
            )

        # Layer 4: browser login cookie (wt2). Browser state is authoritative—`boss status` validates only
        # local session.enc, which does not represent browser login state.
        browser_cookie = _cdp_zhipin_login_cookie()
        if browser_cookie is False:
            return "warn", (
                "CDP is ready, but the dedicated Chrome browser does not contain the zhipin.com login cookie (wt2)"
                "—the browser is logged out and search will return AUTH_EXPIRED. Note that the logged_in value from `boss status` "
                "represents only the local session.enc credentials, not browser authentication. Have the user visually confirm and log in in this Chrome window"
                " (this should be the first step after launching CDP Chrome), then run "
                "`boss --cdp-url http://localhost:9222 login --cdp` to synchronize the login state."
            )

        cookie_note = (
            "browser contains login cookie (wt2)" if browser_cookie else "browser login-cookie probe failed; login state is unknown"
        )

        if _security_check_blocks_all(pages):
            return "warn", (
                f"CDP is ready, but all existing Zhipin tabs are on security-check pages"
                " (security-check / zhipin-security). This is an anti-bot challenge and is independent of login state"
                "—it may appear even when logged in. Do not treat it as proof of logout or ask the user to log in again solely for this reason; "
                "have the user handle the challenge manually if needed."
                f"Browser login-state reference: {cookie_note}。"
                "Do not use `boss status` to determine CDP browser login state; it validates only local session.enc."
            )

        # All four probes passed: CDP is ready; mark the backend actually in service (base contract)
        self.active_backend = self.backends[0]
        return "warn", (
            f"CDP is ready (port 9222 reachable + reusable Zhipin tab present, {cookie_note}. "
            "Doctor does not perform a real search and does not validate server-side cookie validity or the upstream boss-agent-cli #403-#407 API;"
            "first run `boss --cdp-url http://localhost:9222 login --cdp` to synchronize the current login state;"
            "for search, use `boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`, "
            "so execution stops immediately if CDP is unavailable instead of falling back to headless mode."
            "If search returns AUTH_EXPIRED, follow the login runbook (user logs in in the dedicated window + `login --cdp`); "
            "do not reinterpret it as a security-check problem."
        )
