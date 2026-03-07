# -*- coding: utf-8 -*-
"""Boss直聘 — check if mcp-bosszp is available."""

import shutil
import subprocess
from .base import Channel


class BossZhipinChannel(Channel):
    name = "bosszhipin"
    description = "Boss直聘职位搜索"
    backends = ["mcp-bosszp", "Jina Reader"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        return "zhipin.com" in domain or "boss.com" in domain

    def check(self, config=None):
        mcporter = shutil.which("mcporter")
        if not mcporter:
            return "off", (
                "可通过 Jina Reader 读取职位页面。完整功能需要：\n"
                "  1. git clone https://github.com/mucsbr/mcp-bosszp.git\n"
                "  2. cd mcp-bosszp && pip install -r requirements.txt && playwright install chromium\n"
                "  3. python boss_zhipin_fastmcp_v2.py（启动后扫码登录）\n"
                "  4. mcporter config add bosszhipin http://localhost:8000/mcp"
            )
        try:
            r = subprocess.run(
                [mcporter, "config", "get", "bosszhipin", "--json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if r.returncode != 0 or "bosszhipin" not in r.stdout.lower():
                return "off", (
                    "mcporter 已装但 Boss直聘 MCP 未配置。\n"
                    "  详见 https://github.com/mucsbr/mcp-bosszp"
                )
        except Exception:
            return "off", "mcporter 连接异常"

        try:
            r = subprocess.run(
                [mcporter, "call", "bosszhipin.get_login_info_tool", "--output", "json"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            out = r.stdout.lower()
            if r.returncode == 0 and "\"is_logged_in\": true" in out:
                return "ok", "完整可用（职位搜索、登录态检查、向 HR 打招呼）"
            if r.returncode == 0:
                return "ok", "MCP 已连接，可搜索职位；打招呼前可能需要先登录"
            return "warn", "MCP 已配置，但连接异常；请检查 mcp-bosszp 服务状态"
        except subprocess.TimeoutExpired:
            return "warn", "MCP 已配置，但健康检查超时；请检查 mcp-bosszp 服务状态"
        except Exception:
            return "warn", "MCP 已配置，但连接异常；请检查 mcp-bosszp 服务状态"
