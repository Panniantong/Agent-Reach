# -*- coding: utf-8 -*-
"""Quora — Q&A platform. Search via Exa (direct access blocked by Cloudflare)."""

from .base import Channel


class QuoraChannel(Channel):
    name = "quora"
    description = "Quora 问答社区"
    backends = ["Exa"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "quora.com" in d

    def check(self, config=None):
        import shutil
        mcporter = shutil.which("mcporter")
        if mcporter:
            try:
                import subprocess
                r = subprocess.run(
                    [mcporter, "config", "list"], capture_output=True,
                    encoding="utf-8", errors="replace", timeout=5
                )
                if "exa" in r.stdout.lower():
                    return "ok", (
                        "Quora 可通过 Exa 语义搜索访问（搜索内容，非直接抓取）。"
                        "直接访问被 Cloudflare 拦截"
                    )
            except Exception:
                pass
        return "warn", (
            "Quora 反爬严格（Cloudflare），curl 和 Jina Reader 均被 403。\n"
            "推荐通过 Exa 搜索 Quora 内容：\n"
            '  mcporter call \'exa.web_search_exa(query: "site:quora.com YOUR_QUERY")\'\n'
            "配置 Exa：mcporter config add exa http://localhost:PORT/mcp"
        )
