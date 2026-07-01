# -*- coding: utf-8 -*-
"""Exa Search — check if mcporter + Exa MCP is available."""

from agent_reach.probe import probe_command

from .base import Channel

#: mcporter 是 npm 包，断链处方与默认的 pipx/uv 不同
_MCPORTER_BROKEN_HINT = "mcporter 无法执行（node 环境损坏），重装：\n  npm install -g mcporter"


class ExaSearchChannel(Channel):
    name = "exa_search"
    description = "全网语义搜索"
    backends = ["Exa via mcporter"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("mcporter", ["config", "list"], timeout=10, package="mcporter")
        if probe.status == "missing":
            return "off", (
                "需要 mcporter + Exa MCP。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
            )
        if probe.status == "broken":
            return "error", _MCPORTER_BROKEN_HINT
        if not probe.ok:  # timeout / error
            return "error", f"mcporter 执行异常：{probe.hint or probe.output or probe.status}"
        if "exa" in probe.output.lower():
            self.active_backend = self.backends[0]
            return "ok", "全网语义搜索可用（免费，无需 API Key）"
        return "off", (
            "mcporter 已装但 Exa 未配置。运行：\n"
            "  mcporter config add exa https://mcp.exa.ai/mcp --scope home"
        )
