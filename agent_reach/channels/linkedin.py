# -*- coding: utf-8 -*-
"""LinkedIn diagnostics for configured mcp-server-linkedin backends."""

import shutil

from .base import Channel
from .hermes import HermesConfigError, inspect_hermes_mcp_config
from .mcporter import McporterConfigError, inspect_mcporter_config

_LINKEDIN_SERVER_NAMES = {
    "linkedin",
    # Legacy aliases remain detectable for existing mcporter configurations.
    "linkedin-scraper",
    "linkedin-scraper-mcp",
    "mcp-server-linkedin",
}


class LinkedInChannel(Channel):
    name = "linkedin"
    description = "LinkedIn 职业社交"
    backends = ["mcp-server-linkedin", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "linkedin.com")

    def check(self, config=None):
        self.active_backend = None
        try:
            hermes = inspect_hermes_mcp_config()
        except HermesConfigError as exc:
            return "error", f"Hermes MCP 配置检查失败：{exc}"
        if hermes.server_names & _LINKEDIN_SERVER_NAMES:
            return "warn", (
                "LinkedIn MCP 已写入 Hermes 原生配置，但 Doctor 未启动本地"
                "服务做连通验证，不能仅凭配置宣称完整可用。"
            )

        if not shutil.which("mcporter"):
            return "off", (
                "基本内容可通过 Jina Reader 读取。完整功能需要 LinkedIn MCP。\n"
                "  Hermes: hermes mcp add linkedin --command uvx "
                "--args mcp-server-linkedin==4.20.0\n"
                "  详见 https://github.com/stickerdaniel/linkedin-mcp-server"
            )
        try:
            inspection = inspect_mcporter_config()
        except McporterConfigError as exc:
            return "error", f"mcporter 配置检查失败：{exc}"
        if inspection.server_names & _LINKEDIN_SERVER_NAMES:
            return "warn", (
                "LinkedIn MCP 已写入 mcporter 配置，但 Doctor 未启动本地"
                "服务做连通验证，不能仅凭配置宣称完整可用。"
            )
        if inspection.imports_unchecked:
            return "warn", (
                "mcporter 本地配置未发现 LinkedIn MCP；配置还启用了 editor "
                "imports，Doctor 为避免扩大凭据读取范围没有展开，当前未验证。"
            )
        return "off", (
            "mcporter 已装但 LinkedIn MCP 未配置。推荐：\n"
            "  Hermes: hermes mcp add linkedin --command uvx "
            "--args mcp-server-linkedin==4.20.0\n"
            "  或在 mcporter 中配置同名 LinkedIn MCP 服务器"
        )
