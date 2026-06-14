# -*- coding: utf-8 -*-
"""Reddit — multi-backend: OpenCLI / rdt-cli. Login is mandatory.

Honest tiering (live-verified 2026-06): there is NO zero-config path.
Anonymous .json endpoints are blocked (403 anti-bot, all variants), and
the official API closed self-service registration in 2025-11 (manual
approval, individual scripts rarely granted — PRAW is only an option for
users who already hold credentials). Every working backend rides a
logged-in session: OpenCLI reuses the browser's, rdt-cli imports cookies.
"""

import json
import shutil
import subprocess

from agent_reach.utils.process import utf8_subprocess_env

from .base import Channel

_CREDENTIAL_FILE = "~/.config/rdt-cli/credential.json"
# Pinned to the 0.4.2 state — PyPI still only has 0.4.1 (upstream issue #10).
_RDT_GIT_SOURCE = "git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66"

#: shell 对"找到但不可执行/找不到"使用的退出码（对齐 agent_reach.probe）
_BROKEN_EXIT_CODES = (126, 127)

#: rdt 应从固定 git 源安装（PyPI 落后），断链处方与 probe 默认的 pipx/uv 不同
_RDT_BROKEN_HINT = (
    "rdt 命令存在但无法执行——通常是系统 Python 升级后 venv 解释器丢失。\n"
    "PyPI 版本落后，推荐用固定 git 源强制重装：\n"
    f"  pipx install --force '{_RDT_GIT_SOURCE}'"
)


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"
    backends = ["OpenCLI", "rdt-cli"]
    tier = 1  # no zero-config path exists — see module docstring

    def can_handle(self, url: str) -> bool:
        from ..utils.urlmatch import host_matches

        return host_matches(url, "reddit.com", "redd.it")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_rdt()
            if result is None:
                continue
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "未安装任何 Reddit 后端。注意：Reddit 没有零配置路径"
            "（匿名 .json 已被封，官方 API 需人工审批），必须用登录态。推荐：\n"
            "  桌面：agent-reach install --channels opencli\n"
            "       （复用 Chrome 登录态，登录过 reddit.com 即可用）\n"
            f"  服务器/存量：pipx install '{_RDT_GIT_SOURCE}'\n"
            "       然后 `rdt login` 或手动写入 Cookie（见 doctor 提示）\n"
            "中国大陆访问 Reddit 需要代理"
        )

    def _check_opencli(self):
        """OpenCLI candidate. None = not installed."""
        from agent_reach.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "ok", (
                "OpenCLI 可用（复用浏览器登录态）。用法："
                "opencli reddit search/read/subreddit/hot -f yaml"
            )
        return "warn", st.hint

    def _check_rdt(self):
        """rdt-cli candidate. None = not installed."""
        rdt = shutil.which("rdt")
        if not rdt:
            return None

        # 不走 probe_command：实测 `rdt status --json` 成功时（rc=0）也会向 stderr
        # 打网络重试日志，probe 把 stdout+stderr 合并后 JSON 解析必炸。
        # 故保留手写 subprocess（stdout 单独捕获），但异常分类对齐 probe 语义：
        # exec 失败/126/127 → broken（venv 断链处方），TimeoutExpired → 超时。
        try:
            r = subprocess.run(
                [rdt, "status", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                env=utf8_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            return "error", "rdt 响应超时（>10s），Reddit 状态未知。稍后重试或运行 `rdt status` 查看详情"
        except OSError:
            # 含 FileNotFoundError：which 命中但 exec 失败 = venv 断链（probe 的 broken）
            return "error", _RDT_BROKEN_HINT

        if r.returncode in _BROKEN_EXIT_CODES:
            return "error", _RDT_BROKEN_HINT

        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else "无输出"
            return "error", f"rdt 异常退出（exit {r.returncode}）：{tail}。运行 `rdt status` 查看详情"

        # 进程正常退出 → rdt 本身是活的（无论登录与否）
        try:
            data = json.loads(r.stdout or "")
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return "warn", "rdt-cli 可用但状态输出无法解析，运行 `rdt status` 查看登录状态"

        info = data.get("data")
        if not isinstance(info, dict):
            info = {}
        authenticated = info.get("authenticated", False)
        username = info.get("username") or ""

        if authenticated:
            suffix = f"（已登录：{username}）" if username else ""
            return "ok", (
                f"rdt-cli 可用{suffix}（搜索帖子、阅读全文、查看评论；"
                "上游 2026-03 起停更，桌面用户建议迁移到 OpenCLI）"
            )

        return "warn", (
            "rdt-cli 已安装但未登录。Reddit 自 2024 年起要求认证，"
            "未登录时所有请求均返回 403。\n\n"
            "方法一（自动）：运行 `rdt login`\n"
            "  先在浏览器登录 reddit.com，再运行此命令自动提取 Cookie。\n\n"
            "方法二（手动，适用于 Chrome/Edge 127+ 无法自动提取时）：\n"
            "  1. Chrome 应用商店安装 Cookie-Editor 扩展：\n"
            "     https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm\n"
            "  2. 在浏览器打开 reddit.com（确保已登录）\n"
            "  3. 点击 Cookie-Editor 图标，找到 `reddit_session`，复制其 Value\n"
            f"  4. 将以下内容写入 {_CREDENTIAL_FILE}：\n"
            '     {"cookies": {"reddit_session": "<粘贴 Value>"}, '
            '"source": "manual", "username": "<你的用户名>", '
            '"modhash": null, "saved_at": 0, "last_verified_at": null}\n\n'
            "验证：`rdt status --json` 确认 authenticated: true"
        )
