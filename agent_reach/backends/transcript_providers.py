# -*- coding: utf-8 -*-
"""Optional hosted transcript providers for the YouTube ``subtitle`` action.

Off by default. A provider is used only when the user configured one
(``agent-reach configure transcript-provider <name>`` plus
``configure transcript-key <key>``, or the ``TRANSCRIPT_PROVIDER`` /
``TRANSCRIPT_KEY`` env vars) and the agent explicitly picks the ``hosted``
backend. Agent Reach never switches to a paid provider silently.

Adding a provider = one function with the ``Provider`` signature registered
in ``PROVIDERS``. It takes a YouTube watch URL, preferred language codes, the
user's key and a timeout, and returns ``(text, language_code_or_None)``. It
raises ``ReachError`` with the unified codes.
"""

from typing import Callable, Dict, List, Optional, Tuple

import requests

from agent_reach.runtime.result import (
    NEED_SETUP,
    NOT_FOUND,
    RATE_LIMITED,
    UPSTREAM_BROKEN,
    ReachError,
)

Provider = Callable[[str, List[str], str, float], Tuple[str, Optional[str]]]


def _http_error(name: str, resp: requests.Response) -> ReachError:
    if resp.status_code in (401, 403):
        return ReachError(NEED_SETUP, f"{name} rejected the configured key (HTTP {resp.status_code})",
                          hint="Ask the user to check the key with `agent-reach configure transcript-key`.")
    if resp.status_code == 402:
        return ReachError(NEED_SETUP, f"{name} account has no remaining credit (HTTP 402)",
                          hint="Tell the user their hosted transcript account is out of credit.")
    if resp.status_code == 429:
        return ReachError(RATE_LIMITED, f"{name} rate limit (HTTP 429)")
    return ReachError(UPSTREAM_BROKEN, f"{name} returned HTTP {resp.status_code}")


# ── ShepHouse YouTube Transcript Actor on Apify ──
# https://apify.com/shephouse/youtube-transcript-scraper-bulk
# Key: an Apify API token. Billed by Apify to the user's own account.

_APIFY_ACTOR = "shephouse~youtube-transcript-scraper-bulk"
_APIFY_NOT_FOUND = {"NO_CAPTIONS", "EMPTY_CAPTIONS", "NO_MATCHING_CAPTIONS", "VIDEO_UNAVAILABLE", "VIDEO_UNPLAYABLE"}


def shephouse_apify(url: str, langs: List[str], key: str, timeout: float) -> Tuple[str, Optional[str]]:
    run_timeout = max(int(timeout) - 10, 30)
    try:
        resp = requests.post(
            f"https://api.apify.com/v2/acts/{_APIFY_ACTOR}/run-sync-get-dataset-items",
            params={"timeout": run_timeout},
            headers={"Authorization": f"Bearer {key}"},
            json={"startUrls": [{"url": url}], "languages": langs or ["en"],
                  "outputFormats": ["text"], "maxTranscripts": 1},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ReachError(UPSTREAM_BROKEN, f"shephouse-apify request failed: {type(exc).__name__}") from None
    if resp.status_code >= 400:
        raise _http_error("shephouse-apify", resp)
    try:
        items = resp.json()
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "shephouse-apify returned invalid JSON") from None
    item = items[0] if isinstance(items, list) and items else {}
    if item.get("status") == "OK" and item.get("text"):
        return item["text"], item.get("language")
    code = item.get("errorCode") or item.get("status") or "NO_RESULT"
    if code in _APIFY_NOT_FOUND:
        raise ReachError(NOT_FOUND, f"no transcript for this video ({code})")
    raise ReachError(UPSTREAM_BROKEN, f"shephouse-apify could not fetch the transcript ({code})")


PROVIDERS: Dict[str, Provider] = {
    "shephouse-apify": shephouse_apify,
}


def configured(config=None) -> Tuple[Optional[str], Optional[str]]:
    """(provider name, key) from config/env, or (None, None)."""
    if config is None:
        from agent_reach.config import Config
        config = Config(read_only=True)
    name = config.get("transcript_provider")
    key = config.get("transcript_key")
    return (str(name).strip().lower() if name else None), (str(key) if key else None)


def fetch(url: str, langs: List[str], timeout: float, config=None) -> Tuple[str, Optional[str], str]:
    name, key = configured(config)
    if not name or not key:
        raise ReachError(NEED_SETUP, "no hosted transcript provider configured",
                         hint="This optional backend is off. Only the user can enable it: "
                              "`agent-reach configure transcript-provider <name>` and "
                              f"`agent-reach configure transcript-key <key>`. Providers: {', '.join(PROVIDERS)}.")
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ReachError(NEED_SETUP, f"unknown transcript provider '{name}'; valid: {', '.join(PROVIDERS)}")
    text, lang = provider(url, langs, key, timeout)
    return text, lang, name
