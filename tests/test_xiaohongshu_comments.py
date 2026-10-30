"""Comments must be reachable through the same channel, MCP and one-sentence path."""


import pytest

from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.runtime.dispatch import run_action

NOTE = "https://www.xiaohongshu.com/explore/abc123?xsec_token=test"


@pytest.mark.parametrize("target,limit", [("https://example.com/explore/abc", 3),
                                         (NOTE, 51), (NOTE, 0)])
def test_invalid_comments_request_never_accesses_browser(monkeypatch, target, limit):
    from agent_reach.channels import xiaohongshu
    monkeypatch.setattr(xiaohongshu, "opencli_call", lambda *a, **k: pytest.fail("unexpected browser"))
    result = run_action(XiaoHongShuChannel(), "comments", {"target": target, "limit": limit},
                        only_backend="opencli")
    assert result["error"]["code"] == "BAD_INPUT"


def test_opencli_comments_keep_replies_and_explicit_scope(monkeypatch):
    from agent_reach.channels import xiaohongshu
    calls = []
    def command(site, args, **kwargs):
        calls.append(args)
        return [{"author": "A", "text": "parent", "is_reply": False},
                {"author": "B", "text": "reply", "is_reply": True, "reply_to": "A"}]
    monkeypatch.setattr(xiaohongshu, "opencli_call", command)
    result = run_action(XiaoHongShuChannel(), "comments", {"target": NOTE, "limit": 1},
                        only_backend="opencli")
    assert result["ok"]
    assert len(result["items"]) == 2  # limit constrains parents, not replies
    assert result["items"][1]["raw"]["reply_to"] == "A"
    assert all(r["raw"]["exhaustive"] is False for r in result["items"])
    assert calls == [["comments", NOTE, "--limit", "1", "--with-replies", "true"]]












def test_comments_validate_before_prepare(monkeypatch):
    from agent_reach.runtime import browser, manage, session_reuse
    for module, name in ((manage, "add"), (browser, "ensure_running"), (session_reuse, "prepare")):
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("unexpected setup"))
    result = run_action(XiaoHongShuChannel(), "comments", {"target": "invalid", "limit": 999})
    assert result["error"]["code"] == "BAD_INPUT"
