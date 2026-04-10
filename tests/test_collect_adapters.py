# -*- coding: utf-8 -*-
"""Tests for the external collection adapters."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent_reach.adapters.base import BaseAdapter
from agent_reach.adapters.bluesky import BlueskyAdapter
from agent_reach.adapters.crawl4ai import Crawl4AIAdapter
from agent_reach.adapters.exa_search import ExaSearchAdapter
from agent_reach.adapters.github import GitHubAdapter
from agent_reach.adapters.hacker_news import HackerNewsAdapter
from agent_reach.adapters.hatena_bookmark import HatenaBookmarkAdapter
from agent_reach.adapters.mcp_registry import MCPRegistryAdapter
from agent_reach.adapters.qiita import QiitaAdapter
from agent_reach.adapters.reddit import RedditAdapter
from agent_reach.adapters.rss import RSSAdapter
from agent_reach.adapters.searxng import SearXNGAdapter
from agent_reach.adapters.twitter import TwitterAdapter
from agent_reach.adapters.web import WebAdapter
from agent_reach.adapters.youtube import YouTubeAdapter
from agent_reach.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(config_path=tmp_path / "config.yaml")


def _cp(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_web_adapter_success(config, monkeypatch):
    class FakeResponse:
        text = (
            "Title: Example Domain\n\n"
            "Published Time: 2026-04-10T00:00:00Z\n\n"
            "Markdown Content:\n"
            "# Example Domain\n\nThis is a test page.\n"
        )

        def raise_for_status(self):
            return None

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.web._import_requests", lambda: FakeRequests)

    payload = WebAdapter(config=config).read("example.com")

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == "Example Domain"
    assert payload["items"][0]["published_at"] == "2026-04-10T00:00:00Z"
    assert "This is a test page." in payload["items"][0]["text"]
    assert payload["meta"]["text_length"] == len("# Example Domain\n\nThis is a test page.")
    assert payload["meta"]["link_count"] == 0
    assert payload["meta"]["extraction_warning"] is None
    assert payload["meta"]["returned_count"] == 1
    assert payload["items"][0]["extras"]["source_hints"] == {
        "source_kind": "unknown",
        "authority_hint": "unknown",
        "freshness_hint": "timestamped",
        "volatility_hint": "unknown",
    }


def test_web_adapter_navigation_heavy_warning(config, monkeypatch):
    links = "\n".join(f"- [Link {idx}](https://example.com/{idx})" for idx in range(30))

    class FakeResponse:
        text = f"Title: Navigation\n\nMarkdown Content:\n{links}\n"

        def raise_for_status(self):
            return None

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.web._import_requests", lambda: FakeRequests)

    payload = WebAdapter(config=config).read("example.com")

    assert payload["ok"] is True
    assert payload["meta"]["link_count"] >= 30
    assert payload["meta"]["extraction_warning"] == "navigation_heavy"


def test_web_adapter_http_error(config, monkeypatch):
    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, headers=None, timeout=None):
            raise RuntimeError("boom")

    monkeypatch.setattr("agent_reach.adapters.web._import_requests", lambda: FakeRequests)

    payload = WebAdapter(config=config).read("example.com")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "http_error"


def test_exa_adapter_success(config, monkeypatch):
    adapter = ExaSearchAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "mcporter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Title: Example result\n"
                                "URL: https://example.com/post\n"
                                "Published: 2026-04-10T00:00:00Z\n"
                                "Author: Alice\n"
                                "Highlights:\nA useful summary\n"
                            ),
                        }
                    ]
                }
            )
        ),
    )

    payload = adapter.search("example", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == "Example result"
    assert payload["items"][0]["author"] == "Alice"


def test_exa_adapter_missing_dependency(config):
    adapter = ExaSearchAdapter(config=config)
    adapter.command_path = lambda _name: None

    payload = adapter.search("example")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_dependency"


def test_exa_adapter_reports_invalid_response_when_normalization_fails(config, monkeypatch):
    adapter = ExaSearchAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "mcporter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps({"content": [{"type": "text", "text": "unexpected format"}]})
        ),
    )

    payload = adapter.search("example", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_response"


def test_hatena_bookmark_adapter_success(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = '{"ok":true}'

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "eid": "123",
                "title": "Example Domain",
                "url": "https://example.com/",
                "entry_url": "https://b.hatena.ne.jp/entry/s/example.com/",
                "count": 12,
                "screenshot": "https://example.com/image.png",
                "bookmarks": [
                    {"user": "alice", "comment": "useful", "timestamp": "2026/04/10 10:00", "tags": []}
                ],
                "related": [
                    {
                        "eid": "related-1",
                        "title": "Related Entry",
                        "url": "https://example.com/related",
                        "entry_url": "https://b.hatena.ne.jp/entry/s/example.com/related",
                        "count": 5,
                    }
                ],
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.hatena_bookmark._import_requests", lambda: FakeRequests)

    payload = HatenaBookmarkAdapter(config=config).read("https://example.com", limit=2)

    assert payload["ok"] is True
    assert payload["items"][0]["extras"]["bookmark_count"] == 12
    assert payload["items"][1]["kind"] == "related_page"


def test_hatena_bookmark_adapter_handles_missing_entry(config, monkeypatch):
    class EmptyResponse:
        status_code = 200
        text = "null"

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return None

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return EmptyResponse()

    adapter = HatenaBookmarkAdapter(config=config)
    monkeypatch.setattr("agent_reach.adapters.hatena_bookmark._import_requests", lambda: FakeRequests)
    monkeypatch.setattr(adapter, "_bookmark_count", lambda _url: 0)

    payload = adapter.read("https://example.com")

    assert payload["ok"] is True
    assert payload["items"][0]["extras"]["bookmark_count"] == 0


def test_bluesky_adapter_success(config, monkeypatch):
    class PublicApi403Response:
        status_code = 403
        text = "forbidden"

        @staticmethod
        def json():
            raise ValueError("not json")

    class ApiResponse:
        status_code = 200
        text = '{"posts":[]}'

        @staticmethod
        def json():
            return {
                "posts": [
                    {
                        "uri": "at://did:plc:abc/app.bsky.feed.post/3abc",
                        "cid": "cid-1",
                        "author": {"handle": "openai.com", "displayName": "OpenAI"},
                        "record": {
                            "text": "OpenAI shipped a thing",
                            "createdAt": "2026-04-10T00:00:00Z",
                        },
                        "likeCount": 10,
                        "replyCount": 2,
                        "repostCount": 3,
                        "quoteCount": 1,
                        "bookmarkCount": 4,
                        "indexedAt": "2026-04-10T00:00:01Z",
                        "labels": [],
                        "embed": {
                            "$type": "app.bsky.embed.images#view",
                            "images": [
                                {
                                    "fullsize": "https://cdn.bsky.app/img/feed_fullsize/plain/image-1.jpg",
                                    "thumb": "https://cdn.bsky.app/img/feed_thumbnail/plain/image-1.jpg",
                                    "alt": "Example image",
                                    "aspectRatio": {"width": 4, "height": 3},
                                }
                            ],
                        },
                    }
                ]
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, headers=None, timeout=None):
            if "public.api.bsky.app" in url:
                return PublicApi403Response()
            return ApiResponse()

    monkeypatch.setattr("agent_reach.adapters.bluesky._import_requests", lambda: FakeRequests)

    payload = BlueskyAdapter(config=config).search("OpenAI", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["author"] == "openai.com"
    assert payload["meta"]["api_base_url"] == "https://api.bsky.app"
    assert payload["meta"]["fallback_used"] is True
    assert payload["meta"]["attempted_host_results"][0]["reason"] == "http_403"
    assert payload["meta"]["attempted_host_results"][1]["reason"] == "ok"
    assert payload["meta"]["requested_limit"] == 1
    assert payload["meta"]["page_size"] == 1
    assert payload["meta"]["pages_fetched"] == 1
    assert payload["items"][0]["extras"]["media"][0]["type"] == "image"
    assert payload["items"][0]["extras"]["media"][0]["aspect_ratio"] == {"width": 4, "height": 3}
    assert payload["items"][0]["extras"]["source_hints"] == {
        "source_kind": "social_post",
        "authority_hint": "social",
        "freshness_hint": "timestamped",
        "volatility_hint": "high",
    }


def test_bluesky_adapter_normalizes_nested_video_embed(config, monkeypatch):
    class ApiResponse:
        status_code = 200
        text = '{"posts":[]}'

        @staticmethod
        def json():
            return {
                "posts": [
                    {
                        "uri": "at://did:plc:abc/app.bsky.feed.post/3abc",
                        "cid": "cid-1",
                        "author": {"handle": "openai.com", "displayName": "OpenAI"},
                        "record": {
                            "text": "Video post",
                            "createdAt": "2026-04-10T00:00:00Z",
                        },
                        "embed": {
                            "$type": "app.bsky.embed.recordWithMedia#view",
                            "media": {
                                "$type": "app.bsky.embed.video#view",
                                "playlist": "https://video.bsky.app/playlist.m3u8",
                                "thumbnail": "https://video.bsky.app/thumb.jpg",
                                "alt": "Video alt",
                                "aspectRatio": {"width": 9, "height": 16},
                            },
                        },
                    }
                ]
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, headers=None, timeout=None):
            return ApiResponse()

    monkeypatch.setattr("agent_reach.adapters.bluesky._import_requests", lambda: FakeRequests)

    payload = BlueskyAdapter(config=config).search("OpenAI", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["extras"]["media"][0]["type"] == "video"
    assert payload["items"][0]["extras"]["media"][0]["playlist_url"] == "https://video.bsky.app/playlist.m3u8"


def test_qiita_adapter_success(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "[]"
        headers = {"Total-Count": "42"}

        @staticmethod
        def json():
            return [
                {
                    "id": "abc123",
                    "title": "Qiita article",
                    "url": "https://qiita.com/Qiita/items/abc123",
                    "body": "markdown body",
                    "created_at": "2026-04-10T00:00:00+09:00",
                    "updated_at": "2026-04-10T01:00:00+09:00",
                    "likes_count": 10,
                    "stocks_count": 20,
                    "comments_count": 3,
                    "reactions_count": 4,
                    "page_views_count": 50,
                    "private": False,
                    "tags": [{"name": "Python"}],
                    "user": {"id": "Qiita"},
                }
            ]

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.qiita._import_requests", lambda: FakeRequests)

    payload = QiitaAdapter(config=config).search("python", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["author"] == "Qiita"
    assert payload["items"][0]["text"] == "markdown body"
    assert payload["raw"][0]["body"] == "markdown body"
    assert payload["meta"]["total_count"] == "42"
    assert payload["meta"]["body_mode"] == "full"
    assert payload["meta"]["requested_limit"] == 1
    assert payload["meta"]["page_size"] == 1
    assert payload["meta"]["pages_fetched"] == 1
    assert payload["meta"]["total_available"] == 42
    assert payload["meta"]["has_more"] is True


def test_qiita_adapter_body_mode_controls_text_and_raw(config, monkeypatch):
    body = "x" * 600

    class FakeResponse:
        status_code = 200
        text = "[]"
        headers = {"Total-Count": "1"}

        @staticmethod
        def json():
            return [
                {
                    "id": "abc123",
                    "title": "Qiita article",
                    "url": "https://qiita.com/Qiita/items/abc123",
                    "body": body,
                    "created_at": "2026-04-10T00:00:00+09:00",
                    "updated_at": "2026-04-10T01:00:00+09:00",
                    "tags": [],
                    "user": {"id": "Qiita"},
                }
            ]

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.qiita._import_requests", lambda: FakeRequests)

    none_payload = QiitaAdapter(config=config).search("python", limit=1, body_mode="none")
    snippet_payload = QiitaAdapter(config=config).search("python", limit=1, body_mode="snippet")

    assert none_payload["ok"] is True
    assert none_payload["items"][0]["text"] is None
    assert "body" not in none_payload["raw"][0]
    assert none_payload["meta"]["body_mode"] == "none"
    assert snippet_payload["items"][0]["text"] == body[:500]
    assert snippet_payload["raw"][0]["body"] == body[:500]
    assert snippet_payload["meta"]["body_mode"] == "snippet"


def test_github_adapter_read_success(config, monkeypatch):
    adapter = GitHubAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "gh")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=60, env=None: _cp(
            stdout=json.dumps(
                {
                    "name": "openai-python",
                    "nameWithOwner": "openai/openai-python",
                    "description": "Python SDK",
                    "url": "https://github.com/openai/openai-python",
                    "owner": {"login": "openai"},
                    "updatedAt": "2026-04-10T00:00:00Z",
                    "createdAt": "2020-01-01T00:00:00Z",
                    "homepageUrl": "https://example.com",
                    "stargazerCount": 1,
                    "forkCount": 2,
                    "licenseInfo": {"name": "MIT"},
                    "primaryLanguage": {"name": "Python"},
                    "isPrivate": False,
                    "isArchived": False,
                    "defaultBranchRef": {"name": "main"},
                    "repositoryTopics": [{"name": "openai"}],
                }
            )
        ),
    )

    payload = adapter.read("openai/openai-python")

    assert payload["ok"] is True
    assert payload["items"][0]["id"] == "openai/openai-python"
    assert payload["items"][0]["extras"]["default_branch"] == "main"
    assert payload["items"][0]["extras"]["source_hints"] == {
        "source_kind": "repository",
        "authority_hint": "project_owner",
        "freshness_hint": "timestamped",
        "volatility_hint": "medium",
    }


def test_github_adapter_invalid_json(config, monkeypatch):
    adapter = GitHubAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "gh")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=60, env=None: _cp(stdout="not json"),
    )

    payload = adapter.search("agent reach", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_response"


def test_youtube_adapter_success(config, monkeypatch):
    adapter = YouTubeAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "yt-dlp")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps(
                {
                    "id": "abc123",
                    "title": "Example Video",
                    "webpage_url": "https://www.youtube.com/watch?v=abc123",
                    "description": "Video description",
                    "channel": "Example Channel",
                    "upload_date": "20260410",
                    "duration": 19,
                    "subtitles": {"en": [{}]},
                }
            )
        ),
    )

    payload = adapter.read("https://www.youtube.com/watch?v=abc123")

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "video"
    assert payload["items"][0]["extras"]["subtitle_languages"] == ["en"]


def test_youtube_adapter_invalid_json(config, monkeypatch):
    adapter = YouTubeAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "yt-dlp")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(stdout="broken"),
    )

    payload = adapter.read("https://www.youtube.com/watch?v=abc123")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_response"


def test_rss_adapter_success(config, monkeypatch):
    parsed = SimpleNamespace(
        feed={"title": "Example Feed"},
        entries=[
            {
                "id": "entry-1",
                "title": "Example Entry",
                "link": "https://example.com/post",
                "summary": "Summary",
                "author": "Alice",
                "published": "2026-04-10T00:00:00Z",
            }
        ],
        bozo=False,
        status=200,
    )
    monkeypatch.setattr("agent_reach.adapters.rss.feedparser.parse", lambda url: parsed)

    payload = RSSAdapter(config=config).read("https://example.com/feed.xml", limit=1)

    assert payload["ok"] is True
    assert payload["meta"]["feed_title"] == "Example Feed"
    assert payload["meta"]["page_size"] == 1
    assert payload["meta"]["pages_fetched"] == 1
    assert payload["meta"]["total_available"] == 1
    assert payload["meta"]["has_more"] is False
    assert payload["items"][0]["author"] == "Alice"
    assert payload["items"][0]["extras"]["source_hints"] == {
        "source_kind": "feed_item",
        "authority_hint": "unknown",
        "freshness_hint": "timestamped",
        "volatility_hint": "medium",
    }


def test_rss_adapter_parse_failure(config, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.adapters.rss.feedparser.parse",
        lambda url: (_ for _ in ()).throw(RuntimeError("broken")),
    )

    payload = RSSAdapter(config=config).read("https://example.com/feed.xml")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "parse_failed"


def test_twitter_adapter_success(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    captured = {}

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": [
                        {
                            "id": "123",
                            "text": "OpenAI shipped a thing",
                            "author": {"screenName": "OpenAI", "name": "OpenAI"},
                            "createdAtISO": "2026-04-10T00:00:00Z",
                            "metrics": {"likes": 10},
                        }
                    ],
                }
            )
        )

    monkeypatch.setattr(
        adapter,
        "run_command",
        fake_run,
    )

    payload = adapter.search("OpenAI", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["author"] == "OpenAI"
    assert payload["items"][0]["url"] == "https://x.com/OpenAI/status/123"
    assert payload["items"][0]["extras"]["metrics"] == {"likes": 10}
    assert captured["command"][1:3] == ["search", "OpenAI"]


def test_twitter_adapter_search_translates_common_advanced_tokens(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    captured = {}

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(stdout=json.dumps({"ok": True, "data": []}))

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.search("from:OpenAI has:media type:photos lang:ja", limit=5)

    assert payload["ok"] is True
    assert captured["command"] == [
        "twitter",
        "search",
        "--from",
        "OpenAI",
        "--has",
        "media",
        "--type",
        "photos",
        "--lang",
        "ja",
        "-n",
        "5",
        "--json",
    ]


def test_twitter_adapter_user_success(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "id": "4398626122",
                        "name": "OpenAI",
                        "screenName": "OpenAI",
                        "bio": "Research lab",
                        "followers": 100,
                        "following": 4,
                        "tweets": 10,
                        "likes": 5,
                        "verified": True,
                        "url": "https://openai.com",
                        "createdAtISO": "2015-12-06T22:51:08+00:00",
                    },
                }
            )
        ),
    )

    payload = adapter.user("@OpenAI")

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "profile"
    assert payload["items"][0]["url"] == "https://x.com/OpenAI"
    assert payload["items"][0]["extras"]["followers"] == 100


def test_twitter_adapter_user_posts_success(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": [
                        {
                            "id": "123",
                            "text": "OpenAI shipped a thing",
                            "author": {"screenName": "OpenAI", "name": "OpenAI"},
                            "createdAtISO": "2026-04-10T00:00:00Z",
                            "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/a.png"}],
                        }
                    ],
                }
            )
        ),
    )

    payload = adapter.user_posts("https://x.com/OpenAI", limit=1)

    assert payload["ok"] is True
    assert payload["operation"] == "user_posts"
    assert payload["items"][0]["extras"]["media"][0]["type"] == "photo"


def test_twitter_adapter_tweet_success(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    captured = {}

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(
            stdout=json.dumps(
                {
                    "ok": True,
                    "data": [
                        {
                            "id": "123",
                            "text": "OpenAI shipped a thing",
                            "author": {"screenName": "OpenAI", "name": "OpenAI"},
                            "createdAtISO": "2026-04-10T00:00:00Z",
                        }
                    ],
                }
            )
        )

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.tweet("https://x.com/OpenAI/status/123", limit=1)

    assert payload["ok"] is True
    assert captured["command"][2] == "123"
    assert payload["items"][0]["url"] == "https://x.com/OpenAI/status/123"


def test_twitter_adapter_not_authenticated(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stderr="error:\n  code: not_authenticated\n",
            returncode=1,
        ),
    )

    payload = adapter.search("OpenAI", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_authenticated"


def test_twitter_adapter_preserves_structured_backend_errors(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=120, env=None: _cp(
            stdout=json.dumps(
                {
                    "ok": False,
                    "schema_version": "1",
                    "error": {
                        "code": "not_found",
                        "message": "Twitter API error (HTTP 404): Twitter API error 404: ",
                    },
                }
            ),
            returncode=1,
        ),
    )

    payload = adapter.search("OpenAI", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["message"].startswith("Twitter API error (HTTP 404)")
    assert payload["raw"]["error"]["code"] == "not_found"


def test_searxng_adapter_success(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "results": [
                    {
                        "title": "Example result",
                        "url": "https://example.com/post",
                        "content": "A useful snippet",
                        "publishedDate": "2026-04-10T00:00:00Z",
                        "engines": ["duckduckgo"],
                        "category": "general",
                    }
                ]
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    config.set("searxng_base_url", "https://search.example.com/search")
    monkeypatch.setattr("agent_reach.adapters.searxng._import_requests", lambda: FakeRequests)

    payload = SearXNGAdapter(config=config).search("agent reach", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == "Example result"
    assert payload["items"][0]["extras"]["engines"] == ["duckduckgo"]
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "search_result"
    assert payload["meta"]["base_url"] == "https://search.example.com"
    assert payload["meta"]["requested_limit"] == 1
    assert payload["meta"]["page_size"] == 1
    assert payload["meta"]["pages_fetched"] == 1


def test_searxng_adapter_requires_config(config):
    payload = SearXNGAdapter(config=config).search("agent reach", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_configuration"


def test_searxng_adapter_reports_non_json_instances(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "<html>disabled</html>"

        @staticmethod
        def json():
            raise ValueError("not json")

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    config.set("searxng_base_url", "https://search.example.com")
    monkeypatch.setattr("agent_reach.adapters.searxng._import_requests", lambda: FakeRequests)

    payload = SearXNGAdapter(config=config).search("agent reach", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_response"
    assert "format=json" in payload["error"]["message"]


def test_crawl4ai_adapter_missing_dependency(config, monkeypatch):
    monkeypatch.setattr(
        "agent_reach.adapters.crawl4ai._import_crawl4ai",
        lambda: (_ for _ in ()).throw(ImportError("missing crawl4ai")),
    )
    payload = Crawl4AIAdapter(config=config).read("https://example.com")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_dependency"


def test_crawl4ai_adapter_read_success(config, monkeypatch):
    class FakeMarkdown:
        raw_markdown = "# Example\n\nRead body"

    class FakeCrawler:
        def __init__(self, config=None):
            self.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def arun(self, url, config=None):
            return SimpleNamespace(
                url=url,
                redirected_url=url,
                status_code=200,
                success=True,
                metadata={"title": "Example", "author": "Alice", "publishedAt": "2026-04-10T00:00:00Z"},
                markdown=FakeMarkdown(),
                error_message=None,
            )

    bundle = SimpleNamespace(
        AsyncWebCrawler=FakeCrawler,
        BrowserConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        CrawlerRunConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        BestFirstCrawlingStrategy=None,
        DomainFilter=None,
        FilterChain=None,
        KeywordRelevanceScorer=None,
    )
    monkeypatch.setattr("agent_reach.adapters.crawl4ai._import_crawl4ai", lambda: bundle)

    payload = Crawl4AIAdapter(config=config).read("https://example.com")

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == "Example"
    assert payload["items"][0]["author"] == "Alice"
    assert payload["items"][0]["published_at"] == "2026-04-10T00:00:00Z"
    assert payload["raw"]["markdown"] == "# Example\n\nRead body"
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "page"


def test_crawl4ai_adapter_crawl_requires_query(config):
    payload = Crawl4AIAdapter(config=config).crawl("https://example.com", limit=2)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"


def test_crawl4ai_adapter_crawl_success_same_origin_only(config, monkeypatch):
    class FakeMarkdown:
        def __init__(self, text):
            self.raw_markdown = text

    class FakeCrawler:
        def __init__(self, config=None):
            self.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def arun(self, url, config=None):
            return [
                SimpleNamespace(
                    url="https://example.com/start",
                    redirected_url="https://example.com/start",
                    status_code=200,
                    success=True,
                    metadata={"title": "Start"},
                    markdown=FakeMarkdown("# Start"),
                    error_message=None,
                ),
                SimpleNamespace(
                    url="https://example.com/pricing",
                    redirected_url="https://example.com/pricing",
                    status_code=200,
                    success=True,
                    metadata={"title": "Pricing"},
                    markdown=FakeMarkdown("# Pricing"),
                    error_message=None,
                ),
                SimpleNamespace(
                    url="https://other.example.net/offsite",
                    redirected_url="https://other.example.net/offsite",
                    status_code=200,
                    success=True,
                    metadata={"title": "Offsite"},
                    markdown=FakeMarkdown("# Offsite"),
                    error_message=None,
                ),
            ]

    bundle = SimpleNamespace(
        AsyncWebCrawler=FakeCrawler,
        BrowserConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        CrawlerRunConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        BestFirstCrawlingStrategy=lambda **kwargs: SimpleNamespace(**kwargs),
        DomainFilter=lambda **kwargs: SimpleNamespace(**kwargs),
        FilterChain=lambda **kwargs: SimpleNamespace(**kwargs),
        KeywordRelevanceScorer=lambda keywords: SimpleNamespace(keywords=keywords),
    )
    monkeypatch.setattr("agent_reach.adapters.crawl4ai._import_crawl4ai", lambda: bundle)

    payload = Crawl4AIAdapter(config=config).crawl(
        "https://example.com/start",
        limit=5,
        crawl_query="pricing faq",
    )

    assert payload["ok"] is True
    assert [item["url"] for item in payload["items"]] == [
        "https://example.com/start",
        "https://example.com/pricing",
    ]
    assert payload["meta"]["skipped_external_count"] == 1
    assert payload["raw"]["skipped_external_urls"] == ["https://other.example.net/offsite"]
    assert payload["items"][0]["extras"]["crawl_query"] == "pricing faq"


def test_hacker_news_search_success(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "hits": [
                    {
                        "objectID": "123",
                        "title": "Agent frameworks",
                        "url": "https://example.com/agent-frameworks",
                        "author": "alice",
                        "created_at": "2026-04-10T00:00:00Z",
                        "points": 42,
                        "num_comments": 3,
                        "_tags": ["story"],
                    }
                ],
                "hitsPerPage": 1,
                "nbHits": 10,
                "nbPages": 10,
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.hacker_news._import_requests", lambda: FakeRequests)

    payload = HackerNewsAdapter(config=config).search("agent frameworks", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["id"] == "123"
    assert payload["items"][0]["extras"]["hn_url"] == "https://news.ycombinator.com/item?id=123"
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "search_result"
    assert payload["meta"]["backend"] == "hn_algolia"
    assert payload["meta"]["total_available"] == 10


def test_hacker_news_top_reads_story_items(config, monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self):
            return self._payload

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            if url.endswith("/topstories.json"):
                return FakeResponse([123, 456])
            return FakeResponse(
                {
                    "id": 123,
                    "type": "story",
                    "title": "HN Story",
                    "url": "https://example.com/story",
                    "by": "alice",
                    "time": 1775788800,
                    "score": 10,
                    "descendants": 2,
                }
            )

    monkeypatch.setattr("agent_reach.adapters.hacker_news._import_requests", lambda: FakeRequests)

    payload = HackerNewsAdapter(config=config).top("top", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "hacker_news_story"
    assert payload["items"][0]["author"] == "alice"
    assert payload["meta"]["backend"] == "hacker_news_firebase"


def test_mcp_registry_search_success(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "servers": [
                    {
                        "server": {
                            "name": "ac.tandem/docs-mcp",
                            "description": "Remote MCP server for docs",
                            "repository": {"url": "https://github.com/frumu-ai/tandem", "source": "github"},
                            "websiteUrl": "https://tandem.ac",
                            "version": "0.3.0",
                            "remotes": [{"type": "streamable-http", "url": "https://tandem.ac/mcp"}],
                            "unknownPreviewField": True,
                        },
                        "_meta": {
                            "io.modelcontextprotocol.registry/official": {
                                "status": "active",
                                "publishedAt": "2026-04-02T11:22:40Z",
                                "updatedAt": "2026-04-03T00:00:00Z",
                                "isLatest": True,
                            }
                        },
                    }
                ],
                "metadata": {"count": 1, "nextCursor": None},
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.mcp_registry._import_requests", lambda: FakeRequests)

    payload = MCPRegistryAdapter(config=config).search("docs mcp", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "mcp_server"
    assert payload["items"][0]["id"] == "ac.tandem/docs-mcp"
    assert payload["items"][0]["extras"]["repository_url"] == "https://github.com/frumu-ai/tandem"
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "registry_entry"
    assert payload["meta"]["pages_fetched"] == 1


def test_mcp_registry_read_latest_and_not_found(config, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self):
            return self._payload

    captured = {}

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            captured["url"] = url
            if "missing" in url:
                return FakeResponse(404, {"error": "not found"})
            return FakeResponse(
                200,
                {
                    "server": {
                        "name": "ac.tandem/docs-mcp",
                        "description": "Remote MCP server",
                        "version": "0.3.0",
                    },
                    "_meta": {},
                },
            )

    monkeypatch.setattr("agent_reach.adapters.mcp_registry._import_requests", lambda: FakeRequests)

    payload = MCPRegistryAdapter(config=config).read("ac.tandem/docs-mcp")
    missing = MCPRegistryAdapter(config=config).read("missing/server")

    assert payload["ok"] is True
    assert "versions/latest" in captured["url"]
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_found"


def test_reddit_search_success_with_bearer_token(config, monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "kind": "Listing",
                "data": {
                    "after": "t3_next",
                    "children": [
                        {
                            "kind": "t3",
                            "data": {
                                "name": "t3_abc",
                                "id": "abc",
                                "title": "Agent discussion",
                                "permalink": "/r/LocalLLaMA/comments/abc/agent_discussion/",
                                "selftext": "Thread body",
                                "author": "alice",
                                "created_utc": 1775788800,
                                "subreddit": "LocalLLaMA",
                                "score": 10,
                                "num_comments": 2,
                                "url": "https://www.reddit.com/r/LocalLLaMA/comments/abc/agent_discussion/",
                            },
                        }
                    ],
                },
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            assert url.endswith("/r/LocalLLaMA/search")
            assert params["restrict_sr"] == 1
            assert headers["Authorization"] == "Bearer token"
            return FakeResponse()

    config.set("reddit_user_agent", "windows:agent-reach:v1.6.0 (by /u/example)")
    config.set("reddit_access_token", "token")
    monkeypatch.setattr("agent_reach.adapters.reddit._import_requests", lambda: FakeRequests)

    payload = RedditAdapter(config=config).search("r/LocalLLaMA agent frameworks", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "reddit_post"
    assert payload["items"][0]["extras"]["subreddit"] == "LocalLLaMA"
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "forum_post"
    assert payload["meta"]["next_cursor"] == "t3_next"


def test_reddit_read_success_with_client_credentials(config, monkeypatch):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self.status_code = status_code
            self.text = json.dumps(payload)
            self._payload = payload

        def json(self):
            return self._payload

    calls = []

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def post(url, data=None, auth=None, headers=None, timeout=None):
            calls.append(("post", url, data, auth))
            return FakeResponse({"access_token": "oauth-token"})

        @staticmethod
        def get(url, params=None, headers=None, timeout=None):
            calls.append(("get", url, params, headers["Authorization"]))
            return FakeResponse(
                [
                    {
                        "kind": "Listing",
                        "data": {
                            "children": [
                                {
                                    "kind": "t3",
                                    "data": {
                                        "name": "t3_abc",
                                        "id": "abc",
                                        "title": "Thread title",
                                        "permalink": "/r/redditdev/comments/abc/thread/",
                                        "selftext": "Thread body",
                                        "author": "alice",
                                    },
                                }
                            ]
                        },
                    },
                    {
                        "kind": "Listing",
                        "data": {
                            "children": [
                                {
                                    "kind": "t1",
                                    "data": {
                                        "name": "t1_def",
                                        "id": "def",
                                        "body": "Comment body",
                                        "author": "bob",
                                        "permalink": "/r/redditdev/comments/abc/thread/def/",
                                    },
                                }
                            ]
                        },
                    },
                ]
            )

    config.set("reddit_user_agent", "windows:agent-reach:v1.6.0 (by /u/example)")
    config.set("reddit_client_id", "client-id")
    config.set("reddit_client_secret", "client-secret")
    monkeypatch.setattr("agent_reach.adapters.reddit._import_requests", lambda: FakeRequests)

    payload = RedditAdapter(config=config).read("https://www.reddit.com/r/redditdev/comments/abc/thread/", limit=2)

    assert payload["ok"] is True
    assert calls[0][3] == ("client-id", "client-secret")
    assert calls[1][3] == "Bearer oauth-token"
    assert [item["kind"] for item in payload["items"]] == ["reddit_post", "reddit_comment"]
    assert payload["meta"]["comment_count"] == 1


def test_reddit_requires_oauth_configuration(config):
    missing_agent = RedditAdapter(config=config).search("agent frameworks", limit=1)
    config.set("reddit_user_agent", "windows:agent-reach:v1.6.0 (by /u/example)")
    missing_oauth = RedditAdapter(config=config).search("agent frameworks", limit=1)

    assert missing_agent["ok"] is False
    assert missing_agent["error"]["code"] == "missing_configuration"
    assert "User-Agent" in missing_agent["error"]["message"]
    assert missing_oauth["ok"] is False
    assert missing_oauth["error"]["code"] == "missing_configuration"
    assert "OAuth" in missing_oauth["error"]["message"]


def test_base_adapter_runtime_env_is_noninteractive_and_utf8(config, monkeypatch):
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    config.set("qiita_token", "qiita-token")
    config.set("searxng_base_url", "https://search.example.com")
    config.set("reddit_access_token", "reddit-token")
    config.set("reddit_user_agent", "windows:agent-reach:v1.6.0 (by /u/example)")

    env = BaseAdapter(config=config).runtime_env()

    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"
    assert env["QIITA_TOKEN"] == "qiita-token"
    assert env["SEARXNG_BASE_URL"] == "https://search.example.com"
    assert env["REDDIT_ACCESS_TOKEN"] == "reddit-token"
    assert env["REDDIT_USER_AGENT"] == "windows:agent-reach:v1.6.0 (by /u/example)"
