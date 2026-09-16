# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel.

Boss直聘 走 CDP 调试端口复用已登录的真 Chrome（headless 是禁区，code 36 风控）。
check() 只做只读探测：boss-agent-cli 装没装 → CDP 端口通不通 → 有无可复用
zhipin 页签 → 浏览器内有无登录 cookie（wt2）→ 页签是否都停在反爬安全校验页。
各分支各自返回 (status, message)，且永不触发浏览器启动（无副作用）。

注意 `boss status` 只校验本地 session.enc，不代表 CDP 浏览器已登录——第 4 层
以浏览器本体（Storage.getCookies）为准。
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
        "https://zhipin.com/web/geek/job?query=大模型",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url


# --- check() 四分支 ---

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
    # 就绪路径：check() 必须标记实际服役的后端（base 契约，doctor --json 不再恒 null）
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
    assert "登录态未知" in message
    # 链路已就绪（端口通 + 有页签），仅登录态未知 → 仍标记服役后端
    assert ch.active_backend == ch.backends[0]


def test_check_warn_when_browser_not_logged_in():
    """浏览器内无 wt2 → 明确提示未登录，且指出 boss status 只代表 session.enc。"""
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
    assert "安全校验" in message
    assert "不代表未登录" in message
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


# --- _cdp_zhipin_login_cookie 的 WebSocket 客户端（doctor 只读探测 wt2）---

# 固定 urandom → 固定 Sec-WebSocket-Key，使 accept 可预先算准
_FIXED_KEY16 = b"\x01" * 16
_FIXED_KEY = base64.b64encode(_FIXED_KEY16).decode()
_FIXED_ACCEPT = base64.b64encode(
    hashlib.sha1((_FIXED_KEY + boss_mod._WS_ACCEPT_GUID).encode()).digest()
).decode()


def _ws_frame(payload: dict) -> bytes:
    """构造一个服务器→客户端的无 mask 文本帧。"""
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
    """按顺序吐出预设字节流的假 socket，记录 sendall 内容。"""

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
    """用假 socket 跑 _cdp_zhipin_login_cookie，返回 (结果, 假socket)。"""
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
    """#1：事件帧（无 id）先于响应帧到达，仍应读到 id==1 的响应并识别 wt2。"""
    event = _ws_frame({"method": "Storage.cookiesChanged", "params": {}})
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), event + _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_accepts_empty_reason_phrase(monkeypatch):
    """#2：RFC 合法的空 reason 短语 'HTTP/1.1 101'（无尾部空格）应被接受。"""
    chunks = [_handshake(b"HTTP/1.1 101"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is True


def test_ws_probe_rejects_bogus_1019(monkeypatch):
    """#2：伪码 1019（含 ' 101 ' 子串）不应被当作成功升级。"""
    chunks = [_handshake(b"HTTP/1.1 1019 Weird"), _WT2_RESULT]
    result, _ = _run_ws_probe(monkeypatch, chunks)
    assert result is None


def test_ws_probe_ipv6_host_header_bracketed(monkeypatch):
    """#3：IPv6 回环的 webSocketDebuggerUrl，Host 头必须带方括号。"""
    chunks = [_handshake(b"HTTP/1.1 101 Switching Protocols"), _WT2_RESULT]
    result, sock = _run_ws_probe(monkeypatch, chunks, ws_url="ws://[::1]:9222/devtools/browser/x")
    assert result is True
    assert b"Host: [::1]:9222\r\n" in sock.sent
