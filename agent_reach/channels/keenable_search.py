# -*- coding: utf-8 -*-
"""Keenable Search — check if mcporter + Keenable MCP is available."""

import shutil

from .base import Channel
from .mcporter import McporterConfigError, inspect_mcporter_config


class KeenableSearchChannel(Channel):
    name = "keenable_search"
    description = "全网搜索 + 网页抓取"
    backends = ["Keenable via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + Keenable MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add keenable https://api.keenable.ai/mcp --scope home"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter 配置检查失败：{exc}"
        if "keenable" in inspection.server_names:
            return "warn", (
                "Keenable 已写入 mcporter 配置，但 Doctor 未启动远端服务做"
                "连通验证，不能仅凭配置宣称可用。"
            )
        if inspection.imports_unchecked:
            return "warn", (
                "mcporter 本地配置未发现 Keenable；配置还启用了 editor imports，"
                "Doctor 为避免扩大凭据读取范围没有展开，当前未验证。"
            )
        return "off", (
            "mcporter 已装但 Keenable 未配置。运行：\n"
            "  mcporter config add keenable https://api.keenable.ai/mcp --scope home"
        )
