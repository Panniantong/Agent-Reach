"""Exercise the public xiaohongshu-mcp schema through the formatter CLI.

Field names follow xpzouying/xiaohongshu-mcp's service.go FeedsListResponse
and xiaohongshu/types.go Feed, FeedDetailResponse, and CommentList structs.
"""

import json
import subprocess
import sys

import pytest

from agent_reach.channels.xiaohongshu import format_xhs_result
from agent_reach.utils.process import utf8_subprocess_env

MCP_FEED = {
    "id": "note-123",
    "xsecToken": "explicit-test-token",
    "modelType": "note",
    "noteCard": {
        "type": "normal",
        "displayTitle": "搜索结果",
        "user": {"userId": "user-1", "nickname": "作者", "avatar": "discard"},
        "interactInfo": {"likedCount": "12", "commentCount": "3", "sharedCount": "2"},
        "cover": {"urlDefault": "https://example.com/cover.jpg", "width": 1080},
    },
}


def _format_cli(payload):
    result = subprocess.run(
        [sys.executable, "-m", "agent_reach.cli", "format", "xhs"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        env=utf8_subprocess_env(),
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def test_mcp_search_cli_preserves_fields_needed_for_detail():
    result = _format_cli({"feeds": [MCP_FEED], "count": 1})
    assert result == [
        {
            "id": "note-123",
            "xsec_token": "explicit-test-token",
            "title": "搜索结果",
            "type": "normal",
            "user": {"nickname": "作者", "user_id": "user-1"},
            "liked_count": "12",
            "comment_count": "3",
            "share_count": "2",
            "images": ["https://example.com/cover.jpg"],
        }
    ]


def test_mcp_http_success_wrapper_formats_the_same_search():
    wrapped = {"success": True, "data": {"feeds": [MCP_FEED], "count": 1}}
    assert format_xhs_result(wrapped) == format_xhs_result([MCP_FEED])
    assert format_xhs_result(wrapped)[0]["title"] == "搜索结果"


def test_mcp_detail_cli_retains_note_and_sibling_comments():
    payload = {
        "feed_id": "note-123",
        "data": {
            "note": {
                "noteId": "note-123",
                "xsecToken": "explicit-test-token",
                "title": "详情",
                "desc": "正文",
                "type": "normal",
                "user": {"userId": "user-1", "nickname": "作者"},
                "interactInfo": {"collectedCount": "4"},
                "imageList": [{"urlDefault": "https://example.com/detail.jpg"}],
            },
            "comments": {
                "list": [
                    {
                        "content": "好",
                        "userInfo": {"nickname": "读者"},
                        "likeCount": "2",
                        "subCommentCount": "0",
                    }
                ],
                "cursor": "discard",
                "hasMore": False,
            },
        },
    }
    result = _format_cli(payload)
    assert result["note_id"] == "note-123"
    assert result["xsec_token"] == "explicit-test-token"
    assert result["title"] == "详情"
    assert result["desc"] == "正文"
    assert result["collected_count"] == "4"
    assert result["images"] == ["https://example.com/detail.jpg"]
    assert result["comments"] == [
        {"content": "好", "user": "读者", "like_count": "2", "sub_comment_count": "0"}
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"feeds": [], "count": 0},
        {"items": []},
        {"data": {"items": []}},
        {"data": {"notes": []}},
        {"data": {"items": [], "notes": [MCP_FEED]}},
    ],
)
def test_empty_search_remains_a_list(payload):
    assert format_xhs_result(payload) == []


def test_snake_case_card_retains_outer_identity():
    result = format_xhs_result(
        {"id": "outer", "xsec_token": "token", "note_card": {"title": "card"}}
    )
    assert result == {"id": "outer", "xsec_token": "token", "title": "card"}


def test_inner_identity_keeps_precedence_for_legacy_wrappers():
    result = format_xhs_result({"id": "outer", "note_card": {"id": "inner"}})
    assert result["id"] == "inner"
