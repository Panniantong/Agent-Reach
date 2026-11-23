from pathlib import Path

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


# Exactly what npm's cmd-shim writes for a `#!/usr/bin/env node` bin (global or .bin layout).
_CMD_SHIM = (
    '@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\n'
    'CALL :find_dp0\r\n\r\nIF EXIST "%dp0%\\node.exe" (\r\n  SET "_prog=%dp0%\\node.exe"\r\n'
    ') ELSE (\r\n  SET "_prog=node"\r\n  SET PATHEXT=%PATHEXT:;.JS;=;%\r\n)\r\n\r\n'
    'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\\{target}" %*\r\n'
)

TRICKY_ARGS = [
    "https://www.xiaohongshu.com/explore/66f1a2b3000000001e02c3d4"
    "?xsec_token=ABx9%2Bk%3D&xsec_source=pc_search",
    "a|b<c>d^e",
    '"quoted" (paren) !bang! %PATH%',
    "with space",
    "trailing\\",
    "",
]


@pytest.mark.parametrize("layout,target", [
    ("global", "node_modules\\@jackwener\\opencli\\dist\\src\\main.js"),
    ("bin", "..\\@jackwener\\opencli\\dist\\src\\main.js"),
])
def test_real_npm_shim_passes_tricky_args_untouched(tmp_path, monkeypatch, layout, target):
    shim_dir = tmp_path / ("node_modules/.bin" if layout == "bin" else "")
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "opencli.cmd"
    shim.write_text(_CMD_SHIM.format(target=target), encoding="utf-8")
    script = (shim_dir / target.replace("\\", "/")).resolve()
    script.parent.mkdir(parents=True)
    script.touch()
    node = tmp_path / "node.exe"
    node.touch()

    argv = run._windows_argv(str(shim), TRICKY_ARGS, node=str(node))

    assert argv[0] == str(node)
    assert Path(argv[1]).resolve() == script
    assert argv[2:] == TRICKY_ARGS  # no quoting or escaping added: no shell parses them


def test_non_windows_never_rewrites_argv(tmp_path, monkeypatch):
    shim = tmp_path / "opencli.cmd"
    shim.write_text(_CMD_SHIM.format(target="main.js"), encoding="utf-8")
    (tmp_path / "main.js").touch()
    monkeypatch.setattr(run.sys, "platform", "darwin")
    calls = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            calls.append(argv)

        def communicate(self, **kwargs):
            return b"", b""

    monkeypatch.setattr(run.subprocess, "Popen", Process)
    run.run_cmd([str(shim), TRICKY_ARGS[0]], timeout=1)
    assert calls == [[str(shim), TRICKY_ARGS[0]]]


@pytest.mark.parametrize("arg", TRICKY_ARGS[:3] + ["a\nb"])
def test_shim_without_node_rejects_cmd_metacharacters(tmp_path, arg):
    shim = tmp_path / "opencli.cmd"
    shim.write_text(_CMD_SHIM.format(target="main.js"), encoding="utf-8")
    (tmp_path / "main.js").touch()
    with pytest.raises(ReachError) as exc:
        run._windows_argv(str(shim), [arg], node=None)
    assert exc.value.code == BAD_INPUT


def test_unknown_batch_keeps_plain_args(tmp_path):
    shim = tmp_path / "tool.bat"
    shim.write_text("@echo off\r\npython.exe tool.py %*\r\n", encoding="utf-8")
    args = ["search", "with space", "trailing\\"]
    assert run._windows_argv(str(shim), args, node=None) == [str(shim), *args]
