# -*- coding: utf-8 -*-
"""Discord — discord-cli（用户 token，本地优先同步/搜索/导出）。

单后端：discord-cli（PyPI 包 kabi-discord-cli，命令 `discord`）。它用本地
Discord/浏览器会话里的 **user token** 走 Discord HTTP API，把消息同步进本地
SQLite 供人和 Agent 查询。健康信号取 `discord status`：已登录时退出码 0，
未认证/token 失效时非零退出并输出 not_authenticated——所以退出码就是认证态，
无需解析富文本。

风险提示：user token 自动化违反 Discord ToS，可能触发风控封号，务必只在
自己的、可承受风险的账号上使用（见 guides/setup-discord.md）。
"""

from agent_reach.probe import probe_command

from .base import Channel


class DiscordChannel(Channel):
    name = "discord"
    description = "Discord 服务器与频道消息"
    backends = ["discord-cli"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "discord.com" in d or "discord.gg" in d or "discordapp.com" in d

    def check(self, config=None):
        """探测唯一后端 discord-cli；ok 直接当选，warn 兜底给出处方。"""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "discord-cli":
                result = self._check_discord_cli()
            else:
                continue
            if result is None:
                continue  # 未安装——不参与候选
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend
                    return status, message

        if findings:  # 只剩 broken/timeout 候选
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "未安装 discord-cli。安装方式：\n"
            "  uv tool install kabi-discord-cli\n"
            "或：pipx install kabi-discord-cli\n"
            "装好后运行 `discord auth --save` 登录（详见 setup-discord.md）"
        )

    def _check_discord_cli(self):
        """探测 discord-cli。返回 None 表示未安装，否则返回 (status, message)。

        `discord status` 才是健康信号：已登录退出码 0；未认证时非零退出并输出
        not_authenticated——工具进程是活的，业务态归为 warn。
        """
        probe = probe_command(
            "discord", ["status"], timeout=15, retries=1, package="kabi-discord-cli"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "discord 命令存在但无法执行。\n" + probe.hint
        if probe.status == "timeout":
            return "error", "discord-cli 健康检查超时（已重试 1 次）。\n" + probe.hint

        if probe.ok:  # 退出码 0 == 已认证
            return "ok", (
                "discord-cli 完整可用（列服务器/频道、读历史、搜索、导出、AI 分析）"
            )

        # 进程活着但非零退出——业务态，多为未认证
        output = probe.output
        if "not_authenticated" in output or "invalid_token" in output:
            return "warn", (
                "discord-cli 已安装但未认证。运行：\n"
                "  discord auth --save\n"
                "（自动从本地 Discord/浏览器会话提取 user token）"
            )
        return "warn", (
            "discord-cli 已安装但状态检查失败。运行：\n"
            "  discord status 查看详细信息"
        )
