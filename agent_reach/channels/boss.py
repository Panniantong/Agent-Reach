# -*- coding: utf-8 -*-
"""Boss直聘 — 经 boss-agent-cli + CDP 真 Chrome 搜岗位、取 JD。

后端是 boss-agent-cli（CDP 调试端口复用已登录的真 Chrome）。headless 是禁区
（触发 code 36 风控），故 check() 只做四层只读探测，不实例化 BossClient、不拉起浏览器。

抓取走 boss-agent-cli 公开 API（search_jobs + job_card_browser + browser_source="existing-browser"），
调用姿势见 skill/references/career.md；check() 只负责「装没装 + CDP 链路就绪 +
浏览器内有无登录 cookie」的体检，不搜索。

双登录态存储（体检必须区分，历史教训）。两者都是必需的，但认证的是不同通道：

- `~/.boss-agent/auth/session.enc`（`boss status` / `status --live` 只校验它）
  1. 是硬性门槛：`_get_browser()` 无条件 `get_token()`，读不到就 `AuthRequired`，
     所以别删它——CDP 搜索会在连上浏览器之前就失败；
  2. 但**不是搜索的认证凭据**：CDP 连上真 Chrome 后复用 `contexts[0]`，其 cookies
     只在「没有任何 context」的分支才注入，实际从未生效；
  3. httpx 通道（低危 op：status/detail/cities/`job_card_httpx`）真用它的
     cookies + stoken；code 37 的 `force_refresh()` 也回写它。
- 专用 Chrome profile 内的浏览器 cookie：CDP 模式下 search/greet 等高危 op
  实际携带的凭据。

所以 session.enc 有效 + 浏览器未登录 = `boss status` 报已登录但搜索报
`AUTH_EXPIRED`。第 4 层直接问 CDP 浏览器本体（Storage.getCookies），以浏览器为准。
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
    """GET 本地 CDP 端点（禁用系统代理），返回解析后的 JSON；失败返回 None。

    CDP 只绑定回环地址（127.0.0.1），直连即可，故用空 ProxyHandler 显式绕过任何
    已配置的系统/全局代理——localhost 探测走代理既无意义也可能被拦截。这是有意的
    localhost-only 假设，不可被 config 的 proxy 覆盖。
    """
    req = urllib.request.Request(f"{_CDP_URL}{path}", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=_CDP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _has_zhipin_page(pages) -> bool:
    """CDP /json 页签列表里是否存在可复用的 zhipin.com 页签（精确 hostname 校验）。"""
    for page in pages or []:
        if page.get("type") == "page" and host_matches(page.get("url", ""), "zhipin.com"):
            return True
    return False


_SECURITY_CHECK_MARKERS = ("security-check", "zhipin-security", "_security_check")


def _security_check_blocks_all(pages) -> bool:
    """现有 zhipin 页签是否全部停在反爬安全校验页（不是登录页）。"""
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
    """读下一个文本帧，返回 (payload, leftover)。

    leftover 是本次 recv 多收、属于后续帧的字节，调用方应把它作为下一帧的 initial
    传回（一次 recv 可能拿到多帧）。收到 close 帧或连接断开返回 (None, leftover)。
    忽略 ping/pong。
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
        # ping(0x9)/pong(0xA) 等：忽略，继续读下一帧


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
    """只读探测专用 Chrome 浏览器内的 zhipin.com 登录 cookie（wt2）。

    True=有；False=没有（浏览器未登录，CDP 搜索会报 AUTH_EXPIRED）；
    None=探测失败（CDP WebSocket 不可达等），登录态未知。
    只证明浏览器 profile 登录过，不验证 cookie 的服务端有效性。
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
            # IPv6 字面量需在 Host 头里加方括号（urlparse().hostname 已剥掉）
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
            # 精确解析状态码 token：接受 "HTTP/1.1 101"（可空 reason 短语），拒绝 1019 等伪码
            if status_line.split()[1:2] != [b"101"]:
                return None
            accept = base64.b64encode(
                hashlib.sha1((key + _WS_ACCEPT_GUID).encode()).digest()
            ).decode()
            if accept not in head.decode("latin-1"):
                return None
            _send_ws_text(sock, json.dumps({"id": 1, "method": "Storage.getCookies"}))
            # Chrome 可能先推事件帧（无 id）；持续读帧直到拿到 id==1 的响应（设上限防死循环）。
            # leftover 携带上次 recv 多收的字节，确保一次 recv 到多帧时不丢数据。
            buf = rest
            for _ in range(16):
                payload, buf = _read_ws_text_frame(sock, initial=buf)
                if payload is None:
                    return None
                data = json.loads(payload.decode("utf-8"))
                if data.get("id") != 1:
                    continue  # 事件帧等：跳过，读下一帧
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
    description = "Boss直聘 职位搜索与 JD"
    backends = ["boss-agent-cli (CDP)"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    def check(self, config=None):
        self.active_backend = None

        # 层 1：boss-agent-cli 装没装
        probe = probe_command("boss", ["--version"], timeout=10)
        if probe.status == "missing":
            return "off", (
                "boss-agent-cli 未安装。请先获得用户授权，再运行：\n"
                "  agent-reach install --system --channels=boss\n"
                "安装后由用户在专用 Chrome 中手动登录 zhipin.com。"
            )
        if probe.status == "broken":
            return "error", (
                "boss 命令存在但无法执行——安装已损坏。重装：\n"
                "  agent-reach install --system --channels=boss"
            )
        if not probe.ok:
            return "warn", f"boss 命令探测失败（{probe.status}），请检查安装"

        # 层 2：CDP 端口通不通
        if _cdp_json("/json/version") is None:
            return "off", (
                "CDP 调试端口不可达。请先启动调试 Chrome：\n"
                f"  {_chrome_launch_command()}\n"
                "  然后由用户在该窗口手动登录 zhipin.com。\n"
                "仅绑定 127.0.0.1；任何能访问 9222 的进程都可完全控制这个 Chrome。"
            )

        # 层 3：有无可复用 BOSS 页签
        pages = _cdp_json("/json")
        if pages is None:
            return "warn", "CDP 端口可达但 /json 页签枚举失败"
        if not _has_zhipin_page(pages):
            return "warn", (
                "CDP 可达但未发现现成 zhipin.com 页签（不代表未登录：Cookie 可能仍在，"
                "boss-agent-cli 会自行新建页签）。建议先在 Chrome 登录 zhipin.com。"
            )

        # 层 4：浏览器内登录 cookie（wt2）。以浏览器为准——`boss status` 只校验
        # 本地 session.enc，与浏览器登录态互不代表。
        browser_cookie = _cdp_zhipin_login_cookie()
        if browser_cookie is False:
            return "warn", (
                "CDP 链路就绪，但专用 Chrome 浏览器内没有 zhipin.com 登录 cookie（wt2）"
                "——浏览器未登录，搜索会报 AUTH_EXPIRED。注意 `boss status` 报的 logged_in "
                "只代表本地 session.enc 凭据，不代表浏览器已登录。请让用户在该 Chrome 窗口"
                "肉眼确认并登录 zhipin.com（拉起 CDP Chrome 后应先做这一步），然后运行 "
                "`boss --cdp-url http://localhost:9222 login --cdp` 同步登录态。"
            )

        cookie_note = (
            "浏览器内有登录 cookie（wt2）" if browser_cookie else "浏览器登录 cookie 探测失败，登录态未知"
        )

        if _security_check_blocks_all(pages):
            return "warn", (
                f"CDP 链路就绪，但现有 zhipin 页签都停在安全校验页"
                "（security-check / zhipin-security）。这是 Boss 反爬挑战，与登录无关"
                "——已登录也会出现，不代表未登录，不要据此要求用户重新登录，"
                "让用户手动过滑块即可。"
                f"浏览器登录态参考：{cookie_note}。"
                "不要用 `boss status` 判断 CDP 浏览器登录态（它只校验本地 session.enc）。"
            )

        # 四层探测全过：CDP 链路就绪，标记实际服役的后端（base 契约）
        self.active_backend = self.backends[0]
        return "warn", (
            f"CDP 链路就绪（9222 端口通 + 有可复用 zhipin 页签，{cookie_note}）。"
            "Doctor 不实际执行搜索、不验证 cookie 服务端有效性或上游 boss-agent-cli #403-#407 API；"
            "先运行 `boss --cdp-url http://localhost:9222 login --cdp` 同步现有登录态；"
            "搜索时使用 `boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`，"
            "确保 CDP 不可用时立即停止而不是降级 headless。"
            "若搜索报 AUTH_EXPIRED，按登录 runbook 处理（用户在专用窗口登录 + login --cdp），"
            "不要往安全校验方向解释。"
        )
