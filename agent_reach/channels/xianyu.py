# -*- coding: utf-8 -*-
"""Xianyu (闲鱼) — check if mcporter + mcp-goofish is available."""

import platform
import shutil
import subprocess
from typing import Optional

from .base import Channel


def _configured_alias(stdout: str) -> Optional[str]:
    """Return the configured mcporter entry name for Xianyu."""
    text = stdout.lower()
    if "xianyu" in text:
        return "xianyu"
    if "goofish" in text:
        return "goofish"
    return None


class XianyuChannel(Channel):
    name = "xianyu"
    description = "闲鱼二手商品"
    backends = ["mcp-goofish"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "goofish.com" in d or "xianyu.taobao.com" in d

    def check(self, config=None):
        if not shutil.which("node"):
            return "off", (
                "需要 Node.js ≥18 + mcporter + mcp-goofish。安装步骤：\n"
                "  1. 安装 Node.js ≥18：https://nodejs.org\n"
                "  2. npm install -g mcporter\n"
                "  3. mcporter config add xianyu --command 'npx' --args 'mcp-goofish'\n"
                "  4. 按 mcp-goofish 文档完成闲鱼登录态 / Cookie 配置\n"
                "  详见 https://github.com/mercy719/mcp-goofish"
            )

        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "需要 mcporter。安装：\n"
                "  npm install -g mcporter\n"
                "  mcporter config add xianyu --command 'npx' --args 'mcp-goofish'\n"
                "  然后按 mcp-goofish 文档配置闲鱼 Cookie / 登录态"
            )

        is_windows = platform.system() == "Windows"
        config_timeout = 15 if is_windows else 5
        try:
            r = subprocess.run(
                [mcporter, "config", "list"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=config_timeout,
            )
            alias = _configured_alias(r.stdout)
            if not alias:
                return "off", (
                    "mcporter 已装但闲鱼 MCP 未配置。运行：\n"
                    "  mcporter config add xianyu --command 'npx' --args 'mcp-goofish'\n"
                    "  然后按 mcp-goofish 文档配置闲鱼 Cookie / 登录态"
                )
        except Exception:
            return "off", "mcporter 连接异常"

        list_timeout = 30 if is_windows else 15
        try:
            r = subprocess.run(
                [mcporter, "list", alias],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=list_timeout,
            )
            stdout = r.stdout.strip().lower()
            stderr = r.stderr.strip().lower()
            if (
                r.returncode == 0
                and stdout
                and "tools unavailable" not in stdout
                and "connection closed" not in stdout
                and "npm error" not in stderr
            ):
                return "ok", "完整可用（商品搜索、详情查询、关键词监控）"
            return "warn", "MCP 已连接但工具列表为空，检查 mcp-goofish 服务和闲鱼登录态是否正常"
        except subprocess.TimeoutExpired:
            return "warn", "MCP 已配置，但健康检查超时；检查 mcp-goofish 服务和闲鱼 Cookie / 登录态"
        except Exception:
            return "warn", "MCP 连接异常，检查 mcp-goofish 服务和闲鱼登录态是否正常"
