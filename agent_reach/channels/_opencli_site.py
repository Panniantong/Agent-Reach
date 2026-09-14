# -*- coding: utf-8 -*-
"""Shared channel helper for OpenCLI browser-session-only platforms."""

from agent_reach.utils.url import host_matches

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
    requires_login: bool = True

    backends = ["OpenCLI"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return host_matches(url, *self.domains)

    def check(self, config=None):
        from agent_reach.backends import opencli_status

        self.active_backend = None
        st = opencli_status()
        if not st.installed:
            if self.requires_login:
                login_hint = f"然后在 Chrome 里登录 {self.login_hint}"
            else:
                login_hint = f"如页面要求登录，请在 Chrome 里登录 {self.login_hint}"
            return "off", (
                f"未安装 {self.description} 后端。安装：\n"
                "  agent-reach install --system --channels opencli\n"
                f"{login_hint}"
            )
        if st.broken:
            return "error", st.hint

        if st.ready:
            if self.requires_login:
                auth_hint = "登录态和实际命令未实时验证"
                action_hint = f"需要时请先在 Chrome 里登录 {self.login_hint}"
            else:
                auth_hint = "实际命令未实时验证"
                action_hint = f"如页面要求登录，请先在 Chrome 里登录 {self.login_hint}"
            return "warn", (
                f"OpenCLI 桥接已连接，但 {self.description} 的{auth_hint}；"
                "Doctor 不执行平台命令，因此当前不标记为可用。"
                f"{action_hint}"
            )
        return "warn", st.hint
