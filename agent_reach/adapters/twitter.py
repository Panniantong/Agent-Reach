# -*- coding: utf-8 -*-
"""Twitter/X collection adapter."""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from agent_reach.media_references import build_media_reference, dedupe_media_references
from agent_reach.results import (
    CollectionResult,
    NormalizedItem,
    build_item,
    derive_title_from_text,
    parse_timestamp,
)

from .base import BaseAdapter


def _normalize_screen_name(value: str) -> str:
    text = value.strip()
    if text.startswith("@"):
        return text[1:]
    if "twitter.com" in text or "x.com" in text:
        parsed = urlparse(text)
        segments = [segment for segment in parsed.path.split("/") if segment]
        return segments[0] if segments else text
    return text


def _normalize_tweet_id(value: str) -> str:
    text = value.strip()
    if "twitter.com" not in text and "x.com" not in text:
        return text
    parsed = urlparse(text)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if "status" in segments:
        idx = segments.index("status")
        if idx + 1 < len(segments):
            return segments[idx + 1]
    return text


def _tweet_url(tweet: dict) -> str | None:
    tweet_id = tweet.get("id")
    screen_name = (tweet.get("author") or {}).get("screenName")
    if tweet_id:
        return f"https://x.com/{screen_name or 'i'}/status/{tweet_id}"
    return None


def _twitter_media_references(media: object) -> list[dict[str, object]]:
    if not isinstance(media, list):
        return []

    references: list[dict[str, object]] = []
    for entry in media:
        if not isinstance(entry, dict):
            continue
        raw_type = str(entry.get("type") or "")
        normalized_type = "video" if raw_type in {"video", "animated_gif", "gif"} else "image"
        reference = build_media_reference(
            type=normalized_type,
            media_type=raw_type or None,
            url=entry.get("url") or entry.get("mediaUrl") or entry.get("media_url"),
            relation="post_media",
            thumb_url=entry.get("thumbnail") or entry.get("thumbUrl") or entry.get("previewImageUrl"),
            alt=entry.get("alt"),
            width=entry.get("width"),
            height=entry.get("height"),
            duration_seconds=entry.get("durationSeconds"),
            source_field="media[]",
        )
        if reference is not None:
            references.append(reference)
    return dedupe_media_references(references)


def _tweet_item(tweet: dict, idx: int, source: str) -> NormalizedItem:
    media = tweet.get("media") or []
    return build_item(
        item_id=str(tweet.get("id") or f"tweet-{idx}"),
        kind="post",
        title=derive_title_from_text(tweet.get("text"), fallback=f"Tweet {tweet.get('id')}"),
        url=_tweet_url(tweet),
        text=tweet.get("text"),
        author=(tweet.get("author") or {}).get("screenName"),
        published_at=parse_timestamp(tweet.get("createdAtISO") or tweet.get("createdAt")),
        source=source,
        extras={
            "author_name": (tweet.get("author") or {}).get("name"),
            "verified": (tweet.get("author") or {}).get("verified"),
            "metrics": tweet.get("metrics") or {},
            "urls": tweet.get("urls") or [],
            "media": media,
            "media_references": _twitter_media_references(media),
            "lang": tweet.get("lang"),
            "is_retweet": tweet.get("isRetweet"),
            "retweeted_by": tweet.get("retweetedBy"),
            "quoted_tweet": tweet.get("quotedTweet"),
            "score": tweet.get("score"),
        },
    )


def _build_search_args(query: str, limit: int, *, since: str | None = None, until: str | None = None) -> list[str]:
    """Translate common X-style search tokens into twitter-cli flags."""

    args = ["search"]
    remaining: list[str] = []
    option_values = {
        "from": "--from",
        "to": "--to",
        "lang": "--lang",
        "since": "--since",
        "until": "--until",
        "type": "--type",
        "min_likes": "--min-likes",
        "min-likes": "--min-likes",
        "min_retweets": "--min-retweets",
        "min-retweets": "--min-retweets",
    }
    repeatable_values = {
        "has": "--has",
        "exclude": "--exclude",
    }

    for token in query.split():
        if ":" not in token:
            remaining.append(token)
            continue
        key, value = token.split(":", 1)
        lowered_key = key.lower()
        if not value:
            remaining.append(token)
            continue
        if lowered_key == "since" and since is not None:
            continue
        if lowered_key == "until" and until is not None:
            continue
        if lowered_key in option_values:
            args.extend([option_values[lowered_key], value])
            continue
        if lowered_key in repeatable_values:
            args.extend([repeatable_values[lowered_key], value])
            continue
        remaining.append(token)

    text_query = " ".join(remaining).strip()
    if text_query:
        args.append(text_query)
    if since is not None:
        args.extend(["--since", since])
    if until is not None:
        args.extend(["--until", until])
    args.extend(["-n", str(limit), "--json"])
    return args


def _parse_error_output(raw_output: str) -> tuple[str | None, str | None, dict | None]:
    """Extract a structured error from twitter-cli stderr/stdout when available."""

    try:
        payload = json.loads(raw_output or "{}")
    except json.JSONDecodeError:
        return None, None, None

    if not isinstance(payload, dict):
        return None, None, None

    error = payload.get("error")
    if not isinstance(error, dict):
        return None, None, payload

    code = error.get("code")
    message = error.get("message")
    return (str(code) if code else None), (str(message) if message else None), payload


class TwitterAdapter(BaseAdapter):
    """Read Twitter/X data through twitter-cli."""

    channel = "twitter"
    operations = ("search", "user", "user_posts", "tweet")

    def search(
        self,
        query: str,
        limit: int = 10,
        since: str | None = None,
        until: str | None = None,
    ) -> CollectionResult:
        started_at = time.perf_counter()
        result = self._run_twitter(
            _build_search_args(query, limit, since=since, until=until),
            operation="search",
            value=query,
            limit=limit,
            started_at=started_at,
            extra_meta={"since": since, "until": until},
        )
        if isinstance(result, dict):
            return result

        raw, _raw_output = result
        data = raw.get("data", [])
        items = [_tweet_item(tweet, idx, self.channel) for idx, tweet in enumerate(data)]
        return self.ok_result(
            "search",
            items=items,
            raw=raw,
            meta=self.make_meta(value=query, limit=limit, started_at=started_at, since=since, until=until),
        )

    def user(self, screen_name: str, limit: int | None = None) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _normalize_screen_name(screen_name)
        result = self._run_twitter(
            ["user", normalized, "--json"],
            operation="user",
            value=normalized,
            limit=limit,
            started_at=started_at,
        )
        if isinstance(result, dict):
            return result

        raw, _raw_output = result
        data = raw.get("data") or {}
        if not isinstance(data, dict):
            return self.error_result(
                "user",
                code="invalid_response",
                message="Twitter user returned an unexpected payload",
                raw=raw,
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )

        item = build_item(
            item_id=str(data.get("id") or data.get("screenName") or normalized),
            kind="profile",
            title=data.get("name") or data.get("screenName") or normalized,
            url=f"https://x.com/{data.get('screenName') or normalized}",
            text=data.get("bio"),
            author=data.get("screenName"),
            published_at=parse_timestamp(data.get("createdAtISO") or data.get("createdAt")),
            source=self.channel,
            extras={
                "followers": data.get("followers"),
                "following": data.get("following"),
                "tweets": data.get("tweets"),
                "likes": data.get("likes"),
                "verified": data.get("verified"),
                "location": data.get("location"),
                "profile_image_url": data.get("profileImageUrl"),
                "website_url": data.get("url"),
                "media_references": dedupe_media_references(
                    [
                        reference
                        for reference in [
                            build_media_reference(
                                type="image",
                                url=data.get("profileImageUrl"),
                                relation="avatar",
                                source_field="profileImageUrl",
                            )
                        ]
                        if reference is not None
                    ]
                ),
            },
        )
        return self.ok_result(
            "user",
            items=[item],
            raw=raw,
            meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
        )

    def user_posts(self, screen_name: str, limit: int = 10) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _normalize_screen_name(screen_name)
        result = self._run_twitter(
            ["user-posts", normalized, "-n", str(limit), "--json"],
            operation="user_posts",
            value=normalized,
            limit=limit,
            started_at=started_at,
        )
        if isinstance(result, dict):
            return result

        raw, _raw_output = result
        data = raw.get("data", [])
        items = [_tweet_item(tweet, idx, self.channel) for idx, tweet in enumerate(data)]
        return self.ok_result(
            "user_posts",
            items=items,
            raw=raw,
            meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
        )

    def tweet(self, tweet_id_or_url: str, limit: int = 20) -> CollectionResult:
        started_at = time.perf_counter()
        normalized = _normalize_tweet_id(tweet_id_or_url)
        result = self._run_twitter(
            ["tweet", normalized, "-n", str(limit), "--json"],
            operation="tweet",
            value=normalized,
            limit=limit,
            started_at=started_at,
        )
        if isinstance(result, dict):
            return result

        raw, _raw_output = result
        data = raw.get("data", [])
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return self.error_result(
                "tweet",
                code="invalid_response",
                message="Twitter tweet returned an unexpected payload",
                raw=raw,
                meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
            )

        items = [_tweet_item(tweet, idx, self.channel) for idx, tweet in enumerate(data)]
        return self.ok_result(
            "tweet",
            items=items,
            raw=raw,
            meta=self.make_meta(value=normalized, limit=limit, started_at=started_at),
        )

    def _run_twitter(
        self,
        args: list[str],
        *,
        operation: str,
        value: str,
        limit: int | None,
        started_at: float,
        extra_meta: dict[str, object] | None = None,
    ) -> tuple[dict, str] | CollectionResult:
        twitter = self.command_path("twitter")
        if not twitter:
            return self.error_result(
                operation,
                code="missing_dependency",
                message="twitter-cli is missing. Install it with uv tool install twitter-cli",
                meta=self.make_meta(value=value, limit=limit, started_at=started_at, **(extra_meta or {})),
            )

        try:
            result = self.run_command([twitter, *args], timeout=120)
        except Exception as exc:
            return self.error_result(
                operation,
                code="command_failed",
                message=f"Twitter {operation} failed: {exc}",
                meta=self.make_meta(value=value, limit=limit, started_at=started_at, **(extra_meta or {})),
            )

        raw_output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            code = "command_failed"
            message = f"Twitter {operation} command did not complete cleanly"
            raw: dict | str = raw_output
            parsed_code, parsed_message, parsed_payload = _parse_error_output(raw_output)
            if parsed_code:
                code = parsed_code
            elif "not_authenticated" in raw_output.lower():
                code = "not_authenticated"
            if parsed_message:
                message = parsed_message
            if parsed_payload is not None:
                raw = parsed_payload
            return self.error_result(
                operation,
                code=code,
                message=message,
                raw=raw,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at, **(extra_meta or {})),
                details={"returncode": result.returncode},
            )

        try:
            parsed_raw = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Twitter {operation} returned a non-JSON payload",
                raw=raw_output,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at, **(extra_meta or {})),
            )
        if not isinstance(parsed_raw, dict):
            return self.error_result(
                operation,
                code="invalid_response",
                message=f"Twitter {operation} returned an unexpected JSON payload",
                raw=parsed_raw,
                meta=self.make_meta(value=value, limit=limit, started_at=started_at, **(extra_meta or {})),
            )
        return parsed_raw, raw_output
