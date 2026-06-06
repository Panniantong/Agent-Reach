# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

import shutil
import subprocess
from .base import Channel


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "全网语义搜索"
    description_en = "Web semantic search"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        from agent_reach.lang import use_english

        mcporter = shutil.which("mcporter")
        if not mcporter:
            if use_english():
                return "off", (
                    "mcporter + Exa MCP required. Install:\n"
                    "  npm install -g mcporter\n"
                    "  mcporter config add exa https://mcp.exa.ai/mcp"
                )
            return "off", (
                "需要 mcporter + Exa MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "list"], capture_output=True,
                encoding="utf-8", errors="replace", timeout=5
            )
            if "exa" in r.stdout.lower():
                if use_english():
                    return "ok", "Web semantic search available (free, no API key needed)"
                return "ok", "全网语义搜索可用（免费，无需 API Key）"
            if use_english():
                return "off", (
                    "mcporter installed but Exa not configured. Run:\n"
                    "  mcporter config add exa https://mcp.exa.ai/mcp"
                )
            return "off", (
                "mcporter 已装但 Exa 未配置。运行：\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp"
            )
        except Exception:
            if use_english():
                return "off", "mcporter connection error"
            return "off", "mcporter 连接异常"
