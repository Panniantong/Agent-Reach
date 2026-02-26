# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

import shutil
import subprocess
from .base import Channel


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "全网语义搜索"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        if not shutil.which("mcporter"):
            return "off", (
                "需要 mcporter + Exa MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        try:
            r = subprocess.run(
                ["mcporter", "list"], capture_output=True, text=True, timeout=10
            )
            if "exa" in r.stdout.lower():
                return "ok", "全网语义搜索可用（免费，无需 API Key）"
            return "off", (
                "mcporter 已装但 Exa 未配置。运行：\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        except Exception:
            return "off", "mcporter 连接异常"
