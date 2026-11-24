"""Fixes from the 1.6.1 private security report."""

import pytest

from agent_reach.channels import bilibili
from agent_reach.runtime import cdp, sessions, tools
from agent_reach.runtime.result import ReachError


@pytest.mark.parametrize("target", [
    "file:///etc/hosts#b23.tv/x",
    "http://127.0.0.1:8080/admin?b23.tv/x",
    "https://b23.tv.evil.example/x",
    "https://evil.example/b23.tv/x",
])
def test_b23_short_link_check_never_fetches_other_hosts(monkeypatch, target):
    opened = []
    monkeypatch.setattr(bilibili.urllib.request, "urlopen", lambda *a, **k: opened.append(a) or None)
    with pytest.raises(ReachError):
        bilibili._bvid(target, 1)
    assert opened == []


@pytest.mark.parametrize("target", ["b23.tv/abc", "https://b23.tv/abc"])
def test_b23_short_link_is_still_resolved(monkeypatch, target):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def geturl(self):
            return "https://www.bilibili.com/video/BV1xx411c7mD"

    seen = []
    monkeypatch.setattr(bilibili.urllib.request, "urlopen", lambda req, **k: seen.append(req.full_url) or Resp())
    assert bilibili._bvid(target, 1) == "BV1xx411c7mD"
    assert seen == ["https://b23.tv/abc"]


def test_bili_cli_cannot_find_the_users_own_browsers(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    env = sessions.session_env("bili-cli")
    home = env["HOME"]
    # browser-cookie3 locates Windows browser profiles via these, not HOME.
    assert env["APPDATA"] == env["LOCALAPPDATA"] == env["USERPROFILE"] == home
    assert "APPDATA" not in sessions.session_env("other-tool")


def test_cdp_only_connects_to_our_loopback_port(monkeypatch):
    monkeypatch.setattr(cdp, "_json", lambda path: {"webSocketDebuggerUrl": "ws://10.0.0.9:9999/devtools/browser/x"})
    seen = []

    def fake_connect(addr, timeout):
        seen.append(addr)
        raise OSError("stop")

    monkeypatch.setattr(cdp.socket, "create_connection", fake_connect)
    assert cdp.call("Browser.getVersion") is None
    ours = cdp.urlparse(cdp.CDP_URL)
    assert seen == [(ours.hostname, ours.port)]


def test_cloakbrowser_install_keeps_a_compatible_playwright(monkeypatch, tmp_path):
    tool = tools.TOOLS["cloakbrowser"]
    monkeypatch.setattr(tools, "tool_dir", lambda name: tmp_path / name)
    py = tmp_path / tool.name / "venv" / ("Scripts/python.exe" if tools._WIN else "bin/python")
    py.parent.mkdir(parents=True)
    py.write_text("")
    calls = []
    monkeypatch.setattr(tools, "_run", lambda argv, **kwargs: calls.append(argv) or "")
    tools._install_pip(tool)
    assert "cloakbrowser==0.6.3" in calls[0] and "playwright<1.65" in calls[0]


def test_existing_cloakbrowser_copy_is_repaired_on_setup(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "_private_bin", lambda tool, c: tmp_path)  # exists
    monkeypatch.setattr(tools.state, "load", lambda: {"tools": {"cloakbrowser": {"owner": tools.OURS, "version": "0.6.3"}}})
    installed = []
    monkeypatch.setattr(tools, "_install", lambda tool, **k: installed.append(tool.name))
    monkeypatch.setattr(tools, "record", lambda name, version, **k: {"tool": name})
    monkeypatch.setattr(tools, "_private_version", lambda tool: "0.6.3")
    tools.ensure("cloakbrowser")
    assert installed == ["cloakbrowser"]
    # tools without pins keep the fast path
    monkeypatch.setattr(tools.state, "load", lambda: {"tools": {"bili-cli": {"owner": tools.OURS, "version": "0.6.2"}}})
    assert tools.ensure("bili-cli") == {"tool": "bili-cli", "owner": tools.OURS, "version": "0.6.2"}
    assert installed == ["cloakbrowser"]
