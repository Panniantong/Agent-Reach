# -*- coding: utf-8 -*-
"""Telegram — tg-cli（MTProto 用户账号，本地优先同步/搜索/导出）。

单后端：tg-cli（PyPI 包 kabi-tg-cli，命令 `tg`）。它用你自己的 Telegram 账号
走 MTProto（不是 Bot API），把对话同步进本地 SQLite 供人和 Agent 查询。
健康信号取 `tg status`：已登录时退出码 0，未登录时非零退出——退出码即认证态。

自带 Telegram Desktop API 凭据，首次运行 `tg chats` 输入手机号+验证码即可登录，
无需自建应用（也可用 TG_API_ID / TG_API_HASH 覆盖，见 guides/setup-telegram.md）。
"""

from agent_reach.probe import probe_command

from .base import Channel


class TelegramChannel(Channel):
    name = "telegram"
    description = "Telegram 对话与频道消息"
    backends = ["tg-cli"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "t.me" in d or "telegram.me" in d or "telegram.dog" in d

    def check(self, config=None):
        """探测唯一后端 tg-cli；ok 直接当选，warn 兜底给出处方。"""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "tg-cli":
                result = self._check_tg_cli()
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
            "未安装 tg-cli。安装方式：\n"
            "  uv tool install kabi-tg-cli\n"
            "或：pipx install kabi-tg-cli\n"
            "装好后运行 `tg chats` 完成手机号登录（详见 setup-telegram.md）"
        )

    def _check_tg_cli(self):
        """探测 tg-cli。返回 None 表示未安装，否则返回 (status, message)。

        `tg status` 才是健康信号：已登录退出码 0；未登录时非零退出——工具进程
        是活的，业务态归为 warn。
        """
        probe = probe_command(
            "tg", ["status"], timeout=15, retries=1, package="kabi-tg-cli"
        )
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "tg 命令存在但无法执行。\n" + probe.hint
        if probe.status == "timeout":
            return "error", "tg-cli 健康检查超时（已重试 1 次）。\n" + probe.hint

        if probe.ok:  # 退出码 0 == 已登录
            return "ok", (
                "tg-cli 完整可用（同步对话、读历史、搜索、导出、实时监听）"
            )

        # 进程活着但非零退出——业务态，多为未登录
        return "warn", (
            "tg-cli 已安装但未登录。运行：\n"
            "  tg chats\n"
            "（首次运行输入手机号+验证码完成登录）"
        )
