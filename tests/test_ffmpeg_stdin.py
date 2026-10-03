"""File-based transcription must preserve stdin belonging to its caller."""

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest


@pytest.fixture
def long_audio(tmp_path):
    """An hour of sparse PCM keeps the fixture small on disk."""
    audio = tmp_path / "source.wav"
    frames = 16000 * 3600
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0")
    with audio.open("r+b") as output:
        output.seek(4)
        output.write((36 + frames * 2).to_bytes(4, "little"))
        output.seek(40)
        output.write((frames * 2).to_bytes(4, "little"))
        output.truncate(44 + frames * 2)
    return audio


@pytest.mark.parametrize("helper", ["compress_audio", "chunk_audio"])
def test_native_ffmpeg_preserves_caller_stdin(helper, long_audio, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("native FFmpeg and ffprobe are required")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    child = """
import json
import sys
from pathlib import Path
from agent_reach import transcribe

result = getattr(transcribe, sys.argv[1])(Path(sys.argv[2]), Path(sys.argv[3]))
files = result if isinstance(result, list) else [result]
print(json.dumps({"files": [str(path) for path in files], "remaining": sys.stdin.read()}))
"""
    caller_input = "q\nnext step\n"
    result = subprocess.run(
        [sys.executable, "-c", child, helper, str(long_audio), str(output_dir)],
        input=caller_input,
        capture_output=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[1],
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["remaining"] == caller_input
    duration = 0.0
    for audio in data["files"]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
            capture_output=True,
            encoding="utf-8",
            check=True,
            timeout=10,
        )
        duration += float(probe.stdout)
    assert duration == pytest.approx(3600, abs=1)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX executable fixture")
def test_native_podcast_script_preserves_caller_stdin(
    bash_executable, long_audio, tmp_path, monkeypatch
):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("native FFmpeg and ffprobe are required")
    tools = tmp_path / "tools"
    tools.mkdir()
    curl = tools / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import os, shutil, sys\n"
        "args = sys.argv[1:]\n"
        "if '-o' in args:\n"
        "    shutil.copyfile(os.environ['FIXTURE_AUDIO'], args[args.index('-o') + 1])\n"
        "elif 'https://api.groq.com/openai/v1/audio/transcriptions' in args:\n"
        "    print('Fixture transcript\\n200')\n"
        "else:\n"
        '    print(\'{"title":"Fixture","audio":"https://media.xyzcdn.net/test.mp3"}\')\n',
        encoding="utf-8",
    )
    curl.chmod(0o700)
    monkeypatch.setenv("FIXTURE_AUDIO", str(long_audio))
    monkeypatch.setenv("GROQ_API_KEY", "fixture-key")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    script = Path(__file__).resolve().parents[1] / "agent_reach/scripts/transcribe_xiaoyuzhou.sh"
    result = subprocess.run(
        [
            bash_executable,
            "-c",
            'bash "$1" "$2"; status=$?; printf "\\nCALLER_STDIN\\n"; cat; exit "$status"',
            "fixture",
            str(script),
            "https://www.xiaoyuzhoufm.com/episode/fixture",
        ],
        input="q\nnext step\n",
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("CALLER_STDIN\nq\nnext step\n")
