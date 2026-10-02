"""Native UTF-8 pipelines retain content with a simulated Windows code page."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_reach import cli


def _format_pipeline(payload, stdio_encoding):
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONIOENCODING"] = stdio_encoding
    env["PYTHONPATH"] = str(Path(cli.__file__).parent.parent)
    # Import platform-sensitive dependencies before simulating Windows. The
    # child then exercises the production console guard and format handler.
    command = (
        "import sys; from agent_reach import cli; "
        "from agent_reach.channels import xiaohongshu; "
        "sys.platform = 'win32'; "
        "cli._ensure_utf8_console(); "
        "cli._cmd_format(type('Args', (), {'platform': 'xhs'})())"
    )
    return subprocess.run(
        [sys.executable, "-c", command],
        input=payload,
        capture_output=True,
        env=env,
        timeout=10,
    )


@pytest.mark.parametrize("stdio_encoding", ["cp1252", "utf-8"])
def test_format_preserves_utf8_redirected_json(stdio_encoding):
    data = {
        "id": "fixture",
        "title": "\u4e2d\u6587\u6807\u9898",
        "desc": "\u771f\u5b9e\u5185\u5bb9",
    }
    result = _format_pipeline(json.dumps(data, ensure_ascii=False).encode("utf-8"), stdio_encoding)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert json.loads(result.stdout.decode("utf-8")) == data


def test_console_guard_preserves_text_only_captured_stdin(monkeypatch):
    stdin = io.StringIO("\u4e2d\u6587\u8f93\u5165")
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    monkeypatch.setattr(cli.sys, "stderr", io.StringIO())
    cli._ensure_utf8_console()
    assert cli.sys.stdin is stdin
    assert stdin.read() == "\u4e2d\u6587\u8f93\u5165"


def test_console_guard_preserves_interactive_stdin(monkeypatch):
    calls = []
    stdin = SimpleNamespace(
        buffer=io.BytesIO(),
        isatty=lambda: True,
        reconfigure=lambda **options: calls.append(options),
    )
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", stdin)
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    monkeypatch.setattr(cli.sys, "stderr", io.StringIO())
    cli._ensure_utf8_console()
    assert cli.sys.stdin is stdin
    assert calls == []


def test_format_rejects_invalid_utf8_without_corrupting_content():
    result = _format_pipeline(b'{"id":"fixture","title":"\xff"}', "cp1252")
    assert result.returncode == 1
    assert "stdin is not valid UTF-8" in result.stderr.decode("utf-8")
    assert "Traceback" not in result.stderr.decode("utf-8")
    assert result.stdout == b""
