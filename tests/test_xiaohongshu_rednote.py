"""Accounts redirected to rednote.com must work through the xiaohongshu channel."""

import pytest

from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.runtime import state
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import NEED_LOGIN, RATE_LIMITED, ReachError

XHS_NOTE = "https://www.xiaohongshu.com/explore/abc123?xsec_token=test"
RED_NOTE = "https://www.rednote.com/explore/abc123?xsec_token=test"
ROW = {"title": "A title", "author": "An author", "url": RED_NOTE}


@pytest.fixture
def opencli(monkeypatch):
    """Fake OpenCLI: `replies` maps an OpenCLI site to its rows or a ReachError."""
    from agent_reach.channels import xiaohongshu

    monkeypatch.setattr(xiaohongshu, "_FALLBACK_GAP_S", 0)
    state.save({**state.load(), "channels": {"xiaohongshu": {"added_at": state.now()}}})
    calls, replies = [], {}

    def command(site, args, **kwargs):
        calls.append((site, args, kwargs.get("channel")))
        reply = replies[site]
        if isinstance(reply, ReachError):
            raise reply
        return reply

    monkeypatch.setattr(xiaohongshu, "opencli_call", command)
    return calls, replies


def _search(query="coffee"):
    return run_action(XiaoHongShuChannel(), "search", {"query": query, "limit": 1}, only_backend="opencli")


def test_search_moves_to_rednote_on_login_wall_and_remembers_it(opencli):
    calls, replies = opencli
    replies.update(xiaohongshu=ReachError(NEED_LOGIN, "login wall"), rednote=[ROW])

    result = _search()

    assert result["ok"]
    assert result["items"][0]["raw"]["site"] == "rednote"
    assert [c[0] for c in calls] == ["xiaohongshu", "rednote"]
    assert all(c[2] == "xiaohongshu" for c in calls)  # one browser binding for both domains
    assert state.load()["channels"]["xiaohongshu"]["site"] == "rednote"


def test_search_starts_on_the_remembered_site(opencli, monkeypatch):
    from agent_reach.runtime import dispatch

    monkeypatch.setattr(dispatch, "BROWSER_SEARCH_INTERVAL", 0)
    calls, replies = opencli
    replies.update(xiaohongshu=ReachError(NEED_LOGIN, "login wall"), rednote=[ROW])
    _search()
    calls.clear()

    assert _search()["ok"]
    assert [c[0] for c in calls] == ["rednote"]


def test_search_keeps_xiaohongshu_first_by_default(opencli):
    calls, replies = opencli
    replies.update(xiaohongshu=[ROW])

    assert _search()["ok"]
    assert [c[0] for c in calls] == ["xiaohongshu"]
    assert "site" not in state.load()["channels"]["xiaohongshu"]


def test_search_does_not_switch_domain_on_other_errors(opencli):
    calls, replies = opencli
    replies.update(xiaohongshu=ReachError(RATE_LIMITED, "slow down"), rednote=[ROW])

    result = _search()

    assert result["error"]["code"] == RATE_LIMITED
    assert [c[0] for c in calls] == ["xiaohongshu"]


def test_search_reports_login_when_both_domains_need_it(opencli):
    calls, replies = opencli
    replies.update(xiaohongshu=ReachError(NEED_LOGIN, "login wall"), rednote=ReachError(NEED_LOGIN, "login"))

    result = _search()

    assert result["error"]["code"] == NEED_LOGIN
    assert [c[0] for c in calls] == ["xiaohongshu", "rednote"]


def test_rednote_links_route_to_the_rednote_site(opencli):
    calls, replies = opencli
    replies.update(rednote=[{"field": "title", "value": "A title"}])

    assert XiaoHongShuChannel().can_handle(RED_NOTE)
    result = run_action(XiaoHongShuChannel(), "read", {"target": RED_NOTE}, only_backend="opencli")

    assert result["ok"]
    assert calls == [("rednote", ["note", RED_NOTE], "xiaohongshu")]
    assert result["items"][0]["url"] == RED_NOTE


def test_xiaohongshu_link_retries_on_rednote_when_login_lives_there(opencli):
    calls, replies = opencli
    replies.update(xiaohongshu=ReachError(NEED_LOGIN, "login wall"),
                   rednote=[{"author": "A", "text": "parent"}])

    result = run_action(XiaoHongShuChannel(), "comments", {"target": XHS_NOTE, "limit": 1},
                        only_backend="opencli")

    assert result["ok"]
    assert [c[0] for c in calls] == ["xiaohongshu", "rednote"]
    assert calls[1][1][1] == RED_NOTE
    assert result["items"][0]["url"] == RED_NOTE


def test_opencli_call_uses_the_channel_binding_for_another_site(monkeypatch):
    from agent_reach.backends import opencli
    from agent_reach.runtime import browser, browser_binding, run

    seen = {}
    monkeypatch.setattr(browser_binding, "environment", lambda name: seen.setdefault("binding", name) and {})
    monkeypatch.setattr(run, "run_cmd", lambda argv, **kw: seen.setdefault("argv", argv) and "[]")
    monkeypatch.setattr(browser, "save_session", lambda: None)

    opencli.opencli_call("rednote", ["search", "q"], timeout=5, channel="xiaohongshu")

    assert seen["binding"] == "xiaohongshu"
    assert seen["argv"][:2] == ["opencli", "rednote"]


def test_site_domains_include_rednote_for_session_reuse_and_cleanup(monkeypatch):
    from agent_reach.backends import opencli
    from agent_reach.runtime import browser, cdp, manage, session_reuse

    assert manage.site_domains(XiaoHongShuChannel()) == ["xiaohongshu.com", "rednote.com"]

    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(browser, "save_session", lambda: None)
    monkeypatch.setattr(browser, "connected_contexts", lambda: ["daily", "owned"])
    monkeypatch.setattr(browser, "bound_context", lambda: "owned")
    monkeypatch.setattr(
        opencli,
        "export_site_cookies",
        lambda profile, domain: (
            [{"name": "web_session", "value": "rn", "domain": ".rednote.com", "expirationDate": 9999999999}]
            if domain == "rednote.com"
            else []
        ),
    )
    calls = []
    monkeypatch.setattr(cdp, "call", lambda method, params=None: calls.append((method, params)) or {})

    result = session_reuse.prepare("xiaohongshu")

    assert result["source"] == "daily"
    assert result["copied_cookies"] == 1
    applied = next(params["cookies"] for method, params in calls if method == "Storage.setCookies")
    assert any(c["name"] == "web_session" and c["domain"] == ".rednote.com" for c in applied)
