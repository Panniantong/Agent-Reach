"""Bilibili must not report an empty saved credential as a completed login."""

import json

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
