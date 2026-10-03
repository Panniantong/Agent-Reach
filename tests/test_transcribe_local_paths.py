"""Real FFmpeg must receive unambiguous local file paths."""

import os
import shutil
import wave
from pathlib import Path

import pytest

from agent_reach import transcribe as tr


@pytest.fixture
def audio(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("native FFmpeg and ffprobe are required")
    monkeypatch.chdir(tmp_path)
    source = Path("source.wav")
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    return source


@pytest.mark.skipif(os.name == "nt", reason="colons are not valid in Windows file names")
def test_local_colon_filename_reaches_transcription(audio, monkeypatch):
    source = Path("Podcast: interview.wav")
    audio.rename(source)
    calls = []

    class Config:
        def get(self, key):
            return "fixture-key" if key == "groq_api_key" else None

    def transcribe_chunk(chunk, provider, *, config):
        calls.append((chunk, provider))
        assert tr._probe_audio_duration(chunk) == pytest.approx(1, abs=0.1)
        return "fixture transcript"

    monkeypatch.setattr(tr, "transcribe_chunk", transcribe_chunk)
    assert tr.transcribe(str(source), config=Config()) == "fixture transcript"
    assert len(calls) == 1
    assert calls[0][1] == "groq"


@pytest.mark.parametrize("directory", ["-work", "ordinary work"])
@pytest.mark.parametrize("helper", ["compress_audio", "chunk_audio"])
def test_relative_output_directories_work_with_native_ffmpeg(audio, directory, helper):
    output = Path(directory)
    output.mkdir()
    result = getattr(tr, helper)(audio, output)
    files = result if isinstance(result, list) else [result]
    assert files
    assert all(path.parent == output for path in files)
    duration = sum(tr._probe_audio_duration(path) for path in files)
    assert duration == pytest.approx(1, abs=0.1)


@pytest.mark.skipif(os.name == "nt", reason="colons are not valid in Windows file names")
@pytest.mark.parametrize("helper", ["compress_audio", "chunk_audio"])
def test_relative_colon_input_works_with_native_ffmpeg(audio, helper):
    source = Path("Podcast: interview.wav")
    audio.rename(source)
    output = Path("work")
    output.mkdir()
    result = getattr(tr, helper)(source, output)
    files = result if isinstance(result, list) else [result]
    duration = sum(tr._probe_audio_duration(path) for path in files)
    assert duration == pytest.approx(1, abs=0.1)
