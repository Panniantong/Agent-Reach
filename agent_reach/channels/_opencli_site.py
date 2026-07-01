# -*- coding: utf-8 -*-
"""Shared channel helper for OpenCLI browser-session-only platforms."""

from urllib.parse import urlparse

from .base import Channel


class OpenCLISiteChannel(Channel):
    """A platform served directly by OpenCLI.

    These channels are intentionally thin: Agent Reach only installs,
    health-checks, and routes. Agents call `opencli <site> ...` directly.
    """

    site: str = ""
    domains: tuple[str, ...] = ()
    usage: str = ""
    login_hint: str = ""

    backends = ["OpenCLI"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        return any(domain == d or domain.endswith(f".{d}") for d in self.domains)

    def check(self, config=None):
        from agent_reach.backends import opencli_status

        self.active_backend = None
        st = opencli_status()
        if not st.installed:
            return "off", (
                f"未安装 {self.description} 后端。安装：\n"
                "  agent-reach install --channels opencli\n"
                f"然后在 Chrome 里登录 {self.login_hint}"
            )
        if st.broken:
            return "error", st.hint

        self.active_backend = "OpenCLI"
        if st.ready:
            return "ok", (
                f"OpenCLI 可用（复用浏览器登录态）。用法：{self.usage}。"
                f"若提示登录，请先在 Chrome 里登录 {self.login_hint}"
            )
        return "warn", st.hint
