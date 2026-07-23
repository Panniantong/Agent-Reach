# -*- coding: utf-8 -*-
"""Linux.do — health-check the optional linuxdo-reader CLI."""

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from agent_reach.probe import probe_command

from .base import Channel

LINUXDO_READER_SOURCE = "git+https://github.com/kadaliao/linuxdo-reader.git@v0.3.1"
LINUXDO_INSTALL_COMMAND = "agent-reach install --channels=linuxdo"


def linuxdo_tool_executable(tool_dir: str, command: str) -> str:
    """Return an executable from linuxdo-reader's persistent uv tool environment."""
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return str(Path(tool_dir) / "linuxdo-reader" / scripts_dir / f"{command}{suffix}")


def _browser_ready() -> bool:
    try:
        tool_dir = subprocess.run(
            ["uv", "tool", "dir"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if tool_dir.returncode != 0 or not tool_dir.stdout.strip():
            return False

        python = linuxdo_tool_executable(tool_dir.stdout.strip(), "python")
        browser_probe = subprocess.run(
            [
                python,
                "-c",
                "import os; from playwright.sync_api import sync_playwright; "
                "p = sync_playwright().start(); path = p.chromium.executable_path; "
                "p.stop(); raise SystemExit(0 if os.path.isfile(path) else 1)",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        return browser_probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


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
            return "off", f"linuxdo-reader 未完整安装。安装：{LINUXDO_INSTALL_COMMAND}"
        if probe.status == "broken":
            self.active_backend = None
            return "error", (
                "linuxdo-reader 命令存在但无法执行。重装：\n"
                f"  {LINUXDO_INSTALL_COMMAND}"
            )
        if probe.status == "timeout":
            self.active_backend = None
            return "error", f"linuxdo-reader -h 响应超时。重装：{LINUXDO_INSTALL_COMMAND}"
        if not probe.ok:
            self.active_backend = None
            detail = probe.output or probe.hint or probe.status
            return "error", (
                f"linuxdo-reader 无法正常运行：{detail}。重装：{LINUXDO_INSTALL_COMMAND}"
            )
        if not _browser_ready():
            self.active_backend = None
            return "error", (
                "linuxdo-reader 已安装，但 Chromium browser fallback 未就绪。安装："
                f"{LINUXDO_INSTALL_COMMAND}"
            )

        self.active_backend = "linuxdo-reader CLI"
        return "ok", "可抓取、缓存并阅读 Linux.do 主题和讨论楼层"
