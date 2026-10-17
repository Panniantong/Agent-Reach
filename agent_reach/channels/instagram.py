# -*- coding: utf-8 -*-
"""Instagram — CloakBrowser first, OpenCLI fallback."""

from ._opencli_site import OpenCLISiteChannel
from .base import Action, Param


class InstagramChannel(OpenCLISiteChannel):
    name = "instagram"
    description = "Instagram 用户、主页和指定用户帖子"
    site = "instagram"
    domains = ("instagram.com", "instagr.am")
    usage = "opencli instagram search/profile/user/explore -f yaml"
    login_hint = "instagram.com"

    level = "experimental"
    login_url = "https://www.instagram.com/accounts/login/"
    actions = (
        Action(
            "search",
            "Search users (not posts)",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("cloakbrowser", "_cloak_search"), ("opencli", "_opencli_search")),
            live_test={"query": "nasa", "limit": 2},
        ),
        Action(
            "profile",
            "A user's profile",
            (Param("username", "Instagram username"),),
            (("cloakbrowser", "_cloak_profile"), ("opencli", "_opencli_profile")),
            live_test={"username": "nasa"},
        ),
        Action(
            "posts",
            "A user's recent posts",
            (
                Param("username", "Instagram username"),
                Param("limit", "max posts", required=False, type=int, default=6),
            ),
            (("cloakbrowser", "_cloak_posts"), ("opencli", "_opencli_posts")),
            live_test={"username": "nasa", "limit": 2},
        ),
    )

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        return self._opencli(["search", query, "--limit", str(limit)], timeout)[:limit]

    def _opencli_profile(self, *, username: str, timeout: float) -> list:
        return self._opencli(["profile", username], timeout, empty_is_error=False)[:1]

    def _opencli_posts(self, *, username: str, limit: int, timeout: float) -> list:
        return self._opencli(["user", username, "--limit", str(limit)], timeout)[:limit]

    def _cloak_search(self, *, query, limit, timeout):
        from agent_reach.backends.cloak import call
        return call(self.name, "search", query=query, limit=limit, timeout=timeout)

    def _cloak_profile(self, *, username, timeout):
        from agent_reach.backends.cloak import call
        return call(self.name, "profile", username=username, timeout=timeout)

    def _cloak_posts(self, *, username, limit, timeout):
        from agent_reach.backends.cloak import call
        return call(self.name, "posts", username=username, limit=limit, timeout=timeout)

    def on_remove(self):
        from agent_reach.backends.cloak import logout
        logout(self.name)
