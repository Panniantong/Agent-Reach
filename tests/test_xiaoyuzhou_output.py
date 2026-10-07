"""A failed transcript write must preserve a previously saved output."""

import os
import subprocess

import pytest
from test_xiaoyuzhou_install import (
    ROOT,
    TRANSCRIBE_SCRIPT,
    _append_bash_function,
    _bash_path,
    _script_env,
)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX file-size limit")
@pytest.mark.parametrize("fail_write", [True, False])
@pytest.mark.parametrize("symlink_output", [True, False])
def test_final_output_preserves_old_file_on_write_failure(
    tmp_path, bash_executable, fail_write, symlink_output
):
    env, _curl_log, temp_root, bash_env = _script_env(
        tmp_path,
        """
case "$*" in
  *audio/transcriptions*) printf '%s\\n200\\n' "$TEST_TRANSCRIPT" ;;
  *media.xyzcdn.net*)
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "-o" ]; then printf x > "$2"; return 0; fi
      shift
    done ;;
  *) printf '%s' '{"title":"test","url":"https://media.xyzcdn.net/audio.m4a"}' ;;
esac
""",
    )
    env["TEST_TRANSCRIPT"] = "a" * 1200
    _append_bash_function(bash_env, "ffprobe", "printf '10\\n'")
    _append_bash_function(
        bash_env, "ffmpeg", 'for output in "$@"; do :; done; printf x > "$output"'
    )
    target = tmp_path / "out.md"
    output = tmp_path / "link.md" if symlink_output else target
    if symlink_output:
        output.symlink_to(target.name)
    previous = b"previous complete transcript\n"
    target.write_bytes(previous)

    if fail_write:
        # Activate the real OS file-size ceiling only once media/API stages
        # have finished, so this exercises final publication rather than
        # Bash's earlier temporary here-document writes.
        _append_bash_function(
            bash_env,
            "echo",
            """
case "$*" in *正在合并文字稿*) ulimit -f 1 ;; esac
builtin echo "$@"
""",
        )

    result = subprocess.run(
        [
            bash_executable,
            str(TRANSCRIBE_SCRIPT),
            "https://www.xiaoyuzhoufm.com/episode/test",
            _bash_path(output),
        ],
        env=env,
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    if fail_write:
        assert result.returncode != 0
        assert "✅ 完成" not in result.stdout
        assert output.read_bytes() == previous
    else:
        assert result.returncode == 0, result.stderr
        assert "a" * 1200 in output.read_text(encoding="utf-8")
        assert output.read_bytes() != previous
    if symlink_output:
        assert output.is_symlink()
    assert list(temp_root.glob("agent-reach-xiaoyuzhou.*")) == []
    assert list(tmp_path.glob(".agent-reach-output.*")) == []


@pytest.mark.skipif(os.name == "nt", reason="native POSIX file-size limit")
@pytest.mark.parametrize("fail_write", [True, False])
@pytest.mark.parametrize("symlink_output", [True, False])
def test_cli_output_preserves_previous_transcript(tmp_path, fail_write, symlink_output):
    import sys

    target = tmp_path / "saved.md"
    previous = b"previous complete transcript\n"
    target.write_bytes(previous)
    output = tmp_path / "link.md" if symlink_output else target
    if symlink_output:
        output.symlink_to(target.name)
    runner = tmp_path / "cli_runner.py"
    runner.write_text(
        """
import os
import resource
from types import SimpleNamespace
import agent_reach.transcribe as module
from agent_reach.cli import _cmd_transcribe
module.transcribe = lambda *args, **kwargs: "a" * 1200
if os.environ["FAIL_WRITE"] == "yes":
    resource.setrlimit(resource.RLIMIT_FSIZE, (200, 200))
_cmd_transcribe(SimpleNamespace(source="test", provider="groq", output=os.environ["OUTPUT"]))
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "OUTPUT": str(output),
            "FAIL_WRITE": "yes" if fail_write else "no",
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, str(runner)],
        env=env,
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=15,
    )
    if fail_write:
        assert result.returncode != 0
        assert "✅" not in result.stdout
        assert target.read_bytes() == previous
        assert "Traceback" not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert target.read_text(encoding="utf-8") == "a" * 1200 + "\n"
    if symlink_output:
        assert output.is_symlink()
    assert list(tmp_path.glob(".agent-reach-output.*")) == []


@pytest.mark.skipif(os.name == "nt", reason="native POSIX FIFO metadata")
def test_cli_refuses_to_replace_fifo_output(tmp_path, monkeypatch, capsys):
    import stat
    from types import SimpleNamespace

    import agent_reach.transcribe as module
    from agent_reach.cli import _cmd_transcribe

    output = tmp_path / "output.fifo"
    os.mkfifo(output)
    monkeypatch.setattr(module, "transcribe", lambda *args, **kwargs: "transcript")
    with pytest.raises(SystemExit) as exc:
        _cmd_transcribe(SimpleNamespace(source="test", provider="groq", output=str(output)))
    assert exc.value.code == 1
    assert "regular file" in capsys.readouterr().err
    assert stat.S_ISFIFO(output.stat().st_mode)
    assert list(tmp_path.glob(".agent-reach-output.*")) == []


def test_cli_saves_unicode_regular_file_and_preserves_mode(tmp_path, monkeypatch, capsys):
    import stat
    from types import SimpleNamespace

    import agent_reach.transcribe as module
    from agent_reach.cli import _cmd_transcribe

    output = tmp_path / "saved.md"
    output.write_text("previous", encoding="utf-8")
    if os.name != "nt":
        output.chmod(0o640)
    monkeypatch.setattr(module, "transcribe", lambda *args, **kwargs: "播客文本 café")
    _cmd_transcribe(SimpleNamespace(source="test", provider="groq", output=str(output)))
    assert output.read_text(encoding="utf-8") == "播客文本 café\n"
    assert "Transcript written" in capsys.readouterr().out
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o640
    assert list(tmp_path.glob(".agent-reach-output.*")) == []


def test_cli_replace_failure_preserves_output_and_cleans_stage(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    import agent_reach.transcribe as module
    from agent_reach.cli import _cmd_transcribe

    output = tmp_path / "saved.md"
    output.write_text("previous complete transcript", encoding="utf-8")
    monkeypatch.setattr(module, "transcribe", lambda *args, **kwargs: "new transcript")
    replacement_attempts = []

    def fail_replace(source, destination):
        replacement_attempts.append((source, destination))
        assert source.read_text(encoding="utf-8") == "new transcript\n"
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(SystemExit) as exc:
        _cmd_transcribe(SimpleNamespace(source="test", provider="groq", output=str(output)))
    assert exc.value.code == 1
    assert len(replacement_attempts) == 1
    assert output.read_text(encoding="utf-8") == "previous complete transcript"
    captured = capsys.readouterr()
    assert "Could not save transcript" in captured.err
    assert "Transcript written" not in captured.out
    assert list(tmp_path.glob(".agent-reach-output.*")) == []
