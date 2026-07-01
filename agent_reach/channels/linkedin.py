# -*- coding: utf-8 -*-
"""LinkedIn — check if linkedin-scraper-mcp is available."""

from agent_reach.probe import probe_command

from .base import Channel

#: mcporter 是 npm 包，断链处方与默认的 pipx/uv 不同
_MCPORTER_BROKEN_HINT = "mcporter 无法执行（node 环境损坏），重装：\n  npm install -g mcporter"


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn 职业社交"
    backends = ["linkedin-scraper-mcp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.urls import host_matches
        return host_matches(url, "linkedin.com")

    def check(self, config=None):
        self.active_backend = None
        probe = probe_command("mcporter", ["config", "list"], timeout=10, package="mcporter")
        if probe.status == "missing":
            return "off", (
                "基本内容可通过 Jina Reader 读取。完整功能需要：\n"
                "  pip install linkedin-scraper-mcp\n"
                "  mcporter config add linkedin http://localhost:3000/mcp\n"
                "  详见 https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        if probe.status == "broken":
            return "error", _MCPORTER_BROKEN_HINT
        if not probe.ok:  # timeout / error
            return "error", f"mcporter 执行异常：{probe.hint or probe.output or probe.status}"
        if "linkedin" in probe.output.lower():
            self.active_backend = "linkedin-scraper-mcp"
            return "ok", "完整可用（Profile、公司、职位搜索）"
        return "off", (
            "mcporter 已装但 LinkedIn MCP 未配置。运行：\n"
            "  pip install linkedin-scraper-mcp\n"
            "  mcporter config add linkedin http://localhost:3000/mcp"
        )
