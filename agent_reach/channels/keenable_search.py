# -*- coding: utf-8 -*-
"""Keenable Search — check if mcporter + Keenable MCP is available."""

from agent_reach.probe import probe_command

from .base import Channel

#: mcporter 是 npm 包，断链处方与默认的 pipx/uv 不同
_MCPORTER_BROKEN_HINT = "mcporter 无法执行（node 环境损坏），重装：\n  npm install -g mcporter"


class KeenableSearchChannel(Channel):
    name = "keenable_search"
    description = "全网搜索 + 网页抓取"
    backends = ["Keenable via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("mcporter", ["config", "list"], timeout=10, package="mcporter")
        if probe.status == "missing":
            return "off", (
                "需要 mcporter + Keenable MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add keenable https://api.keenable.ai/mcp"
            )
        if probe.status == "broken":
            return "error", _MCPORTER_BROKEN_HINT
        if not probe.ok:  # timeout / error
            return "error", f"mcporter 执行异常：{probe.hint or probe.output or probe.status}"
        if "keenable" in probe.output.lower():
            self.active_backend = self.backends[0]
            return "ok", "全网搜索 + 网页抓取可用（免费，无需 API Key）"
        return "off", (
            "mcporter 已装但 Keenable 未配置。运行：\n"
            "  mcporter config add keenable https://api.keenable.ai/mcp"
        )
