# -*- coding: utf-8 -*-
"""Deprecated re-export — use agent_reach.channels.web_search instead.

Kept for backward compatibility with scripts that import ExaSearchChannel
directly. The channel has been renamed to WebSearchChannel and now includes
DuckDuckGo as a zero-config fallback backend.
"""

from agent_reach.channels.web_search import WebSearchChannel

# Backward-compatible alias
ExaSearchChannel = WebSearchChannel

__all__ = ["ExaSearchChannel", "WebSearchChannel"]
