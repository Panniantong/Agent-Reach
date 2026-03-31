# -*- coding: utf-8 -*-
"""Tavily Search — API-based web search via tavily-python."""

import os
from .base import Channel


class TavilySearchChannel(Channel):
    name = "tavily_search"
    description = "全网搜索（Tavily API）"
    backends = ["Tavily API"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        # Check for tavily-python
        try:
            import tavily  # noqa: F401
        except ImportError:
            return "off", (
                "需要安装 tavily-python：\n"
                "  pip install tavily-python"
            )

        # Check for API key via config or env
        api_key = None
        if config:
            api_key = config.get("tavily_api_key")
        if not api_key:
            api_key = os.environ.get("TAVILY_API_KEY")

        if not api_key:
            return "off", (
                "需要 TAVILY_API_KEY。获取：\n"
                "  1. 访问 https://app.tavily.com 注册（每月 1000 次免费）\n"
                "  2. agent-reach configure tavily_api_key <YOUR_KEY>"
            )

        return "ok", "Tavily 全网搜索可用（API Key 已配置）"
