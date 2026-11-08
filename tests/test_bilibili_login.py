"""Bilibili must not report an empty saved credential as a completed login."""

import json
import subprocess
import sys

import pytest

from agent_reach.channels import bilibili
from agent_reach.runtime import cli, sessions, state, tools
from agent_reach.runtime.result import ReachError


@pytest.fixture
def credential(monkeypatch):
    root = sessions.session_dir("bili-cli") / ".bilibili-cli"
    root.mkdir()
    monkeypatch.setattr(cli, "get_all_channels", lambda: [bilibili.BilibiliChannel()])
    monkeypatch.setattr(tools, "resolve", lambda name: "fake-bili")
    monkeypatch.setattr(cli.subprocess, "call", lambda *args, **kwargs: 0)
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(bilibili, "reuse_browser_session", lambda timeout: False)
    return root / "credential.json"


@pytest.mark.parametrize("saved", [
    '{"sessdata":"","bili_jct":"","saved_at":123}',
    '{}', '[]', 'null', '{', '{"sessdata":null}', '{"sessdata":123}',
])
def test_empty_or_malformed_credential_is_not_a_successful_login(credential, saved, capsys):
    credential.write_text(saved, encoding="utf-8")
    assert cli.main(["login", "bilibili"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_BROKEN"
    assert "bilibili" not in state.load().get("session_reuse", {})
    assert cli.main(["channels"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["channels"][0]["login"]["logged_in"] is False
    assert credential.read_text(encoding="utf-8") == saved


def test_unrelated_session_file_does_not_count_as_bilibili_login(credential, capsys):
    (credential.parent / "settings.json").write_text("{}")
    assert cli.main(["login", "bilibili"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_saved_session_cookie_can_complete_login(credential, capsys):
    credential.write_text('{"sessdata":"test-session-cookie"}', encoding="utf-8")
    assert cli.main(["login", "bilibili"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"] == [{"logged_in": True}]
    assert state.load()["session_reuse"]["bilibili"]["source"] == "manual"
    assert cli.main(["channels"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["channels"][0]["login"]["logged_in"] is True
    assert "test-session-cookie" not in json.dumps(result)


@pytest.mark.parametrize("saved,code", [
    ('{"sessdata":"","saved_at":123}', "NEED_LOGIN"),
    ('{}', "NEED_LOGIN"),
    ('{"sessdata":"test-session-cookie"}', "UPSTREAM_BROKEN"),
])
def test_unavailable_subtitle_distinguishes_empty_login_from_upstream_failure(
    credential, monkeypatch, saved, code,
):
    credential.write_text(saved, encoding="utf-8")
    monkeypatch.setattr(bilibili, "_bili_json", lambda args, timeout: {
        "subtitle": {"available": False}, "warnings": [{"code": "subtitle_unavailable"}],
    })
    with pytest.raises(ReachError) as exc:
        bilibili.BilibiliChannel()._cli_subtitle(target="BV1GJ411x7h7", timeout=5)
    assert exc.value.code == code
    if code == "NEED_LOGIN":
        assert "user" in exc.value.hint


def test_available_subtitle_does_not_require_saved_login(credential, monkeypatch):
    monkeypatch.setattr(bilibili, "_bili_json", lambda args, timeout: {
        "subtitle": {"available": True, "text": "public subtitle"},
    })
    items = bilibili.BilibiliChannel()._cli_subtitle(target="BV1GJ411x7h7", timeout=5)
    assert items[0]["text"] == "public subtitle"


def test_login_child_uses_utf8_for_interactive_output(monkeypatch, capfd):
    root = sessions.session_dir("bili-cli") / ".bilibili-cli"
    root.mkdir()
    (root / "credential.json").write_text('{"sessdata":"test-session-cookie"}', encoding="utf-8")
    monkeypatch.setattr(cli, "get_all_channels", lambda: [bilibili.BilibiliChannel()])
    monkeypatch.setattr(tools, "resolve", lambda name: "fake-bili")
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "gbk")
    real_call = subprocess.call

    def login_command(*args, **kwargs):
        return real_call(
            [sys.executable, "-c", "print('📱')"],
            env=kwargs["env"],
            stdout=kwargs["stdout"],
            stderr=kwargs["stderr"],
        )

    monkeypatch.setattr(cli.subprocess, "call", login_command)

    assert cli.main(["login", "bilibili"]) == 0
    captured = capfd.readouterr()
    assert "📱" in captured.err
    assert json.loads(captured.out)["items"] == [{"logged_in": True}]


def test_empty_credential_is_recovered_from_a_connected_browser(credential, monkeypatch, capsys):
    def recover(timeout):
        credential.write_text('{"sessdata":"browser-cookie","saved_at":123}', encoding="utf-8")
        return True

    monkeypatch.setattr(bilibili, "reuse_browser_session", recover)
    assert cli.main(["login", "bilibili"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"] == [{"logged_in": True, "recovered_from": "local-browser"}]
    assert "browser-cookie" not in json.dumps(result)


def test_login_failure_names_the_upstream_qr_bug(credential, capsys):
    credential.write_text('{"sessdata":"","saved_at":123}', encoding="utf-8")
    assert cli.main(["login", "bilibili"]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "UPSTREAM_BROKEN"
    assert "bilibili-cli#32" in error["hint"]
    assert "bilibili.com" in error["hint"]


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

