# -*- coding: utf-8 -*-
"""Transcript text from a hosted transcript API the user configured.

The yt-dlp backends ask YouTube directly from this machine. This one asks a
provider that fetches the captions on its own servers, which is the only
route that still works where YouTube serves a bot check to the local IP.

It never runs unless the user saved a key (`agent-reach configure
transcript-api-key`), it talks to exactly one provider (`transcript_api_provider`;
with a single provider in the table that one is used, with several the user must
choose), and a failure is reported as is: no retry, no second provider.
"""

from typing import Callable, Dict, Optional, Tuple

import requests

from agent_reach.config import Config
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_SETUP,
    NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    UPSTREAM_BROKEN,
    ReachError,
)

KEY_FIELD = "transcript_api_key"
PROVIDER_FIELD = "transcript_api_provider"
_MAX_PROVIDER_MESSAGE_CHARS = 200


def _data(body: dict) -> dict:
    data = body.get("data")
    return data if isinstance(data, dict) else {}


# To add a provider: an endpoint, how to build its query from a video link and
# a language code, and how to read the transcript (and title) from its JSON.
# Every provider is called with `Authorization: Bearer <key>`.
PROVIDERS: Dict[str, dict] = {
    "getyoutubetranscript": {
        "endpoint": "https://getyoutubetranscript.com/api/v1/transcript",
        "query": lambda video_url, lang: {"v": video_url, "language": lang},
        "text": lambda body: _data(body).get("transcript"),
        "title": lambda body: _data(body).get("title"),
    },
}


def _provider_message(resp: requests.Response) -> str:
    try:
        message = resp.json().get("message")
    except (ValueError, AttributeError):
        message = None
    return str(message)[:_MAX_PROVIDER_MESSAGE_CHARS] if message else f"HTTP {resp.status_code}"


def _provider_name(cfg: Config) -> str:
    name = cfg.get(PROVIDER_FIELD)
    if name:
        return str(name)
    if len(PROVIDERS) == 1:
        return next(iter(PROVIDERS))
    raise ReachError(
        NEED_SETUP,
        "no hosted transcript provider selected",
        hint=(
            f"Ask the user which hosted transcript provider they use ({', '.join(PROVIDERS)}), "
            "then run `agent-reach configure transcript-api-provider <name>`."
        ),
    )


def fetch(
    video_url: str,
    lang: str,
    *,
    timeout: float,
    config: Optional[Config] = None,
    http_get: Callable[..., requests.Response] = requests.get,
) -> Tuple[Optional[str], str]:
    """Return `(title, transcript text)` for a YouTube link, or raise ReachError."""
    cfg = config or Config()
    name = _provider_name(cfg)
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ReachError(BAD_INPUT, f"unknown transcript provider: {name}; valid: {', '.join(PROVIDERS)}")

    key = cfg.get(KEY_FIELD)
    if not key:
        raise ReachError(
            NEED_SETUP,
            "no hosted transcript API key configured",
            hint=(
                f"Ask the user for an API key from their hosted transcript provider "
                f"({', '.join(PROVIDERS)}), then run `agent-reach configure transcript-api-key`."
            ),
        )

    try:
        resp = http_get(
            provider["endpoint"],
            params=provider["query"](video_url, lang),
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
    except requests.Timeout:
        raise ReachError(TIMEOUT, f"{name}: no answer in time") from None
    except requests.RequestException:
        raise ReachError(UPSTREAM_BROKEN, f"{name}: network error") from None

    if resp.status_code in (401, 402, 403):
        raise ReachError(
            NEED_SETUP,
            f"{name}: {_provider_message(resp)}",
            hint=(
                "The provider refused the key or the account has no quota left. Tell the user in plain words, "
                "and if the key is wrong, ask them to run `agent-reach configure transcript-api-key` with a valid one."
            ),
        )
    if resp.status_code == 404:
        raise ReachError(NOT_FOUND, f"{name}: no transcript for this video")
    if resp.status_code == 429:
        raise ReachError(RATE_LIMITED, f"{name}: HTTP 429")
    if not resp.ok:
        raise ReachError(UPSTREAM_BROKEN, f"{name}: {_provider_message(resp)}")

    try:
        body = resp.json()
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, f"{name}: reply was not JSON") from None
    text = provider["text"](body) if isinstance(body, dict) else None
    if not text:
        raise ReachError(NOT_FOUND, f"{name}: empty transcript")
    return provider["title"](body), text
