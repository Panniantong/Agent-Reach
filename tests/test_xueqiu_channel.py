# -*- coding: utf-8 -*-
"""Dedicated tests for the ``xueqiu`` (雪球) channel.

Xueqiu wraps several public JSON endpoints and does real shaping of the
responses — normalising quotes, unwrapping the JSON-in-JSON hot-post
payload, stripping HTML, and ranking hot stocks. These tests stub the
shared ``_get_json`` helper so the parsing/precedence logic is exercised
offline. Follow-up to #331 — extends dedicated channel coverage after rss
(#360), github (#361), web (#363) and reddit (#364).
"""

import json
from unittest.mock import patch

from agent_reach.channels import xueqiu as xq
from agent_reach.channels.xueqiu import XueqiuChannel, _strip_html


# --- can_handle ---

def test_can_handle_matches_xueqiu_hosts():
    ch = XueqiuChannel()
    for url in ["https://xueqiu.com/S/SH600519", "https://XUEQIU.COM/u/123", "https://www.xueqiu.com"]:
        assert ch.can_handle(url) is True, url
    for url in ["https://example.com", "https://twitter.com", ""]:
        assert ch.can_handle(url) is False, url


# --- _strip_html (pure helper) ---

def test_strip_html_removes_tags_and_decodes_entities():
    assert _strip_html("<p>hello&nbsp;<b>world</b></p>") == "hello world"
    assert _strip_html("a &amp; b &lt;c&gt;") == "a & b <c>"
    assert _strip_html("   <br/>  padded  ") == "padded"


# --- check(): single public endpoint, items present/empty/error ---

def test_check_ok_when_items_present():
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", return_value={"data": {"items": [{"quote": {}}]}}):
        status, message = ch.check()
    assert status == "ok"
    assert ch.active_backend == ch.backends[0]


def test_check_warn_when_items_empty():
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", return_value={"data": {"items": []}}):
        status, message = ch.check()
    assert status == "warn"
    assert "为空" in message
    assert ch.active_backend is None


def test_check_warn_on_exception():
    import urllib.error
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", side_effect=urllib.error.URLError("refused")):
        status, message = ch.check()
    assert status == "warn"
    assert "连接失败" in message
    assert ch.active_backend is None


# --- get_stock_quote: field mapping + missing-data fallback ---

def test_get_stock_quote_maps_fields():
    ch = XueqiuChannel()
    payload = {"data": {"items": [{"quote": {
        "symbol": "SH600519", "name": "贵州茅台", "current": 1700.5,
        "percent": 1.23, "pe_ttm": 30.1,
    }}]}}
    with patch.object(xq, "_get_json", return_value=payload):
        q = ch.get_stock_quote("SH600519")
    assert q["symbol"] == "SH600519"
    assert q["name"] == "贵州茅台"
    assert q["current"] == 1700.5
    assert q["pe_ttm"] == 30.1
    # keys are always present even when the source omits them
    assert q["volume"] is None


def test_get_stock_quote_falls_back_when_no_items():
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", return_value={"data": {"items": []}}):
        q = ch.get_stock_quote("AAPL")
    assert q["symbol"] == "AAPL"  # echoes the requested symbol
    assert q["name"] == ""
    assert q["current"] is None


# --- search_stock: mapping + limit ---

def test_search_stock_maps_and_respects_limit():
    ch = XueqiuChannel()
    stocks = [
        {"code": "SH600519", "name": "贵州茅台", "exchange": "SH"},
        {"code": "SZ000858", "name": "五粮液", "exchange": "SZ"},
        {"code": "SH601318", "name": "中国平安", "exchange": "SH"},
    ]
    with patch.object(xq, "_get_json", return_value={"stocks": stocks}):
        results = ch.search_stock("酒", limit=2)
    assert len(results) == 2
    assert results[0] == {"symbol": "SH600519", "name": "贵州茅台", "exchange": "SH"}


def test_search_stock_handles_missing_stocks_key():
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", return_value={}):
        assert ch.search_stock("无") == []


# --- get_hot_posts: JSON-in-JSON unwrap, html strip, url build, bad data ---

def test_get_hot_posts_unwraps_and_shapes():
    ch = XueqiuChannel()
    inner = {
        "id": 42, "title": "茅台大涨",
        "text": "<p>今天<b>大涨</b>&nbsp;了</p>",
        "user": {"screen_name": "韭菜王"},
        "like_count": 99, "target": "/SH600519/123",
    }
    payload = {"list": [{"data": json.dumps(inner, ensure_ascii=False)}]}
    with patch.object(xq, "_get_json", return_value=payload):
        posts = ch.get_hot_posts(limit=5)
    assert len(posts) == 1
    p = posts[0]
    assert p["id"] == 42
    assert p["title"] == "茅台大涨"
    assert p["text"] == "今天大涨 了"          # html stripped, entity decoded
    assert p["author"] == "韭菜王"
    assert p["likes"] == 99
    assert p["url"] == "https://xueqiu.com/SH600519/123"


def test_get_hot_posts_truncates_text_to_200_chars():
    ch = XueqiuChannel()
    inner = {"text": "x" * 500, "target": ""}
    payload = {"list": [{"data": json.dumps(inner)}]}
    with patch.object(xq, "_get_json", return_value=payload):
        posts = ch.get_hot_posts()
    assert len(posts[0]["text"]) == 200
    assert posts[0]["url"] == ""  # no target -> no url


def test_get_hot_posts_tolerates_bad_data_field():
    ch = XueqiuChannel()
    # one item with non-string data, one with invalid JSON -> both -> defaults
    payload = {"list": [{"data": 123}, {"data": "{not json"}]}
    with patch.object(xq, "_get_json", return_value=payload):
        posts = ch.get_hot_posts()
    assert len(posts) == 2
    for p in posts:
        assert p["id"] == 0
        assert p["author"] == ""
        assert p["url"] == ""


# --- get_hot_stocks: ranking + code/symbol fallback ---

def test_get_hot_stocks_ranks_and_falls_back_to_symbol():
    ch = XueqiuChannel()
    items = [
        {"code": "SH600519", "name": "贵州茅台", "current": 1700, "percent": 1.2},
        {"symbol": "SZ000858", "name": "五粮液", "current": 150, "percent": -0.5},
    ]
    with patch.object(xq, "_get_json", return_value={"data": {"items": items}}):
        results = ch.get_hot_stocks(limit=10)
    assert results[0]["rank"] == 1
    assert results[0]["symbol"] == "SH600519"
    assert results[1]["rank"] == 2
    assert results[1]["symbol"] == "SZ000858"  # used `symbol` since `code` absent


def test_get_hot_stocks_empty_when_no_items():
    ch = XueqiuChannel()
    with patch.object(xq, "_get_json", return_value={"data": {}}):
        assert ch.get_hot_stocks() == []
