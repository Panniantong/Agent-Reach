# -*- coding: utf-8 -*-
"""Tests for agent_reach.transcript_backends — opt-in hosted YouTube transcripts."""

import json
from unittest.mock import patch

import pytest
import requests

from agent_reach import transcript_backends as tb
from agent_reach.cli import main
from agent_reach.config import Config

_ENV_KEYS = (
    "APIFY_TOKEN",
    "YOUTUBE_TRANSCRIPT_BACKEND",
    "APIFY_TRANSCRIPT_ACTOR",
    "APIFY_TRANSCRIPT_INPUT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def cfg(tmp_path):
    return Config(config_path=tmp_path / "config.yaml")


class FakeResponse:
    def __init__(self, status_code=201, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _apify(cfg):
    cfg.set("youtube_transcript_backend", "apify")
    cfg.set("apify_token", "apify_api_test")


# --- off by default ------------------------------------------------------ #


class TestOptIn:
    def test_nothing_selected_raises_without_network(self, cfg):
        with patch("requests.post") as post:
            with pytest.raises(tb.NoBackendConfigured):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)
        post.assert_not_called()

    def test_token_alone_does_not_enable_backend(self, cfg):
        cfg.set("apify_token", "apify_api_test")
        assert tb.configured_backend(cfg) is None

    def test_backend_without_token_is_not_configured(self, cfg):
        cfg.set("youtube_transcript_backend", "apify")
        assert tb.configured_backend(cfg) is None
        with pytest.raises(tb.NoBackendConfigured, match="apify_token"):
            tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_env_vars_enable_backend(self, cfg, monkeypatch):
        monkeypatch.setenv("YOUTUBE_TRANSCRIPT_BACKEND", "apify")
        monkeypatch.setenv("APIFY_TOKEN", "apify_api_env")
        assert tb.configured_backend(cfg) == "apify"

    def test_unknown_backend_is_rejected(self, cfg):
        cfg.set("youtube_transcript_backend", "nope")
        assert tb.configured_backend(cfg) is None
        with pytest.raises(tb.TranscriptBackendError, match="unknown transcript backend"):
            tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_configured_backend_ignores_non_string_values(self):
        class Duck:
            def get(self, key):
                return object()

            def is_configured(self, feature):
                return True

        assert tb.configured_backend(Duck()) is None
        assert tb.configured_backend(None) is None


# --- input validation ---------------------------------------------------- #


class TestVideoTarget:
    def test_accepts_video_id(self):
        assert tb._video_target("dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        ],
    )
    def test_accepts_youtube_urls(self, url):
        assert tb._video_target(url) == url

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/watch?v=x", "https://youtube.com.evil.test/x", "file:///etc/passwd", ""],
    )
    def test_refuses_other_urls(self, url):
        with pytest.raises(tb.TranscriptBackendError, match="not a YouTube"):
            tb._video_target(url)


# --- Apify backend ------------------------------------------------------- #


class TestApifyBackend:
    def test_calls_run_sync_endpoint_with_default_actor(self, cfg):
        _apify(cfg)
        captured = {}

        def fake_post(url, params=None, headers=None, json=None, timeout=None):
            captured.update(url=url, params=params, headers=headers, json=json, timeout=timeout)
            return FakeResponse(payload=[{"status": "ok", "text": "never gonna give you up"}])

        with patch("requests.post", side_effect=fake_post):
            item = tb.fetch_transcript("dQw4w9WgXcQ", lang="en, es", config=cfg)

        assert captured["url"] == (
            "https://api.apify.com/v2/acts/"
            "apimint~youtube-transcript-scraper/run-sync-get-dataset-items"
        )
        assert captured["headers"] == {"Authorization": "Bearer apify_api_test"}
        assert captured["json"] == {
            "urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            "languages": ["en", "es"],
        }
        assert captured["params"]["timeout"] == tb.ApifyBackend.RUN_TIMEOUT_SECONDS
        assert captured["timeout"] > captured["params"]["timeout"]
        assert item["text"] == "never gonna give you up"
        assert item["backend"] == "apify"
        assert item["actor"] == "apimint~youtube-transcript-scraper"

    def test_omits_languages_when_not_requested(self, cfg):
        _apify(cfg)
        with patch("requests.post", return_value=FakeResponse(payload=[{"text": "x"}])) as post:
            tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)
        assert post.call_args.kwargs["json"] == {
            "urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        }

    def test_actor_id_is_configurable(self, cfg, monkeypatch):
        _apify(cfg)
        monkeypatch.setenv("APIFY_TRANSCRIPT_ACTOR", "someone/other-transcripts")
        with patch("requests.post", return_value=FakeResponse(payload=[{"text": "x"}])) as post:
            tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)
        assert "/acts/someone~other-transcripts/" in post.call_args.args[0]

    def test_input_template_fills_url(self, cfg, monkeypatch):
        _apify(cfg)
        monkeypatch.setenv(
            "APIFY_TRANSCRIPT_INPUT",
            '{"startUrls": [{"url": "{url}"}], "outputFormat": "text"}',
        )
        with patch("requests.post", return_value=FakeResponse(payload=[{"text": "x"}])) as post:
            tb.fetch_transcript("dQw4w9WgXcQ", lang="en", config=cfg)
        assert post.call_args.kwargs["json"] == {
            "startUrls": [{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}],
            "outputFormat": "text",
        }

    def test_invalid_input_template_is_reported(self, cfg, monkeypatch):
        _apify(cfg)
        monkeypatch.setenv("APIFY_TRANSCRIPT_INPUT", "{not json")
        with patch("requests.post") as post:
            with pytest.raises(tb.TranscriptBackendError, match="not valid JSON"):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)
        post.assert_not_called()

    def test_joins_segments_when_actor_has_no_text_field(self, cfg):
        _apify(cfg)
        payload = [{"transcript": [{"start": 0, "text": "hello"}, {"start": 1.2, "text": "world"}]}]
        with patch("requests.post", return_value=FakeResponse(payload=payload)):
            item = tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)
        assert item["text"] == "hello\nworld"

    def test_status_row_without_transcript_raises_with_reason(self, cfg):
        _apify(cfg)
        payload = [{"status": "no-captions", "errorMessage": "This video has no captions."}]
        with patch("requests.post", return_value=FakeResponse(payload=payload)):
            with pytest.raises(tb.TranscriptBackendError, match="no captions"):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_empty_dataset_raises(self, cfg):
        _apify(cfg)
        with patch("requests.post", return_value=FakeResponse(payload=[])):
            with pytest.raises(tb.TranscriptBackendError, match="no items"):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_http_error_is_reported(self, cfg):
        _apify(cfg)
        resp = FakeResponse(status_code=401, text='{"error":{"type":"user-or-token-not-found"}}')
        with patch("requests.post", return_value=resp):
            with pytest.raises(tb.TranscriptBackendError, match="HTTP 401"):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_network_error_is_wrapped(self, cfg):
        _apify(cfg)
        with patch("requests.post", side_effect=requests.ConnectionError("down")):
            with pytest.raises(tb.TranscriptBackendError, match="network error"):
                tb.fetch_transcript("dQw4w9WgXcQ", config=cfg)

    def test_explicit_backend_overrides_config(self, cfg):
        cfg.set("apify_token", "apify_api_test")
        with patch("requests.post", return_value=FakeResponse(payload=[{"text": "x"}])):
            item = tb.fetch_transcript("dQw4w9WgXcQ", backend="apify", config=cfg)
        assert item["backend"] == "apify"


# --- CLI ----------------------------------------------------------------- #


class TestCLI:
    def test_prints_text(self, capsys):
        with patch(
            "agent_reach.transcript_backends.fetch_transcript",
            return_value={"text": "hello transcript", "backend": "apify"},
        ) as fetch:
            with patch("sys.argv", ["agent-reach", "youtube-transcript", "dQw4w9WgXcQ", "--lang", "en"]):
                main()
        fetch.assert_called_once_with("dQw4w9WgXcQ", lang="en", backend=None)
        assert capsys.readouterr().out.strip() == "hello transcript"

    def test_json_output(self, capsys):
        item = {"text": "hi", "segments": [{"start": 0, "end": 1, "text": "hi"}]}
        with patch("agent_reach.transcript_backends.fetch_transcript", return_value=item):
            with patch("sys.argv", ["agent-reach", "youtube-transcript", "dQw4w9WgXcQ", "--json"]):
                main()
        assert json.loads(capsys.readouterr().out) == item

    def test_writes_output_file(self, capsys, tmp_path):
        out_file = tmp_path / "t.txt"
        with patch(
            "agent_reach.transcript_backends.fetch_transcript",
            return_value={"text": "saved"},
        ):
            with patch(
                "sys.argv",
                ["agent-reach", "youtube-transcript", "dQw4w9WgXcQ", "-o", str(out_file)],
            ):
                main()
        assert out_file.read_text(encoding="utf-8").strip() == "saved"

    def test_not_configured_exits_nonzero(self, capsys):
        with patch("sys.argv", ["agent-reach", "youtube-transcript", "dQw4w9WgXcQ"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
        assert "no hosted transcript backend selected" in capsys.readouterr().out

    def test_configure_backend_validates_name(self, capsys):
        with patch("sys.argv", ["agent-reach", "configure", "youtube-transcript-backend", "nope"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
        assert Config().get("youtube_transcript_backend") is None

    def test_configure_backend_and_token(self, capsys):
        with patch("sys.argv", ["agent-reach", "configure", "youtube-transcript-backend", "Apify"]):
            main()
        with patch("sys.argv", ["agent-reach", "configure", "apify-token", "--stdin"]):
            with patch("sys.stdin.read", return_value="apify_api_test\n"):
                main()
        config = Config()
        assert config.get("youtube_transcript_backend") == "apify"
        assert config.get("apify_token") == "apify_api_test"
        assert config.to_dict()["apify_token"] == "[REDACTED]"
        assert tb.configured_backend(config) == "apify"
