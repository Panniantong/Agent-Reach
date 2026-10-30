"""Local credential setup, denied requests and platform challenges stay distinct."""
import json
import urllib.error

import pytest

from agent_reach.channels import github, xueqiu, youtube
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError, classify
from agent_reach.runtime.run import CommandFailed


def test_missing_gh_auth_falls_back_to_public_api_without_login(monkeypatch):
    def no_gh(*a, **k):
        raise CommandFailed("UPSTREAM_BROKEN", "gh exited", stderr="please run gh auth login")
    monkeypatch.setattr(github, "run_cmd", no_gh)
    monkeypatch.setattr(github, "http_request", lambda *a, **k: json.dumps(
        {"items": [{"full_name": "owner/repo", "html_url": "https://github.com/owner/repo"}]}
    ).encode())
    out = run_action(github.GitHubChannel(), "search", {"query": "repo", "limit": 1})
    assert out["ok"] and out["backend"] == "github-api" and len(out["items"]) == 1


@pytest.mark.parametrize("headers,code", [({}, "UPSTREAM_BROKEN"),
    ({"X-RateLimit-Remaining": "0"}, "RATE_LIMITED"), ({"Retry-After": "60"}, "RATE_LIMITED")])
def test_github_403_requires_rate_limit_evidence(monkeypatch, headers, code):
    def denied(*a, **k):
        raise urllib.error.HTTPError("https://api.github.com/test", 403, "Forbidden", headers, None)
    monkeypatch.setattr(github, "http_request", denied)
    with pytest.raises(ReachError) as exc:
        github._api_get("/test", 5)
    assert exc.value.code == code


def _http_error(code, body):
    import io
    return urllib.error.HTTPError("https://xueqiu.com/test", code, "x", {}, io.BytesIO(body))


@pytest.mark.parametrize("failure,code", [
    (json.JSONDecodeError("invalid", "", 0), "UPSTREAM_BROKEN"),
    (urllib.error.HTTPError("https://xueqiu.com/test", 403, "Forbidden", {}, None), "UPSTREAM_BROKEN"),
    (urllib.error.HTTPError("https://xueqiu.com/test", 401, "Unauthorized", {}, None), "NEED_LOGIN"),
    (_http_error(400, b'{"error_code":"400016"}'), "NEED_LOGIN"),
    (_http_error(400, b'{"error_code":"10001"}'), "UPSTREAM_BROKEN"),
    (_http_error(400, b"<html>"), "UPSTREAM_BROKEN"),
])
def test_xueqiu_only_confirmed_auth_failure_requests_login(monkeypatch, failure, code):
    def fail(*a, **k):
        raise failure
    monkeypatch.setattr(xueqiu, "_get_json", fail)
    try:
        xueqiu._xq_json("https://xueqiu.com/test")
    except Exception as exc:
        assert classify(exc).code == code
    else:
        pytest.fail("Failure was silently accepted")


def test_youtube_bot_challenge_does_not_instruct_a_login(monkeypatch):
    def blocked(*a, **k):
        raise CommandFailed("UPSTREAM_BROKEN", "YouTube rejected request", stderr="Sign in to confirm you're not a bot")
    monkeypatch.setattr(youtube, "run_cmd", blocked)
    with pytest.raises(ReachError) as exc:
        youtube._run_ytdlp([], 5)
    assert exc.value.code == "PLATFORM_BLOCKED"


def test_bilibili_subtitles_without_login_ask_for_login(monkeypatch, tmp_path):
    from agent_reach.channels import bilibili
    monkeypatch.setattr(bilibili, "sessions_root", lambda: tmp_path)
    monkeypatch.setattr(bilibili, "_reuse_subtitle_login", lambda timeout: None)
    monkeypatch.setattr(bilibili, "_bvid", lambda target, timeout: "BV1")
    monkeypatch.setattr(bilibili, "_bili_json", lambda argv, timeout: {
        "subtitle": {"available": False}, "warnings": [{"code": "subtitle_unavailable"}]})
    ch = bilibili.BilibiliChannel()
    with pytest.raises(ReachError) as exc:
        ch._cli_subtitle(target="https://www.bilibili.com/video/BV1", timeout=5)
    assert exc.value.code == "NEED_LOGIN"
    cred = tmp_path / "bili-cli" / ".bilibili-cli" / "credential.json"
    cred.parent.mkdir(parents=True)
    cred.write_text("{}")
    with pytest.raises(ReachError) as exc:
        ch._cli_subtitle(target="https://www.bilibili.com/video/BV1", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"  # logged in: a real upstream failure stays one


@pytest.mark.parametrize("cookies,code", [([], "NEED_LOGIN"), ([{"name": "li_at"}], "UPSTREAM_BROKEN")])
def test_opencli_failure_without_the_site_login_cookie_asks_for_login(monkeypatch, cookies, code):
    from agent_reach.channels import _opencli_site, linkedin
    from agent_reach.runtime import browser, cdp
    def broken(*a, **k):
        raise ReachError("UPSTREAM_BROKEN", "OpenCLI: Error: Text not found: Jobs")
    monkeypatch.setattr(_opencli_site, "opencli_call", broken)
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(cdp, "cookies", lambda domain: cookies)
    with pytest.raises(ReachError) as exc:
        linkedin.LinkedInChannel()._jobs(query="python", location=None, limit=2, timeout=5)
    assert exc.value.code == code
