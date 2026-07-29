"""Indeed job search through a configured JobSpy MCP backend."""

from __future__ import annotations

import shutil

from .base import Channel
from .hermes import HermesConfigError, inspect_hermes_mcp_config
from .mcporter import McporterConfigError, inspect_mcporter_config

_JOBSPY_SERVER_NAMES = {
    "indeed",
    "jobspy",
    "jobspy-mcp",
    "jobspy-mcp-server",
}
_INDEED_DOMAINS = (
    "indeed.com",
    "indeed.co.uk",
    "indeed.ca",
    "indeed.com.au",
    "indeed.de",
    "indeed.fr",
    "indeed.nl",
    "indeed.se",
    "indeed.no",
    "indeed.fi",
    "indeed.es",
    "indeed.it",
    "indeed.ch",
    "indeed.ie",
    "indeed.co.in",
    "indeed.co.jp",
    "indeed.com.br",
    "indeed.com.mx",
    "indeed.co.za",
    "indeed.ae",
    "indeed.sg",
    "indeed.hk",
    "indeed.co.kr",
    "indeed.co.nz",
)


class IndeedChannel(Channel):
    name = "indeed"
    description = "Indeed 职位搜索"
    backends = ["JobSpy MCP", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, *_INDEED_DOMAINS)

    def check(self, config=None):
        self.active_backend = None
        try:
            hermes = inspect_hermes_mcp_config()
        except HermesConfigError as exc:
            return "error", f"Hermes MCP 配置检查失败：{exc}"
        if hermes.server_names & _JOBSPY_SERVER_NAMES:
            return "warn", (
                "JobSpy MCP 已写入 Hermes 原生配置，但 Doctor 未启动本地"
                "服务做连通验证，不能仅凭配置宣称 Indeed 搜索可用。"
            )

        if shutil.which("mcporter"):
            try:
                inspection = inspect_mcporter_config()
            except McporterConfigError as exc:
                return "error", f"mcporter 配置检查失败：{exc}"
            if inspection.server_names & _JOBSPY_SERVER_NAMES:
                return "warn", (
                    "JobSpy MCP 已写入 mcporter 配置，但 Doctor 未启动本地"
                    "服务做连通验证，不能仅凭配置宣称 Indeed 搜索可用。"
                )
            if inspection.imports_unchecked:
                return "warn", (
                    "Hermes 和 mcporter 本地配置未发现 JobSpy MCP；mcporter "
                    "还启用了 editor imports，Doctor 未展开这些文件。"
                )

        return "off", (
            "Indeed 搜索需要配置名为 jobspy 或 indeed 的 JobSpy MCP。"
            "单个公开职位页可尝试 Jina Reader。\n"
            "  参考：https://github.com/speedyapply/JobSpy"
        )
