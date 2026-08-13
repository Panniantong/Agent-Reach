# -*- coding: utf-8 -*-
"""Tests for agent_reach.transcribe — provider routing, fallback, and errors."""

import subprocess
from pathlib import Path
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


@pytest.fixture
def bounded_audio_duration(monkeypatch):
    """Treat synthetic fixture bytes as a short valid audio stream."""
    monkeypatch.setattr(tr, "_probe_audio_duration", lambda _path: 60.0)


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
    def test_provider_fallback_consent_requires_auto(self, fake_config, chunk_file):
        with pytest.raises(tr.TranscribeError, match="requires provider='auto'"):
            tr.transcribe(
                str(chunk_file),
                provider="groq",
                config=fake_config,
                allow_provider_fallback=True,
            )

    def test_auto_does_not_send_audio_to_second_provider_without_consent(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        fake_config.set("openai_api_key", "sk-test")
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"compressed")
        monkeypatch.setattr(tr, "compress_audio", lambda *_args: compressed)
        calls: List[str] = []

        def fake_post(url, **_kwargs):
            calls.append(url)
            if url == tr.PROVIDERS["groq"]["endpoint"]:
                return FakeResponse(429, "rate limited")
            return FakeResponse(200, "from-openai")

        monkeypatch.setattr(tr.requests, "post", fake_post)

        with pytest.raises(tr.TranscribeError, match="groq.*HTTP 429"):
            tr.transcribe(
                str(chunk_file),
                out_dir=tmp_path / "work",
                config=fake_config,
            )

        assert calls == [tr.PROVIDERS["groq"]["endpoint"]]

    def test_auto_falls_back_only_with_explicit_consent(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        fake_config.set("openai_api_key", "sk-test")
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"compressed")
        monkeypatch.setattr(tr, "compress_audio", lambda *_args: compressed)
        calls: List[str] = []

        def fake_post(url, **_kwargs):
            calls.append(url)
            if url == tr.PROVIDERS["groq"]["endpoint"]:
                return FakeResponse(429, "rate limited")
            return FakeResponse(200, "from-openai")

        monkeypatch.setattr(tr.requests, "post", fake_post)

        text = tr.transcribe(
            str(chunk_file),
            out_dir=tmp_path / "work",
            config=fake_config,
            allow_provider_fallback=True,
        )

        assert text == "from-openai"
        assert calls == [
            tr.PROVIDERS["groq"]["endpoint"],
            tr.PROVIDERS["openai"]["endpoint"],
        ]

    def test_auto_uses_openai_when_it_is_the_only_configured_provider(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
        fake_config.set("openai_api_key", "sk-test")
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"compressed")
        monkeypatch.setattr(tr, "compress_audio", lambda *_args: compressed)
        calls: List[str] = []

        def fake_post(url, **_kwargs):
            calls.append(url)
            return FakeResponse(200, "from-openai")

        monkeypatch.setattr(tr.requests, "post", fake_post)

        text = tr.transcribe(
            str(chunk_file),
            out_dir=tmp_path / "work",
            config=fake_config,
        )

        assert text == "from-openai"
        assert calls == [tr.PROVIDERS["openai"]["endpoint"]]

    def test_rejects_overlong_audio_before_compression(
        self, monkeypatch, fake_config, chunk_file
    ):
        fake_config.set("groq_api_key", "gsk_test")
        events = []

        def fake_run(cmd, **_kwargs):
            events.append(cmd[0])
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=str(tr.MAX_AUDIO_SECONDS + 1),
                stderr="",
            )

        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr.subprocess, "run", fake_run)
        monkeypatch.setattr(
            tr,
            "compress_audio",
            lambda *_args: (_ for _ in ()).throw(
                AssertionError("overlong audio must fail before compression")
            ),
        )

        with pytest.raises(tr.TranscribeError, match="duration.*limit"):
            tr.transcribe(str(chunk_file), config=fake_config)

        assert events == ["ffprobe"]

    def test_duration_probe_timeout_fails_before_compression(
        self, monkeypatch, fake_config, chunk_file
    ):
        fake_config.set("groq_api_key", "gsk_test")
        observed = {}

        def timeout_probe(cmd, **_kwargs):
            observed["timeout"] = _kwargs.get("timeout")
            raise subprocess.TimeoutExpired(
                cmd,
                timeout=tr.FFPROBE_TIMEOUT_SECONDS,
            )

        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr.subprocess, "run", timeout_probe)
        monkeypatch.setattr(
            tr,
            "compress_audio",
            lambda *_args: (_ for _ in ()).throw(
                AssertionError("timed-out probe must fail before compression")
            ),
        )

        with pytest.raises(
            tr.TranscribeError,
            match=r"ffprobe timed out.*30s",
        ):
            tr.transcribe(str(chunk_file), config=fake_config)

        assert observed["timeout"] == tr.FFPROBE_TIMEOUT_SECONDS

    def test_unparseable_duration_fails_before_compression(
        self, monkeypatch, fake_config, chunk_file
    ):
        fake_config.set("groq_api_key", "gsk_test")
        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(
            tr.subprocess,
            "run",
            lambda cmd, **_kwargs: subprocess.CompletedProcess(
                cmd,
                0,
                stdout="N/A\n",
                stderr="",
            ),
        )
        monkeypatch.setattr(
            tr,
            "compress_audio",
            lambda *_args: (_ for _ in ()).throw(
                AssertionError("invalid duration must fail before compression")
            ),
        )

        with pytest.raises(
            tr.TranscribeError,
            match=r"ffprobe could not parse.*duration",
        ):
            tr.transcribe(str(chunk_file), config=fake_config)

    def test_rejects_oversized_source_before_compression(
        self, monkeypatch, fake_config, chunk_file
    ):
        fake_config.set("groq_api_key", "gsk_test")
        monkeypatch.setattr(tr, "MAX_SOURCE_BYTES", 4)
        monkeypatch.setattr(
            tr,
            "compress_audio",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("oversized source must fail before ffmpeg")
            ),
        )

        with pytest.raises(tr.TranscribeError, match="source.*limit"):
            tr.transcribe(str(chunk_file), config=fake_config)

    def test_local_file_skips_yt_dlp(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
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
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
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

    def test_rejects_too_many_chunks_before_any_provider_call(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        monkeypatch.setattr(tr, "SIZE_LIMIT_BYTES", 1)
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"xx")
        monkeypatch.setattr(tr, "compress_audio", lambda *_args: compressed)

        chunks = []
        for index in range(tr.MAX_CHUNKS + 1):
            chunk = tmp_path / f"chunk_{index:03d}.m4a"
            chunk.write_bytes(b"x")
            chunks.append(chunk)
        monkeypatch.setattr(tr, "chunk_audio", lambda *_args: chunks)

        provider_calls = []
        monkeypatch.setattr(
            tr,
            "_transcribe_with_fallback",
            lambda *_args: provider_calls.append("called") or "text",
        )

        with pytest.raises(tr.TranscribeError, match="chunks.*limit"):
            tr.transcribe(str(chunk_file), out_dir=tmp_path / "work", config=fake_config)

        assert provider_calls == []

    def test_rejects_excessive_total_chunk_bytes_before_provider_calls(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        chunk_file,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        monkeypatch.setattr(tr, "SIZE_LIMIT_BYTES", 10)
        monkeypatch.setattr(tr, "MAX_TOTAL_CHUNK_BYTES", 5)
        compressed = tmp_path / "compressed.m4a"
        compressed.write_bytes(b"x" * 11)
        monkeypatch.setattr(tr, "compress_audio", lambda *_args: compressed)

        first = tmp_path / "chunk_000.m4a"
        second = tmp_path / "chunk_001.m4a"
        first.write_bytes(b"aaa")
        second.write_bytes(b"bbb")
        monkeypatch.setattr(tr, "chunk_audio", lambda *_args: [first, second])

        provider_calls = []
        monkeypatch.setattr(
            tr,
            "_transcribe_with_fallback",
            lambda *_args: provider_calls.append("called") or "text",
        )

        with pytest.raises(tr.TranscribeError, match="total.*limit"):
            tr.transcribe(str(chunk_file), out_dir=tmp_path / "work", config=fake_config)

        assert provider_calls == []

    def test_no_provider_configured_fails_fast(self, fake_config, chunk_file):
        with pytest.raises(tr.NoProviderConfigured):
            tr.transcribe(str(chunk_file), config=fake_config)

    def test_invalid_provider_string(self, fake_config, chunk_file):
        with pytest.raises(tr.TranscribeError, match="unknown provider"):
            tr.transcribe(str(chunk_file), provider="azure", config=fake_config)

    def test_auto_temp_dir_is_cleaned_up(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        created_work_dirs = []

        class FakeTemporaryDirectory:
            def __init__(self, prefix=None):
                self.path = tmp_path / "auto-work"

            def __enter__(self):
                self.path.mkdir()
                created_work_dirs.append(self.path)
                return str(self.path)

            def __exit__(self, *_):
                for child in self.path.iterdir():
                    child.unlink()
                self.path.rmdir()

        def fake_download(source, out_dir):
            assert Path(out_dir) == tmp_path / "auto-work"
            audio = Path(out_dir) / "source.m4a"
            audio.write_bytes(b"audio")
            return audio

        def fake_compress(src, out_dir):
            compressed = Path(out_dir) / "compressed.m4a"
            compressed.write_bytes(b"x" * 1024)
            return compressed

        monkeypatch.setattr(tr.tempfile, "TemporaryDirectory", FakeTemporaryDirectory)
        monkeypatch.setattr(tr, "download_audio", fake_download)
        monkeypatch.setattr(tr, "compress_audio", fake_compress)
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(200, "transcript text"),
        )

        text = tr.transcribe("https://example.com/video", config=fake_config)

        assert text == "transcript text"
        assert created_work_dirs
        assert not created_work_dirs[0].exists()

    def test_explicit_out_dir_is_preserved(
        self,
        monkeypatch,
        fake_config,
        tmp_path,
        bounded_audio_duration,
    ):
        fake_config.set("groq_api_key", "gsk_test")
        work = tmp_path / "caller-owned"

        def fake_download(source, out_dir):
            audio = Path(out_dir) / "source.m4a"
            audio.write_bytes(b"audio")
            return audio

        def fake_compress(src, out_dir):
            compressed = Path(out_dir) / "compressed.m4a"
            compressed.write_bytes(b"x" * 1024)
            return compressed

        monkeypatch.setattr(tr, "download_audio", fake_download)
        monkeypatch.setattr(tr, "compress_audio", fake_compress)
        monkeypatch.setattr(
            tr.requests,
            "post",
            lambda *a, **k: FakeResponse(200, "transcript text"),
        )

        tr.transcribe("https://example.com/video", out_dir=work, config=fake_config)

        assert work.exists()
        assert (work / "compressed.m4a").exists()


class TestDownloadAudioSafety:
    def test_rejects_download_that_exceeds_limit(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr, "MAX_SOURCE_BYTES", 4)

        def fake_run(_cmd, timeout=600):
            (tmp_path / "source.m4a").write_bytes(b"audio")

        monkeypatch.setattr(tr, "_run", fake_run)

        with pytest.raises(tr.TranscribeError, match="downloaded source.*limit"):
            tr.download_audio("https://example.com/watch?v=123", tmp_path)

    def test_rejects_private_network_url_before_yt_dlp(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tr, "_require", lambda binary: None)

        def should_not_run(*args, **kwargs):
            raise AssertionError("yt-dlp must not run for private/internal URLs")

        monkeypatch.setattr(tr, "_run", should_not_run)

        with pytest.raises(tr.TranscribeError, match="private|internal|SSRF"):
            tr.download_audio("http://169.254.169.254/latest/meta-data/", tmp_path)

    def test_passes_public_url_after_end_of_options_marker(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tr, "_require", lambda binary: None)
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "source.m4a").write_bytes(b"audio")

        monkeypatch.setattr(tr, "_run", fake_run)

        audio = tr.download_audio("https://example.com/watch?v=123", tmp_path)

        assert audio == tmp_path / "source.m4a"
        assert "--" in captured["cmd"]
        assert "--no-playlist" in captured["cmd"]
        marker_index = captured["cmd"].index("--")
        assert captured["cmd"][marker_index + 1] == "https://example.com/watch?v=123"
        max_size_index = captured["cmd"].index("--max-filesize")
        assert captured["cmd"][max_size_index + 1] == str(tr.MAX_SOURCE_BYTES)

    def test_preserves_bare_public_urls_supported_by_yt_dlp(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tr, "_require", lambda binary: None)
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "source.m4a").write_bytes(b"audio")

        monkeypatch.setattr(tr, "_run", fake_run)

        tr.download_audio("youtu.be/abc123", tmp_path)

        assert captured["cmd"][-1] == "youtu.be/abc123"

    def test_does_not_dns_resolve_public_hostnames(self, monkeypatch, tmp_path):
        import socket

        monkeypatch.setattr(tr, "_require", lambda binary: None)
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("public hostnames should not be DNS-resolved here")
            ),
        )
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "source.m4a").write_bytes(b"audio")

        monkeypatch.setattr(tr, "_run", fake_run)

        tr.download_audio("https://youtu.be/abc123", tmp_path)

        assert captured["cmd"][-1] == "https://youtu.be/abc123"

    # The C resolver behind yt-dlp accepts the full inet_aton grammar, so a
    # canonical dotted-quad check alone lets loopback and the cloud metadata
    # endpoint through under a different spelling.
    @pytest.mark.parametrize(
        ("url", "reaches"),
        [
            ("http://127.1/a.mp3", "127.0.0.1"),
            ("http://127.0.1/a.mp3", "127.0.0.1"),
            ("http://2130706433/a.mp3", "127.0.0.1"),
            ("http://0x7f000001/a.mp3", "127.0.0.1"),
            ("http://0177.0.0.1/a.mp3", "127.0.0.1"),
            ("http://017700000001/a.mp3", "127.0.0.1"),
            ("http://0/a.mp3", "0.0.0.0"),
            ("http://192.168.1/a.mp3", "192.168.0.1"),
            ("http://2852039166/a.mp3", "169.254.169.254"),
            ("http://0xA9FEA9FE/a.mp3", "169.254.169.254"),
            ("http://１２７.０.０.１/a.mp3", "127.0.0.1"),
            ("http://２１３０７０６４３３/a.mp3", "127.0.0.1"),
            ("http://０x７f０００００１/a.mp3", "127.0.0.1"),
            ("http://ⓛⓞⓒⓐⓛⓗⓞⓢⓣ/a.mp3", "localhost"),
            ("http://ℓocalhost/a.mp3", "localhost"),
            ("http://%31%32%37.0.0.1/a.mp3", "127.0.0.1"),
            ("http://127%2e0%2e0%2e1/a.mp3", "127.0.0.1"),
            ("http://local%68ost/a.mp3", "localhost"),
            ("http://127.0.0.1\\@example.com/a.mp3", "127.0.0.1"),
        ],
    )
    def test_rejects_shorthand_ipv4_spellings_of_internal_hosts(
        self, monkeypatch, tmp_path, url, reaches
    ):
        monkeypatch.setattr(tr, "_require", lambda binary: None)

        def should_not_run(*args, **kwargs):
            raise AssertionError(f"yt-dlp must not run for a URL reaching {reaches}")

        monkeypatch.setattr(tr, "_run", should_not_run)

        with pytest.raises(tr.TranscribeError, match="private|internal|SSRF"):
            tr.download_audio(url, tmp_path)

    def test_shorthand_ipv4_check_stays_dns_free(self, monkeypatch, tmp_path):
        import socket as socket_module

        monkeypatch.setattr(tr, "_require", lambda binary: None)
        monkeypatch.setattr(
            socket_module,
            "getaddrinfo",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("literal IP parsing must not resolve names")
            ),
        )

        def should_not_run(*args, **kwargs):
            raise AssertionError("yt-dlp must not run for private/internal URLs")

        monkeypatch.setattr(tr, "_run", should_not_run)

        with pytest.raises(tr.TranscribeError, match="private|internal|SSRF"):
            tr.download_audio("http://２１３０７０６４３３/a.mp3", tmp_path)

    @pytest.mark.parametrize(
        "url",
        [
            "https://1.1.1.1/a.mp3",
            "https://8.8.8.8/a.mp3",
            # Octal dotted-quad that denotes a public address, not loopback.
            "http://010.010.010.010/a.mp3",
        ],
    )
    def test_allows_public_literal_addresses(self, monkeypatch, tmp_path, url):
        monkeypatch.setattr(tr, "_require", lambda binary: None)
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "source.m4a").write_bytes(b"audio")

        monkeypatch.setattr(tr, "_run", fake_run)

        tr.download_audio(url, tmp_path)

        assert captured["cmd"][-1] == url


class TestMediaGenerationBudget:
    def test_compression_has_hard_duration_cap(
        self, monkeypatch, tmp_path, chunk_file
    ):
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "compressed.m4a").write_bytes(b"compressed")

        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr, "_run", fake_run)

        tr.compress_audio(chunk_file, tmp_path)

        duration_index = captured["cmd"].index("-t")
        assert captured["cmd"][duration_index + 1] == str(tr.MAX_AUDIO_SECONDS)

    def test_chunk_generation_has_hard_duration_cap(
        self, monkeypatch, tmp_path, chunk_file
    ):
        captured = {}

        def fake_run(cmd, timeout=600):
            captured["cmd"] = cmd
            (tmp_path / "chunk_000.m4a").write_bytes(b"chunk")

        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr, "_run", fake_run)

        tr.chunk_audio(chunk_file, tmp_path)

        duration_index = captured["cmd"].index("-t")
        assert captured["cmd"][duration_index + 1] == str(tr.MAX_AUDIO_SECONDS)

    def test_chunk_generation_rejects_segment_size_that_can_exceed_budget(
        self, monkeypatch, tmp_path, chunk_file
    ):
        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(
            tr,
            "_run",
            lambda *_args, **_kwargs: pytest.fail(
                "unsafe chunk budget must fail before ffmpeg"
            ),
        )

        with pytest.raises(tr.TranscribeError, match=r"chunk.*limit.*24"):
            tr.chunk_audio(
                chunk_file,
                tmp_path,
                segment_seconds=tr.CHUNK_SECONDS - 1,
            )


# --- Subprocess output decoding ---------------------------------------- #


class TestSubprocessDecoding:
    CJK_BYTES = "中文标题".encode("utf-8")

    def _decoding_run(self, returncode: int):
        def fake_run(cmd, **kwargs):
            encoding = kwargs.get("encoding") or "gbk"
            errors = kwargs.get("errors") or "strict"
            text = self.CJK_BYTES.decode(encoding, errors)
            return subprocess.CompletedProcess(cmd, returncode, text, text)

        return fake_run

    def test_run_preserves_cjk_failure_as_transcribe_error(self, monkeypatch):
        monkeypatch.setattr(tr.subprocess, "run", self._decoding_run(1))

        with pytest.raises(tr.TranscribeError, match="yt-dlp"):
            tr._run(["yt-dlp", "https://example.com/video"], timeout=5)

    def test_probe_preserves_cjk_failure_as_transcribe_error(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(tr, "_require", lambda _binary: None)
        monkeypatch.setattr(tr.subprocess, "run", self._decoding_run(1))

        with pytest.raises(tr.TranscribeError, match="duration"):
            tr._probe_audio_duration(tmp_path / "audio.m4a")

    @pytest.mark.parametrize(
        "launch_error",
        [
            FileNotFoundError("missing executable"),
            PermissionError("access denied"),
        ],
        ids=["not-found", "permission"],
    )
    def test_run_wraps_launch_errors_without_command_details(
        self,
        monkeypatch,
        launch_error,
    ):
        sentinel_argument = "https://example.test/private-value"

        def fail_to_start(_cmd, **_kwargs):
            raise launch_error

        monkeypatch.setattr(tr.subprocess, "run", fail_to_start)

        with pytest.raises(tr.TranscribeError) as exc_info:
            tr._run(["yt-dlp", sentinel_argument], timeout=5)

        message = str(exc_info.value)
        assert message == "failed to start yt-dlp"
        assert sentinel_argument not in message
        assert str(launch_error) not in message
        assert exc_info.value.__cause__ is launch_error


# --- YouTubeChannel integration --------------------------------------- #


class TestYouTubeChannelTranscribe:
    def test_delegates_to_transcribe(self, monkeypatch, fake_config):
        from agent_reach.channels.youtube import YouTubeChannel

        captured = {}

        def fake_transcribe(
            source,
            *,
            provider="auto",
            out_dir=None,
            config=None,
            allow_provider_fallback=False,
        ):
            captured["source"] = source
            captured["provider"] = provider
            captured["config"] = config
            captured["allow_provider_fallback"] = allow_provider_fallback
            return "delegated text"

        monkeypatch.setattr(tr, "transcribe", fake_transcribe)
        out = YouTubeChannel().transcribe(
            "https://youtu.be/abc",
            provider="groq",
            config=fake_config,
            allow_provider_fallback=True,
        )
        assert out == "delegated text"
        assert captured["source"] == "https://youtu.be/abc"
        assert captured["provider"] == "groq"
        assert captured["config"] is fake_config
        assert captured["allow_provider_fallback"] is True


# --- Config feature requirement --------------------------------------- #


class TestConfigOpenAIWhisper:
    def test_openai_whisper_feature_registered(self, fake_config):
        assert "openai_whisper" in Config.FEATURE_REQUIREMENTS
        assert Config.FEATURE_REQUIREMENTS["openai_whisper"] == ["openai_api_key"]
        assert not fake_config.is_configured("openai_whisper")
        fake_config.set("openai_api_key", "sk-test")
        assert fake_config.is_configured("openai_whisper")
