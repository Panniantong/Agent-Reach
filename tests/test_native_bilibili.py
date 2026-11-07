# -*- coding: utf-8 -*-
"""Native Bilibili backend: search/read/subtitle/summary mapping and failure modes."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from agent_reach.runtime.result import ReachError

BV = "BV1GJ411x7h7"


def _native():
    from agent_reach.native import bilibili

    return bilibili


def _view_payload(**overrides):
    data = {
        "bvid": BV,
        "aid": 123,
        "cid": 456,
        "title": "测试视频",
        "desc": "视频简介",
        "owner": {"name": "某UP"},
        "duration": 60,
        "pubdate": 1700000000,
        "stat": {"view": 99},
        "pages": [{"cid": 456, "page": 1, "part": "P1", "duration": 60}],
        "subtitle": {"allow_submit": True},
    }
    data.update(overrides)
    return {"code": 0, "data": data}


class _Response:
    def __init__(self, status_code=200, payload=None, text="", url="https://api.bilibili.com/x/test"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.url = url

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


# ── error mapping ──


@pytest.mark.parametrize(
    "code,expected",
    [
        (-404, "NOT_FOUND"),
        (-101, "NEED_SETUP"),
        (-352, "UPSTREAM_BROKEN"),
        (412, "UPSTREAM_BROKEN"),
        (429, "RATE_LIMITED"),
        (-509, "RATE_LIMITED"),
        (-799, "RATE_LIMITED"),
        (401, "NEED_LOGIN"),
        (-403, "PLATFORM_BLOCKED"),
        (-10403, "PLATFORM_BLOCKED"),
        (-400, "BAD_INPUT"),
    ],
)
def test_map_bili_error_codes(code, expected):
    from agent_reach.native._items import map_bili_error

    assert map_bili_error(code, "message", "read").code == expected


def test_map_bili_error_names_the_action_in_fallback_messages():
    from agent_reach.native._items import map_bili_error

    assert "search" in map_bili_error(-999, "", "search").message


def test_read_404_is_not_found(monkeypatch):
    native = _native()
    from agent_reach.native._items import map_bili_error

    def fake_fetch(*args, **kwargs):
        raise map_bili_error(-404, "啥都木有")

    monkeypatch.setattr(native, "fetch_json", fake_fetch)
    with pytest.raises(ReachError) as exc:
        native.read(BV, timeout=5)
    assert exc.value.code == "NOT_FOUND"


def test_read_maps_title_author_desc_and_stat(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "fetch_json", lambda *a, **k: _view_payload())
    items = native.read(BV, timeout=5)
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "测试视频"
    assert item["url"] == f"https://www.bilibili.com/video/{BV}"
    assert item["author"] == "某UP"
    assert item["published_at"] == "2023-11-14T22:13:20Z"
    assert item["text"] == "视频简介"
    assert item["raw"]["stat"]["view"] == 99


def test_b23_redirect_is_followed(monkeypatch):
    native = _native()
    response = _Response(200, url=f"https://www.bilibili.com/video/{BV}")
    session = _Session(response)
    monkeypatch.setattr(native, "_session", lambda: session)
    assert native._bvid_from_target("https://b23.tv/abc123", timeout=5) == BV
    assert session.calls[0][0][0] == "HEAD"


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.test/b23.tv/abc",
        "evil.test/b23.tv/abc",
        "https://b23.tv@evil.test/b23.tv/abc",
        "ftp://b23.tv/abc",
        "http://127.0.0.1/b23.tv/abc",
    ],
)
def test_b23_links_must_stay_on_b23_tv(monkeypatch, target):
    native = _native()
    monkeypatch.setattr(native, "_session", lambda: pytest.fail("must not make a request"))
    with pytest.raises(ReachError) as exc:
        native._bvid_from_target(target, timeout=5)
    assert exc.value.code == "BAD_INPUT"


def test_html_instead_of_json_is_upstream_broken(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_session", lambda: _Session(_Response(200, None, "<html>")))
    with pytest.raises(ReachError) as exc:
        native.fetch_json("https://api.bilibili.com/x/test", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_http_412_is_upstream_broken(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_session", lambda: _Session(_Response(412, None, "blocked")))
    with pytest.raises(ReachError) as exc:
        native.fetch_json("https://api.bilibili.com/x/test", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"


@pytest.mark.parametrize("status", [401, 403])
def test_anonymous_auth_denial_is_not_final_but_rejected_login_is(monkeypatch, status):
    native = _native()
    monkeypatch.setattr(
        native, "_session", lambda: _Session(_Response(status, None, "forbidden"))
    )
    with pytest.raises(ReachError) as exc:
        native.fetch_json("https://api.bilibili.com/x/test", timeout=5, cookies={})
    assert exc.value.code == "UPSTREAM_BROKEN"
    with pytest.raises(ReachError) as exc:
        native.fetch_json(
            "https://api.bilibili.com/x/test", timeout=5, cookies={"SESSDATA": "stale"}
        )
    assert exc.value.code == "NEED_LOGIN"


def test_request_timeout_is_timeout(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_session", lambda: _Session(error=requests.exceptions.Timeout()))
    with pytest.raises(ReachError) as exc:
        native.fetch_json("https://api.bilibili.com/x/test", timeout=5)
    assert exc.value.code == "TIMEOUT"


# ── search (WBI) ──


def test_search_uses_wbi_search_endpoint_and_strips_highlights(monkeypatch):
    native = _native()
    seen = {}
    monkeypatch.setattr(
        native, "get_wbi_keys", lambda *, timeout, cookies=None: ("i" * 32, "s" * 32)
    )

    def fake_fetch(url, params=None, *, timeout, cookies=None, action="read", check_code=True):
        seen["url"] = url
        seen["timeout"] = timeout
        return {
            "code": 0,
            "data": {
                "result": [
                    {
                        "bvid": BV,
                        "title": '<em class="keyword">Python</em> 教程',
                        "author": "UP主",
                        "description": "desc",
                        "pubdate": 1700000000,
                        "play": 5,
                        "pic": "//i0.hdslb.com/x.jpg",
                    },
                    {"bvid": "BV2", "title": "第二条", "author": "A"},
                ]
            },
        }

    monkeypatch.setattr(native, "fetch_json", fake_fetch)
    items = native.search("Python", limit=1, timeout=7)
    assert "/x/web-interface/wbi/search/type" in seen["url"]
    assert "search_type=video" in seen["url"] and "page_size=1" in seen["url"]
    assert seen["timeout"] == 7
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Python 教程"
    assert item["url"] == f"https://www.bilibili.com/video/{BV}"
    assert item["author"] == "UP主"
    assert item["raw"]["play"] == 5


def test_search_error_code_is_mapped(monkeypatch):
    native = _native()
    from agent_reach.native._items import map_bili_error

    monkeypatch.setattr(
        native, "get_wbi_keys", lambda *, timeout, cookies=None: ("i" * 32, "s" * 32)
    )

    def fake_fetch(*args, **kwargs):
        raise map_bili_error(-352, "风控校验失败")

    monkeypatch.setattr(native, "fetch_json", fake_fetch)
    with pytest.raises(ReachError) as exc:
        native.search("Python", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"


def test_sign_wbi_params_is_deterministic_and_contains_signature():
    native = _native()
    signed = native.sign_wbi_params(
        {"keyword": "Python", "search_type": "video"}, "i" * 32, "s" * 32, wts="1700000000"
    )
    assert "wts=1700000000" in signed
    assert "w_rid=" in signed
    assert len(native.get_mixin_key("a" * 64)) == 32


def test_encode_param_escapes_slashes_for_wbi():
    native = _native()
    signed = native.sign_wbi_params(
        {"keyword": "C/C++"}, "i" * 32, "s" * 32, wts="1700000000"
    )
    assert "keyword=C%2FC%2B%2B" in signed
    assert "keyword=C/C" not in signed


# ── cookies ──


def test_parse_cookie_string_and_mapping():
    native = _native()
    assert native._parse_cookie_value("SESSDATA=abc; bili_jct=def") == {
        "SESSDATA": "abc",
        "bili_jct": "def",
    }
    assert native._parse_cookie_value({"SESSDATA": "abc"}) == {"SESSDATA": "abc"}
    assert native._parse_cookie_value(None) == {}


def test_cookie_precedence_config_then_env_then_cdp_file(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_load_cookies_from_cdp_file", lambda: {"SESSDATA": "file"})
    monkeypatch.setattr(native, "_configured_cookies", lambda: {"SESSDATA": "config"})
    monkeypatch.setattr(native, "_load_cookies_from_chrome", lambda: {"SESSDATA": "chrome"})
    assert native._resolve_cookies()["SESSDATA"] == "config"
    monkeypatch.setattr(native, "_configured_cookies", lambda: {})
    assert native._resolve_cookies()["SESSDATA"] == "file"
    monkeypatch.setattr(native, "_load_cookies_from_cdp_file", lambda: {})
    assert native._resolve_cookies(allow_chrome=True)["SESSDATA"] == "chrome"


def test_env_cookie_is_used_when_config_is_empty(monkeypatch):
    native = _native()
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=env-cookie; bili_jct=jct")
    assert native._configured_cookies()["SESSDATA"] == "env-cookie"


def test_yaml_dict_cookie_from_config():
    from agent_reach.config import Config

    Config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    Config.CONFIG_FILE.write_text(
        "bili_cookie:\n  SESSDATA: config-cookie\n  bili_jct: jct\n", encoding="utf-8"
    )
    assert _native()._configured_cookies()["SESSDATA"] == "config-cookie"


def test_config_and_env_cookies_merge_by_name(monkeypatch):
    from agent_reach.config import Config

    Config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    Config.CONFIG_FILE.write_text(
        "bili_cookie:\n  bili_jct: config-jct\n", encoding="utf-8"
    )
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=env-session; buvid3=env-buvid3")
    jar = _native()._configured_cookies()
    assert jar == {
        "SESSDATA": "env-session",
        "bili_jct": "config-jct",
        "buvid3": "env-buvid3",
    }


def test_cdp_cookie_file_is_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / ".local" / "share" / "bili-sub" / "cookies.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"SESSDATA": "file-cookie", "other": "ignored"}))
    assert _native()._load_cookies_from_cdp_file() == {"SESSDATA": "file-cookie"}


def test_cdp_cookie_file_refuses_symlinks(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "real-cookies.json"
    target.write_text(json.dumps({"SESSDATA": "sneaky"}))
    path = tmp_path / ".local" / "share" / "bili-sub" / "cookies.json"
    path.parent.mkdir(parents=True)
    path.symlink_to(target)
    assert _native()._load_cookies_from_cdp_file() == {}


def test_cdp_cookie_file_rejects_oversized_files(monkeypatch, tmp_path):
    native = _native()
    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / ".local" / "share" / "bili-sub" / "cookies.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (native.MAX_COOKIE_FILE_BYTES + 1))
    assert native._load_cookies_from_cdp_file() == {}


# ── subtitles ──


def test_subtitle_without_login_is_non_final_need_setup(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {})
    monkeypatch.setattr(native, "fetch_json", lambda *a, **k: pytest.fail("no HTTP without login"))
    with pytest.raises(ReachError) as exc:
        native.subtitle(BV, part=1, language="ai-zh", timestamps="true", timeout=5)
    assert exc.value.code == "NEED_SETUP"
    assert exc.value.code not in {"NEED_LOGIN"}


def _one_page_info():
    return {
        "bvid": BV,
        "aid": 123,
        "cid": 456,
        "pages": [{"cid": 456, "page": 1, "part": "P1", "duration": 60, "time_offset": 0}],
        "page_count": 1,
        "title": "测试视频",
        "desc": "",
        "owner": "某UP",
        "duration": 60,
        "pubdate": 1700000000,
        "views": 1,
        "subtitle_allow_submit": True,
        "subtitle_list": [],
        "url": f"https://www.bilibili.com/video/{BV}",
    }


def test_subtitle_selects_language_and_part(monkeypatch):
    native = _native()
    info = _one_page_info()
    info["pages"] = [
        {"cid": 456, "page": 1, "part": "P1", "duration": 10, "time_offset": 0},
        {"cid": 789, "page": 2, "part": "P2", "duration": 10, "time_offset": 10},
    ]
    info["page_count"] = 2
    selected = {}

    def fake_tracks(bvid, cid, aid, *, timeout, cookies):
        selected["cid"] = cid
        return [
            {"id": "1", "language": "ai-zh", "label": "中文", "url": "https://sub/zh"},
            {"id": "2", "language": "ai-en", "label": "English", "url": "https://sub/en"},
        ]

    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: dict(info))
    monkeypatch.setattr(native, "get_subtitle_tracks", fake_tracks)
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    monkeypatch.setattr(
        native,
        "fetch_text",
        lambda url, *, timeout, cookies=None, action="read": json.dumps(
            {"body": [{"from": 1.5, "to": 3, "content": "你好" if url.endswith("zh") else "hello"}]}
        ),
    )

    items = native.subtitle(BV, part=2, language="ai-zh", timestamps="true", timeout=5)
    assert selected["cid"] == 789
    assert items[0]["text"] == "[00:00:11] 你好"
    assert items[0]["raw"]["part"] == 2

    items = native.subtitle(BV, part=2, language="ai-zh", timestamps="false", timeout=5)
    assert items[0]["text"] == "你好"


def test_subtitle_part_out_of_range_falls_back_to_last(monkeypatch, caplog):
    native = _native()
    info = _one_page_info()
    info["pages"] = [
        {"cid": 456, "page": 1, "part": "P1", "duration": 10, "time_offset": 0},
        {"cid": 789, "page": 2, "part": "P2", "duration": 10, "time_offset": 10},
    ]
    info["page_count"] = 2
    selected = {}

    def fake_tracks(bvid, cid, aid, *, timeout, cookies):
        selected["cid"] = cid
        return []

    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: dict(info))
    monkeypatch.setattr(native, "get_subtitle_tracks", fake_tracks)
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})

    with caplog.at_level("WARNING"):
        result = native.extract_subtitle(BV, part=5, timeout=5)
    assert result["parts"][0]["part"] == 2
    assert selected["cid"] == 789
    assert any("P5" in record.getMessage() for record in caplog.records)


def test_subtitle_without_tracks_is_not_found(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: _one_page_info())
    monkeypatch.setattr(native, "get_subtitle_tracks", lambda *a, **k: [])
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    with pytest.raises(ReachError) as exc:
        native.subtitle(BV, part=1, language="ai-zh", timestamps="true", timeout=5)
    assert exc.value.code == "NOT_FOUND"


def test_missing_requested_language_is_non_final_upstream_broken(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: _one_page_info())
    monkeypatch.setattr(
        native,
        "get_subtitle_tracks",
        lambda *a, **k: [
            {"id": "1", "language": "zh-Hans", "label": "简体", "url": "https://sub/zh"}
        ],
    )
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    monkeypatch.setattr(
        native, "fetch_text", lambda *a, **k: json.dumps({"body": [{"from": 0, "to": 1, "content": "你好"}]})
    )
    with pytest.raises(ReachError) as exc:
        native.subtitle(BV, language="ai-zh", timeout=5)
    assert exc.value.code == "UPSTREAM_BROKEN"
    assert exc.value.code != "NOT_FOUND"
    assert "zh-Hans" in exc.value.message


def test_subtitle_closed_uses_allow_submit_not_subtitle_list(monkeypatch):
    native = _native()
    info = _one_page_info()
    monkeypatch.setattr(native, "get_subtitle_tracks", lambda *a, **k: [])
    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: dict(info))

    info["subtitle_allow_submit"] = False
    info["subtitle_list"] = []
    result = native.extract_subtitle(BV, timeout=5, cookies={"SESSDATA": "test"})
    assert result["subtitle_closed"] is True

    info["subtitle_allow_submit"] = True
    info["subtitle_list"] = [{"lan": "ai-zh"}]  # other parts may list tracks
    result = native.extract_subtitle(BV, timeout=5, cookies={"SESSDATA": "test"})
    assert "subtitle_closed" not in result
    assert result["subtitle_count"] == 1


def test_extract_one_part_skips_empty_tracks_and_joins_same_language(monkeypatch):
    native = _native()
    info = _one_page_info()
    page = {"cid": 456, "page": 1, "part": "P1", "duration": 60, "time_offset": 0}
    tracks = [
        {"id": "1", "language": "ai-zh", "label": "中文", "url": "https://sub/empty"},
        {"id": "2", "language": "ai-zh", "label": "中文2", "url": "https://sub/a"},
        {"id": "3", "language": "ai-zh", "label": "中文3", "url": "https://sub/b"},
    ]
    bodies = {
        "https://sub/empty": {"body": []},
        "https://sub/a": {"body": [{"from": 1, "to": 2, "content": "甲"}]},
        "https://sub/b": {"body": [{"from": 3, "to": 4, "content": "乙"}]},
    }
    monkeypatch.setattr(native, "get_subtitle_tracks", lambda *a, **k: tracks)
    monkeypatch.setattr(
        native, "fetch_text", lambda url, **kwargs: json.dumps(bodies[url])
    )
    result = native._extract_one_part(
        BV, info, page, "ai-zh", True, timeout=5, cookies={"SESSDATA": "test"}
    )
    assert result["has_subtitles"] is True
    assert result["subtitles"]["ai-zh"]["text"] == "[00:00:01] 甲\n\n[00:00:03] 乙"
    assert result["subtitles"]["ai-zh"]["line_count"] == 2


def test_extract_one_part_empty_segments_do_not_claim_subtitles(monkeypatch):
    native = _native()
    info = _one_page_info()
    page = {"cid": 456, "page": 1, "part": "P1", "duration": 60, "time_offset": 0}
    monkeypatch.setattr(
        native,
        "get_subtitle_tracks",
        lambda *a, **k: [
            {"id": "1", "language": "ai-zh", "label": "中文", "url": "https://sub/empty"}
        ],
    )
    monkeypatch.setattr(
        native,
        "fetch_text",
        lambda *a, **k: json.dumps({"body": [{"from": 0, "to": 1, "content": "   "}]}),
    )
    result = native._extract_one_part(
        BV, info, page, "ai-zh", True, timeout=5, cookies={"SESSDATA": "test"}
    )
    assert result["has_subtitles"] is False
    assert result["subtitles"] == {}


def test_get_subtitle_tracks_skips_missing_urls(monkeypatch):
    native = _native()
    monkeypatch.setattr(
        native, "get_wbi_keys", lambda *, timeout, cookies=None: ("i" * 32, "s" * 32)
    )
    monkeypatch.setattr(
        native,
        "fetch_json",
        lambda *a, **k: {
            "code": 0,
            "data": {
                "login_mid": 1,
                "subtitle": {
                    "subtitles": [
                        {"id": 1, "lan": "ai-zh", "lan_doc": "中文", "subtitle_url": None},
                        {"id": 2, "lan": "ai-en", "lan_doc": "English"},
                        {"id": 3, "lan": "zh-Hans", "lan_doc": "简体", "subtitle_url": "//sub/zh"},
                    ]
                },
            },
        },
    )
    tracks = native.get_subtitle_tracks(
        BV, 456, 123, timeout=5, cookies={"SESSDATA": "test"}
    )
    assert [track["language"] for track in tracks] == ["zh-Hans"]
    assert tracks[0]["url"] == "https://sub/zh"


def test_extract_subtitle_uses_real_page_time_offsets(monkeypatch):
    native = _native()

    def fake_fetch(url, params=None, *, timeout, cookies=None, action="read", check_code=True):
        if "/x/web-interface/view" in url:
            return _view_payload(
                pages=[
                    {"cid": 11, "page": 1, "part": "P1", "duration": 10},
                    {"cid": 22, "page": 2, "part": "P2", "duration": 20},
                ],
                subtitle={"allow_submit": True},
            )
        if "/x/web-interface/nav" in url:
            return {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/" + "i" * 32 + ".png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/" + "s" * 32 + ".png",
                    }
                },
            }
        if "/x/player/" in url:
            return {
                "code": 0,
                "data": {
                    "login_mid": 1,
                    "subtitle": {
                        "subtitles": [
                            {
                                "id": 1,
                                "lan": "ai-zh",
                                "lan_doc": "中文",
                                "subtitle_url": "https://sub/2",
                            }
                        ]
                    },
                },
            }
        raise AssertionError(url)

    monkeypatch.setattr(native, "fetch_json", fake_fetch)
    monkeypatch.setattr(
        native,
        "fetch_text",
        lambda *a, **k: json.dumps({"body": [{"from": 1, "to": 2, "content": "P2"}]}),
    )
    result = native.extract_subtitle(BV, part=2, timeout=5, cookies={"SESSDATA": "test"})
    assert result["pages"][1]["time_offset"] == 10
    assert result["parts"][0]["part"] == 2
    assert result["subtitles"]["ai-zh"]["text"] == "[00:00:11] P2"


def test_rejected_login_is_need_login(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "get_video_info", lambda *a, **k: _one_page_info())
    monkeypatch.setattr(
        native, "get_wbi_keys", lambda *, timeout, cookies=None: ("i" * 32, "s" * 32)
    )
    monkeypatch.setattr(
        native,
        "fetch_json",
        lambda *a, **k: {"code": 0, "data": {"login_mid": 0, "subtitle": {"subtitles": []}}},
    )
    with pytest.raises(ReachError) as exc:
        native.extract_subtitle(BV, timeout=5, cookies={"SESSDATA": "stale"})
    assert exc.value.code == "NEED_LOGIN"


def test_timestamps_argument_must_be_boolean_text():
    native = _native()
    with pytest.raises(ReachError) as exc:
        native.subtitle(BV, timestamps="maybe", timeout=5)
    assert exc.value.code == "BAD_INPUT"


# ── summary ──


def test_summary_without_api_key_is_need_setup(monkeypatch):
    native = _native()
    monkeypatch.delenv("SUMMARY_API_KEY", raising=False)
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: pytest.fail("no network without a key"))
    with pytest.raises(ReachError) as exc:
        native.summary(BV, timeout=5)
    assert exc.value.code == "NEED_SETUP"
    assert "summary_api_key" in (exc.value.hint or "")


def test_summary_settings_env_fallback_when_config_value_is_empty(monkeypatch):
    from agent_reach.config import Config

    Config.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    Config.CONFIG_FILE.write_text("summary_api_key: ''\n", encoding="utf-8")
    monkeypatch.setenv("SUMMARY_API_KEY", "env-key")
    assert _native()._summary_settings()[0] == "env-key"


def test_summary_settings_accepts_legacy_env_names(monkeypatch):
    native = _native()
    for name in ("SUMMARY_API_KEY", "SUMMARY_BASE_URL", "SUMMARY_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BILIBILI_SUMMARY_API_KEY", "legacy-key")
    monkeypatch.setenv("BILIBILI_SUMMARY_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("BILIBILI_SUMMARY_MODEL", "legacy/model")
    assert native._summary_settings() == (
        "legacy-key",
        "https://legacy.example/v1",
        "legacy/model",
    )


def test_session_trusts_environment_proxies(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_SESSION", None)
    assert native._session().trust_env is True


def test_summary_returns_one_item(monkeypatch):
    native = _native()
    monkeypatch.setenv("SUMMARY_API_KEY", "test-key")
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    result = _one_page_info()
    result["parts"] = [{
        "part": 1, "part_name": "P1", "cid": 456, "duration": 60,
        "has_subtitles": True, "subtitle_available": True, "tracks": [],
        "subtitles": {"ai-zh": {"label": "中文", "url": "u", "line_count": 1, "text": "字幕内容"}},
    }]
    seen = {}

    def fake_extract(*args, **kwargs):
        seen.update(kwargs)
        return result

    def fake_summary(text, *, model, base_url, api_key, timeout):
        seen.update(text=text, model=model, base_url=base_url, api_key=api_key)
        return "这是总结"

    monkeypatch.setattr(native, "extract_subtitle", fake_extract)
    monkeypatch.setattr(native, "get_ai_summary", fake_summary)
    items = native.summary(BV, timeout=5)
    assert len(items) == 1
    assert items[0]["text"] == "这是总结"
    assert seen["text"] == "字幕内容"
    assert seen["api_key"] == "test-key"
    assert "qnaigc" in seen["base_url"]
    assert seen["show_timestamps"] is True
    assert items[0]["raw"]["input_characters"] == len("字幕内容")
    assert items[0]["raw"]["truncated"] is False


def test_summary_records_truncated_input(monkeypatch):
    native = _native()
    monkeypatch.setenv("SUMMARY_API_KEY", "test-key")
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    long_text = "字" * (native.MAX_SUMMARY_INPUT + 10)
    result = _one_page_info()
    result["parts"] = [{
        "part": 1, "part_name": "P1", "cid": 456, "duration": 60,
        "has_subtitles": True, "subtitle_available": True, "tracks": [],
        "subtitles": {"ai-zh": {"label": "中文", "url": "u", "line_count": 1, "text": long_text}},
    }]
    monkeypatch.setattr(native, "extract_subtitle", lambda *a, **k: result)
    monkeypatch.setattr(native, "get_ai_summary", lambda text, **k: "总结")
    items = native.summary(BV, timeout=5)
    assert items[0]["raw"]["input_characters"] == len(long_text)
    assert items[0]["raw"]["truncated"] is True


def test_summary_end_to_end_real_parsing(monkeypatch):
    native = _native()
    monkeypatch.setenv("SUMMARY_API_KEY", "test-key")
    monkeypatch.setenv("BILI_COOKIE", "SESSDATA=test-session")

    def fake_fetch(url, params=None, *, timeout, cookies=None, action="read", check_code=True):
        if "/x/web-interface/view" in url:
            return _view_payload(
                pages=[
                    {"cid": 11, "page": 1, "part": "P1", "duration": 10},
                    {"cid": 22, "page": 2, "part": "P2", "duration": 20},
                ],
                subtitle={"allow_submit": True},
            )
        if "/x/web-interface/nav" in url:
            return {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/" + "i" * 32 + ".png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/" + "s" * 32 + ".png",
                    }
                },
            }
        if "/x/player/" in url:
            return {
                "code": 0,
                "data": {
                    "login_mid": 1,
                    "subtitle": {
                        "subtitles": [
                            {
                                "id": 1,
                                "lan": "ai-zh",
                                "lan_doc": "中文",
                                "subtitle_url": "https://sub/2",
                            }
                        ]
                    },
                },
            }
        raise AssertionError(url)

    monkeypatch.setattr(native, "fetch_json", fake_fetch)
    monkeypatch.setattr(
        native,
        "fetch_text",
        lambda *a, **k: json.dumps({"body": [{"from": 1, "to": 2, "content": "P2"}]}),
    )
    seen = {}

    def fake_summary(text, **kwargs):
        seen["text"] = text
        return "总结"

    monkeypatch.setattr(native, "get_ai_summary", fake_summary)
    items = native.summary(BV, part=2, language="ai-zh", timeout=5)
    assert items[0]["text"] == "总结"
    assert "[00:00:11]" in seen["text"]
    assert items[0]["raw"]["input_characters"] == len(seen["text"])
    assert items[0]["raw"]["truncated"] is False


def test_summary_falls_back_to_an_available_language(monkeypatch):
    native = _native()
    monkeypatch.setenv("SUMMARY_API_KEY", "test-key")
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    missing = _one_page_info()
    missing["parts"] = [{
        "part": 1, "part_name": "P1", "cid": 456, "duration": 60,
        "has_subtitles": False, "subtitle_available": True,
        "tracks": [{"id": "1", "language": "zh-Hans", "label": "简体", "url": "u"}],
        "subtitles": {},
    }]
    fallback = _one_page_info()
    fallback["parts"] = [{
        "part": 1, "part_name": "P1", "cid": 456, "duration": 60,
        "has_subtitles": True, "subtitle_available": True,
        "tracks": [{"id": "1", "language": "zh-Hans", "label": "简体", "url": "u"}],
        "subtitles": {
            "zh-Hans": {"label": "简体", "url": "u", "line_count": 1, "text": "中文字幕"}
        },
    }]
    calls = []

    def fake_extract(*args, **kwargs):
        calls.append(kwargs.get("language"))
        return missing if len(calls) == 1 else fallback

    seen = {}

    def fake_summary(text, **kwargs):
        seen["text"] = text
        return "总结"

    monkeypatch.setattr(native, "extract_subtitle", fake_extract)
    monkeypatch.setattr(native, "get_ai_summary", fake_summary)

    items = native.summary(BV, timeout=5)

    assert items[0]["text"] == "总结"
    assert seen["text"] == "中文字幕"
    assert calls == ["ai-zh", "zh-Hans"]


def test_summary_without_subtitles_is_not_found(monkeypatch):
    native = _native()
    monkeypatch.setenv("SUMMARY_API_KEY", "test-key")
    monkeypatch.setattr(native, "_resolve_cookies", lambda **kw: {"SESSDATA": "test"})
    result = _one_page_info()
    result["parts"] = [{
        "part": 1, "part_name": "", "cid": 456, "duration": 60,
        "has_subtitles": False, "subtitle_available": False, "tracks": [], "subtitles": {},
    }]
    monkeypatch.setattr(native, "extract_subtitle", lambda *a, **k: result)
    with pytest.raises(ReachError) as exc:
        native.summary(BV, timeout=5)
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "NEED_SETUP"),
        (403, "NEED_SETUP"),
        (429, "RATE_LIMITED"),
        (500, "UPSTREAM_BROKEN"),
    ],
)
def test_summary_provider_statuses_map_to_unified_codes(monkeypatch, status, code):
    native = _native()
    session = _Session(_Response(status, {"error": {"message": "provider detail"}}, "detail"))
    monkeypatch.setattr(native, "_session", lambda: session)
    with pytest.raises(ReachError) as exc:
        native.get_ai_summary(
            "text", model="m", base_url="https://api.example.test/v1", api_key="k", timeout=5
        )
    assert exc.value.code == code
    assert "provider detail" in exc.value.message


def test_summary_timeout_is_timeout(monkeypatch):
    native = _native()
    monkeypatch.setattr(native, "_session", lambda: _Session(error=requests.exceptions.Timeout()))
    with pytest.raises(ReachError) as exc:
        native.get_ai_summary(
            "text", model="m", base_url="https://api.example.test/v1", api_key="k", timeout=5
        )
    assert exc.value.code == "TIMEOUT"


def test_summary_error_message_never_contains_the_api_key(monkeypatch):
    native = _native()
    session = _Session(_Response(401, {"message": "bad key"}, "bad key"))
    monkeypatch.setattr(native, "_session", lambda: session)
    with pytest.raises(ReachError) as exc:
        native.get_ai_summary(
            "text", model="m", base_url="https://api.example.test/v1", api_key="super-secret", timeout=5
        )
    assert exc.value.code == "NEED_SETUP"
    assert "super-secret" not in exc.value.message
    assert "super-secret" not in (exc.value.hint or "")


# ── saving ──


def test_save_result_creates_missing_parent_directories(tmp_path):
    native = _native()
    result = {"title": "T", "page_count": 1, "parts": [{"part": 1, "part_name": "P1"}]}
    args = argparse.Namespace(save=str(tmp_path / "nested" / "subs" / "file.md"))
    saved = native._save_result(result, args, "body")
    assert Path(saved).read_text(encoding="utf-8") == "body"


def test_save_result_auto_names_in_a_directory(tmp_path):
    native = _native()
    result = {"title": "T", "page_count": 1, "parts": [{"part": 1, "part_name": "P1"}]}
    args = argparse.Namespace(save=str(tmp_path / "subs") + "/")
    saved = native._save_result(result, args, "body")
    assert Path(saved).name == "T.md"
    assert Path(saved).read_text(encoding="utf-8") == "body"


def test_save_result_auto_names_a_multi_part_directory(tmp_path):
    native = _native()
    result = {
        "title": "T",
        "page_count": 2,
        "parts": [{"part": 2, "part_name": "第二集"}],
    }
    directory = tmp_path / "subs"
    directory.mkdir()
    args = argparse.Namespace(save=str(directory))
    saved = native._save_result(result, args, "body")
    assert Path(saved).name == "T [P2 第二集].md"


# ── import hygiene ──


def test_import_of_channels_prints_nothing_and_reads_no_chrome():
    code = "import agent_reach.channels, agent_reach.native.bilibili"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


def test_import_does_not_import_rookiepy():
    code = (
        "import builtins\n"
        "real_import = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    if name == 'rookiepy' or name.startswith('rookiepy.'):\n"
        "        raise AssertionError('rookiepy imported at import time')\n"
        "    return real_import(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n"
        "import agent_reach.native.bilibili\n"
        "import agent_reach.channels\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
