# -*- coding: utf-8 -*-
"""Reddit browser actions supplement public web search and reading.

Public posts and some comments can be available through an agent's existing
web tools without Reddit login. A blocked anonymous JSON endpoint does not
establish a site-wide login requirement. These actions use managed browser
sessions; request authentication only when the selected path requires it.
"""

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import BAD_INPUT, UPSTREAM_BROKEN, ReachError

from .base import Action, Channel, Param

_REDDIT_LOGIN_HINT = (
    "Ask the user to log in to reddit.com in the Agent Reach dedicated browser. Never log in on their behalf."
)


def _reddit(args, timeout: float) -> list:
    items = opencli_items(opencli_call("reddit", list(args), timeout=timeout, login_hint=_REDDIT_LOGIN_HINT))
    if not items:
        raise ReachError(UPSTREAM_BROKEN, "OpenCLI finished but returned no items")
    return items


class RedditChannel(Channel):
    name = "reddit"
    description = "Reddit 帖子和评论"

    level = "optional"
    login_url = "https://www.reddit.com/login/"
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser_binding import setup_problems

        return setup_problems(self.name)

    actions = (
        Action(
            "search",
            "Search public posts first; --backend opencli uses site search",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_search"),),
            live_test={"query": "python", "limit": 2},
            public_web=("reddit.com/r/",),
        ),
        Action(
            "read",
            "Read public page text first; --backend opencli requests the post and top comments",
            (Param("target", "post link or id"),),
            (("opencli", "_opencli_read"),),
            public_web=("reddit.com/r/", "redd.it/"),
        ),
        Action(
            "subreddit",
            "Latest posts in a subreddit",
            (
                Param("name", "subreddit name without r/, e.g. python"),
                Param("limit", "max posts", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_subreddit"),),
            live_test={"name": "python", "limit": 2},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "reddit.com", "redd.it")

    # ── unified entry backends ──

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        return _reddit(["search", query, "--limit", str(limit)], timeout)[:limit]


    def _opencli_read(self, *, target: str, timeout: float) -> list:
        t = str(target).strip()
        if not (self.can_handle(t) or t.isalnum()):
            raise ReachError(BAD_INPUT, "target must be a reddit.com post link or post id")
        items = _reddit(["read", t, "--limit", "20"], timeout)
        post, comments = items[0], items[1:]
        if comments:
            lines = [post["text"] or ""] + [f"\n@{c['author'] or ''}: {c['text'] or ''}" for c in comments]
            post["text"] = "\n".join(lines).strip()
            post["raw"] = {"post": post["raw"], "comments": [c["raw"] for c in comments]}
        return [post]

    def _opencli_subreddit(self, *, name: str, limit: int, timeout: float) -> list:
        return _reddit(["subreddit", name.removeprefix("r/"), "--limit", str(limit)], timeout)[:limit]
