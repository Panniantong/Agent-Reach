import pytest

from agent_reach.runtime import run, tools
from agent_reach.runtime.result import BAD_INPUT, ReachError


def test_run_cmd_bypasses_npm_shim_for_windows_metacharacters(tmp_path, monkeypatch):
    shim = tmp_path / "opencli.cmd"
    script = tmp_path / "node_modules" / "@jackwener" / "opencli" / "bin" / "opencli.js"
    node = tmp_path / "node.exe"
    script.parent.mkdir(parents=True)
    script.write_text("// fixture entry point\n", encoding="utf-8")
    node.touch()
    shim.write_text(
        '@ECHO OFF\r\n"%_prog%" "%dp0%\\node_modules\\@jackwener\\opencli\\bin\\opencli.js" %*\r\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(run.sys, "platform", "win32")
    monkeypatch.setattr(tools, "resolve", lambda name: str(node) if name == "node" else None)
    calls = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            calls.append(argv)

        def communicate(self, **kwargs):
            return b"[]", b""

    monkeypatch.setattr(run.subprocess, "Popen", Process)
    url = "https://www.xiaohongshu.com/search_result/1?xsec_token=abc&xsec_source="
    result = run.run_cmd([str(shim), "xiaohongshu", "read", url, "-f", "json"], timeout=1)

    assert result == "[]"
    assert calls == [[str(node), str(script), "xiaohongshu", "read", url, "-f", "json"]]


def test_run_cmd_rejects_metacharacters_for_unknown_batch_shim(tmp_path, monkeypatch):
    shim = tmp_path / "tool.cmd"
    shim.write_text("@echo off\r\npython.exe tool.py %*\r\n", encoding="utf-8")
    monkeypatch.setattr(run.sys, "platform", "win32")
    monkeypatch.setattr(tools, "resolve", lambda name: None)
    calls = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            calls.append(argv)

    monkeypatch.setattr(run.subprocess, "Popen", Process)

    with pytest.raises(ReachError) as exc:
        run.run_cmd([str(shim), "https://example.test/?a=1&b=2"], timeout=1)

    assert exc.value.code == BAD_INPUT
    assert not calls
