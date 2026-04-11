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
            "![Chart](https://example.com/chart.png)\n"
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
    assert payload["meta"]["text_length"] == len(
        "# Example Domain\n\nThis is a test page.\n![Chart](https://example.com/chart.png)"
    )
    assert payload["meta"]["link_count"] == 1
    assert payload["meta"]["image_count"] == 1
    assert payload["meta"]["link_density"] > 0
    assert payload["meta"]["extraction_warning"] is None
    assert payload["meta"]["extraction_hygiene"]["image_count"] == 1
    assert payload["items"][0]["media_references"] == [
        {
            "type": "image",
            "url": "https://example.com/chart.png",
            "relation": "page_image",
            "source_field": "markdown",
        }
    ]
    assert payload["meta"]["returned_count"] == 1
    assert payload["items"][0]["extras"]["extraction_hygiene"]["image_count"] == 1
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


def test_web_adapter_http_status_reports_reader_dns_error(config, monkeypatch):
    class FakeResponse:
        status_code = 400
        text = "ParamValidationError(url): Domain 'docs.hyperbrowser.ai' could not be resolved"

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.web._import_requests", lambda: FakeRequests)

    payload = WebAdapter(config=config).read("https://docs.hyperbrowser.ai/agents/browser-use")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "dns_error"
    assert payload["meta"]["reader_status_code"] == 400
    assert payload["error"]["details"]["unresolved_domain"] == "docs.hyperbrowser.ai"
    assert "could not be resolved" in payload["raw"]


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
    assert payload["items"][0]["extras"]["media_references"][0] == {
        "type": "image",
        "url": "https://example.com/image.png",
        "relation": "screenshot",
        "source_field": "screenshot",
    }
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
    assert payload["items"][0]["extras"]["media_references"][0]["relation"] == "embed_media"
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
    assert payload["items"][0]["extras"]["media_references"][0]["type"] == "video"
    assert payload["items"][0]["extras"]["media_references"][0]["url"] == "https://video.bsky.app/playlist.m3u8"


def test_bluesky_adapter_paginates_with_cursor(config, monkeypatch):
    captured_urls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, cursor_value):
            self._cursor_value = cursor_value
            self.text = '{"posts":[]}'

        def json(self):
            if self._cursor_value == "c1":
                base = 3
                next_cursor = "c2"
            else:
                base = 1
                next_cursor = "c1"
            return {
                "posts": [
                    {
                        "uri": f"at://did:plc:abc/app.bsky.feed.post/{base}",
                        "cid": f"cid-{base}",
                        "author": {"handle": "openai.com"},
                        "record": {"text": f"Post {base}", "createdAt": "2026-04-10T00:00:00Z"},
                    },
                    {
                        "uri": f"at://did:plc:abc/app.bsky.feed.post/{base + 1}",
                        "cid": f"cid-{base + 1}",
                        "author": {"handle": "openai.com"},
                        "record": {"text": f"Post {base + 1}", "createdAt": "2026-04-10T00:00:00Z"},
                    },
                ],
                "cursor": next_cursor,
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, headers=None, timeout=None):
            captured_urls.append(url)
            cursor_value = "c1" if "cursor=c1" in url else None
            return FakeResponse(cursor_value)

    monkeypatch.setattr("agent_reach.adapters.bluesky._import_requests", lambda: FakeRequests)

    payload = BlueskyAdapter(config=config).search("OpenAI", limit=5, page_size=2, max_pages=2)

    assert payload["ok"] is True
    assert "limit=2" in captured_urls[0]
    assert "cursor=c1" in captured_urls[1]
    assert payload["meta"]["requested_page_size"] == 2
    assert payload["meta"]["requested_max_pages"] == 2
    assert payload["meta"]["page_size"] == 2
    assert payload["meta"]["pages_fetched"] == 2
    assert payload["meta"]["next_cursor"] == "c2"
    assert payload["meta"]["has_more"] is True
    assert payload["meta"]["pagination"]["next_cursor"] == "c2"
    assert len(payload["items"]) == 4
    assert len(payload["raw"]["posts"]) == 4


def test_bluesky_adapter_keeps_partial_results_when_later_page_fails(config, monkeypatch):
    captured_urls = []

    class FirstPageResponse:
        status_code = 200
        text = '{"posts":[]}'

        @staticmethod
        def json():
            return {
                "posts": [
                    {
                        "uri": "at://did:plc:abc/app.bsky.feed.post/1",
                        "cid": "cid-1",
                        "author": {"handle": "openai.com"},
                        "record": {"text": "Post 1", "createdAt": "2026-04-10T00:00:00Z"},
                    }
                ],
                "cursor": "c1",
            }

    class ForbiddenResponse:
        status_code = 403
        text = "<html><body><h1>403 Forbidden</h1></body></html>"

        @staticmethod
        def json():
            raise ValueError("not json")

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(url, headers=None, timeout=None):
            captured_urls.append(url)
            if "cursor=c1" in url:
                return ForbiddenResponse()
            return FirstPageResponse()

    monkeypatch.setattr("agent_reach.adapters.bluesky._import_requests", lambda: FakeRequests)

    payload = BlueskyAdapter(config=config).search("OpenAI", limit=3, page_size=1, max_pages=2)

    assert payload["ok"] is True
    assert "cursor=c1" in captured_urls[1]
    assert payload["items"][0]["title"] == "Post 1"
    assert payload["meta"]["next_cursor"] == "c1"
    assert payload["meta"]["has_more"] is True
    assert payload["meta"]["pagination_interrupted"]["code"] == "http_error"


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
                    "body": "markdown body ![diagram](https://cdn.qiita.com/diagram.png)",
                    "rendered_body": "<p>markdown body</p>",
                    "created_at": "2026-04-10T00:00:00+09:00",
                    "updated_at": "2026-04-10T01:00:00+09:00",
                    "likes_count": 10,
                    "stocks_count": 20,
                    "comments_count": 3,
                    "reactions_count": 4,
                    "page_views_count": 50,
                    "private": False,
                    "tags": [{"name": "Python"}],
                    "user": {"id": "Qiita", "profile_image_url": "https://qiita-user.example/avatar.png"},
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
    assert payload["items"][0]["text"] == "markdown body ![diagram](https://cdn.qiita.com/diagram.png)"
    assert payload["raw"][0]["body"] == "markdown body ![diagram](https://cdn.qiita.com/diagram.png)"
    assert payload["raw"][0]["tags"] == ["Python"]
    assert "rendered_body" not in payload["raw"][0]
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://qiita-user.example/avatar.png",
            "relation": "avatar",
            "source_field": "user.profile_image_url",
        },
        {
            "type": "image",
            "url": "https://cdn.qiita.com/diagram.png",
            "relation": "body_image",
            "source_field": "body",
        },
    ]
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "article"
    assert payload["meta"]["total_count"] == "42"
    assert payload["meta"]["body_mode"] == "full"
    assert payload["meta"]["requested_limit"] == 1
    assert payload["meta"]["page_size"] == 1
    assert payload["meta"]["pages_fetched"] == 1
    assert payload["meta"]["total_available"] == 42
    assert payload["meta"]["has_more"] is True


def test_qiita_adapter_body_mode_controls_text_and_raw(config, monkeypatch):
    body = ("x" * 580) + " ![diagram](https://cdn.qiita.com/diagram.png)"

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
                    "user": {"id": "Qiita", "profile_image_url": "https://qiita-user.example/avatar.png"},
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
    assert none_payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://qiita-user.example/avatar.png",
            "relation": "avatar",
            "source_field": "user.profile_image_url",
        }
    ]
    assert snippet_payload["items"][0]["text"] == body[:500]
    assert snippet_payload["raw"][0]["body"] == body[:500]
    assert snippet_payload["meta"]["body_mode"] == "snippet"
    assert snippet_payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://qiita-user.example/avatar.png",
            "relation": "avatar",
            "source_field": "user.profile_image_url",
        }
    ]


def test_qiita_adapter_paginates_with_body_mode(config, monkeypatch):
    captured_params = []

    class FakeResponse:
        def __init__(self, page_number):
            self.status_code = 200
            self.text = "[]"
            self.headers = {"Total-Count": "10"}
            self._page_number = page_number

        def json(self):
            base = (self._page_number - 1) * 2
            return [
                {
                    "id": f"q{base + 1}",
                    "title": f"Qiita article {base + 1}",
                    "url": f"https://qiita.com/Qiita/items/q{base + 1}",
                    "body": f"body {base + 1}",
                    "created_at": "2026-04-10T00:00:00+09:00",
                    "updated_at": "2026-04-10T01:00:00+09:00",
                    "tags": [],
                    "user": {"id": "Qiita"},
                },
                {
                    "id": f"q{base + 2}",
                    "title": f"Qiita article {base + 2}",
                    "url": f"https://qiita.com/Qiita/items/q{base + 2}",
                    "body": f"body {base + 2}",
                    "created_at": "2026-04-10T00:00:00+09:00",
                    "updated_at": "2026-04-10T01:00:00+09:00",
                    "tags": [],
                    "user": {"id": "Qiita"},
                },
            ]

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            captured_params.append(params)
            return FakeResponse(int(params["page"]))

    monkeypatch.setattr("agent_reach.adapters.qiita._import_requests", lambda: FakeRequests)

    payload = QiitaAdapter(config=config).search("python", limit=5, body_mode="snippet", page_size=2, max_pages=2, page=3)

    assert payload["ok"] is True
    assert captured_params == [
        {"query": "python", "page": "3", "per_page": "2"},
        {"query": "python", "page": "4", "per_page": "2"},
    ]
    assert payload["meta"]["body_mode"] == "snippet"
    assert payload["meta"]["requested_page_size"] == 2
    assert payload["meta"]["requested_max_pages"] == 2
    assert payload["meta"]["requested_page"] == 3
    assert payload["meta"]["page_size"] == 2
    assert payload["meta"]["pages_fetched"] == 2
    assert payload["meta"]["next_page"] == 5
    assert payload["meta"]["has_more"] is True
    assert payload["meta"]["pagination"]["next_page"] == 5
    assert len(payload["items"]) == 4
    assert payload["raw"][0]["body"] == "body 5"


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
    assert payload["items"][0]["engagement"] == {"stars": 1, "forks": 2}
    assert payload["items"][0]["identifiers"]["repo_full_name"] == "openai/openai-python"
    assert payload["items"][0]["extras"]["default_branch"] == "main"
    assert payload["items"][0]["extras"]["source_hints"] == {
        "source_kind": "repository",
        "authority_hint": "project_owner",
        "freshness_hint": "timestamped",
        "volatility_hint": "medium",
    }


def test_github_adapter_search_paginates_via_gh_api(config, monkeypatch):
    adapter = GitHubAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "gh")
    captured_commands = []

    def fake_run(command, timeout=60, env=None):
        captured_commands.append(command)
        page_number = int(command[-1].split("=", 1)[1])
        start = (page_number - 1) * 2
        items = [
            {
                "name": f"repo-{start + 1}",
                "fullName": f"openai/repo-{start + 1}",
                "description": f"Repo {start + 1}",
                "url": f"https://github.com/openai/repo-{start + 1}",
                "owner": {"login": "openai"},
                "updatedAt": "2026-04-10T00:00:00Z",
                "stargazersCount": start + 1,
                "language": "Python",
            },
            {
                "name": f"repo-{start + 2}",
                "fullName": f"openai/repo-{start + 2}",
                "description": f"Repo {start + 2}",
                "url": f"https://github.com/openai/repo-{start + 2}",
                "owner": {"login": "openai"},
                "updatedAt": "2026-04-10T00:00:00Z",
                "stargazersCount": start + 2,
                "language": "Python",
            },
        ]
        return _cp(stdout=json.dumps({"total_count": 10, "items": items}))

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.search("agent reach", limit=5, page_size=2, max_pages=2, page=1)

    assert payload["ok"] is True
    assert captured_commands[0] == [
        "gh",
        "api",
        "-X",
        "GET",
        "search/repositories",
        "-f",
        "q=agent reach",
        "-f",
        "per_page=2",
        "-f",
        "page=1",
    ]
    assert captured_commands[1][-1] == "page=2"
    assert payload["meta"]["backend"] == "gh_api"
    assert payload["meta"]["requested_page_size"] == 2
    assert payload["meta"]["requested_max_pages"] == 2
    assert payload["meta"]["requested_page"] == 1
    assert payload["meta"]["page_size"] == 2
    assert payload["meta"]["pages_fetched"] == 2
    assert payload["meta"]["next_page"] == 3
    assert payload["meta"]["has_more"] is True
    assert payload["meta"]["pagination"]["next_page"] == 3
    assert len(payload["items"]) == 4
    assert len(payload["raw"]) == 4
    assert payload["items"][0]["engagement"]["stars"] == 1
    assert payload["items"][0]["identifiers"]["repo_full_name"] == "openai/repo-1"


def test_github_adapter_search_normalizes_rest_api_repository_fields(config, monkeypatch):
    adapter = GitHubAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "gh")
    monkeypatch.setattr(
        adapter,
        "run_command",
        lambda command, timeout=60, env=None: _cp(
            stdout=json.dumps(
                {
                    "total_count": 1,
                    "items": [
                        {
                            "name": "Agent-Reach",
                            "full_name": "iwachacha/Agent-Reach",
                            "html_url": "https://github.com/iwachacha/Agent-Reach",
                            "description": "Research integration",
                            "owner": {"login": "iwachacha"},
                            "updated_at": "2026-04-10T00:00:00Z",
                            "stargazers_count": 42,
                            "forks_count": 3,
                        }
                    ],
                }
            )
        ),
    )

    payload = adapter.search("agent reach", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["id"] == "iwachacha/Agent-Reach"
    assert payload["items"][0]["url"] == "https://github.com/iwachacha/Agent-Reach"
    assert payload["items"][0]["engagement"] == {"stars": 42, "forks": 3}
    assert payload["items"][0]["identifiers"]["repo_full_name"] == "iwachacha/Agent-Reach"


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
                    "thumbnail": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
                    "thumbnails": [
                        {"url": "https://i.ytimg.com/vi/abc123/1.jpg"},
                        {"url": "https://i.ytimg.com/vi/abc123/2.jpg"},
                    ],
                    "subtitles": {"en": [{}]},
                    "automatic_captions": {"ja": [{}]},
                    "requested_subtitles": {"en": {}},
                }
            )
        ),
    )

    payload = adapter.read("https://www.youtube.com/watch?v=abc123")

    assert payload["ok"] is True
    assert payload["items"][0]["kind"] == "video"
    assert payload["items"][0]["extras"]["thumbnail_url"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    assert payload["items"][0]["extras"]["thumbnail_count"] == 2
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
            "relation": "thumbnail",
            "source_field": "thumbnail",
        },
        {
            "type": "image",
            "url": "https://i.ytimg.com/vi/abc123/1.jpg",
            "relation": "thumbnail",
            "source_field": "thumbnails[]",
        },
        {
            "type": "image",
            "url": "https://i.ytimg.com/vi/abc123/2.jpg",
            "relation": "thumbnail",
            "source_field": "thumbnails[]",
        },
    ]
    assert payload["items"][0]["extras"]["subtitle_languages"] == ["en"]
    assert payload["items"][0]["extras"]["automatic_caption_languages"] == ["ja"]
    assert payload["items"][0]["extras"]["has_subtitles"] is True
    assert payload["items"][0]["extras"]["has_automatic_captions"] is True
    assert payload["items"][0]["extras"]["requested_subtitle_languages"] == ["en"]
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "video"


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
    assert payload["items"][0]["engagement"] == {"likes": 10}
    assert payload["meta"]["diagnostics"]["unbounded_time_window"] is True
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


def test_twitter_adapter_search_prefers_explicit_since_until(config, monkeypatch):
    adapter = TwitterAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "twitter")
    captured = {}

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(stdout=json.dumps({"ok": True, "data": []}))

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.search("OpenAI since:2025-01-01", limit=5, since="2026-01-01", until="2026-12-31")

    assert payload["ok"] is True
    assert captured["command"] == [
        "twitter",
        "search",
        "OpenAI",
        "--since",
        "2026-01-01",
        "--until",
        "2026-12-31",
        "-n",
        "5",
        "--json",
    ]
    assert payload["meta"]["since"] == "2026-01-01"
    assert payload["meta"]["until"] == "2026-12-31"
    assert payload["meta"]["diagnostics"]["unbounded_time_window"] is False


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
                        "profileImageUrl": "https://pbs.twimg.com/profile_images/openai.png",
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
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://pbs.twimg.com/profile_images/openai.png",
            "relation": "avatar",
            "source_field": "profileImageUrl",
        }
    ]


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
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://pbs.twimg.com/media/a.png",
            "relation": "post_media",
            "source_field": "media[]",
            "media_type": "photo",
        }
    ]


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
    assert "agent-reach[crawl4ai]" in payload["error"]["message"]
    assert "playwright install chromium" in payload["error"]["message"]


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
    assert payload["meta"]["link_count"] == 0
    assert payload["items"][0]["extras"]["extraction_hygiene"]["text_length"] == len("# Example\n\nRead body")


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


def test_hacker_news_repairs_obvious_mojibake(config, monkeypatch):
    repaired_title = "\u65e5\u672c\u8a9e"
    mojibake_title = repaired_title.encode("utf-8").decode("cp1252")

    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "hits": [
                    {
                        "objectID": "123",
                        "title": mojibake_title,
                        "url": "https://example.com/mojibake",
                        "author": "alice",
                        "created_at": "2026-04-10T00:00:00Z",
                    }
                ],
                "hitsPerPage": 1,
                "nbHits": 1,
                "nbPages": 1,
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.hacker_news._import_requests", lambda: FakeRequests)

    payload = HackerNewsAdapter(config=config).search("mojibake", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == repaired_title
    assert payload["items"][0]["extras"]["text_normalization"]["mojibake_repaired"] is True
    assert payload["raw"]["hits"][0]["title"] == mojibake_title


def test_hacker_news_leaves_normal_japanese_text_alone(config, monkeypatch):
    title = "\u65e5\u672c\u8a9e\u306e\u8a18\u4e8b"

    class FakeResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {
                "hits": [
                    {
                        "objectID": "123",
                        "title": title,
                        "url": "https://example.com/japanese",
                        "author": "alice",
                        "created_at": "2026-04-10T00:00:00Z",
                    }
                ],
                "hitsPerPage": 1,
                "nbHits": 1,
                "nbPages": 1,
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.hacker_news._import_requests", lambda: FakeRequests)

    payload = HackerNewsAdapter(config=config).search("japanese", limit=1)

    assert payload["ok"] is True
    assert payload["items"][0]["title"] == title
    assert "text_normalization" not in payload["items"][0]["extras"]


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
                            "iconUrl": "https://tandem.ac/icon.png",
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
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://tandem.ac/icon.png",
            "relation": "icon",
            "source_field": "server.iconUrl",
        }
    ]
    assert payload["raw"]["matched_count"] == 1
    assert payload["raw"]["pages"][0]["matched_count"] == 1
    assert payload["raw"]["pages"][0]["matched_entries"][0]["server"]["name"] == "ac.tandem/docs-mcp"
    assert "unknownPreviewField" not in payload["raw"]["pages"][0]["matched_entries"][0]["server"]
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "registry_entry"
    assert payload["meta"]["pages_fetched"] == 1


def test_mcp_registry_search_dedupes_versions_and_keeps_latest(config, monkeypatch):
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
                            "version": "0.3.0",
                        },
                        "_meta": {
                            "io.modelcontextprotocol.registry/official": {
                                "publishedAt": "2026-04-02T11:22:40Z",
                                "updatedAt": "2026-04-02T11:22:40Z",
                                "isLatest": False,
                            }
                        },
                    },
                    {
                        "server": {
                            "name": "ac.tandem/docs-mcp",
                            "description": "Remote MCP server for docs",
                            "repository": {"url": "https://github.com/frumu-ai/tandem", "source": "github"},
                            "version": "0.3.1",
                        },
                        "_meta": {
                            "io.modelcontextprotocol.registry/official": {
                                "publishedAt": "2026-04-02T11:40:41Z",
                                "updatedAt": "2026-04-02T11:40:41Z",
                                "isLatest": True,
                            }
                        },
                    },
                    {
                        "server": {
                            "name": "agency.lona/trading",
                            "description": "Trading MCP server",
                            "repository": {"url": "https://github.com/mindsightventures/lona", "source": "github"},
                            "version": "2.0.0",
                        },
                        "_meta": {
                            "io.modelcontextprotocol.registry/official": {
                                "publishedAt": "2026-02-24T00:07:27Z",
                                "updatedAt": "2026-02-24T00:07:27Z",
                                "isLatest": True,
                            }
                        },
                    },
                ],
                "metadata": {"count": 3, "nextCursor": None},
            }

    class FakeRequests:
        RequestException = RuntimeError

        @staticmethod
        def get(_url, params=None, headers=None, timeout=None):
            return FakeResponse()

    monkeypatch.setattr("agent_reach.adapters.mcp_registry._import_requests", lambda: FakeRequests)

    payload = MCPRegistryAdapter(config=config).search("mcp", limit=2)

    assert payload["ok"] is True
    assert [item["id"] for item in payload["items"]] == [
        "ac.tandem/docs-mcp",
        "agency.lona/trading",
    ]
    assert payload["items"][0]["extras"]["version"] == "0.3.1"
    assert payload["items"][0]["extras"]["alternate_versions"][0]["version"] == "0.3.0"
    assert payload["meta"]["dedupe_key"] == "server_name"
    assert payload["meta"]["duplicates_removed"] == 1


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


def test_reddit_search_success_with_rdt_cli(config, monkeypatch):
    listing = {
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
                        "url": "https://i.redd.it/example-image.png",
                        "thumbnail": "https://preview.redd.it/example-thumb.png?width=140&format=png&auto=webp&s=1",
                        "thumbnail_width": 140,
                        "thumbnail_height": 140,
                        "preview": {
                            "images": [
                                {
                                    "source": {
                                        "url": "https://preview.redd.it/example-preview.png?width=1024&format=png&auto=webp&s=1",
                                        "width": 1024,
                                        "height": 768,
                                    },
                                    "resolutions": [
                                        {
                                            "url": "https://preview.redd.it/example-preview.png?width=108&format=png&auto=webp&s=1"
                                        }
                                    ],
                                }
                            ]
                        },
                    },
                }
            ],
        },
    }
    captured = {}
    adapter = RedditAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "rdt")

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(stdout=json.dumps({"ok": True, "data": listing}) + '\n  More: rdt search "agent" --after t3_next')

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.search("r/LocalLLaMA agent frameworks", limit=1)

    assert payload["ok"] is True
    assert captured["command"] == [
        "rdt",
        "search",
        "agent frameworks",
        "-n",
        "1",
        "--json",
        "-r",
        "LocalLLaMA",
    ]
    assert payload["items"][0]["kind"] == "reddit_post"
    assert payload["items"][0]["extras"]["subreddit"] == "LocalLLaMA"
    assert payload["items"][0]["extras"]["media_references"] == [
        {
            "type": "image",
            "url": "https://preview.redd.it/example-preview.png?width=1024&format=png&auto=webp&s=1",
            "relation": "preview",
            "thumb_url": "https://preview.redd.it/example-preview.png?width=108&format=png&auto=webp&s=1",
            "width": 1024,
            "height": 768,
            "source_field": "preview.images[].source",
        },
        {
            "type": "image",
            "url": "https://preview.redd.it/example-thumb.png?width=140&format=png&auto=webp&s=1",
            "relation": "thumbnail",
            "width": 140,
            "height": 140,
            "source_field": "thumbnail",
        },
        {
            "type": "image",
            "url": "https://i.redd.it/example-image.png",
            "relation": "external_url",
            "source_field": "url",
        },
    ]
    assert payload["items"][0]["extras"]["source_hints"]["source_kind"] == "forum_post"
    assert payload["meta"]["backend"] == "rdt_cli"
    assert payload["meta"]["next_cursor"] == "t3_next"


def test_reddit_read_success_with_rdt_cli(config, monkeypatch):
    raw_thread = [
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
    captured = {}
    adapter = RedditAdapter(config=config)
    monkeypatch.setattr(adapter, "command_path", lambda _name: "rdt")

    def fake_run(command, timeout=120, env=None):
        captured["command"] = command
        return _cp(stdout=json.dumps({"ok": True, "data": raw_thread}))

    monkeypatch.setattr(adapter, "run_command", fake_run)

    payload = adapter.read("https://www.reddit.com/r/redditdev/comments/abc/thread/", limit=2)

    assert payload["ok"] is True
    assert captured["command"] == ["rdt", "read", "abc", "-n", "2", "--json"]
    assert [item["kind"] for item in payload["items"]] == ["reddit_post", "reddit_comment"]
    assert payload["meta"]["backend"] == "rdt_cli"
    assert payload["meta"]["comment_count"] == 1


def test_reddit_reports_missing_rdt_cli(config):
    adapter = RedditAdapter(config=config)
    adapter.command_path = lambda _name: None

    payload = adapter.search("agent frameworks", limit=1)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "missing_dependency"
    assert "rdt-cli" in payload["error"]["message"]


def test_base_adapter_runtime_env_is_noninteractive_and_utf8(config, monkeypatch):
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    config.set("qiita_token", "qiita-token")
    config.set("searxng_base_url", "https://search.example.com")

    env = BaseAdapter(config=config).runtime_env()

    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"
    assert env["QIITA_TOKEN"] == "qiita-token"
    assert env["SEARXNG_BASE_URL"] == "https://search.example.com"
