# -*- coding: utf-8 -*-
"""Optional hosted backends for YouTube transcripts.

yt-dlp stays the default subtitle route. On servers YouTube often answers with
"Sign in to confirm you're not a bot" (#566, #774), and a hosted service that
fetches captions on its own infrastructure can stand in. Nothing here runs
unless the user picks a backend:

    youtube_transcript_backend: apify   # or env YOUTUBE_TRANSCRIPT_BACKEND

Each backend is a small class with a ``name``, the config ``feature`` it needs
(see ``Config.FEATURE_REQUIREMENTS``) and ``fetch()``. Adding a provider means
adding one class to ``BACKENDS``.

Public entry point:
    fetch_transcript(url, *, lang=None, backend=None, config=None) -> dict
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import requests

from agent_reach.config import Config
from agent_reach.utils.url import host_matches

_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class TranscriptBackendError(RuntimeError):
    """Base error for hosted transcript backends."""


class NoBackendConfigured(TranscriptBackendError):
    """Raised when no hosted backend is selected or its credentials are missing."""


def _video_target(url: str) -> str:
    """Accept a YouTube URL or an 11-character video ID; refuse anything else.

    Keeps the backend from forwarding arbitrary URLs to a third-party service.
    """
    value = (url or "").strip()
    if _VIDEO_ID.fullmatch(value):
        return f"https://www.youtube.com/watch?v={value}"
    if host_matches(value, "youtube.com", "youtu.be"):
        return value
    raise TranscriptBackendError(f"not a YouTube video URL or ID: {value!r}")


def _item_text(item: Dict[str, Any]) -> str:
    """Pull the transcript text out of a dataset item.

    Transcript Actors name the field differently: a ``text``/``transcript``
    string, or a list of ``{text, ...}`` segments.
    """
    for key in ("text", "transcript", "segments", "captions", "subtitles"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [s.get("text") if isinstance(s, dict) else s for s in value]
            lines = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
            if lines:
                return "\n".join(lines)
    return ""


class ApifyBackend:
    """Runs a transcript Actor on Apify and reads its dataset in one call.

    Uses the ``run-sync-get-dataset-items`` endpoint, so there is no job
    polling. Any Actor that takes YouTube URLs and returns a transcript field
    works; ``apify_transcript_input`` adapts the input for Actors whose field
    names differ.
    """

    name = "apify"
    feature = "apify_transcript"
    DEFAULT_ACTOR = "apimint/youtube-transcript-scraper"
    API_BASE = "https://api.apify.com/v2"
    RUN_TIMEOUT_SECONDS = 180

    def _actor_id(self, config: Config) -> str:
        actor = str(config.get("apify_transcript_actor") or self.DEFAULT_ACTOR).strip()
        # The API takes "owner~name"; Store pages show "owner/name".
        return actor.replace("/", "~")

    def _input(self, url: str, lang: Optional[str], config: Config) -> Dict[str, Any]:
        template = config.get("apify_transcript_input")
        if not template:
            payload: Dict[str, Any] = {"urls": [url]}
            if lang:
                payload["languages"] = [x.strip() for x in lang.split(",") if x.strip()]
            return payload
        if isinstance(template, str):
            try:
                template = json.loads(template)
            except ValueError as e:
                raise TranscriptBackendError(f"apify_transcript_input is not valid JSON: {e}") from e
        if not isinstance(template, dict):
            raise TranscriptBackendError("apify_transcript_input must be a JSON object")

        def fill(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace("{url}", url)
            if isinstance(value, list):
                return [fill(v) for v in value]
            if isinstance(value, dict):
                return {k: fill(v) for k, v in value.items()}
            return value

        return fill(template)

    def fetch(self, url: str, *, lang: Optional[str], config: Config) -> Dict[str, Any]:
        token = config.get("apify_token")
        if not token:
            raise NoBackendConfigured(
                "apify: missing apify_token (set APIFY_TOKEN or run "
                "`agent-reach configure apify-token`)"
            )
        actor = self._actor_id(config)
        endpoint = f"{self.API_BASE}/acts/{actor}/run-sync-get-dataset-items"
        try:
            resp = requests.post(
                endpoint,
                params={"timeout": self.RUN_TIMEOUT_SECONDS},
                headers={"Authorization": f"Bearer {token}"},
                json=self._input(url, lang, config),
                timeout=self.RUN_TIMEOUT_SECONDS + 30,
            )
        except requests.RequestException as e:
            raise TranscriptBackendError(f"apify: network error: {e}") from e

        if not resp.ok:
            raise TranscriptBackendError(
                f"apify: HTTP {resp.status_code} from {actor}: {resp.text[:300]}"
            )
        try:
            items = resp.json()
        except ValueError as e:
            raise TranscriptBackendError(f"apify: {actor} did not return JSON") from e
        if not isinstance(items, list) or not items:
            raise TranscriptBackendError(f"apify: {actor} returned no items for {url}")

        dict_items: List[Dict[str, Any]] = [i for i in items if isinstance(i, dict)]
        for item in dict_items:
            text = _item_text(item)
            if text:
                return {**item, "text": text, "backend": self.name, "actor": actor}
        first = dict_items[0] if dict_items else {}
        reason = first.get("errorMessage") or first.get("error") or first.get("status")
        raise TranscriptBackendError(
            f"apify: {actor} returned no transcript for {url}"
            + (f" ({reason})" if reason else "")
        )


BACKENDS = {backend.name: backend for backend in (ApifyBackend(),)}


def configured_backend(config: Optional[Config]) -> Optional[str]:
    """Name of the selected backend when its credentials are present, else None.

    Reads config only; never calls the network (safe for ``doctor``).
    """
    if config is None:
        return None
    name = config.get("youtube_transcript_backend")
    if not isinstance(name, str) or name.strip().lower() not in BACKENDS:
        return None
    name = name.strip().lower()
    return name if config.is_configured(BACKENDS[name].feature) else None


def fetch_transcript(
    url: str,
    *,
    lang: Optional[str] = None,
    backend: Optional[str] = None,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """Fetch one video's transcript from a hosted backend.

    ``backend`` overrides ``youtube_transcript_backend``. Returns the provider's
    item with a normalised ``text`` field plus ``backend``. Raises
    :class:`NoBackendConfigured` when nothing is selected, so callers can fall
    through to yt-dlp / OpenCLI / audio transcription.
    """
    cfg = config or Config(read_only=True)
    name = (backend or cfg.get("youtube_transcript_backend") or "").strip().lower()
    if not name:
        raise NoBackendConfigured(
            "no hosted transcript backend selected "
            f"(set youtube_transcript_backend to one of: {', '.join(BACKENDS)})"
        )
    if name not in BACKENDS:
        raise TranscriptBackendError(
            f"unknown transcript backend: {name} (use one of: {', '.join(BACKENDS)})"
        )
    return BACKENDS[name].fetch(_video_target(url), lang=lang, config=cfg)
