# -*- coding: utf-8 -*-
"""Quora — public question and answer pages, found and read through public web search."""

from agent_reach.runtime.result import NOT_FOUND, ReachError
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param


class QuoraChannel(Channel):
    name = "quora"
    description = "Quora 公开问答"

    # Quora's own search needs a login, so this channel only uses public pages.
    level = "default"
    actions = (
        Action(
            "search",
            "Search public Quora questions and answers",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("site", "_no_site_tool"),),
            live_test={"query": "python", "limit": 2},
            public_web=("quora.com/",),
            web_only=True,
        ),
        Action(
            "read",
            "Read a public Quora question page",
            (Param("target", "full quora.com URL"),),
            (("site", "_no_site_tool"),),
            public_web=("quora.com/",),
            web_only=True,
        ),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "quora.com")

    def _no_site_tool(self, **_params):
        # Public web is the only route; dispatch has already tried it.
        raise ReachError(NOT_FOUND, "No public Quora result for this request",
                         hint="Try different keywords, or the question's full quora.com URL.")
