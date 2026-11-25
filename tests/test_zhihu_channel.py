"""Zhihu's read-only contract through dispatch, OpenCLI decoding, and CLI routing."""

import io
import json
from unittest.mock import Mock

import pytest

from agent_reach.channels.zhihu import ZhihuChannel
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.run import CommandFailed

QUESTION_ID = "1900000000000000001"
ANSWER_ID = "1937205528846655537"
QUESTION = f"https://www.zhihu.com/question/{QUESTION_ID}"
ANSWER = f"{QUESTION}/answer/{ANSWER_ID}"
ARTICLE = "https://zhuanlan.zhihu.com/p/123456789"


@pytest.fixture
def opencli_output(monkeypatch):
    """Replace only external command/session I/O; retain actual adapter decoding."""
    from agent_reach.runtime import browser, browser_binding, run

    response = {"rows": []}
    calls = []

    def command(argv, **kwargs):
        calls.append(list(argv))
        assert argv[:2] == ["opencli", "zhihu"]
        assert argv[-2:] == ["-f", "json"]
        assert kwargs["timeout"] > 0
        if "failure" in response:
            raise response["failure"]
        return json.dumps(response["rows"], ensure_ascii=False)

    monkeypatch.setattr(run, "run_cmd", command)
    monkeypatch.setattr(browser_binding, "environment", lambda site: {})
    monkeypatch.setattr(browser, "save_session", lambda: None)
    response["calls"] = calls
    return response


@pytest.fixture
def forbid_setup(monkeypatch):
    from agent_reach.runtime import browser, browser_binding, manage, run, session_reuse

    guards = []
    for module, name in (
        (manage, "add"),
        (session_reuse, "prepare"),
        (browser, "ensure_running"),
        (browser_binding, "environment"),
        (run, "run_cmd"),
    ):
        guard = Mock(side_effect=AssertionError(f"unexpected setup or browser: {name}"))
        monkeypatch.setattr(module, name, guard)
        guards.append(guard)
    return guards


INVALID_TARGETS = [
    "",
    "not-a-url",
    "1937205528846655537.0",
    "https://evil.example/question/123/answer/456",
    "https://www.zhihu.com.evil.example/question/123/answer/456",
    "https://www.zhihu.com@evil.example/question/123/answer/456",
    "https://user@www.zhihu.com/question/123/answer/456",
    "https://api.zhihu.com/answer/456",
    "https://www.zhihu.com:444/question/123/answer/456",
    "https://www.zhihu.com:invalid/question/123/answer/456",
    "https://www.zhihu.com:99999/question/123/answer/456",
    "http://www.zhihu.com/question/123/answer/456",
    "file:///question/123/answer/456",
    "//www.zhihu.com/question/123/answer/456",
    "https://127.0.0.1/question/123/answer/456",
    "https://www.zhihu.com/question/123/answer/456/extra",
    "https://www.zhihu.com/question/123/answer/%34%35%36",
    "https://www.zhihu.com/question/123/answer/４５６",
    "https://www.zhihu.com/question/123/answer/4 56",
    "https://www.zhihu.com/question/123/answer/4\n56",
    "https://www.zhihu.com/question/123/answer/4\t56",
    "https://www.zhihu.com/question/123/answer/4\x0056",
    "https://www.zhihu.com\\@evil.example/question/123/answer/456",
    ARTICLE,
]


@pytest.mark.parametrize("action", ["read", "comments"])
@pytest.mark.parametrize("target", INVALID_TARGETS)
def test_invalid_targets_fail_before_install_session_or_browser(forbid_setup, action, target):
    result = run_action(ZhihuChannel(), action, {"target": target})

    assert result["ok"] is False
    assert result["error"]["code"] == "BAD_INPUT"
    assert result["items"] == []
    for guard in forbid_setup:
        guard.assert_not_called()


@pytest.mark.parametrize("target", [QUESTION, "https://www.zhihu.com/people/alice"])
def test_comments_require_answer_target_before_setup(forbid_setup, target):
    result = run_action(ZhihuChannel(), "comments", {"target": target})

    assert result["error"]["code"] == "BAD_INPUT"
    for guard in forbid_setup:
        guard.assert_not_called()


@pytest.mark.parametrize("action,params", [
    ("search", {"query": "大模型"}),
    ("hot", {}),
    ("read", {"target": ANSWER}),
    ("comments", {"target": ANSWER}),
])
@pytest.mark.parametrize("limit", [0, -1, 51, True, 1.5, "many"])
def test_invalid_limits_fail_before_setup(forbid_setup, action, params, limit):
    result = run_action(ZhihuChannel(), action, {**params, "limit": limit})

    assert result["error"]["code"] == "BAD_INPUT"
    for guard in forbid_setup:
        guard.assert_not_called()


@pytest.mark.parametrize("limit", [-1, 21, True, 1.5, "many"])
def test_invalid_reply_limits_fail_before_setup(forbid_setup, limit):
    result = run_action(ZhihuChannel(), "comments", {"target": ANSWER, "replies-limit": limit})

    assert result["error"]["code"] == "BAD_INPUT"
    for guard in forbid_setup:
        guard.assert_not_called()


@pytest.mark.parametrize("query", ["", " \n\t "])
def test_empty_search_is_bad_input_before_setup(forbid_setup, query):
    result = run_action(ZhihuChannel(), "search", {"query": query})

    assert result["error"]["code"] == "BAD_INPUT"
    for guard in forbid_setup:
        guard.assert_not_called()


@pytest.mark.parametrize("action,params,command", [
    ("search", {"query": "大模型", "limit": 1}, ["search", "大模型", "--limit", "1"]),
    ("hot", {"limit": 1}, ["hot", "--limit", "1"]),
])
def test_discovery_normalizes_rows_and_honors_limit(opencli_output, action, params, command):
    opencli_output["rows"] = [
        {"rank": 1, "title": "如何理解大模型？", "author": "作者甲", "url": QUESTION},
        {"rank": 2, "title": "另一个问题", "author": "作者乙", "url": "https://www.zhihu.com/question/2"},
    ]

    result = run_action(ZhihuChannel(), action, params)

    assert result["ok"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert (item["title"], item["author"], item["url"]) == ("如何理解大模型？", "作者甲", QUESTION)
    assert opencli_output["calls"] == [["opencli", "zhihu", *command, "-f", "json"]]


@pytest.mark.parametrize("target", [
    ANSWER_ID,
    ANSWER,
    f"https://zhihu.com/answer/{ANSWER_ID}",
    f"{ANSWER}?utm_source=share#answer",
    f" \n{ANSWER}\t ",
])
def test_answer_id_precision_and_full_text_survive_dispatch(opencli_output, target):
    full_text = "这是应当完整保留的回答正文。" * 100 + "结尾不应丢失。"
    opencli_output["rows"] = [{
        "id": ANSWER_ID,
        "author": "回答者",
        "votes": 42,
        "comments": 3,
        "question_id": QUESTION_ID,
        "question_title": "如何理解大模型？",
        "url": ANSWER,
        "created_at": 1700000000,
        "updated_at": 1700000001,
        "content": full_text,
    }]

    result = run_action(ZhihuChannel(), "read", {"target": target})

    assert result["ok"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["text"] == full_text
    assert item["title"] == "如何理解大模型？"
    assert item["author"] == "回答者"
    assert item["url"] == ANSWER
    assert item["published_at"] == "2023-11-14T22:13:20Z"
    assert item["raw"]["id"] == ANSWER_ID
    assert item["raw"]["question_id"] == QUESTION_ID
    assert opencli_output["calls"] == [[
        "opencli", "zhihu", "answer-detail", ANSWER_ID, "--max-content", "0", "-f", "json",
    ]]


def test_question_results_are_explicit_answer_excerpts(opencli_output):
    excerpt = "摘" * 200
    opencli_output["rows"] = [
        {"rank": 1, "id": ANSWER_ID, "author": "回答者", "votes": 42, "url": ANSWER, "content": excerpt},
        {"rank": 2, "id": "456", "author": "其他作者", "votes": 1,
         "url": f"{QUESTION}/answer/456", "content": "另一条摘要"},
    ]

    result = run_action(ZhihuChannel(), "read", {"target": QUESTION, "limit": 1})

    assert result["ok"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["text"] == excerpt
    assert item["url"] == ANSWER
    assert item["raw"]["id"] == ANSWER_ID
    assert item["raw"]["content_scope"] == "answer_excerpt"
    assert item["raw"]["exhaustive"] is False
    assert opencli_output["calls"] == [[
        "opencli", "zhihu", "question", QUESTION_ID, "--limit", "1", "-f", "json",
    ]]


@pytest.mark.parametrize("target", [ANSWER_ID, ANSWER])
@pytest.mark.parametrize("parent_id", ["", "1937205528846655541"])
def test_comment_limit_keeps_replies_and_relationship_fields(opencli_output, target, parent_id):
    parent = "1937205528846655541"
    opencli_output["rows"] = [
        {"rank": 1, "comment_rank": 1, "reply_rank": 0, "depth": 0,
         "id": parent, "parent_id": "", "author": "甲", "reply_to": "",
         "likes": 3, "created_at": 1700000000, "url": f"{ANSWER}#comment-{parent}", "content": "顶级评论"},
        {"rank": 2, "comment_rank": 1, "reply_rank": 1, "depth": 0,
         "id": "1937205528846655542", "parent_id": parent_id, "author": "乙", "reply_to": "甲",
         "likes": 2, "created_at": 1700000001, "url": f"{ANSWER}#comment-1937205528846655542", "content": "回复甲"},
    ]

    result = run_action(ZhihuChannel(), "comments", {"target": target, "limit": 1, "replies-limit": 3})

    assert result["ok"] is True
    assert [item["text"] for item in result["items"]] == ["顶级评论", "回复甲"]
    reply = result["items"][1]
    assert reply["author"] == "乙"
    assert reply["raw"]["parent_id"] == parent_id
    assert reply["raw"]["reply_to"] == "甲"
    assert reply["raw"]["comment_rank"] == 1
    assert reply["raw"]["reply_rank"] == 1
    assert all(item["raw"]["exhaustive"] is False for item in result["items"])
    assert all(item["raw"]["content_scope"] == "loaded_comments" for item in result["items"])
    assert opencli_output["calls"] == [[
        "opencli", "zhihu", "answer-comments", ANSWER_ID, "--limit", "1", "--replies-limit", "3", "-f", "json",
    ]]


def test_cli_reply_limit_flag_accepts_zero(opencli_output, capsys):
    from agent_reach.runtime import cli

    code = cli.main(["zhihu", "comments", ANSWER, "--replies-limit", "0"])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["ok"] is True
    assert result["items"] == []
    assert opencli_output["calls"] == [[
        "opencli", "zhihu", "answer-comments", ANSWER_ID, "--limit", "20", "--replies-limit", "0", "-f", "json",
    ]]


@pytest.mark.parametrize("action,params", [
    ("search", {"query": "大模型"}),
    ("hot", {}),
    ("read", {"target": ANSWER}),
    ("comments", {"target": ANSWER}),
])
@pytest.mark.parametrize("upstream_code,message,expected", [
    ("AUTH_REQUIRED", "Login is required", "NEED_LOGIN"),
    ("CAPTCHA_REQUIRED", "Complete the captcha", "PLATFORM_BLOCKED"),
    ("RATE_LIMITED", "Too many requests", "RATE_LIMITED"),
])
@pytest.mark.parametrize("transport", ["nonzero_yaml", "json_error"])
def test_upstream_failures_remain_failures_without_fallback(
    opencli_output, monkeypatch, action, params, upstream_code, message, expected, transport,
):
    from agent_reach.runtime import public_web

    public = Mock(side_effect=AssertionError("must not bypass a platform failure"))
    monkeypatch.setattr(public_web, "attempt", public)
    if transport == "nonzero_yaml":
        opencli_output["failure"] = CommandFailed(
            "UPSTREAM_BROKEN", "opencli exited 77",
            stdout=f"ok: false\nerror:\n  code: {upstream_code}\n  message: {message}\n",
        )
    else:
        opencli_output["rows"] = {"ok": False, "error": {"code": upstream_code, "message": message}}

    result = run_action(ZhihuChannel(), action, params)

    assert result["ok"] is False
    assert result["items"] == []
    assert result["error"]["code"] == expected
    assert result["error"]["message"] == message
    assert len(opencli_output["calls"]) == 1
    assert [attempt["result"] for attempt in result["meta"]["attempts"]] == [expected]
    public.assert_not_called()


@pytest.mark.parametrize("rows", [[], {"items": []}, {"ok": True, "data": []}])
@pytest.mark.parametrize("action,params,expected", [
    ("search", {"query": "不存在的内容"}, "UPSTREAM_BROKEN"),
    ("hot", {}, "UPSTREAM_BROKEN"),
    ("read", {"target": ANSWER}, "NOT_FOUND"),
    ("read", {"target": QUESTION}, "NOT_FOUND"),
    ("comments", {"target": ANSWER}, None),
])
def test_empty_results_never_become_fake_rows(opencli_output, rows, action, params, expected):
    opencli_output["rows"] = rows

    result = run_action(ZhihuChannel(), action, params)

    assert result["items"] == []
    assert result["ok"] is (expected is None)
    if expected is not None:
        assert result["error"]["code"] == expected


@pytest.mark.parametrize("target", [ANSWER, QUESTION])
@pytest.mark.parametrize("content", [None, "", " \n\t "])
def test_read_with_no_body_is_not_success(opencli_output, target, content):
    opencli_output["rows"] = [{"id": ANSWER_ID, "url": ANSWER, "content": content}]

    result = run_action(ZhihuChannel(), "read", {"target": target})

    assert result["ok"] is False
    assert result["items"] == []
    assert result["error"]["code"] == "UPSTREAM_BROKEN"


def test_generic_read_leaves_columns_to_web_channel(monkeypatch, capsys):
    import urllib.request

    from agent_reach.runtime import browser_binding, cli

    request_urls = []

    def urlopen(request, **kwargs):
        request_urls.append(request.full_url)
        return io.BytesIO("Title: 专栏文章\n\nMarkdown Content:\n这是专栏正文。".encode())

    browser = Mock(side_effect=AssertionError("column must not use the Zhihu browser adapter"))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(browser_binding, "environment", browser)

    code = cli.main(["read", ARTICLE])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["channel"] == "web"
    assert result["items"][0]["title"] == "专栏文章"
    assert result["items"][0]["text"] == "这是专栏正文。"
    assert result["items"][0]["url"] == ARTICLE
    assert request_urls == [f"https://r.jina.ai/{ARTICLE}"]
    browser.assert_not_called()
