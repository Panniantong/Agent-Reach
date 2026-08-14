# -*- coding: utf-8 -*-
"""Boss直聘 — 经 boss-agent-cli + CDP 真 Chrome 搜岗位、取 JD。

后端是 boss-agent-cli（CDP 调试端口复用已登录的真 Chrome）。headless 是禁区
（触发 code 36 风控），故 check() 只做三层只读探测，不实例化 BossClient、不拉起浏览器。

抓取走 boss-agent-cli 公开 API（search_jobs + job_card_browser + browser_mode="cdp_required"），
调用姿势见 skill/references/career.md；check() 只负责「装没装 + CDP 链路就绪」的体检，不搜索。
"""

import json
import platform
import urllib.request

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
    """GET 本地 CDP 端点（禁用系统代理），返回解析后的 JSON；失败返回 None。"""
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

        return "warn", (
            "CDP 链路就绪（9222 端口通 + 有可复用 zhipin 页签）。"
            "Doctor 不实际执行搜索、不验证登录态 liveness 或 PR #382 API；"
            "先运行 `boss --cdp-url http://localhost:9222 login --cdp` 同步现有登录态；"
            "搜索时使用 `boss --browser-mode cdp-required --cdp-url http://localhost:9222 search ...`，"
            "确保 CDP 不可用时立即停止而不是降级 headless。"
        )
