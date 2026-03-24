# -*- coding: utf-8 -*-
"""Tavily Search — web search via tavily-python SDK."""

import os
from .base import Channel


class TavilySearchChannel(Channel):
    name = "tavily_search"
    description = "Tavily 全网搜索"
    backends = ["tavily-python"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return False  # Search-only channel

    def check(self, config=None):
        api_key = os.environ.get("TAVILY_API_KEY") or (
            config.get("tavily_api_key") if config else None
        )
        if not api_key:
            return "off", (
                "需要 TAVILY_API_KEY。获取：\n"
                "  1. 前往 https://app.tavily.com 注册（每月 1000 次免费）\n"
                "  2. 设置环境变量：export TAVILY_API_KEY=tvly-xxx"
            )
        try:
            from tavily import TavilyClient  # noqa: F401
        except ImportError:
            return "off", (
                "tavily-python 未安装。运行：\n"
                "  pip install agent-reach[tavily]"
            )
        if not api_key.startswith("tvly-"):
            return "warn", "TAVILY_API_KEY 格式异常（应以 tvly- 开头）"
        return "ok", "Tavily 全网搜索可用"
