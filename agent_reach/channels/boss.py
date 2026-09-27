# -*- coding: utf-8 -*-
"""Boss Zhipin — job search and descriptions through boss-agent-cli and CDP.

Reuse an existing logged-in Chrome session. Headless access triggers code 36
risk controls. check() performs read-only checks of the CLI, CDP connection,
tabs, and browser cookies; it never creates BossClient or launches a browser.
Use the public search_jobs/job_card_browser APIs with
browser_source="existing-browser"; see skill/references/career.md.

Two credential stores are required, but authenticate different paths:

* ~/.boss-agent/auth/session.enc: _get_browser() calls get_token() before
  connecting to Chrome, so deleting this file causes AuthRequired. The HTTP
  path (status/detail/cities/job_card_httpx) uses its cookies and stoken;
  code 37 force_refresh() updates it. With an existing CDP context, its cookies
  are not injected into Chrome. boss status/status --live only check this file.
* Dedicated Chrome profile cookies: these authenticate CDP search/greet calls.

Valid session.enc credentials do not prove that the browser is logged in.
A logged-out browser returns AUTH_EXPIRED on search. The fourth health-check
layer queries Storage.getCookies directly to inspect the browser's wt2 cookie.
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
    """GET local CDP endpoint (system proxy disabled), returns parsed JSON; returns None on failure.

    CDP only binds the loopback address (127.0.0.1) and can be connected directly, so use an empty ProxyHandler to explicitly bypass any
    Configured system/global proxy - localhost Probing for proxies is meaningless and may be blocked. this is intentional
    The localhost-only assumption cannot be overridden by the proxy of config.
    """
    req = urllib.request.Request(f"{_CDP_URL}{path}", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=_CDP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _has_zhipin_page(pages) -> bool:
    """Whether there is a reusable zhipin.com tag in the CDP/json tag list (accurate hostname verification)."""
    for page in pages or []:
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com"):
            return True
    return False


_SECURITY_CHECK_MARKERS = ("security-check", "zhipin-security", "_security_check")


def _security_check_blocks_all(pages) -> bool:
    """Whether all existing zhipin tabs are stopped on the anti-crawling security verification page (not the login page)."""
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

    leftover is the byte that is over-received by this recv and belongs to the subsequent frame. The caller should use it as the initial of the next frame.
    Pass back (one recv may get multiple frames). Returns (None, leftover) when a close frame is received or the connection is disconnected.
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
        # ping(0x9)/pong(0xA), etc.: ignore and continue reading the next frame


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
    """Read-only detection of the zhipin.com login cookie (wt2) in the dedicated Chrome browser.

    True=yes; False=no (the browser is not logged in, CDP search will report AUTH_EXPIRED);
    None=Detection failed (CDP WebSocket unreachable, etc.), login status is unknown.
    It only proves that the browser profile has been logged in, and does not verify the server validity of the cookie.
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
            # IPv6 literals require square brackets in the Host header (urlparse().hostname has been stripped off)
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
            # Accurately parse status code tokens: accept "HTTP/1.1 101" (nullable reason phrase), reject 1019 and other pseudocodes
            if status_line.split()[1:2] != [b"101"]:
                return None
            accept = base64.b64encode(
                hashlib.sha1((key + _WS_ACCEPT_GUID).encode()).digest()
            ).decode()
            if accept not in head.decode("latin-1"):
                return None
            _send_ws_text(sock, json.dumps({"id": 1, "method": "Storage.getCookies"}))
            # Chrome may push the event frame first (without id); continue reading frames until it gets a response with id==1 (set an upper limit to prevent an infinite loop).
            # leftover carries the extra bytes received in the last recv to ensure that no data is lost when recv reaches multiple frames at one time.
            buf = rest
            for _ in range(16):
                payload, buf = _read_ws_text_frame(sock, initial=buf)
                if payload is None:
                    return None
                data = json.loads(payload.decode("utf-8"))
                if data.get("id") != 1:
                    continue  # Event frames, etc.: skip, read next frame
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
    description = "Boss Zhipin Job Search and JD"
    backends = ["boss-agent-cli (CDP)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    def check(self, config=None):
        self.active_backend = None

        # Layer 1: boss-agent-cli installed or not
        probe = probe_command("boss", ["--version"], timeout=10)
        if probe.status == "missing":
            return "off", (
                "boss-agent-cli is not installed. Please obtain user authorization before running: \n"
                "  agent-reach install --system --channels=boss\n"
                "After installation, users manually log in to zhipin.com in dedicated Chrome."
            )
        if probe.status == "broken":
            return "error", (
                "The boss command exists but cannot be executed - the installation is corrupted. Reinstall: \n"
                "  agent-reach install --system --channels=boss"
            )
        if not probe.ok:
            return "warn", f"Boss command detection failed ({probe.status}), please check the installation"

        # Layer 2: Check CDP port reachability
        if _cdp_json("/json/version") is None:
            return "off", (
                "The CDP debug port is unreachable. Please start debugging Chrome first: \n"
                f"  {_chrome_launch_command()}\n"
                "  Then the user manually logs in to zhipin.com in this window. \n"
                "Only binds to 127.0.0.1; any process with access to 9222 will have full control of this Chrome."
            )

        # Layer 3: Is there a reusable BOSS tab?
        pages = _cdp_json("/json")
        if pages is None:
            return "warn", "CDP port is reachable but /json tab enumeration failed"
        if not _has_zhipin_page(pages):
            return "warn", (
                "CDP is reachable but no ready-made zhipin.com tab is found (it does not mean that you are not logged in: the cookie may still be there, "
                "boss-agent-cli will create new tabs by itself). It is recommended to log in to zhipin.com in Chrome first."
            )

        # Layer 4: In-browser login cookie (wt2). Subject to browser - `boss status` only verify
        # Local session.enc does not represent the browser login state.
        browser_cookie = _cdp_zhipin_login_cookie()
        if browser_cookie is False:
            return "warn", (
                "The CDP link is ready, but there is no zhipin.com login cookie in the dedicated Chrome browser (wt2) "
                "— the browser is not logged in, so search will report AUTH_EXPIRED. The logged_in value from `boss status` "
                "only describes local session.enc credentials. Ask the user to "
                "visually confirm login to zhipin.com in the dedicated Chrome window, then run "
                "`boss --cdp-url http://localhost:9222 login --cdp` to synchronize the session."
            )

        cookie_note = (
            "There is a login cookie in the browser (wt2)" if browser_cookie else "Browser login cookie detection failed, login status unknown"
        )

        if _security_check_blocks_all(pages):
            return "warn", (
                f"The CDP link is ready, but the existing zhipin tabs are stuck on the security verification page. "
                "(security-check/zhipin-security). This is a Boss anti-bot challenge and has nothing to do with logging in "
                "——It will also appear if you are logged in. It does not mean that you are not logged in. Do not ask the user to log in again based on this. "
                "Just let the user manually move the slider. "
                f"Browser login status reference: {cookie_note}. "
                "Do not use `boss status` to determine the CDP browser login status (it only verifies the local session.enc)."
            )

        # All four layers of detection passed: CDP link is ready, marking the actual backend in service (base contract)
        self.active_backend = self.backends[0]
        return "warn", (
            f"The CDP link is ready (9222 port is open + there is a reusable zhipin tab, {cookie_note}). "
            "Doctor does not actually perform searches, verify cookie server-side validity, or upstream boss-agent-cli #403-#407 API; "
            "First run `boss --cdp-url http://localhost:9222 login --cdp` to synchronize the existing login status; "
            "Use `boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...` when searching, "
            "If CDP is unavailable, stop the operation rather than falling back to headless. "
            "If the search reports AUTH_EXPIRED, process it according to the login runbook (the user logs in in a dedicated window + login --cdp). "
            "Do not treat AUTH_EXPIRED as an anti-bot challenge."
        )
