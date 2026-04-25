# -*- coding: utf-8 -*-
"""Tests for agent_reach.transcribe — provider routing, fallback, and errors."""

from typing import List

import pytest

from agent_reach import transcribe as tr
from agent_reach.config import Config

# --- Fixtures ----------------------------------------------------------- #


@pytest.fixture
def fake_config(tmp_path, monkeypatch):
    """A Config that writes to a temp dir and never touches the user's HOME."""
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(Config, "CONFIG_FILE", cfg_path)
    cfg = Config(config_path=cfg_path)
    return cfg


@pytest.fixture
def chunk_file(tmp_path):
    p = tmp_path / "chunk.m4a"
    p.write_bytes(b"\x00fake-m4a-bytes")
    return p


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


# --- transcribe_chunk: provider routing -------------------------------- #


class TestTranscribeChunk:
    def test_routes_to_groq_endpoint(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")
        captured = {}

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["model"] = data["model"]
            return FakeResponse(200, "hello world")

        monkeypatch.setattr(tr.requests, "post", fake_post)
        text = tr.transcribe_chunk(chunk_file, "groq", config=fake_config)
        assert text == "hello world"
        assert captured["url"] == tr.PROVIDERS["groq"]["endpoint"]
        assert captured["model"] == "whisper-large-v3"
        assert captured["headers"]["Authorization"] == "Bearer gsk_test"

    def test_routes_to_openai_endpoint(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("openai_api_key", "sk-test")
        captured = {}

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            captured["url"] = url
            captured["model"] = data["model"]
            return FakeResponse(200, "openai output")

        monkeypatch.setattr(tr.requests, "post", fake_post)
        text = tr.transcribe_chunk(chunk_file, "openai", config=fake_config)
        assert text == "openai output"
        assert captured["url"] == tr.PROVIDERS["openai"]["endpoint"]
        assert captured["model"] == "whisper-1"

    def test_raises_when_key_missing(self, fake_config, chunk_file):
        with pytest.raises(tr.NoProviderConfigured):
            tr.transcribe_chunk(chunk_file, "groq", config=fake_config)

    def test_raises_on_http_error(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(429, "rate limited"),
        )
        with pytest.raises(tr.TranscribeError, match="HTTP 429"):
            tr.transcribe_chunk(chunk_file, "groq", config=fake_config)

    def test_unknown_provider(self, fake_config, chunk_file):
        with pytest.raises(tr.TranscribeError, match="unknown provider"):
            tr.transcribe_chunk(chunk_file, "azure", config=fake_config)


# --- _transcribe_with_fallback ----------------------------------------- #


class TestFallback:
    def test_groq_succeeds_no_openai_call(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")
        fake_config.set("openai_api_key", "sk-test")
        calls: List[str] = []

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            calls.append(url)
            return FakeResponse(200, "from-groq")

        monkeypatch.setattr(tr.requests, "post", fake_post)
        text = tr._transcribe_with_fallback(chunk_file, ["groq", "openai"], fake_config)
        assert text == "from-groq"
        assert calls == [tr.PROVIDERS["groq"]["endpoint"]]

    def test_groq_429_falls_back_to_openai(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")
        fake_config.set("openai_api_key", "sk-test")
        calls: List[str] = []

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            calls.append(url)
            if url == tr.PROVIDERS["groq"]["endpoint"]:
                return FakeResponse(429, "rate limited")
            return FakeResponse(200, "from-openai")

        monkeypatch.setattr(tr.requests, "post", fake_post)
        text = tr._transcribe_with_fallback(chunk_file, ["groq", "openai"], fake_config)
        assert text == "from-openai"
        assert calls == [
            tr.PROVIDERS["groq"]["endpoint"],
            tr.PROVIDERS["openai"]["endpoint"],
        ]

    def test_skip_unconfigured_provider(self, monkeypatch, fake_config, chunk_file):
        # Only openai key configured — fallback should skip groq silently.
        fake_config.set("openai_api_key", "sk-test")
        calls: List[str] = []

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            calls.append(url)
            return FakeResponse(200, "via-openai")

        monkeypatch.setattr(tr.requests, "post", fake_post)
        text = tr._transcribe_with_fallback(chunk_file, ["groq", "openai"], fake_config)
        assert text == "via-openai"
        assert calls == [tr.PROVIDERS["openai"]["endpoint"]]

    def test_all_fail_raises_with_last_error(self, monkeypatch, fake_config, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")
        fake_config.set("openai_api_key", "sk-test")
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(500, "boom"),
        )
        with pytest.raises(tr.TranscribeError, match="all providers failed"):
            tr._transcribe_with_fallback(chunk_file, ["groq", "openai"], fake_config)


# --- transcribe (orchestrator) ---------------------------------------- #


class TestOrchestrator:
    def test_local_file_skips_yt_dlp(self, monkeypatch, fake_config, tmp_path, chunk_file):
        fake_config.set("groq_api_key", "gsk_test")

        def boom_download(*a, **k):
            raise AssertionError("yt-dlp must not be called for local files")

        # Stub heavy external steps to no-ops that keep file paths valid.
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"x" * 1024)

        def fake_compress(src, out_dir):
            return compressed

        monkeypatch.setattr(tr, "download_audio", boom_download)
        monkeypatch.setattr(tr, "compress_audio", fake_compress)
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(200, "transcript text"),
        )

        text = tr.transcribe(
            str(chunk_file),
            out_dir=tmp_path / "work",
            config=fake_config,
        )
        assert text == "transcript text"

    def test_chunks_concatenated_with_newlines(
        self, monkeypatch, fake_config, tmp_path, chunk_file
    ):
        fake_config.set("groq_api_key", "gsk_test")
        # Force the "needs chunking" path by writing a file above the size limit.
        big = tmp_path / "compressed.m4a"
        big.write_bytes(b"x" * (tr.SIZE_LIMIT_BYTES + 1))
        monkeypatch.setattr(tr, "compress_audio", lambda src, out_dir: big)
        c1 = tmp_path / "chunk_001.m4a"
        c2 = tmp_path / "chunk_002.m4a"
        c1.write_bytes(b"a")
        c2.write_bytes(b"b")
        monkeypatch.setattr(tr, "chunk_audio", lambda src, out_dir: [c1, c2])

        responses = iter(["part one ", "part two "])
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(200, next(responses)),
        )

        text = tr.transcribe(
            str(chunk_file),
            out_dir=tmp_path / "work",
            config=fake_config,
        )
        assert text == "part one\npart two"

    def test_no_provider_configured_fails_fast(self, fake_config, chunk_file):
        with pytest.raises(tr.NoProviderConfigured):
            tr.transcribe(str(chunk_file), config=fake_config)

    def test_invalid_provider_string(self, fake_config, chunk_file):
        with pytest.raises(tr.TranscribeError, match="unknown provider"):
            tr.transcribe(str(chunk_file), provider="azure", config=fake_config)


# --- YouTubeChannel integration --------------------------------------- #


class TestYouTubeChannelTranscribe:
    def test_delegates_to_transcribe(self, monkeypatch, fake_config):
        from agent_reach.channels.youtube import YouTubeChannel

        captured = {}

        def fake_transcribe(source, *, provider="auto", out_dir=None, config=None):
            captured["source"] = source
            captured["provider"] = provider
            captured["config"] = config
            return "delegated text"

        monkeypatch.setattr(tr, "transcribe", fake_transcribe)
        out = YouTubeChannel().transcribe(
            "https://youtu.be/abc", provider="groq", config=fake_config
        )
        assert out == "delegated text"
        assert captured["source"] == "https://youtu.be/abc"
        assert captured["provider"] == "groq"
        assert captured["config"] is fake_config

    def test_transcription_providers_in_order(self, fake_config):
        from agent_reach.channels.youtube import YouTubeChannel

        assert YouTubeChannel.transcription_providers(fake_config) == []
        fake_config.set("openai_api_key", "sk-test")
        assert YouTubeChannel.transcription_providers(fake_config) == ["openai"]
        fake_config.set("groq_api_key", "gsk_test")
        assert YouTubeChannel.transcription_providers(fake_config) == [
            "groq",
            "openai",
        ]


# --- Config feature requirement --------------------------------------- #


class TestConfigOpenAIWhisper:
    def test_openai_whisper_feature_registered(self, fake_config):
        assert "openai_whisper" in Config.FEATURE_REQUIREMENTS
        assert Config.FEATURE_REQUIREMENTS["openai_whisper"] == ["openai_api_key"]
        assert not fake_config.is_configured("openai_whisper")
        fake_config.set("openai_api_key", "sk-test")
        assert fake_config.is_configured("openai_whisper")
