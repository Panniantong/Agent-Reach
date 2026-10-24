# -*- coding: utf-8 -*-
"""Twitter/X — OpenCLI in the Agent Reach browser (experimental)."""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import UPSTREAM_BROKEN, ReachError
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param

_TWITTER_LOGIN_HINT = (
    "Ask the user to log in to x.com in the Agent Reach dedicated browser. Never log in on their behalf."
)


def _x(args, timeout: float) -> list:
    items = opencli_items(opencli_call("twitter", list(args), timeout=timeout, login_hint=_TWITTER_LOGIN_HINT))
    if not items:
        raise ReachError(UPSTREAM_BROKEN, "OpenCLI finished but returned no items")
    return items


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"

    # twitter-cli is not used here: even with explicit credentials it re-reads
    # browser cookies whenever verification fails.
    level = "experimental"
    login_url = "https://x.com/i/flow/login"
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    actions = (
        Action(
            "search",
            "Search tweets",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_search"),),
            live_test={"query": "openai", "limit": 2},
            public_web=("x.com/", "twitter.com/"),
        ),
        Action(
            "profile",
            "A user's profile",
            (Param("username", "handle without @"),),
            (("opencli", "_opencli_profile"),),
            live_test={"username": "OpenAI"},
        ),
        Action(
            "tweets",
            "A user's recent tweets",
            (
                Param("username", "handle without @"),
                Param("limit", "max tweets", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_tweets"),),
        ),
        Action(
            "thread",
            "A tweet with its replies",
            (Param("target", "tweet id or link"),),
            (("opencli", "_opencli_thread"),),
        ),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "x.com", "twitter.com")

    # ── unified entry backends ──

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        return _x(["search", query, "--limit", str(limit)], timeout)[:limit]


    def _opencli_profile(self, *, username: str, timeout: float) -> list:
        return _x(["profile", username.lstrip("@")], timeout)[:1]

    def _opencli_tweets(self, *, username: str, limit: int, timeout: float) -> list:
        return _x(["tweets", username.lstrip("@"), "--limit", str(limit)], timeout)[:limit]

    def _opencli_thread(self, *, target: str, timeout: float) -> list:
        tweet_id = str(target).rstrip("/").split("/")[-1].split("?")[0]
        return _x(["thread", tweet_id], timeout)
