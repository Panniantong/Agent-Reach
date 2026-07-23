# -*- coding: utf-8 -*-
"""Linux.do — health-check the optional linuxdo-reader CLI."""

from urllib.parse import urlparse

from agent_reach.probe import probe_command

from .base import Channel

LINUXDO_READER_SOURCE = "git+https://github.com/kadaliao/linuxdo-reader.git@v0.3.0"


def _install_command() -> str:
    return f"uv tool install '{LINUXDO_READER_SOURCE}' --with playwright --force"


class LinuxDoChannel(Channel):
    name = "linuxdo"
    description = "Linux.do 主题和讨论楼层"
    backends = ["linuxdo-reader CLI"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower().rstrip(".")
        return hostname == "linux.do" or hostname.endswith(".linux.do")

    def check(self, config=None):
        probe = probe_command(
            "linuxdo-reader",
            ["-h"],
            timeout=10,
            package=LINUXDO_READER_SOURCE,
        )
        if probe.status == "missing":
            self.active_backend = None
            return "off", f"linuxdo-reader 未安装。安装：{_install_command()}"
        if probe.status == "broken":
            self.active_backend = None
            return "error", (
                "linuxdo-reader 命令存在但无法执行。重装：\n"
                f"  {_install_command()}"
            )
        if probe.status == "timeout":
            self.active_backend = None
            return "error", "linuxdo-reader -h 响应超时，请重装或检查 uv tool 环境"
        if not probe.ok:
            self.active_backend = None
            detail = probe.output or probe.hint or probe.status
            return "error", f"linuxdo-reader 无法正常运行：{detail}"

        self.active_backend = "linuxdo-reader CLI"
        return "ok", "可抓取、缓存并阅读 Linux.do 主题和讨论楼层"
