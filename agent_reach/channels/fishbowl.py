# -*- coding: utf-8 -*-
"""Fishbowl — public community posts, found and read through public web search."""

from agent_reach.runtime.result import NOT_FOUND, ReachError
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param


class FishbowlChannel(Channel):
    name = "fishbowl"
    description = "Fishbowl 职场社区公开帖子"

    # Only public community pages are used; posting or login is never involved.
    level = "default"
    actions = (
        Action(
            "search",
            "Search public Fishbowl posts",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("site", "_no_site_tool"),),
            live_test={"query": "salary", "limit": 2},
            public_web=("fishbowlapp.com/",),
            web_only=True,
        ),
        Action(
            "read",
            "Read a public Fishbowl post page",
            (Param("target", "full fishbowlapp.com URL"),),
            (("site", "_no_site_tool"),),
            public_web=("fishbowlapp.com/",),
            web_only=True,
        ),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "fishbowlapp.com")

    def _no_site_tool(self, **_params):
        # Public web is the only route; dispatch has already tried it.
        raise ReachError(NOT_FOUND, "No public Fishbowl result for this request",
                         hint="Try different keywords, or the post's full fishbowlapp.com URL.")
