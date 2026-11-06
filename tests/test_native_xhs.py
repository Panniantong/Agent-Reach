"""Native XiaoHongShu backend: item mapping, error codes, cookie and throttle budget."""

import ast
import contextlib
import inspect
import io
import json
import os
import re
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.native import xhs
from agent_reach.native._items import map_xhs_error
from agent_reach.runtime import dispatch
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE = "https://www.xiaohongshu.com/explore/abc123?xsec_token=test&xsec_source=pc_search"

SEARCH_ROWS = [
    {
        "id": "abc123",
        "xsec_token": "test",
        "url": NOTE,
        "title": "A title",
        "nickname": "An author",
        "likes": "7",
        "collects": "2",
        "comments": "1",
        "cover_url": "https://img.example/cover.jpg",
    },
    {
        "id": "def456",
        "xsec_token": "other",
        "url": "https://www.xiaohongshu.com/explore/def456?xsec_token=other",
        "title": "Another title",
        "nickname": "Another author",
        "likes": "1",
        "collects": "0",
        "comments": "0",
        "cover_url": "",
    },
]


def fake_run_py(monkeypatch, payload):
    calls = []

    def run(code, *, timeout, extra_env=None):
        calls.append({"code": code, "timeout": timeout, "env": dict(extra_env or {})})
        return payload if isinstance(payload, str) else json.dumps(payload)

    monkeypatch.setattr(xhs, "run_py", run)
    return calls


def allow_site_backends(monkeypatch):
    """Skip the public-web-first branch so the full backend chain is deterministic."""
    monkeypatch.setattr(dispatch, "_channel_added", lambda channel: True)


# ── happy paths ──────────────────────────────────────────────────────────────


def test_search_maps_native_payload_through_the_channel(monkeypatch):
    calls = fake_run_py(monkeypatch, {"success": True, "msg": "", "code": "", "notes": SEARCH_ROWS})

    result = run_action(
        XiaoHongShuChannel(), "search", {"query": "咖啡", "limit": 2}, only_backend="native"
    )

    assert result["ok"]
    assert result["backend"] == "native"
    assert len(result["items"]) == 2
    assert result["items"][0]["title"] == "A title"
    assert result["items"][0]["url"] == NOTE
    assert result["items"][0]["author"] == "An author"
    assert calls[0]["env"]["XHS_QUERY"] == "咖啡"
    assert calls[0]["env"]["XHS_LIMIT"] == "2"
    assert calls[0]["env"]["XHS_SORT"] == "0"


def test_search_passes_the_legacy_cli_sort(monkeypatch):
    calls = fake_run_py(monkeypatch, {"success": True, "msg": "", "code": "", "notes": SEARCH_ROWS})
    xhs.search(query="咖啡", limit=1, timeout=5, sort=2)
    assert calls[0]["env"]["XHS_SORT"] == "2"


@pytest.mark.parametrize("publish_time", [1700000000, 1700000000000],
                         ids=["seconds", "milliseconds"])
def test_read_maps_detail_payload(monkeypatch, publish_time):
    fake_run_py(monkeypatch, {
        "success": True,
        "msg": "",
        "code": "",
        "note": {
            "id": "abc123",
            "title": "A title",
            "desc": "The body",
            "nickname": "An author",
            "publish_time": publish_time,
            "likes": "7",
        },
    })

    result = run_action(XiaoHongShuChannel(), "read", {"target": NOTE}, only_backend="native")

    assert result["ok"]
    assert result["backend"] == "native"
    item = result["items"][0]
    assert item["title"] == "A title"
    assert item["text"] == "The body"
    assert item["author"] == "An author"
    assert item["url"] == NOTE
    assert item["published_at"] == "2023-11-14T22:13:20Z"


def test_comments_limits_top_level_comments_and_keeps_replies(monkeypatch):
    calls = fake_run_py(monkeypatch, {
        "success": True,
        "msg": "",
        "code": "",
        "comments": [
            {
                "nickname": "A",
                "content": "parent",
                "likes": "2",
                "ip": "上海",
                "sub_count": 1,
                "sub": [{"nickname": "B", "content": "reply", "likes": "1"}],
            },
            {"nickname": "C", "content": "second parent", "sub": []},
        ],
    })

    result = run_action(
        XiaoHongShuChannel(), "comments", {"target": NOTE, "limit": 1}, only_backend="native"
    )

    assert result["ok"]
    assert len(result["items"]) == 1  # limit caps parents; replies travel inside raw
    item = result["items"][0]
    assert item["author"] == "A"
    assert item["text"] == "parent"
    assert item["url"] == NOTE
    assert item["raw"]["sub"][0]["content"] == "reply"
    assert item["raw"]["exhaustive"] is False
    assert calls[0]["env"]["XHS_COMMENT_LIMIT"] == "1"


@pytest.mark.parametrize(
    "call,payload",
    [
        ("search", {"success": True, "msg": "", "code": ""}),
        ("read", {"success": True, "msg": "", "code": ""}),
        ("comments", {"success": True, "msg": "", "code": ""}),
    ],
)
def test_success_payload_with_a_broken_shape_is_upstream_broken(monkeypatch, call, payload):
    fake_run_py(monkeypatch, payload)
    with pytest.raises(ReachError) as exc:
        if call == "search":
            xhs.search(query="咖啡", limit=1, timeout=5)
        elif call == "read":
            xhs.read(target=NOTE, timeout=5)
        else:
            xhs.comments(target=NOTE, limit=1, timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_empty_native_search_result_is_ok(monkeypatch):
    fake_run_py(monkeypatch, {"success": True, "msg": "", "code": "", "notes": []})
    assert xhs.search(query="咖啡", limit=1, timeout=5) == []


# ── error-code routing ───────────────────────────────────────────────────────


def test_transient_native_failure_falls_back_to_opencli(monkeypatch):
    from agent_reach.channels import xiaohongshu

    fake_run_py(monkeypatch, {"success": False, "msg": "temporary upstream failure", "code": ""})
    allow_site_backends(monkeypatch)
    opencli_calls = []

    def opencli(site, args, **kwargs):
        opencli_calls.append(args)
        return [{"title": "fallback", "url": NOTE, "author": "opencli author"}]

    monkeypatch.setattr(xiaohongshu, "opencli_call", opencli)

    result = run_action(XiaoHongShuChannel(), "search", {"query": "咖啡", "limit": 2})

    assert result["ok"]
    assert result["backend"] == "opencli"
    assert [row["backend"] for row in result["meta"]["attempts"]] == ["native", "opencli"]
    assert opencli_calls == [["search", "咖啡", "--limit", "2"]]


def test_search_risk_code_blocks_the_whole_chain(monkeypatch):
    from agent_reach.channels import xiaohongshu

    fake_run_py(monkeypatch, {"success": False, "msg": "访问频繁", "code": "300031"})
    allow_site_backends(monkeypatch)
    monkeypatch.setattr(
        xiaohongshu, "opencli_call", lambda *a, **k: pytest.fail("opencli must not run")
    )

    result = run_action(XiaoHongShuChannel(), "search", {"query": "咖啡", "limit": 2})

    assert not result["ok"]
    assert result["error"]["code"] == "PLATFORM_BLOCKED"
    assert [row["backend"] for row in result["meta"]["attempts"]] == ["native"]


def test_read_risk_code_means_deleted_note_not_platform_block(monkeypatch):
    fake_run_py(monkeypatch, {"success": False, "msg": "笔记已删除", "code": "300031"})

    result = run_action(XiaoHongShuChannel(), "read", {"target": NOTE}, only_backend="native")

    assert not result["ok"]
    assert result["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "action,payload,code",
    [
        ("search", {"success": False, "code": "300031", "msg": ""}, "PLATFORM_BLOCKED"),
        ("search", {"success": False, "code": "", "msg": "验证码"}, "PLATFORM_BLOCKED"),
        ("search", {"success": False, "code": "300035", "msg": ""}, "PLATFORM_BLOCKED"),
        ("read", {"success": False, "code": "300031", "msg": "已删除"}, "NOT_FOUND"),
        ("read", {"success": False, "code": "300031", "msg": "风控"}, "NOT_FOUND"),
        ("read", {"success": False, "code": "", "msg": "笔记不存在"}, "NOT_FOUND"),
        ("comments", {"success": False, "code": "300031", "msg": "设私"}, "NOT_FOUND"),
        ("read", {"success": False, "code": "", "msg": "请先登录"}, "NEED_LOGIN"),
        ("search", {"success": False, "code": "", "msg": "boom"}, "UPSTREAM_BROKEN"),
        ("search", {"success": True, "code": "", "msg": ""}, None),
        ("search", {"success": True, "code": "0", "msg": "成功"}, None),
        ("search", {"success": True, "code": "300031", "msg": "风控"}, None),
        ("read", {"success": True, "code": "0", "msg": "登录成功"}, None),
        ("read", {"success": True, "code": "300031", "msg": "已删除"}, "NOT_FOUND"),
        ("search", {"code": "", "msg": "", "notes": []}, "UPSTREAM_BROKEN"),
        ("search", {"success": False, "code": "", "msg": ""}, "UPSTREAM_BROKEN"),
    ],
)
def test_map_xhs_error_is_action_sensitive(action, payload, code):
    error = map_xhs_error(action, payload)
    assert (error.code if error else None) == code


def test_error_message_scrubs_xsec_tokens_and_url_credentials():
    payload = {
        "success": False,
        "code": "",
        "msg": "failed https://user:pass@www.xiaohongshu.com/explore/x"
               "?xsec_token=SECRET&xsec_source=pc_search",
    }
    error = map_xhs_error("search", payload)

    assert "SECRET" not in error.message
    assert "xsec_token=***" in error.message
    assert "user:pass" not in error.message


# ── local setup and input validation ─────────────────────────────────────────


def test_missing_cookie_is_need_setup_and_the_chain_continues(monkeypatch):
    from agent_reach.channels import xiaohongshu

    monkeypatch.delenv("XHS_COOKIE", raising=False)
    with pytest.raises(ReachError) as exc:
        xhs.search(query="咖啡", limit=1, timeout=5)
    assert exc.value.code == "NEED_SETUP"

    allow_site_backends(monkeypatch)
    monkeypatch.setattr(
        xiaohongshu,
        "opencli_call",
        lambda *a, **k: [{"title": "fallback", "url": NOTE, "author": "opencli author"}],
    )

    result = run_action(XiaoHongShuChannel(), "search", {"query": "咖啡", "limit": 1})

    assert result["ok"]
    assert result["backend"] == "opencli"
    assert result["meta"]["attempts"][0]["backend"] == "native"
    assert result["meta"]["attempts"][0]["result"] == "NEED_SETUP"
    assert result["meta"]["attempts"][1]["backend"] == "opencli"


def test_invalid_input_never_starts_the_subprocess(monkeypatch):
    monkeypatch.setattr(xhs, "run_py", lambda *a, **k: pytest.fail("unexpected subprocess"))

    with pytest.raises(ReachError) as read_exc:
        xhs.read(target="https://www.xiaohongshu.com/explore/abc123", timeout=5)
    assert read_exc.value.code == "BAD_INPUT"

    with pytest.raises(ReachError) as path_exc:
        xhs.read(target="https://www.xiaohongshu.com/foo?xsec_token=test", timeout=5)
    assert path_exc.value.code == "BAD_INPUT"

    with pytest.raises(ReachError) as comments_exc:
        xhs.comments(target=NOTE, limit=51, timeout=5)
    assert comments_exc.value.code == "BAD_INPUT"

    with pytest.raises(ReachError) as search_exc:
        xhs.search(query="咖啡", limit=0, timeout=5)
    assert search_exc.value.code == "BAD_INPUT"


def test_missing_interpreter_is_need_setup_without_waiting_for_throttle(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_COOKIE", "test-cookie")
    monkeypatch.setattr(xhs, "_interpreter", lambda: tmp_path / "missing-python")
    monkeypatch.setattr(xhs, "_throttle", lambda *a: pytest.fail("must fail before throttling"))

    with pytest.raises(ReachError) as exc:
        xhs.run_py("pass", timeout=5)
    assert exc.value.code == "NEED_SETUP"


def test_windows_default_interpreter_uses_scripts(monkeypatch):
    monkeypatch.setattr(xhs, "_WINDOWS", True)
    monkeypatch.delenv("XHS_PYTHON", raising=False)

    path = xhs._interpreter()

    assert path.parent.name == "Scripts"
    assert path.name == "python.exe"


def test_short_link_resolution_failure_is_not_terminal(monkeypatch):
    monkeypatch.setattr(xhs, "run_py", lambda *a, **k: pytest.fail("unexpected subprocess"))
    with pytest.raises(ReachError) as exc:
        xhs.read(target="https://xhslink.com/a/1", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_short_link_read_resolves_and_stays_on_native(monkeypatch):
    allow_site_backends(monkeypatch)
    resolved = []
    monkeypatch.setattr(
        xhs, "_resolve_short_link", lambda url, timeout: resolved.append(url) or NOTE
    )
    fake_run_py(monkeypatch, {"success": True, "msg": "", "code": "", "note": {"title": "T"}})

    result = run_action(
        XiaoHongShuChannel(), "read", {"target": "https://xhslink.com/a/1"}
    )

    assert result["ok"]
    assert result["backend"] == "native"
    assert result["items"][0]["title"] == "T"
    assert resolved == ["https://xhslink.com/a/1"]


def test_note_url_upgrades_http_and_strips_a_trailing_slash():
    url = xhs._note_url(
        "http://www.xiaohongshu.com/discovery/item/abc123/?xsec_token=test", 5
    )
    assert url == "https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=test"


def test_comments_require_an_xsec_token():
    with pytest.raises(ReachError) as exc:
        xhs._comment_url("https://www.xiaohongshu.com/explore/abc123", 5)
    assert exc.value.code == "BAD_INPUT"


def test_comments_without_a_token_stops_the_chain_before_opencli(monkeypatch):
    from agent_reach.channels import xiaohongshu

    allow_site_backends(monkeypatch)
    monkeypatch.setattr(
        xiaohongshu, "opencli_call", lambda *a, **k: pytest.fail("opencli must not run")
    )

    result = run_action(
        XiaoHongShuChannel(),
        "comments",
        {"target": "https://www.xiaohongshu.com/explore/abc123", "limit": 1},
    )

    assert result["error"]["code"] == "BAD_INPUT"


# ── configuration and setup diagnostics ─────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="symlink fixture")
def test_spider_dir_keeps_the_external_checkout_behind_a_symlinked_python(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_SPIDER_DIR", raising=False)
    checkout = tmp_path / "Spider_XHS"
    (checkout / "apis").mkdir(parents=True)
    (checkout / ".venv" / "bin").mkdir(parents=True)
    interpreter = checkout / ".venv" / "bin" / "python"
    interpreter.symlink_to(sys.executable)

    assert xhs._spider_dir(interpreter) == checkout


def test_configured_proxy_overrides_inherited_lowercase_and_all_proxy(monkeypatch):
    monkeypatch.setenv("PROXY", "http://configured:8080")
    monkeypatch.setenv("http_proxy", "http://inherited:1")
    monkeypatch.setenv("ALL_PROXY", "socks5://inherited:2")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")

    env = xhs._proxy_env()

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert env[key] == "http://configured:8080"
    assert env["no_proxy"] == env["NO_PROXY"] == "localhost,127.0.0.1"


def test_setup_problems_reports_native_prerequisites_and_labels_the_fallback(monkeypatch):
    from agent_reach.runtime import browser_binding

    monkeypatch.delenv("XHS_COOKIE", raising=False)
    monkeypatch.setattr(xhs, "_interpreter", lambda: Path("/nonexistent/xhs-python"))
    monkeypatch.setattr(
        browser_binding, "setup_problems", lambda channel: ["browser is not connected"]
    )

    problems = XiaoHongShuChannel().setup_problems()

    assert any("xhs_cookie" in problem for problem in problems)
    assert any("xhs_python" in problem for problem in problems)
    assert "opencli fallback: browser is not connected" in problems


def test_setup_problems_reports_a_missing_spider_xhs_checkout(monkeypatch):
    from agent_reach.runtime import browser_binding

    monkeypatch.setenv("XHS_COOKIE", "cookie")
    monkeypatch.setattr(xhs, "_interpreter", lambda: Path(sys.executable))
    monkeypatch.setattr(xhs, "_spider_dir", lambda interpreter: Path("/nonexistent/spider"))
    monkeypatch.setattr(browser_binding, "setup_problems", lambda channel: [])

    problems = XiaoHongShuChannel().setup_problems()

    assert any("Spider_XHS checkout not found" in problem for problem in problems)


# ── throttle ─────────────────────────────────────────────────────────────────


def test_throttle_wait_is_subtracted_from_the_run_cmd_timeout(monkeypatch):
    monkeypatch.setenv("XHS_COOKIE", "test-cookie")
    seen = []
    captured = {}

    def throttle(remaining=None):
        seen.append(remaining)
        time.sleep(0.2)

    def run_cmd(argv, *, timeout, env=None, cwd=None, label=None):
        captured["timeout"] = timeout
        captured["env"] = dict(env or {})
        return json.dumps({"success": True, "msg": "", "code": "", "notes": []})

    monkeypatch.setattr(xhs, "_throttle", throttle)
    monkeypatch.setattr(xhs, "run_cmd", run_cmd)
    monkeypatch.setattr(xhs, "_interpreter", lambda: Path(sys.executable))

    xhs.run_py("pass", timeout=5)

    assert seen == [5]
    assert captured["timeout"] <= 5 - 0.2 + 0.1
    assert captured["timeout"] > 4
    assert captured["env"]["XHS_COOKIE_INTERNAL"] == "test-cookie"


def test_throttle_gives_up_instead_of_sleeping_past_the_budget(monkeypatch, tmp_path):
    lock = tmp_path / ".cache" / "xhs_api.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(str(time.time()))
    monkeypatch.setenv("XHS_MIN_INTERVAL", "60")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XHS_LOCK_FILE", str(lock))

    started = time.monotonic()
    with pytest.raises(ReachError) as exc:
        xhs._throttle(1)
    assert exc.value.code == "TIMEOUT"
    assert time.monotonic() - started < 1.0


def test_throttle_lock_wait_stops_at_the_remaining_budget(monkeypatch, tmp_path):
    fcntl = pytest.importorskip("fcntl")
    lock = tmp_path / "xhs.lock"
    monkeypatch.setenv("XHS_LOCK_FILE", str(lock))
    monkeypatch.setenv("XHS_MIN_INTERVAL", "1")

    holder = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        started = time.monotonic()
        with pytest.raises(ReachError) as exc:
            xhs._throttle(0.2)
        assert exc.value.code == "TIMEOUT"
        assert time.monotonic() - started < 1.0
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)


def test_fcntl_is_imported_lazily_and_windows_uses_a_process_lock(monkeypatch, tmp_path):
    tree = ast.parse(inspect.getsource(xhs))
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name != "fcntl" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "fcntl"

    monkeypatch.setattr(xhs, "_WINDOWS", True)
    monkeypatch.setenv("XHS_MIN_INTERVAL", "0.05")
    monkeypatch.setenv("XHS_LOCK_FILE", str(tmp_path / "xhs.lock"))
    xhs._throttle(5)
    started = time.monotonic()
    xhs._throttle(5)
    assert time.monotonic() - started >= 0.02


# ── embedded snippets and legacy CLI ────────────────────────────────────────


def _env_keys(code: str) -> set[str]:
    keys = set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z0-9_]+)["\']', code))
    keys |= set(re.findall(r'os\.environ\[\s*["\']([A-Z0-9_]+)["\']\s*\]', code))
    return keys


def test_embedded_snippets_compile_and_declare_their_env_contract():
    for code in (xhs.SEARCH_CODE, xhs.DETAIL_CODE, xhs.COMMENTS_CODE):
        compile(code, "<xhs-snippet>", "exec")

    assert _env_keys(xhs.SEARCH_CODE) == {
        "XHS_COOKIE_INTERNAL", "XHS_QUERY", "XHS_LIMIT", "XHS_SORT",
    }
    assert _env_keys(xhs.DETAIL_CODE) == {"XHS_COOKIE_INTERNAL", "XHS_NOTE_URL"}
    assert _env_keys(xhs.COMMENTS_CODE) == {
        "XHS_COOKIE_INTERNAL", "XHS_NOTE_URL", "XHS_COMMENT_LIMIT", "XHS_INTERVAL",
    }


def _install_snippet_stubs(monkeypatch, api_class):
    names = (
        "dotenv",
        "xhs_utils",
        "xhs_utils.xhs_pc",
        "xhs_utils.xhs_pc.params",
        "apis",
        "apis.xhs_pc_apis",
    )
    modules = {name: types.ModuleType(name) for name in names}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    modules["xhs_utils"].xhs_pc = modules["xhs_utils.xhs_pc"]
    modules["xhs_utils.xhs_pc"].params = modules["xhs_utils.xhs_pc.params"]
    modules["apis"].xhs_pc_apis = modules["apis.xhs_pc_apis"]
    modules["dotenv"].load_dotenv = lambda *a, **k: None
    modules["xhs_utils.xhs_pc"].XHSPcAuth = type(
        "XHSPcAuth", (), {"from_cookie": classmethod(lambda cls, cookie: object())}
    )
    modules["xhs_utils.xhs_pc.params"].generate_search_id = lambda root=None: root or "root"
    modules["apis.xhs_pc_apis"].XHS_Apis = api_class
    return modules


def _exec_snippet(code):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(code, "<xhs-snippet>", "exec"), {"__name__": "__main__"})
    return json.loads(output.getvalue())


def test_search_snippet_dedupes_rows_and_reuses_the_root_search_id(monkeypatch):
    class Api:
        instances = []

        def __init__(self, auth):
            self.calls = []
            Api.instances.append(self)

        def bootstrap(self):
            return self

        def search_note(self, query, page, sort, search_id=None):
            self.calls.append((query, page, sort, search_id))
            rows = [
                {"model_type": "note", "id": "one", "xsec_token": "tok",
                 "note_card": {"display_title": "T"}},
                {"model_type": "note", "id": "one", "xsec_token": "tok", "note_card": {}},
                {"model_type": "note", "id": None, "xsec_token": "tok", "note_card": {}},
                {"model_type": "note", "id": "two", "xsec_token": "", "note_card": {}},
                {"model_type": "video", "id": "v", "xsec_token": "tok", "note_card": {}},
            ]
            return True, "", {"code": "0", "data": {"items": rows, "has_more": False}}

    _install_snippet_stubs(monkeypatch, Api)
    monkeypatch.setenv("XHS_COOKIE_INTERNAL", "cookie")
    monkeypatch.setenv("XHS_QUERY", "咖啡")
    monkeypatch.setenv("XHS_LIMIT", "2")
    monkeypatch.setenv("XHS_SORT", "0")

    out = _exec_snippet(xhs.SEARCH_CODE)

    assert out["success"] is True
    assert [row["id"] for row in out["notes"]] == ["one"]
    assert Api.instances[0].calls == [("咖啡", 1, 0, "root")]


def test_search_snippet_reuses_the_root_id_across_pages(monkeypatch):
    class Api:
        instances = []

        def __init__(self, auth):
            self.calls = []
            Api.instances.append(self)

        def bootstrap(self):
            return self

        def search_note(self, query, page, sort, search_id=None):
            self.calls.append((page, search_id))
            return True, "", {
                "code": "0",
                "data": {
                    "items": [{"model_type": "note", "id": f"n{page}",
                               "xsec_token": "tok", "note_card": {}}],
                    "has_more": page == 1,
                },
            }

    _install_snippet_stubs(monkeypatch, Api)
    monkeypatch.setenv("XHS_COOKIE_INTERNAL", "cookie")
    monkeypatch.setenv("XHS_QUERY", "咖啡")
    monkeypatch.setenv("XHS_LIMIT", "2")
    monkeypatch.setenv("XHS_SORT", "0")

    out = _exec_snippet(xhs.SEARCH_CODE)

    assert [row["id"] for row in out["notes"]] == ["n1", "n2"]
    assert Api.instances[0].calls == [(1, "root"), (2, "root")]


def test_detail_and_comments_snippets_execute(monkeypatch):
    class DetailApi:
        def __init__(self, auth):
            pass

        def bootstrap(self):
            return self

        def get_note_info(self, url):
            return True, "", {
                "code": "0",
                "data": {"items": [{"note_card": {
                    "note_id": "n", "display_title": "T", "desc": "D",
                }}]},
            }

    _install_snippet_stubs(monkeypatch, DetailApi)
    monkeypatch.setenv("XHS_COOKIE_INTERNAL", "cookie")
    monkeypatch.setenv("XHS_NOTE_URL", NOTE)
    detail = _exec_snippet(xhs.DETAIL_CODE)
    assert detail["success"] is True
    assert detail["note"]["id"] == "n"

    class CommentsApi:
        def __init__(self, auth):
            pass

        def bootstrap(self):
            return self

        def get_note_out_comment(self, note_id, cursor, token, proxies):
            return True, "", {
                "code": "0",
                "data": {
                    "comments": [
                        {"user_info": {"nickname": "A"}, "content": "c", "sub_comments": []}
                    ],
                    "has_more": False,
                },
            }

    _install_snippet_stubs(monkeypatch, CommentsApi)
    monkeypatch.setenv("XHS_COMMENT_LIMIT", "10")
    monkeypatch.setenv("XHS_INTERVAL", "0")
    comments = _exec_snippet(xhs.COMMENTS_CODE)
    assert comments["success"] is True
    assert comments["total_fetched"] == 1


def test_comments_snippet_waits_between_pages(monkeypatch):
    class Api:
        pages = 0

        def __init__(self, auth):
            pass

        def bootstrap(self):
            return self

        def get_note_out_comment(self, note_id, cursor, token, proxies):
            Api.pages += 1
            if Api.pages == 1:
                return True, "", {
                    "code": "0",
                    "data": {
                        "comments": [{"user_info": {"nickname": "A"}, "content": "1"}],
                        "has_more": True,
                        "cursor": "c1",
                    },
                }
            return True, "", {
                "code": "0",
                "data": {
                    "comments": [{"user_info": {"nickname": "B"}, "content": "2"}],
                    "has_more": False,
                },
            }

    _install_snippet_stubs(monkeypatch, Api)
    monkeypatch.setenv("XHS_COOKIE_INTERNAL", "cookie")
    monkeypatch.setenv("XHS_NOTE_URL", NOTE)
    monkeypatch.setenv("XHS_COMMENT_LIMIT", "2")
    monkeypatch.setenv("XHS_INTERVAL", "0.05")

    started = time.monotonic()
    out = _exec_snippet(xhs.COMMENTS_CODE)

    assert out["total_fetched"] == 2
    assert time.monotonic() - started >= 0.04


def test_snippet_auth_failure_is_reported_and_maps_to_need_login(monkeypatch):
    modules = _install_snippet_stubs(monkeypatch, object)

    def fail(cls, cookie):
        raise RuntimeError("登录已过期")

    modules["xhs_utils.xhs_pc"].XHSPcAuth = type(
        "XHSPcAuth", (), {"from_cookie": classmethod(fail)}
    )
    monkeypatch.setenv("XHS_COOKIE_INTERNAL", "cookie")
    monkeypatch.setenv("XHS_QUERY", "咖啡")

    out = _exec_snippet(xhs.SEARCH_CODE)

    assert out["success"] is False
    assert "登录" in out["msg"]
    assert map_xhs_error("search", out).code == "NEED_LOGIN"


def test_payload_parses_the_last_json_line_after_warnings():
    assert xhs._payload('warning: retry\n{"success": true, "notes": []}\n')["success"] is True


def test_main_legacy_bare_url_maps_pages_and_reports_total(monkeypatch, capsys):
    fake_run_py(monkeypatch, {
        "success": True,
        "msg": "",
        "code": "",
        "comments": [{"nickname": "A", "content": "x"}],
    })

    assert xhs.main([NOTE, "1"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert len(out["comments"]) == 1
    assert out["total_fetched"] == 1


def test_main_detail_search_and_error_forms(monkeypatch, capsys):
    def run(code, *, timeout, extra_env=None):
        if "XHS_NOTE_URL" in (extra_env or {}):
            return json.dumps({"success": True, "code": "", "note": {"title": "T"}})
        return json.dumps({"success": True, "code": "", "notes": [{"title": "T"}]})

    monkeypatch.setattr(xhs, "run_py", run)

    assert xhs.main(["detail", NOTE]) == 0
    assert json.loads(capsys.readouterr().out)["note"]["title"] == "T"

    assert xhs.main(["search", "咖啡", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["notes"][0]["title"] == "T"

    assert xhs.main(["detail", "https://www.xiaohongshu.com/explore/x"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "BAD_INPUT"


# ── registry and import side effects ─────────────────────────────────────────


def test_xiaohongshu_actions_chain_native_before_opencli_and_allow_throttle_time():
    for action in XiaoHongShuChannel().actions:
        assert [label for label, _ in action.backends] == ["native", "opencli"]
        assert action.timeout == 120


def test_import_agent_reach_channels_is_silent(tmp_path):
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["AGENT_REACH_NO_UPDATE_CHECK"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", "import agent_reach.channels"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
