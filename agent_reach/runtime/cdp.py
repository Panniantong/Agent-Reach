"""Minimal Chrome DevTools Protocol client for the Agent Reach browser (127.0.0.1 only).

Only used against the dedicated browser, never the user's own Chrome.
Two transports: the 127.0.0.1 debugging port (`call`, any process) and the
launch pipe (`PipeConnection`, only the idle watcher, which owns the browser).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import urllib.request
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .browser import CDP_URL

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_TIMEOUT = 5


def _json(path: str):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never proxy
    try:
        with opener.open(f"{CDP_URL}{path}", timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return None


def _read_frame(sock: socket.socket, buf: bytes):
    while True:
        while len(buf) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        opcode, length, head = buf[0] & 0x0F, buf[1] & 0x7F, 2
        if length in (126, 127):
            need = 2 if length == 126 else 8
            while len(buf) < head + need:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">H" if need == 2 else ">Q", buf[head:head + need])[0]
            head += need
        while len(buf) < head + length:
            chunk = sock.recv(65536)
            if not chunk:
                return None, buf
            buf += chunk
        payload, buf = buf[head:head + length], buf[head + length:]
        if opcode == 0x8:
            return None, buf
        if opcode in (0x0, 0x1, 0x2):
            return payload, buf


def _send(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    n = len(payload)
    head = bytes([0x81]) + (
        bytes([0x80 | n]) if n < 126
        else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
        else bytes([0x80 | 127]) + struct.pack(">Q", n)
    )
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def call(method: str, params: Optional[dict] = None, *, page: bool = False,
         target_id: Optional[str] = None) -> Optional[dict]:
    """One browser-level CDP call; returns `result` or None if unreachable."""
    target = (next((t for t in (_json("/json/list") or []) if
                    (t.get("id") == target_id if target_id else t.get("type") == "page")), {})
              if page or target_id else (_json("/json/version") or {}))
    ws = target.get("webSocketDebuggerUrl")
    if not ws:
        return None
    u = urlparse(ws)
    host, port = u.hostname or "127.0.0.1", u.port or 80
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT) as sock:
            sock.settimeout(_TIMEOUT)
            key = base64.b64encode(os.urandom(16)).decode()
            sock.sendall(
                (f"GET {u.path or '/'} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                 f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
            )
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                resp += chunk
            head, _, buf = resp.partition(b"\r\n\r\n")
            accept = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
            if head.split(b"\r\n", 1)[0].split()[1:2] != [b"101"] or accept not in head.decode("latin-1"):
                return None
            _send(sock, json.dumps({"id": 1, "method": method, "params": params or {}}))
            for _ in range(32):
                payload, buf = _read_frame(sock, buf)
                if payload is None:
                    return None
                msg = json.loads(payload.decode("utf-8"))
                if msg.get("id") == 1:
                    return msg.get("result")
    except Exception:  # noqa: BLE001
        return None
    return None


def domain_matches(cookie_domain: str, domain: str) -> bool:
    """`cookie_domain` is `domain` or one of its subdomains (".a.reddit.com" yes, "notreddit.com" no)."""
    c, d = cookie_domain.lstrip(".").lower(), domain.lstrip(".").lower()
    return c == d or c.endswith("." + d)


def cookies(domain: str) -> List[dict]:
    """Cookies the dedicated browser holds for `domain` (and its subdomains)."""
    result = call("Storage.getCookies") or {}
    return [c for c in result.get("cookies", []) if domain_matches(c.get("domain", ""), domain)]


def extension_value(key: str) -> Optional[str]:
    """A string an extension saved in `chrome.storage.local` inside the dedicated browser, or None."""
    expr = f"chrome.storage.local.get({json.dumps(key)}).then(r => r[{json.dumps(key)}] || null)"
    for target in _json("/json/list") or []:
        if target.get("type") != "service_worker" or not target.get("url", "").startswith("chrome-extension://"):
            continue
        result = call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True},
                      target_id=target.get("id"))
        value = ((result or {}).get("result") or {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class PipeConnection:
    """CDP over `--remote-debugging-pipe`: NUL-delimited JSON, we write `wfd`, read `rfd`.

    A reader thread drains the pipe for as long as the browser lives (an
    undrained pipe would stall Chrome); `closed` is set when Chrome exits.
    Closing our write end makes Chrome exit.
    """

    def __init__(self, wfd: int, rfd: int) -> None:
        self._wfd, self._rfd = wfd, rfd
        self._lock = threading.Lock()
        self._next_id = 0
        self._waiting: Dict[int, list] = {}
        self.closed = threading.Event()
        threading.Thread(target=self._read_loop, name="cdp-pipe", daemon=True).start()

    def _read_loop(self) -> None:
        buf = b""
        try:
            while True:
                chunk = os.read(self._rfd, 65536)
                if not chunk:
                    break
                buf += chunk
                while b"\0" in buf:
                    raw, buf = buf.split(b"\0", 1)
                    try:
                        msg = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        continue
                    with self._lock:
                        message_id = msg.get("id") if isinstance(msg, dict) else None
                        slot = self._waiting.get(message_id) if isinstance(message_id, int) else None
                    if slot is not None:
                        slot.append(msg)
                        slot[0].set()
        except OSError:
            pass
        finally:
            self.closed.set()
            with self._lock:
                for slot in self._waiting.values():
                    slot[0].set()

    def call(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict:
        """Send one command; returns the whole reply ({"result": ...} or {"error": ...})."""
        with self._lock:
            self._next_id += 1
            msg_id = self._next_id
            slot: list = [threading.Event()]
            self._waiting[msg_id] = slot
        try:
            if self.closed.is_set():
                return {"error": {"message": "browser closed"}}
            data = json.dumps({"id": msg_id, "method": method, "params": params or {}}).encode("utf-8") + b"\0"
            try:
                while data:
                    data = data[os.write(self._wfd, data):]
            except OSError as exc:
                return {"error": {"message": f"pipe write failed: {exc}"}}
            if not slot[0].wait(timeout) or len(slot) < 2:
                return {"error": {"message": "browser closed" if self.closed.is_set() else f"no reply in {timeout:.0f}s"}}
            return slot[1]
        finally:
            with self._lock:
                self._waiting.pop(msg_id, None)

    def close(self) -> None:
        """Close our write end (Chrome exits); the reader thread closes the read end when it stops."""
        try:
            os.close(self._wfd)
        except OSError:
            pass
        if self.closed.wait(15):
            try:
                os.close(self._rfd)
            except OSError:
                pass
