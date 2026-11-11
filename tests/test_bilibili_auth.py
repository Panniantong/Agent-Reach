"""Bilibili auth regression and QR lifecycle tests; never use real credentials/network."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from agent_reach.channels import bilibili
from agent_reach.runtime import bilibili_auth as auth
from agent_reach.runtime import cli, sessions, state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: pytest.fail("unmocked auth request"))


def response(data=None, code=0, status=200, cookies=None):
    return SimpleNamespace(status_code=status, json=lambda: {"code": code, "data": data},
                           cookies=SimpleNamespace(get_dict=lambda: cookies or {}))


def saved(value=None):
    path = sessions.session_dir("bili-cli") / ".bilibili-cli" / "credential.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value or {"sessdata": "old-secret"}))
    return path


@pytest.fixture
def qr(monkeypatch):
    def request(url, **kwargs):
        if url == auth.GENERATE:
            return response({"url": "https://passport.bilibili.com/h5-app/passport/login/scan?token=qr-secret",
                             "qrcode_key": "qr-secret"})
        if url == auth.NAV:
            return response(code=-101)
        return response({"code": 86101})
    mock = Mock(side_effect=request)
    monkeypatch.setattr(auth.requests, "get", mock)
    monkeypatch.setattr(auth, "_render_qr", lambda url, path, timeout: path.write_bytes(b"test-png"))
    return mock


@pytest.mark.parametrize("value", [{}, [], None, {"sessdata": ""}, {"sessdata": None}, {"sessdata": 123}])
def test_missing_cookie_is_not_authenticated(value):
    path = saved()
    path.write_text(json.dumps(value))
    assert auth.status()["logged_in"] is False


@pytest.mark.parametrize("code", [-101, -111])
def test_expired_nonempty_cookie_is_not_authenticated(monkeypatch, code):
    path = saved()
    original = path.read_bytes()
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response(code=code))
    assert auth.status()["logged_in"] is False
    assert path.read_bytes() == original


def test_status_validates_on_every_call_and_never_exposes_account(monkeypatch):
    saved()
    get = Mock(return_value=response({"isLogin": True, "mid": 123, "uname": "private-name"}))
    monkeypatch.setattr(auth.requests, "get", get)
    assert auth.status() == auth.status() == {"logged_in": True, "verified": True, "status": "authenticated"}
    assert get.call_count == 2
    assert get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("reply,expected", [
    (response(status=429), "RATE_LIMITED"), (response(status=412), "PLATFORM_BLOCKED"),
    (response(status=403), "PLATFORM_BLOCKED"), (response(status=302), "UPSTREAM_BROKEN"),
    (response(status=500), "UPSTREAM_BROKEN"), (response(code=-352), "PLATFORM_BLOCKED"),
    (response(code=-509), "RATE_LIMITED"), (response(code=123), "UPSTREAM_BROKEN"),
    (response({}), "UPSTREAM_BROKEN"), (response({"isLogin": "yes"}), "UPSTREAM_BROKEN"),
])
def test_auth_failure_is_not_inferred_as_logout(monkeypatch, reply, expected):
    saved()
    get = Mock(return_value=reply)
    monkeypatch.setattr(auth.requests, "get", get)
    with pytest.raises(ReachError) as exc:
        auth.login()
    assert exc.value.code == expected
    assert get.call_count == 1  # no QR or fallback on network/verification errors


@pytest.mark.parametrize("error,expected", [
    (requests.Timeout("secret-token"), "TIMEOUT"),
    (requests.ConnectionError("secret-token"), "UPSTREAM_BROKEN"),
])
def test_transport_errors_never_leak_secrets_or_start_qr(monkeypatch, error, expected):
    saved()
    get = Mock(side_effect=error)
    monkeypatch.setattr(auth.requests, "get", get)
    with pytest.raises(ReachError) as exc:
        auth.login()
    assert exc.value.code == expected
    assert "secret-token" not in str(exc.value)
    assert get.call_count == 1


def test_expired_session_blocks_subtitle_fetch_and_returns_qr(qr, monkeypatch):
    saved()
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: pytest.fail("read before login"))
    result = run_action(bilibili.BilibiliChannel(), "subtitle", {"target": "BV1QmW46tEQn"})
    assert result["error"]["code"] == "NEED_LOGIN"
    login = result["error"]["details"]["login"]
    assert Path(login["qr_path"]).is_file()
    assert login["poll_command"].endswith("--poll")
    assert "qr-secret" not in json.dumps(result) and "old-secret" not in json.dumps(result)
    assert len(result["meta"]["attempts"]) == 1


def test_repeated_and_concurrent_requests_reuse_one_unexpired_qr(qr):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: auth.login(), range(2)))
    assert results[0]["qr_path"] == results[1]["qr_path"]
    assert sum(call.args[0] == auth.GENERATE for call in qr.call_args_list) == 1
    assert auth.login()["expires_at"] == results[0]["expires_at"]


def test_expired_qr_is_replaced_once_on_next_login(qr):
    first = auth.login()
    pending = auth._read(auth._files()[1])
    pending["expires_at"] = time.time() - 1
    auth._files()[1].write_text(json.dumps(pending))
    second = auth.login()
    assert second["expires_at"] >= first["expires_at"]
    assert sum(call.args[0] == auth.GENERATE for call in qr.call_args_list) == 2


@pytest.mark.parametrize("code,status", [(86101, "waiting_for_scan"), (86090, "waiting_for_confirmation"), (86038, "expired")])
def test_poll_intermediate_states(qr, monkeypatch, code, status):
    auth.login()
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response({"code": code}))
    result = auth.login(poll=True)
    assert result["logged_in"] is False and result["status"] == status
    assert not auth._files()[0].exists()
    if code == 86038:
        assert not auth._files()[1].exists() and not auth._files()[2].exists()


def test_poll_without_pending_login_does_not_generate_qr():
    assert auth.login(poll=True)["status"] == "expired"


@pytest.mark.parametrize("via", ["cookies", "query", "both"])
@pytest.mark.parametrize("delayed_poll", [False, True])
def test_confirmed_qr_validates_and_saves_credentials(qr, monkeypatch, via, delayed_poll):
    auth.login()
    if delayed_poll:
        pending = auth._read(auth._files()[1])
        pending["expires_at"] = time.time() - 1
        auth._files()[1].write_text(json.dumps(pending))
    secret = {"SESSDATA": "new-secret", "bili_jct": "csrf-secret", "DedeUserID": "123"}
    def request(url, **kwargs):
        if url == auth.POLL:
            return response({"code": 0, "refresh_token": "refresh-secret",
                             "url": "https://www.bilibili.com/?SESSDATA=query-secret&bili_jct=csrf-secret" if via != "cookies" else ""},
                            cookies=secret if via != "query" else {})
        assert kwargs["cookies"]["SESSDATA"] == ("query-secret" if via == "query" else "new-secret")
        return response({"isLogin": True})
    monkeypatch.setattr(auth.requests, "get", request)
    result = auth.login(poll=True)
    assert result["logged_in"] is True and result["verified"] is True
    credential_file, pending_file, image_file = auth._files()
    assert json.loads(credential_file.read_text())["sessdata"] == ("query-secret" if via == "query" else "new-secret")
    assert not pending_file.exists() and not image_file.exists()
    assert "secret" not in json.dumps(result)
    assert state.load()["session_reuse"]["bilibili"]["verified"] is True
    if os.name != "nt":
        assert credential_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("cookie,nav", [({}, True), ({"SESSDATA": "new-secret"}, False)])
def test_confirmation_without_valid_session_preserves_saved_credentials(qr, monkeypatch, cookie, nav):
    old = saved()
    original = old.read_bytes()
    auth.login()
    def request(url, **kwargs):
        if url == auth.NAV:
            return response({"isLogin": nav and kwargs["cookies"]["SESSDATA"] != "old-secret"})
        return response({"code": 0, "url": ""}, cookies=cookie)
    monkeypatch.setattr(auth.requests, "get", request)
    with pytest.raises(ReachError) as exc:
        auth.login(poll=True)
    assert exc.value.code == "NEED_LOGIN"
    assert old.read_bytes() == original


def test_logged_in_session_needs_no_qr_or_browser(monkeypatch):
    saved()
    get = Mock(return_value=response({"isLogin": True}))
    monkeypatch.setattr(auth.requests, "get", get)
    assert auth.login()["logged_in"] is True
    assert [c.args[0] for c in get.call_args_list] == [auth.NAV]


def test_explicit_check_does_not_start_login(capsys):
    assert cli.main(["login", "bilibili", "--check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"][0]["logged_in"] is False
    assert not auth._files()[1].exists()


def test_channels_reports_presence_separately_from_verification(capsys):
    saved()
    assert cli.main(["channels"]) == 0
    result = json.loads(capsys.readouterr().out)
    login = next(c for c in result["channels"] if c["name"] == "bilibili")["login"]
    assert login["logged_in"] is None and login["saved_session"] is True


@pytest.mark.parametrize("argv", [
    ["bilibili", "read", "BV1QmW46tEQn", "--no-login"],
    ["read", "https://www.bilibili.com/video/BV1QmW46tEQn", "--no-login"],
])
def test_explicit_no_login_preview_never_checks_or_generates_qr(monkeypatch, capsys, argv):
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: {"video": {"title": "public title"}})
    assert cli.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["items"][0]["title"] == "public title"
    assert not auth._files()[1].exists()


def test_boolean_string_cannot_silently_enable_anonymous_mode():
    result = run_action(bilibili.BilibiliChannel(), "read", {"target": "BV1QmW46tEQn", "no_login": "false"})
    assert result["error"]["code"] == "BAD_INPUT"


@pytest.mark.parametrize("subtitle,warnings,expected", [
    ({"available": False}, [], "NOT_FOUND"),
    ({"available": False}, [{"code": "subtitle_unavailable"}], "UPSTREAM_BROKEN"),
    (None, [], "UPSTREAM_BROKEN"), ({}, [], "UPSTREAM_BROKEN"),
])
def test_verified_login_still_distinguishes_missing_subtitles_from_failure(monkeypatch, subtitle, warnings, expected):
    verify = Mock()
    monkeypatch.setattr(auth, "require_login", verify)
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: {"subtitle": subtitle, "warnings": warnings})
    with pytest.raises(ReachError) as exc:
        bilibili.BilibiliChannel()._cli_subtitle(target="BV1QmW46tEQn", timeout=5)
    assert exc.value.code == expected
    assert verify.call_count == (1 if subtitle is None or subtitle == {} else 2)


def test_session_expiring_during_subtitle_request_is_not_no_subtitles(monkeypatch):
    monkeypatch.setattr(auth, "require_login", Mock(side_effect=[None, ReachError("NEED_LOGIN", "expired")]))
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: {"subtitle": {"available": False}})
    with pytest.raises(ReachError) as exc:
        bilibili.BilibiliChannel()._cli_subtitle(target="BV1QmW46tEQn", timeout=5)
    assert exc.value.code == "NEED_LOGIN"


def test_valid_subtitle_returns_after_verification(monkeypatch):
    verify = Mock()
    monkeypatch.setattr(auth, "require_login", verify)
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: {"subtitle": {"available": True, "text": "actual transcript"}})
    assert bilibili.BilibiliChannel()._cli_subtitle(target="BV1QmW46tEQn", timeout=5)[0]["text"] == "actual transcript"
    verify.assert_called_once()


def test_explicit_import_is_validated_before_replacing_session(monkeypatch):
    old = saved()
    original = old.read_bytes()
    native = auth.home_dir() / ".bilibili-cli" / "credential.json"
    native.parent.mkdir()
    native.write_text('{"sessdata":"import-secret"}')
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response(code=-101))
    with pytest.raises(ReachError):
        auth.import_existing()
    assert old.read_bytes() == original
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response({"isLogin": True}))
    assert auth.import_existing()["logged_in"] is True
    assert json.loads(old.read_text())["sessdata"] == "import-secret"


def test_logout_removes_pending_login_and_cannot_be_revived(qr, capsys):
    auth.login()
    assert cli.main(["logout", "bilibili"]) == 0
    capsys.readouterr()
    assert not auth._files()[1].exists()
    assert auth.login(poll=True)["status"] == "expired"


def test_login_cli_returns_one_json_line_with_qr(qr, capsys):
    assert cli.main(["login", "bilibili"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["items"][0]["status"] == "waiting_for_scan"
    assert "qr-secret" not in lines[0]


@pytest.mark.parametrize("args", [["--poll", "--check"], ["--sync"], ["--import-existing", "--poll"]])
def test_conflicting_login_modes_are_rejected(args, capsys):
    assert cli.main(["login", "bilibili", *args]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BAD_INPUT"


def test_unexpected_qr_destination_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response({"url": "https://evil.test/qr", "qrcode_key": "secret"}))
    with pytest.raises(ReachError) as exc:
        auth.login()
    assert exc.value.code == "UPSTREAM_BROKEN"
    assert not auth._files()[1].exists()


@pytest.mark.parametrize("body", [None, [], "bad", {"code": 0, "data": []}])
def test_malformed_auth_payload_is_not_logout(monkeypatch, body):
    saved()
    reply = response()
    reply.json = lambda: body
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: reply)
    with pytest.raises(ReachError) as exc:
        auth.status()
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_slow_auth_response_cannot_save_after_deadline(monkeypatch):
    original = saved().read_bytes()
    def slow(*args, **kwargs):
        time.sleep(0.03)
        return response({"isLogin": True})
    monkeypatch.setattr(auth.requests, "get", slow)
    with pytest.raises(ReachError) as exc:
        auth.login(timeout=0.01)
    assert exc.value.code == "TIMEOUT"
    assert auth._files()[0].read_bytes() == original
    assert not auth._files()[1].exists()


def test_render_error_does_not_expose_qr_token(monkeypatch):
    from agent_reach.runtime import tools
    monkeypatch.setattr(tools, "resolve", lambda name: "/fake/bin/bili")
    def fail(*a, **k):
        raise RuntimeError("secret-qr-token")
    monkeypatch.setattr(auth, "run_cmd", fail)
    with pytest.raises(ReachError) as exc:
        auth._render_qr("secret-qr-token", sessions.session_dir("bili-cli") / "qr.png", 5)
    assert "secret-qr-token" not in str(exc.value)


def test_auth_failure_after_preflight_gets_a_login_handoff(monkeypatch):
    check = Mock(side_effect=[None, ReachError("NEED_LOGIN", "expired", details={"login": {"qr_path": "/test/qr.png"}})])
    monkeypatch.setattr(auth, "require_login", check)
    def fail(*a, **k):
        raise ReachError("NEED_LOGIN", "session expired in upstream")
    monkeypatch.setattr(bilibili, "_bili_json", fail)
    with pytest.raises(ReachError) as exc:
        bilibili.BilibiliChannel()._cli_read(target="BV1QmW46tEQn", timeout=5)
    assert exc.value.details["login"]["qr_path"] == "/test/qr.png"
    assert check.call_count == 2


def test_preview_upstream_auth_error_does_not_generate_qr(monkeypatch):
    monkeypatch.setattr(auth, "require_login", lambda *a: pytest.fail("preview attempted login"))
    def fail(*a, **k):
        raise ReachError("NEED_LOGIN", "upstream requires login")
    monkeypatch.setattr(bilibili, "_bili_json", fail)
    with pytest.raises(ReachError) as exc:
        bilibili.BilibiliChannel()._cli_read(target="BV1QmW46tEQn", timeout=5, no_login=True)
    assert exc.value.code == "NEED_LOGIN"


@pytest.mark.skipif(os.name == "nt", reason="symlink privileges differ on Windows")
def test_qr_symlink_is_rejected_without_touching_target(qr, tmp_path):
    from agent_reach.utils.paths import PrivatePathError
    sessions.session_dir("bili-cli")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"preserve")
    auth._files()[2].symlink_to(outside)
    with pytest.raises(PrivatePathError):
        auth.login()
    assert outside.read_bytes() == b"preserve"


def test_poll_unrecognized_state_is_not_a_success(qr, monkeypatch):
    auth.login()
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response({"code": 999}))
    with pytest.raises(ReachError) as exc:
        auth.login(poll=True)
    assert exc.value.code == "UPSTREAM_BROKEN"
    assert not auth._files()[0].exists()


@pytest.mark.parametrize("action,params", [("read", {"target": "BV1QmW46tEQn"}), ("search", {"query": "Python"}), ("hot", {})])
def test_default_content_actions_stop_before_reading_when_logged_out(qr, monkeypatch, action, params):
    monkeypatch.setattr(bilibili, "_bili_json", lambda *a: pytest.fail("content before auth"))
    result = run_action(bilibili.BilibiliChannel(), action, params)
    assert result["error"]["code"] == "NEED_LOGIN"
    assert result["error"]["details"]["login"]["qr_path"]


@pytest.mark.parametrize("host", ["passport.bilibili.com", "account.bilibili.com"])
def test_supported_official_qr_destinations(monkeypatch, host):
    monkeypatch.setattr(auth.requests, "get", lambda *a, **k: response({"url": f"https://{host}/scan?token=secret", "qrcode_key": "secret"}))
    monkeypatch.setattr(auth, "_render_qr", lambda url, path, timeout: path.write_bytes(b"png"))
    assert auth.login()["status"] == "waiting_for_scan"


def test_qr_keys_are_private_and_never_in_command_arguments(monkeypatch):
    from agent_reach.runtime import tools
    monkeypatch.setattr(tools, "resolve", lambda name: "/fake/bin/bili")
    def render(argv, **kwargs):
        assert "secret-token" not in repr(argv)
        assert kwargs["input_data"].endswith("secret-token")
        Path(argv[-1]).write_bytes(b"png")
    monkeypatch.setattr(auth, "run_cmd", render)
    path = sessions.session_dir("bili-cli") / "qr.png"
    auth._render_qr("https://passport.bilibili.com/scan?token=secret-token", path, 5)
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_login_entrypoint_obeys_authentication_rate_limit(monkeypatch):
    saved()
    get = Mock(return_value=response(status=429))
    monkeypatch.setattr(auth.requests, "get", get)
    for _ in range(2):
        with pytest.raises(ReachError) as exc:
            auth.login()
        assert exc.value.code == "RATE_LIMITED"
    assert get.call_count == 1


def test_no_login_mode_does_not_apply_to_other_channels(capsys):
    assert cli.main(["read", "https://example.com", "--no-login"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BAD_INPUT"
