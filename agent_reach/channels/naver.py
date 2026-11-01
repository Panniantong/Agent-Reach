# -*- coding: utf-8 -*-
"""Naver — read-only channel for news articles, blog posts and cafe boards.

Two backends: the official Naver Open API for search (needs a free
`X-Naver-Client-Id`/`Secret` pair, stored as "id:secret" via
`agent-reach configure naver-api`) and best-effort HTML extraction for read.
Experimental: portal pages are JS-heavy; when extraction comes back short the
error tells the caller to use the public-web backend (Jina/Exa).
"""

import json
import os
import re
from urllib.parse import quote_plus

from agent_reach.runtime.result import BAD_INPUT, NEED_SETUP, UPSTREAM_BROKEN, ReachError, make_item
from agent_reach.runtime.run import http_request
from agent_reach.utils.htmltext import extract_text, extract_title

from .base import Action, Channel, Param

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_BYTES = 3 * 1024 * 1024
_MIN_TEXT_CHARS = 200

_HOSTS = ("naver.com", "news.naver.com", "blog.naver.com", "cafe.naver.com", "m.blog.naver.com", "in.naver.com")

#: (start marker, end marker) pairs that bracket the real article body on each
#: Naver surface; the first pair whose slice yields enough text wins.
_BODY_MARKERS = (
    ('id="newsct_article"', "저작권자"),      # news article
    ('newsct_article _article_body', "저작권자"),
    ('class="se-main-container"', "container_link"),  # blog post
    ('id="se_component"', "post_area"),
)


def _parse_target(target: str) -> str:
    """Accept a naver.com news/blog/cafe URL; reject everything else."""
    t = str(target).strip()
    if "://" not in t:
        t = "https://" + t
    if not re.match(r"^https://(?:[a-z0-9-]+\.)*naver\.com/", t, re.I):
        raise ReachError(BAD_INPUT, "target must be a naver.com news/blog/cafe link")
    return t


def _parse_naver_date(value) -> str | None:
    """Naver pubDate ('Tue, 01 Nov 2026 09:00:00 +0900') → ISO date."""
    if not value:
        return None
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(str(value)).isoformat()
    except Exception:
        return None


def _body_text(html: str) -> str:
    """Prefer the article container over whole-page text (drops nav chrome)."""
    for start_marker, end_marker in _BODY_MARKERS:
        start = html.find(start_marker)
        if start == -1:
            continue
        end = html.find(end_marker, start)
        if end == -1 or end <= start:
            end = min(start + 300_000, len(html))
        text = extract_text(html[start:end])
        # The marker itself can sit inside a JS template; drop such residue lines.
        lines = [l for l in text.splitlines() if not ("id=" in l or 'class="' in l)]
        text = "\n".join(lines).strip()
        if len(text) >= _MIN_TEXT_CHARS:
            return text
    return extract_text(html)


_API_HOSTS = ("openapi.naver.com",)
_SOURCES = ("news", "blog", "cafearticle", "webkr")


def _naver_api_key() -> tuple[str, str] | None:
    """Return (client_id, client_secret) from env or config; None when absent."""
    raw = os.environ.get("NAVER_API_KEY") or ""
    if not raw:
        try:
            from agent_reach.config import Config

            raw = Config(read_only=True).get("naver_api") or ""
        except Exception:
            raw = ""
    if ":" in raw:
        client_id, secret = raw.split(":", 1)
        if client_id.strip() and secret.strip():
            return client_id.strip(), secret.strip()
    return None


class NaverChannel(Channel):
    name = "naver"
    description = "네이버 검색(Open API)과 뉴스·블로그·카페 글 읽기 (experimental)"

    level = "experimental"
    needs_key = "naver-api"
    actions = (
        Action(
            "search",
            "Search Naver news/blog/cafe/web via the official Open API",
            (
                Param("query", "search keyword"),
                Param("source", "news | blog | cafearticle | webkr", required=False, default="news"),
                Param("limit", "max items", required=False, type=int, default=10),
            ),
            (("naver-api", "_api_search"),),
            public_web=_HOSTS,
        ),
        Action(
            "read",
            "Read a Naver news article, blog post or cafe post",
            (Param("target", "naver.com article/post URL"),),
            (("site-html", "_html_read"),),
            public_web=_HOSTS,
        ),
    )

    def setup_problems(self) -> list:
        if _naver_api_key():
            return []
        return ["no Naver Open API key: get one at https://developers.naver.com/apps, then `agent-reach configure naver-api` (id:secret)"]

    def validate_params(self, action: str, params: dict) -> None:
        if action == "search" and params.get("source") not in _SOURCES:
            raise ReachError(BAD_INPUT, f"source must be one of: {', '.join(_SOURCES)}")

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "naver.com")

    # ------------------------------------------------------------------ #
    # Backends
    # ------------------------------------------------------------------ #

    def _api_search(self, *, query: str, source: str, limit: int, timeout: float) -> list:
        key = _naver_api_key()
        if not key:
            raise ReachError(
                NEED_SETUP,
                "no Naver Open API key configured",
                hint="Ask the user for a client id/secret from https://developers.naver.com/apps, "
                     "then run `agent-reach configure naver-api` with 'id:secret'.",
            )
        client_id, secret = key
        url = f"https://openapi.naver.com/v1/search/{source}.json?query={quote_plus(query)}&display={min(limit, 100)}&sort=sim"
        try:
            body = http_request(
                url,
                timeout=timeout,
                headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": secret},
            )
        except Exception as exc:
            raise ReachError(UPSTREAM_BROKEN, f"Naver Open API request failed: {exc}") from exc
        data = json.loads(body.decode("utf-8", errors="replace"))
        items = data.get("items") or []
        if not items:
            return []
        return [
            make_item(
                title=re.sub(r"<[^>]+>", "", str(it.get("title") or "")),
                url=it.get("originallink") or it.get("link"),
                author=it.get("bloggername") or None,
                published_at=_parse_naver_date(it.get("pubDate")),
                text=re.sub(r"<[^>]+>", "", str(it.get("description") or "")) or None,
                raw={"source": "naver-api"},
            )
            for it in items[:limit]
        ]

    def _html_read(self, *, target: str, timeout: float) -> list:
        url = _parse_target(target)
        try:
            body = http_request(url, timeout=timeout, headers={"User-Agent": _UA}, max_bytes=_MAX_BYTES)
        except ReachError:
            raise
        except Exception as exc:
            raise ReachError(UPSTREAM_BROKEN, f"Naver fetch failed: {exc}") from exc
        html = body.decode("utf-8", errors="replace")
        title = extract_title(html)
        text = _body_text(html)
        if len(text) < _MIN_TEXT_CHARS:
            raise ReachError(
                UPSTREAM_BROKEN,
                "Naver page came back without readable article text (JS-rendered or login-gated)",
                hint="Retry with --backend public-web, or open the link in a browser.",
            )
        return [make_item(title=title, url=url, text=text, raw={"source": "site-html"})]
