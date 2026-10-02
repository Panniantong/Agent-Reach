"""Native process regressions for bounded POSIX health probes."""

import json
import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

import agent_reach.probe as probe


@pytest.mark.parametrize(
    "exit_code,status", [(0, "ok"), (3, "error"), (127, "broken"), (None, "timeout")]
)
def test_non_posix_fallback_preserves_run_contract(monkeypatch, exit_code, status):
    monkeypatch.setattr(probe, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(probe.shutil, "which", lambda _cmd: "C:/test/tool.exe")
    monkeypatch.setattr(probe, "utf8_subprocess_env", lambda: {"BASE": "test"})

    def run(command, **kwargs):
        assert command == ["C:/test/tool.exe", "--version"]
        assert kwargs == {
            "capture_output": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 2,
            "env": {"BASE": "test", "EXPLICIT": "child"},
        }
        if exit_code is None:
            raise subprocess.TimeoutExpired(command, 2)
        return subprocess.CompletedProcess(command, exit_code, "version", "")

    monkeypatch.setattr(probe.subprocess, "run", run)
    result = probe.probe_command("tool", timeout=2, env={"EXPLICIT": "child"})
    assert result.status == status


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
@pytest.mark.parametrize("parent_exits", [False, True])
def test_timeout_stops_descendant_probe_work(tmp_path, parent_exits):
    pid_file = tmp_path / "child.pid"
    escaped_work = tmp_path / "continued-after-timeout"
    child_code = (
        "import pathlib, time; time.sleep(2); "
        f"pathlib.Path({str(escaped_work)!r}).write_text('still running')"
    )
    shim = tmp_path / "shim.py"
    shim.write_text(
        "import pathlib, subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        + ("" if parent_exits else "time.sleep(60)\n")
    )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import json, sys; from agent_reach.probe import probe_command; "
            "r = probe_command(sys.executable, args=[sys.argv[1]], timeout=1); "
            "print(json.dumps({'status': r.status}))",
            str(shim),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = worker.communicate(timeout=6)
        except subprocess.TimeoutExpired:
            pytest.fail("probe exceeded its timeout while a descendant held its output pipes")
        assert worker.returncode == 0, stderr
        assert json.loads(stdout) == {"status": "timeout"}
        time.sleep(2)
        assert not escaped_work.exists(), "descendant kept working after the probe timed out"
    finally:
        # Clean up our fixture even when the original implementation hangs.
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.communicate(timeout=3)
