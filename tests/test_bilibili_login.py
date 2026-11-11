"""Legacy explicit site-session import remains compatible."""
import pytest

from agent_reach.channels import bilibili
from agent_reach.runtime import sessions, state, tools


def test_reuse_browser_session_writes_the_official_credential(monkeypatch):
    from agent_reach.runtime import session_reuse

    root = sessions.session_dir("bili-cli") / ".bilibili-cli"
    root.mkdir(parents=True, exist_ok=True)
    (root / "credential.json").write_text('{"sessdata":""}', encoding="utf-8")
    monkeypatch.setattr(session_reuse, "_source_cookies",
                        lambda channel, domains: ([{"name": "SESSDATA", "value": "abc"}], "chrome"))
    monkeypatch.setattr(tools, "resolve", lambda name: r"C:\fake\bili.exe")
    monkeypatch.setattr(bilibili, "session_env", lambda session: {})
    monkeypatch.setattr(bilibili, "run_cmd", lambda cmd, **kwargs: (
        root / "credential.json").write_text('{"sessdata":"abc"}', encoding="utf-8"))

    assert bilibili.reuse_browser_session(5) is True
    assert sessions.has_login_state("bili-cli") is True
    assert state.load()["session_reuse"]["bilibili"]["source"] == "chrome"


def test_reuse_browser_session_stays_quiet_without_a_connected_source(monkeypatch):
    from agent_reach.runtime import session_reuse

    monkeypatch.setattr(session_reuse, "_source_cookies", lambda channel, domains: ([], "saved-profile"))
    monkeypatch.setattr(bilibili, "run_cmd", lambda cmd, **kwargs: pytest.fail("must not run the writer"))
    assert bilibili.reuse_browser_session(5) is False

