# -*- coding: utf-8 -*-
"""FM Korea — read-only channel for the Korean community fmkorea.com.

The site sits behind aggressive bot protection, so the direct backend often
fails; the channel still works through the public-web backend (Jina/Exa) which
the dispatcher tries first when the channel is not installed. Experimental.
"""

import re

from agent_reach.runtime.result import BAD_INPUT, NOT_FOUND, UPSTREAM_BROKEN, ReachError, make_item
from agent_reach.runtime.run import http_request
from agent_reach.utils.htmltext import extract_text, extract_title

from .base import Action, Channel, Param

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_BYTES = 3 * 1024 * 1024
_MIN_TEXT_CHARS = 80
_BASE = "https://www.fmkorea.com"
_HOSTS = ("fmkorea.com", "www.fmkorea.com")

_POST_URL_RE = re.compile(r"^https://(?:www\.)?fmkorea\.com/(?:[0-9a-z_]+/)*\d+(?:\?.*)?$")


def _body_text(html: str) -> str:
    """Prefer the XE document container; fall back to whole-page text."""
    for start_marker, end_marker in (
        ('class="xe_content"', 'class="document_'),
        ('class="document_', 'class="xe_content'),
    ):
        start = html.find(start_marker)
        if start == -1:
            continue
        end = html.find(end_marker, start)
        if end == -1 or end <= start:
            end = min(start + 200_000, len(html))
        text = extract_text(html[start:end])
        # JS templates repeat the markers as raw text; drop such residue lines.
        lines = [l for l in text.splitlines()
                 if not ('class="' in l or 'href=' in l or 'onclick' in l or 'return false' in l)]
        text = "\n".join(lines).strip()
        if len(text) >= _MIN_TEXT_CHARS:
            return text
    return extract_text(html)


class FMKoreaChannel(Channel):
    name = "fmkorea"
    description = "FM코리아(fmkorea.com) 검색과 글 읽기 (experimental)"

    level = "experimental"
    actions = (
        # No `search` action: the public search endpoint returns the sidebar
        # best-of list for any keyword, so results would be wrong. Use the
        # public-web backend (`site:fmkorea.com` queries) for discovery.
        Action(
            "read",
            "Read an fmkorea.com post and its comments",
            (Param("target", "fmkorea.com post URL"),),
            (("site-html", "_html_read"),),
            public_web=_HOSTS,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "fmkorea.com")

    # ------------------------------------------------------------------ #
    # Backends
    # ------------------------------------------------------------------ #

    def _blocked(self, html: str) -> bool:
        sample = html[:4096].casefold()
        return "just a moment" in sample or "cloudflare" in sample and "challenge" in sample

    def _html_read(self, *, target: str, timeout: float) -> list:
        url = str(target).strip()
        if "://" not in url:
            url = "https://" + url
        if not _POST_URL_RE.match(url):
            raise ReachError(BAD_INPUT, "target must be an fmkorea.com post URL (https://www.fmkorea.com/<board>/<id>)")
        try:
            body = http_request(url, timeout=timeout, headers={"User-Agent": _UA, "Accept-Language": "ko"}, max_bytes=_MAX_BYTES)
        except Exception as exc:
            raise ReachError(UPSTREAM_BROKEN, f"fmkorea fetch failed (bot protection): {exc}", hint="Retry with --backend public-web.") from exc
        html = body.decode("utf-8", errors="replace")
        if self._blocked(html):
            raise ReachError(UPSTREAM_BROKEN, "fmkorea returned a bot-check page", hint="Retry with --backend public-web.")
        title = extract_title(html)
        text = _body_text(html)
        if len(text) < _MIN_TEXT_CHARS:
            raise ReachError(UPSTREAM_BROKEN, "fmkorea page came back without readable text", hint="Retry with --backend public-web.")
        return [make_item(title=title, url=url, text=text, raw={"source": "site-html"})]
