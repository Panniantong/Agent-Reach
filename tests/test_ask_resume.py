"""An interrupted one-sentence request must still finish with an answer."""

import pytest

from agent_reach import mcp_server
from agent_reach.runtime import ask, flow, state
from agent_reach.runtime.result import UPSTREAM_BROKEN, ReachError


def _pause(monkeypatch):
    monkeypatch.setattr(ask, "_plan", lambda instruction: [
        {"channel": "xiaohongshu", "action": "search", "params": {"query": "VLA", "limit": 2}}])
    monkeypatch.setattr(mcp_server, "_invoke", lambda *a, **k: {
        "ok": False, "status": "needs_user_action", "channel": "xiaohongshu",
        "required_action": {"type": "login", "message": "Log in"}, "operation_id": "op_test"})
    first = ask.ask("帮我去小红书找 VLA 并总结")
    assert first["status"] == "needs_user_action"
    assert first["answer"] is None
    assert first["pending_operations"] == ["op_test"]
    assert first["required_actions"] == [{"channel": "xiaohongshu", "operation_id": "op_test",
                                          "type": "login", "message": "Log in"}]
    assert state.load()["ask_pending"]["op_test"]["instruction"] == "帮我去小红书找 VLA 并总结"


def test_resume_finishes_original_summary(monkeypatch):
    _pause(monkeypatch)
    monkeypatch.setattr(flow, "resume", lambda operation_id: {
        "ok": True, "status": "ready", "channel": "xiaohongshu", "action": "search",
        "backend": "cloakbrowser", "items": [{"title": "VLA", "url": "https://example.test"}]})
    monkeypatch.setattr(ask, "_summarize", lambda instruction, results: "VLA 摘要 [1]")
    done = ask.resume("op_test")
    assert done["status"] == "ready" and done["answer"] == "VLA 摘要 [1]"
    assert "op_test" not in state.load().get("ask_pending", {})


def test_resume_retries_model_without_requerying_site(monkeypatch):
    _pause(monkeypatch)
    calls = []
    def site(operation_id):
        calls.append("site")
        return {"ok": True, "status": "ready", "channel": "xiaohongshu",
                "items": [{"title": "VLA", "url": "https://example.test"}]}
    monkeypatch.setattr(flow, "resume", site)
    def model_failed(*args):
        raise ReachError(UPSTREAM_BROKEN, "Model unavailable")
    monkeypatch.setattr(ask, "_summarize", model_failed)
    with pytest.raises(ReachError):
        ask.resume("op_test")
    assert state.load()["ask_pending"]["op_test"].get("result", {}).get("status") == "ready"
    monkeypatch.setattr(ask, "_summarize", lambda *args: "Recovered summary")
    assert ask.resume("op_test")["answer"] == "Recovered summary"
    assert calls == ["site"]


def test_mcp_resume_uses_one_sentence_context(monkeypatch):
    monkeypatch.setattr(ask, "resume", lambda operation_id: {"ok": True, "status": "ready",
                                                              "answer": f"Summary for {operation_id}"})
    result = mcp_server._invoke("reach_resume", {"operation_id": "op_test"})
    assert result["answer"] == "Summary for op_test"


def test_partial_request_does_not_claim_every_channel_succeeded(monkeypatch):
    monkeypatch.setattr(ask, "_plan", lambda instruction: [
        {"channel": "xiaohongshu", "action": "search", "params": {"query": "VLA"}},
        {"channel": "facebook", "action": "search", "params": {"query": "VLA"}}])
    def execute(name, args):
        if args["channel"] == "xiaohongshu":
            return {"ok": True, "status": "ready", "channel": "xiaohongshu",
                    "items": [{"title": "VLA", "url": "https://example.test"}]}
        return {"ok": False, "status": "failed", "channel": "facebook",
                "error": {"code": "UPSTREAM_BROKEN", "message": "Site unavailable"}}
    monkeypatch.setattr(mcp_server, "_invoke", execute)
    monkeypatch.setattr(ask, "_summarize", lambda *args: "Partial summary")
    result = ask.ask("两个平台找 VLA")
    assert result["status"] == "partial" and result["ok"] is False
    assert result["answer"] == "Partial summary"
