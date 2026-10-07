"""Keep retained transcription artifacts isolated without touching caller files."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from agent_reach import transcribe as tr
from agent_reach.config import Config


@pytest.fixture
def offline_transcription(tmp_path, monkeypatch):
    """Exercise real orchestration and file selection; replace only external IO."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = Config(config_path=tmp_path / "config.yaml", read_only=True)
    cfg.data["groq_api_key"] = "gsk_test_not_a_real_key"
    uploaded = []

    def fake_post(_url, *, files, **_kwargs):
        payload = files["file"][1].read().decode("utf-8")
        uploaded.append(payload)
        return SimpleNamespace(ok=True, text=payload)

    def fake_run(cmd, timeout=600):
        if cmd[0] == "yt-dlp":
            template = cmd[cmd.index("-o") + 1]
            output = Path(template.replace("%(ext)s", "m4a"))
            # yt-dlp can reuse a completed file at the same output path.
            if not output.exists():
                output.write_text(cmd[-1], encoding="utf-8")
        elif cmd[0] == "ffmpeg":
            source = Path(cmd[cmd.index("-i") + 1])
            destination = Path(cmd[-1])
            if "-f" in cmd:
                for index, piece in enumerate(source.read_text(encoding="utf-8").split("|")):
                    Path(str(destination).replace("%03d", f"{index:03d}")).write_text(
                        piece, encoding="utf-8"
                    )
            else:
                # Mimic ffmpeg's refusal to overwrite its own input.
                if source.resolve() == destination.resolve():
                    raise tr.TranscribeError("ffmpeg cannot edit existing files in-place")
                destination.write_bytes(source.read_bytes())
        else:
            pytest.fail(f"unexpected external command: {cmd[0]}")

    monkeypatch.setattr(tr, "_require", lambda _binary: None)
    monkeypatch.setattr(tr, "_probe_audio_duration", lambda _path: 60.0)
    monkeypatch.setattr(tr, "_run", fake_run)
    monkeypatch.setattr(tr.requests, "post", fake_post)
    return cfg, uploaded


def test_reused_output_root_does_not_reuse_previous_download(
    tmp_path, offline_transcription
):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    first = "https://example.com/first"
    second = "https://example.com/second"

    assert tr.transcribe(first, out_dir=root, config=cfg) == first
    assert tr.transcribe(second, out_dir=root, config=cfg) == second
    assert uploaded == [first, second]
    runs = list(root.glob("transcribe-*"))
    assert len(runs) == 2
    assert {p.joinpath("source.m4a").read_text() for p in runs} == {first, second}


def test_shorter_second_run_does_not_upload_old_tail_chunks(
    tmp_path, monkeypatch, offline_transcription
):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    first = tmp_path / "first.m4a"
    second = tmp_path / "second.m4a"
    first.write_text("aaa|bbb|ccc", encoding="utf-8")
    second.write_text("ddd|eee", encoding="utf-8")
    monkeypatch.setattr(tr, "SIZE_LIMIT_BYTES", 4)

    assert tr.transcribe(str(first), out_dir=root, config=cfg) == "aaa\nbbb\nccc"
    assert tr.transcribe(str(second), out_dir=root, config=cfg) == "ddd\neee"
    assert uploaded == ["aaa", "bbb", "ccc", "ddd", "eee"]


def test_existing_output_root_files_are_not_overwritten(tmp_path, offline_transcription):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    root.mkdir()
    previous = {
        "source.m4a": b"previous download",
        "compressed.m4a": b"caller-owned audio",
        "chunk_000.m4a": b"previous chunk",
        "notes.txt": b"keep this too",
    }
    for name, payload in previous.items():
        (root / name).write_bytes(payload)
    source = "https://example.com/new"

    assert tr.transcribe(source, out_dir=root, config=cfg) == source
    assert uploaded == [source]
    assert {name: (root / name).read_bytes() for name in previous} == previous


def test_local_input_named_compressed_is_not_used_as_output(tmp_path, offline_transcription):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    root.mkdir()
    source = root / "compressed.m4a"
    source.write_bytes(b"original recording")

    assert tr.transcribe(str(source), out_dir=root, config=cfg) == "original recording"
    assert source.read_bytes() == b"original recording"
    assert uploaded == ["original recording"]


def test_no_download_output_does_not_upload_stale_audio(
    tmp_path, monkeypatch, offline_transcription
):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    root.mkdir()
    stale = root / "source.m4a"
    stale.write_bytes(b"old audio")
    run = tr._run

    def skip_download(cmd, timeout=600):
        # --max-filesize or an upstream archive rule can produce no file.
        if cmd[0] != "yt-dlp":
            run(cmd, timeout=timeout)

    monkeypatch.setattr(tr, "_run", skip_download)
    with pytest.raises(tr.TranscribeError, match="no output file"):
        tr.transcribe("https://example.com/skipped", out_dir=root, config=cfg)
    assert uploaded == []
    assert stale.read_bytes() == b"old audio"


def test_concurrent_runs_in_one_output_root_are_independent(
    tmp_path, monkeypatch, offline_transcription
):
    cfg, uploaded = offline_transcription
    root = tmp_path / "retained"
    sources = []
    for name in ("first", "second"):
        source = tmp_path / f"{name}.m4a"
        source.write_text(name, encoding="utf-8")
        sources.append(source)
    barrier = Barrier(2, timeout=10)
    run = tr._run

    def synchronized_compression(cmd, timeout=600):
        run(cmd, timeout=timeout)
        if cmd[0] == "ffmpeg":
            # Both writes finish before either upload, without timing sleeps.
            barrier.wait()

    monkeypatch.setattr(tr, "_run", synchronized_compression)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(tr.transcribe, str(source), out_dir=root, config=cfg)
            for source in sources
        ]
        results = [future.result(timeout=15) for future in futures]

    assert results == ["first", "second"]
    assert sorted(uploaded) == ["first", "second"]
    assert len(list(root.glob("transcribe-*"))) == 2


@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
def test_explicit_output_retains_current_run_artifacts(
    tmp_path, monkeypatch, offline_transcription, fail
):
    cfg, _ = offline_transcription
    root = tmp_path / "new-parent" / "retained"
    if fail:
        def fail_upload(*_args, **_kwargs):
            raise tr.TranscribeError("simulated provider failure")

        monkeypatch.setattr(tr, "transcribe_chunk", fail_upload)
        with pytest.raises(tr.TranscribeError, match="simulated provider failure"):
            tr.transcribe("https://example.com/video", out_dir=root, config=cfg)
    else:
        tr.transcribe("https://example.com/video", out_dir=root, config=cfg)

    runs = list(root.iterdir())
    assert len(runs) == 1
    assert runs[0].is_dir()
    assert runs[0].name.startswith("transcribe-")
    assert (runs[0] / "source.m4a").is_file()
    assert (runs[0] / "compressed.m4a").is_file()


@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
def test_default_temporary_output_is_still_cleaned(
    tmp_path, monkeypatch, offline_transcription, fail
):
    cfg, _ = offline_transcription
    seen = []
    compress = tr.compress_audio

    def record_work_dir(source, work_dir):
        seen.append(work_dir)
        return compress(source, work_dir)

    monkeypatch.setattr(tr, "compress_audio", record_work_dir)
    monkeypatch.setattr(tr.tempfile, "tempdir", str(tmp_path))
    if fail:
        def fail_upload(*_args, **_kwargs):
            raise tr.TranscribeError("simulated provider failure")

        monkeypatch.setattr(tr, "transcribe_chunk", fail_upload)
        with pytest.raises(tr.TranscribeError, match="simulated provider failure"):
            tr.transcribe("https://example.com/video", config=cfg)
    else:
        tr.transcribe("https://example.com/video", config=cfg)

    assert len(seen) == 1
    assert not seen[0].exists()


def test_missing_provider_does_not_create_output_directory(tmp_path, offline_transcription):
    cfg, _ = offline_transcription
    cfg.data.clear()
    root = tmp_path / "not-created"
    with pytest.raises(tr.NoProviderConfigured):
        tr.transcribe("https://example.com/video", out_dir=root, config=cfg)
    assert not root.exists()


def test_relative_output_root_is_supported(tmp_path, monkeypatch, offline_transcription):
    cfg, _ = offline_transcription
    monkeypatch.chdir(tmp_path)
    source = "https://example.com/relative"
    root = Path("relative output")
    assert tr.transcribe(source, out_dir=root, config=cfg) == source
    runs = list(root.glob("transcribe-*"))
    assert len(runs) == 1
    assert (runs[0] / "compressed.m4a").read_text() == source
