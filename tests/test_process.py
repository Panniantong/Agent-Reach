from agent_reach.utils import process
from agent_reach.utils.process import utf8_subprocess_env, windows_hidden_kwargs


def test_utf8_subprocess_env_forces_python_utf8():
    env = utf8_subprocess_env({"PYTHONUTF8": "0", "OTHER": "value"})

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["OTHER"] == "value"


def test_windows_hidden_kwargs_is_empty_on_non_windows(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")

    assert windows_hidden_kwargs() == {}


def test_windows_hidden_kwargs_hides_windows_console_without_detaching(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(process.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(process.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr(process.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)

    flags = windows_hidden_kwargs()["creationflags"]

    assert flags & process.subprocess.CREATE_NO_WINDOW
    assert flags & process.subprocess.CREATE_NEW_PROCESS_GROUP
    assert flags & process.subprocess.DETACHED_PROCESS == 0
