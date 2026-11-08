"""Regression cases from the 63c272a audit; no real accounts or user processes."""
import json
import time
from unittest.mock import Mock

import pytest

from agent_reach.runtime import bridge, browser, cdp, manage, state, tools
from agent_reach.runtime.result import ReachError


def test_cleanup_failure_retains_channel_and_tools(monkeypatch):
    from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
    ch = XiaoHongShuChannel()
    state.mutate(lambda data: data["channels"].update(xiaohongshu={"added_at": state.now()}))
    monkeypatch.setattr(browser, "clear_site", Mock(side_effect=ReachError("UPSTREAM_BROKEN", "clear failed")))
    monkeypatch.setattr(tools, "prune", lambda *a: pytest.fail("pruned before cleanup succeeded"))
    with pytest.raises(ReachError, match="clear failed"):
        manage.remove(ch.name)
    assert manage.is_added(ch)


def test_cleanup_includes_www_and_remembered_subdomains_preserving_other_sites(monkeypatch):
    browser.update_state(visited_origins=["https://edith.xiaohongshu.com", "https://other.example"])
    jar = [{"name": "sid", "value": "test", "domain": ".xiaohongshu.com", "path": "/"},
           {"name": "sid", "value": "keep", "domain": "other.example", "path": "/"}]
    cleared = []
    monkeypatch.setattr(cdp, "_json", lambda _: [{"type": "page", "id": "note", "url": "https://www.xiaohongshu.com/explore/a"},
                                                {"type": "page", "id": "other", "url": "https://other.example"}])
    def call(method, params=None, **kwargs):
        if method == "Storage.getCookies":
            return {"cookies": list(jar)}
        if method == "Storage.setCookies":
            jar[:] = [c for c in jar if c["domain"] == "other.example"]
        if method == "Storage.clearDataForOrigin":
            cleared.append(params["origin"])
        return {}
    monkeypatch.setattr(cdp, "call", call)
    assert browser._clear_running_site(["xiaohongshu.com"]) == 1
    assert {"https://www.xiaohongshu.com", "https://edith.xiaohongshu.com"} <= set(cleared)
    assert not any("other.example" in url for url in cleared)
    assert browser._load_state()["visited_origins"] == ["https://other.example"]
    assert jar[0]["value"] == "keep"


def test_cleanup_never_claims_success_if_cookie_remains(monkeypatch):
    monkeypatch.setattr(cdp, "_json", lambda _: [])
    monkeypatch.setattr(cdp, "call", lambda method, *a, **k: {"cookies": [{"name": "sid", "domain": "reddit.com"}]} if method == "Storage.getCookies" else {})
    with pytest.raises(ReachError, match="verified"):
        browser._clear_running_site(["reddit.com"])


def test_boss_detail_uses_upstream_browser_adapter_without_native_http(monkeypatch):
    from agent_reach.backends import opencli
    from agent_reach.channels.boss import BossChannel
    call = Mock(return_value=[{"title": "Data Engineer", "description": "JD"}])
    monkeypatch.setattr(opencli, "opencli_call", call)
    ch = BossChannel()
    assert ch.actions[1].backends == (("boss-agent-cli", "_cli_read"), ("opencli", "_opencli_read"))
    assert ch._opencli_read(target="https://www.zhipin.com/job_detail/abc123.html", timeout=20)[0]["text"] == "JD"
    assert call.call_args.args == ("boss", ["detail", "abc123"])


def test_boss_zip_install_provenance_is_reused(monkeypatch):
    tool = tools.TOOLS["boss-agent-cli"]
    binpath = tools._private_bin(tool, "boss")
    binpath.parent.mkdir(parents=True)
    binpath.touch()
    direct = tools.tool_dir(tool.name) / "venv/lib/python3.12/site-packages/boss_agent_cli-1.0.dist-info/direct_url.json"
    direct.parent.mkdir(parents=True)
    direct.write_text(json.dumps({"url": tool.package.split(" @ ")[1], "archive_info": {}}))
    tools.record(tool.name, "1.0")
    install = Mock()
    monkeypatch.setattr(tools, "_install", install)
    tools.ensure(tool.name)
    tools.ensure(tool.name)
    install.assert_not_called()


def test_unknown_tool_and_session_are_preserved():
    from agent_reach.runtime.sessions import clear_session
    unknown = tools.tool_dir("bili-cli")
    unknown.mkdir(parents=True)
    (unknown / "notes").write_text("keep")
    session = state.root() / "sessions/bili-cli"
    session.mkdir(parents=True)
    assert not tools.remove_private("bili-cli")
    assert not clear_session("bili-cli")
    assert unknown.exists() and session.exists()


def test_uninstall_keeps_unknown_root_and_skill_files(monkeypatch):
    monkeypatch.setattr(manage, "linked_agents", lambda: {})
    manage.place_skill()
    note = manage.skill_dir() / "my-notes.md"
    note.write_text("keep")
    foreign = state.root() / "config.yaml"
    foreign.write_text("unrecorded")
    manage.uninstall()
    assert foreign.exists() and note.read_text() == "keep"
    assert not (manage.skill_dir() / "SKILL.md").exists()


def test_trusted_page_activity_extends_idle_but_script_activity_does_not(monkeypatch):
    browser.touch()
    before = browser.last_used()
    monkeypatch.setattr(cdp, "_json", lambda _: [{"type": "page", "id": "owned", "url": "https://example.com"}])
    monkeypatch.setattr(cdp, "call", lambda *a, **k: {"result": {"value": 0}})
    browser.observe_activity()
    assert browser.last_used() == before
    time.sleep(0.01)
    monkeypatch.setattr(cdp, "call", lambda *a, **k: {"result": {"value": time.time() * 1000}})
    browser.observe_activity()
    assert browser.last_used() > before
    assert browser._load_state()["visited_origins"] == ["https://example.com"]


def test_bridge_shutdown_reaps_only_our_child_even_if_others_connected(monkeypatch):
    proc = Mock(pid=123)
    proc.poll.return_value = None
    monkeypatch.setattr(bridge, "status", lambda: {"pid": 123, "profiles": [{"contextId": "reach"}]})
    assert bridge.close(proc) is None
    proc.terminate.assert_called_once()
    proc.wait.assert_called_once()
    proc.reset_mock()
    monkeypatch.setattr(bridge, "status", lambda: {"pid": 123, "profiles": [{"contextId": "other"}]})
    assert bridge.close(proc) is None
    proc.terminate.assert_called_once()
    assert bridge.close(None) is None


def test_release_gate_rejects_doctor_stale_and_wrong_source():
    from scripts.check_release_acceptance import validate
    row = {"channel": "web", "action": "search", "passed": True, "item_count": 1,
           "backend": "exa", "os": "macOS", "at": state.now(), "method": "doctor", "source_sha256": "source"}
    data = {"source_sha256": "source", "release_ready": True, "results": [row]}
    assert validate(data, {("web", "search")}, "source")
    row["method"] = "real-cli"
    assert not validate(data, {("web", "search")}, "source")
    assert validate(data, {("web", "search"), ("web", "read")}, "source")
    assert validate(data, {("web", "search")}, "changed")
    row["at"] = "2020-01-01T00:00:00Z"
    assert validate(data, {("web", "search")}, "source")


def test_gate_cannot_ignore_release_flag_pending_validation_or_invalid_time():
    from scripts.check_release_acceptance import validate
    row = {"channel": "web", "action": "search", "passed": True, "item_count": 1,
           "backend": "exa", "os": "macOS", "at": state.now(), "method": "real-cli", "source_sha256": "s"}
    data = {"source_sha256": "s", "release_ready": True, "results": [row]}
    required = {("web", "search")}
    assert not validate(data, required, "s")
    assert validate({**data, "release_ready": False}, required, "s")
    assert validate({**data, "additional_required_validation": ["Windows"]}, required, "s")
    assert validate({**data, "pending": ["web/read"]}, required, "s")
    assert validate({**data, "results": [{**row, "at": None}]}, required, "s")
    assert validate({**data, "results": [{**row, "item_count": True}]}, required, "s")

def test_gate_lets_only_listed_reasoned_waivers_through():
    from scripts.check_release_acceptance import validate
    row = {"channel": "web", "action": "search", "passed": True, "item_count": 1,
           "backend": "exa", "os": "macOS", "at": state.now(), "method": "real-cli", "source_sha256": "s"}
    required = {("web", "search"), ("reddit", "search")}
    data = {"source_sha256": "s", "release_ready": True, "results": [row]}
    assert validate(data, required, "s")  # reddit untested, not waived: blocked
    waiver = {"channel": "reddit", "action": "search", "reason": "network blocked by Reddit"}
    assert not validate({**data, "waived": [waiver]}, required, "s")
    assert validate({**data, "waived": [{**waiver, "reason": " "}]}, required, "s")  # a reason is required
    assert validate({**data, "waived": [{**waiver, "action": "nope"}]}, required, "s")  # only real actions



def test_install_and_uninstall_preserve_preexisting_unrecorded_cache(monkeypatch):
    cache = state.root() / "cache"
    cache.mkdir(parents=True)
    note = cache / "my-notes.txt"
    note.write_text("keep")
    tools.install_env()
    assert not state.owned_path(cache)
    assert state.owned_path(cache / "downloads")
    monkeypatch.setattr(manage, "linked_agents", lambda: {})
    manage.uninstall()
    assert note.read_text() == "keep"
    assert not (cache / "downloads").exists()


def test_temporary_work_is_private_recorded_and_removed_on_failure():
    from pathlib import Path

    from agent_reach.utils.paths import private_temporary_directory
    with pytest.raises(RuntimeError, match="work failed"):
        with private_temporary_directory("test-") as tmp:
            path = Path(tmp)
            assert path.parent == state.root() and state.owned_path(path)
            (path / "audio").write_bytes(b"private")
            raise RuntimeError("work failed")
    assert not path.exists() and not state.owned_path(path)


def test_existing_incompatible_bridge_is_never_restarted(monkeypatch):
    monkeypatch.setattr(bridge, "launch_spec", lambda: (["node", "daemon.js"], "1.8.7"))
    monkeypatch.setattr(bridge, "status", lambda: {"ok": True, "daemonVersion": "2.0.1", "pid": 123})
    with pytest.raises(ReachError, match="left it unchanged"):
        bridge.require_compatible()


def test_unknown_browser_files_are_not_deleted(monkeypatch):
    monkeypatch.setattr(browser, "stop", lambda: pytest.fail("unowned browser was stopped"))
    browser.browser_root().mkdir(parents=True)
    note = browser.browser_root() / "my-notes"
    note.write_text("keep")
    assert not browser.delete_profile()
    assert note.read_text() == "keep"


def test_uninstall_stops_before_deleting_files_if_browser_cannot_close(monkeypatch):
    browser.update_state(backend="cloakbrowser")
    note = state.root() / "must-keep.txt"
    note.write_text("keep")
    state.remember_path(note, "test owned artifact")
    monkeypatch.setattr(browser, "stop", lambda: False)
    with pytest.raises(ReachError, match="could not close"):
        manage.uninstall()
    assert note.read_text() == "keep" and state.exists()


def test_watcher_closes_with_its_failed_bridge(monkeypatch):
    from agent_reach.runtime import browser_watcher
    proc = Mock(pid=123)
    proc.poll.return_value = 1
    monkeypatch.setattr(bridge, "start", lambda: proc)
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(browser, "observe_activity", lambda: pytest.fail("used browser after bridge failed"))
    assert "Bridge exited" in browser_watcher.watch(poll=0.01)


def test_unrecorded_native_session_cannot_be_claimed_on_use():
    from agent_reach.runtime.sessions import session_dir
    path = state.root() / "sessions/unknown"
    path.mkdir(parents=True)
    (path / "notes").write_text("keep")
    with pytest.raises(ReachError, match="Unrecorded"):
        session_dir("unknown")
    assert not state.owned_path(path)
