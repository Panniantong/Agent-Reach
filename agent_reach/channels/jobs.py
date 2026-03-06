# -*- coding: utf-8 -*-
"""Jobs (招聘聚合) — 猎聘、Boss直聘、智联、51Job via mcp-jobs."""

import shutil
import subprocess
from .base import Channel


class JobsChannel(Channel):
    name = "jobs"
    description = "招聘聚合（猎聘、智联、51Job）"
    backends = ["mcp-jobs"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return any(x in d for x in [
            "liepin.com", "zhaopin.com", "51job.com",
            "lagou.com", "kanzhun.com",
        ])

    def check(self, config=None):
        # mcp-jobs runs via npx, check if npx is available
        npx = shutil.which("npx")
        if not npx:
            return "off", (
                "需要 Node.js (npx)。安装：\n"
                "  https://nodejs.org/\n"
                "  然后直接使用：npx -y mcp-jobs"
            )
        # Check if mcporter has mcp-jobs configured
        mcporter = shutil.which("mcporter")
        if mcporter:
            try:
                r = subprocess.run(
                    [mcporter, "config", "list"], capture_output=True,
                    encoding="utf-8", errors="replace", timeout=5
                )
                if "jobs" in r.stdout or "mcp-jobs" in r.stdout:
                    return "ok", "招聘聚合可用（猎聘、智联、51Job，零配置）"
            except Exception:
                pass
        return "warn", (
            "npx 可用，mcp-jobs 可直接运行。配置 mcporter 以便 Agent 调用：\n"
            "  npx -y mcp-jobs  # 启动服务\n"
            "  mcporter config add jobs http://localhost:3000/mcp\n"
            "  详见 https://github.com/mergedao/mcp-jobs"
        )
