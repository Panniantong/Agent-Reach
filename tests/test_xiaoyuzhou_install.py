# -*- coding: utf-8 -*-

import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import agent_reach.cli as cli

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIBE_SCRIPT = ROOT / "agent_reach" / "scripts" / "transcribe_xiaoyuzhou.sh"


class _DummyConfig:
    def get(self, _key):
        return None


def test_install_xiaoyuzhou_deps_does_not_raise_when_no_groq_key(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli.os.path,
        "expanduser",
        lambda value: value.replace("~", str(tmp_path)),
    )
    with patch("agent_reach.config.Config", return_value=_DummyConfig()), patch(
        "shutil.which", return_value=None
    ):
        cli._install_xiaoyuzhou_deps()

    out = capsys.readouterr().out
    assert "Xiaoyuzhou" in out
    assert "Groq API key not set" in out


def test_install_xiaoyuzhou_deps_replaces_stale_managed_script(
    monkeypatch, tmp_path, capsys
):
    import stat

    installed = tmp_path / ".agent-reach" / "tools" / "xiaoyuzhou" / "transcribe.sh"
    installed.parent.mkdir(parents=True)
    installed.write_text("#!/bin/sh\necho stale\n", encoding="utf-8")

    monkeypatch.setattr(
        cli.os.path,
        "expanduser",
        lambda value: value.replace("~", str(tmp_path)),
    )
    monkeypatch.setattr("agent_reach.config.Config", lambda: _DummyConfig())
    monkeypatch.setattr("shutil.which", lambda _name: None)

    cli._install_xiaoyuzhou_deps()

    assert installed.read_text(encoding="utf-8") == TRANSCRIBE_SCRIPT.read_text(
        encoding="utf-8"
    )
    if os.name != "nt":
        assert installed.stat().st_mode & stat.S_IXUSR
    assert "script updated" in capsys.readouterr().out


def test_transcribe_script_is_cross_platform_shell_syntax(bash_executable):
    subprocess.run(
        [bash_executable, "-n", TRANSCRIBE_SCRIPT.relative_to(ROOT).as_posix()],
        check=True,
        cwd=ROOT,
    )


def test_transcribe_script_handles_git_bash_python_and_size_math():
    text = TRANSCRIBE_SCRIPT.read_text(encoding="utf-8")
    assert "command -v python3" in text
    assert "command -v python" in text
    assert "command -v py" in text
    assert "cygpath -w" in text
    assert "| bc" not in text


def _bash_path(path: Path) -> str:
    """Render a native path for a Bash process, including Git Bash on Windows."""
    rendered = path.resolve().as_posix()
    if os.name == "nt" and len(rendered) >= 3 and rendered[1:3] == ":/":
        return f"/{rendered[0].lower()}{rendered[2:]}"
    return rendered


def _append_bash_function(path: Path, name: str, script: str) -> None:
    lines = script.splitlines()
    if lines and lines[0].startswith("#!"):
        lines = lines[1:]
    body = "\n".join(lines)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}() {{\n{body}\n}}\n")


def _script_env(
    tmp_path: Path, curl_script: str
) -> tuple[dict[str, str], Path, Path, Path]:
    curl_log = tmp_path / "curl.log"
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    bash_env = tmp_path / "bash-env.sh"
    _append_bash_function(bash_env, "curl", curl_script)

    env = os.environ.copy()
    env.update({
        "BASH_ENV": _bash_path(bash_env),
        "CURL_LOG": _bash_path(curl_log),
        "GROQ_API_KEY": "test-key",
        "TMPDIR": _bash_path(temp_root),
    })
    return env, curl_log, temp_root, bash_env


def _assert_work_dir_cleaned(temp_root: Path) -> None:
    assert list(temp_root.glob("agent-reach-xiaoyuzhou.*")) == []


@pytest.mark.parametrize(
    "url",
    [
        "ftp://xiaoyuzhoufm.com/episode/123",
        "https://notxiaoyuzhoufm.com/episode/123",
        "https://xiaoyuzhoufm.com.evil.example/episode/123",
        "https://evil.example/episode/123?next=xiaoyuzhoufm.com",
    ],
)
def test_transcribe_script_rejects_non_xiaoyuzhou_urls_before_curl(
    tmp_path, url, bash_executable
):
    env, curl_log, temp_root, _ = _script_env(
        tmp_path,
        "#!/bin/sh\nprintf 'called\\n' >> \"$CURL_LOG\"\nexit 42\n",
    )

    result = subprocess.run(
        [
            bash_executable,
            TRANSCRIBE_SCRIPT.relative_to(ROOT).as_posix(),
            url,
            _bash_path(tmp_path / "out.txt"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=ROOT,
    )

    assert result.returncode != 0
    assert "Only http/https URLs from xiaoyuzhoufm.com" in result.stderr
    assert not curl_log.exists()
    _assert_work_dir_cleaned(temp_root)


@pytest.mark.parametrize(
    "url",
    [
        "http://xiaoyuzhoufm.com/episode/123",
        "https://www.xiaoyuzhoufm.com/episode/123",
    ],
)
def test_transcribe_script_accepts_http_xiaoyuzhou_hosts(
    tmp_path, url, bash_executable
):
    env, curl_log, temp_root, _ = _script_env(
        tmp_path,
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CURL_LOG\"\nexit 42\n",
    )

    result = subprocess.run(
        [
            bash_executable,
            TRANSCRIBE_SCRIPT.relative_to(ROOT).as_posix(),
            url,
            _bash_path(tmp_path / "out.txt"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=ROOT,
    )

    assert result.returncode != 0
    assert curl_log.exists()
    _assert_work_dir_cleaned(temp_root)


def test_transcribe_script_uses_secure_temp_and_bounded_curl_calls():
    text = TRANSCRIBE_SCRIPT.read_text(encoding="utf-8")

    assert "mktemp -d" in text
    assert "xiaoyuzhou_$$" not in text
    assert "/tmp/podcast_transcript.txt" not in text
    assert 'mktemp "${TEMP_ROOT%/}/agent-reach-transcript.XXXXXX"' in text
    assert "trap cleanup EXIT" in text
    assert text.count('--connect-timeout "$CURL_CONNECT_TIMEOUT"') == 4
    assert text.count('--max-time "$GROQ_TIMEOUT"') == 2
    assert text.count("--fail --show-error --location") == 2
    assert text.count("--max-filesize") == 4
    assert text.count('--max-filesize "$MAX_API_RESPONSE_BYTES"') == 2
    assert "MAX_DURATION_SECONDS=10800" in text
    assert '-t "$MAX_DURATION_SECONDS"' in text
    assert 'if [ "$WAIT_SEC" -gt 900 ]' in text
    assert "r.read(32 * 1024 * 1024 + 1)" in text

    page_limit = int(re.search(r"^MAX_PAGE_BYTES=(\d+)$", text, re.MULTILINE).group(1))
    audio_limit = int(re.search(r"^MAX_AUDIO_BYTES=(\d+)$", text, re.MULTILINE).group(1))
    api_response_limit = int(
        re.search(r"^MAX_API_RESPONSE_BYTES=(\d+)$", text, re.MULTILINE).group(1)
    )
    assert page_limit <= 10 * 1024 * 1024
    assert 25 * 1024 * 1024 <= audio_limit <= 2 * 1024 * 1024 * 1024
    assert api_response_limit <= 32 * 1024 * 1024


@pytest.mark.parametrize("ffprobe_output", ["", "not-a-number"])
def test_transcribe_script_fails_clearly_for_invalid_duration(
    tmp_path, ffprobe_output, bash_executable
):
    env, _, temp_root, bash_env = _script_env(
        tmp_path,
        """#!/bin/bash
output=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        output="$2"
        shift 2
    else
        shift
    fi
done
if [ -n "$output" ]; then
    printf 'fake audio' > "$output"
else
    printf '%s' '<html><script>"title":"Test"</script>https://media.xyzcdn.net/test.mp3</html>'
fi
""",
    )
    _append_bash_function(
        bash_env,
        "ffprobe",
        "#!/bin/sh\nprintf '%s' \"$FFPROBE_OUTPUT\"\n",
    )
    env["FFPROBE_OUTPUT"] = ffprobe_output

    result = subprocess.run(
        [
            bash_executable,
            TRANSCRIBE_SCRIPT.relative_to(ROOT).as_posix(),
            "https://www.xiaoyuzhoufm.com/episode/123",
            _bash_path(tmp_path / "out.txt"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=ROOT,
    )

    assert result.returncode != 0
    assert "ffprobe returned an invalid audio duration" in result.stderr
    _assert_work_dir_cleaned(temp_root)


@pytest.mark.parametrize("ffprobe_output", ["10801", "9" * 500])
def test_transcribe_script_rejects_overlong_audio_before_ffmpeg_or_groq(
    tmp_path, ffprobe_output, bash_executable
):
    env, curl_log, temp_root, bash_env = _script_env(
        tmp_path,
        """#!/bin/bash
printf '%s\n' "$*" >> "$CURL_LOG"
output=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        output="$2"
        shift 2
    else
        shift
    fi
done
if [ -n "$output" ]; then
    printf 'fake audio' > "$output"
else
    printf '%s' '<html><script>"title":"Test"</script>https://media.xyzcdn.net/test.mp3</html>'
fi
""",
    )
    ffmpeg_marker = tmp_path / "ffmpeg-called"
    _append_bash_function(
        bash_env,
        "ffprobe",
        "#!/bin/sh\nprintf '%s' \"$FFPROBE_OUTPUT\"\n",
    )
    _append_bash_function(
        bash_env,
        "ffmpeg",
        "#!/bin/sh\nprintf 'called' > \"$FFMPEG_MARKER\"\n",
    )
    env["FFMPEG_MARKER"] = _bash_path(ffmpeg_marker)
    env["FFPROBE_OUTPUT"] = ffprobe_output

    result = subprocess.run(
        [
            bash_executable,
            TRANSCRIBE_SCRIPT.relative_to(ROOT).as_posix(),
            "https://www.xiaoyuzhoufm.com/episode/123",
            _bash_path(tmp_path / "out.txt"),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=ROOT,
    )

    assert result.returncode != 0
    assert "Audio duration exceeds the 3-hour limit" in result.stderr
    assert not ffmpeg_marker.exists()
    curl_calls = curl_log.read_text(encoding="utf-8").splitlines()
    assert len(curl_calls) == 2
    assert all("api.groq.com" not in call for call in curl_calls)
    _assert_work_dir_cleaned(temp_root)
