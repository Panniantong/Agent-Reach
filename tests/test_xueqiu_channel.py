# -*- coding: utf-8 -*-
"""Dedicated tests for the ``xueqiu`` (雪球) channel.

Xueqiu wraps several public JSON endpoints and does real shaping of the
responses — normalising quotes, unwrapping the JSON-in-JSON hot-post
payload, stripping HTML, and ranking hot stocks. These tests stub the
shared ``_get_json`` helper so the parsing/precedence logic is exercised
offline. Follow-up to #331 — extends dedicated channel coverage after rss
(#360), github (#361), web (#363) and reddit (#364).
"""



import pytest

from agent_reach.channels.xueqiu import XueqiuChannel, _strip_html
from agent_reach.runtime.dispatch import run_action


def test_quote_routes_bare_920_symbol_to_beijing_exchange(monkeypatch):
    requests = []

    def fake_http_request(url, timeout):
        requests.append(url)
        if url != "https://qt.gtimg.cn/q=bj920008":
            return b'v_sh920008="";'
        fields = ["1", "成电光信", "920008", "12.34", "12.00", "12.10"]
        fields += [""] * 24
        fields += ["20261106150000", "0.34", "2.83", "12.50", "11.90"]
        return ("v_bj920008=\"" + "~".join(fields) + "\";").encode("gbk")

    monkeypatch.setattr("agent_reach.channels.xueqiu.http_request", fake_http_request)

    out = run_action(XueqiuChannel(), "quote", {"symbol": "920008"}, only_backend="tencent")

    assert out["ok"] is True
    assert requests == ["https://qt.gtimg.cn/q=bj920008"]
    assert out["items"][0]["title"] == "成电光信 (BJ920008)"
    assert out["items"][0]["raw"]["symbol"] == "BJ920008"


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









# --- get_stock_quote: field mapping + missing-data fallback ---





# --- search_stock: mapping + limit ---


def test_search_maps_tencent_fund_to_xueqiu_fund_symbol(monkeypatch):
    payload = (
        'v_hint="jj~007005~\\u4e2d\\u91d1\\u65b0\\u533b\\u836f\\u80a1\\u7968C~zjxyygpc~KJ'
        '^hk~00700~\\u817e\\u8baf\\u63a7\\u80a1~txkg~GP'
        '^us~aapl.oq~\\u82f9\\u679c~pg~GP";'
    )
    monkeypatch.setattr(
        "agent_reach.channels.xueqiu.http_request",
        lambda url, timeout: payload.encode("ascii"),
    )

    out = run_action(
        XueqiuChannel(), "search", {"query": "007005", "limit": 3}, only_backend="tencent"
    )

    assert out["ok"] is True
    assert [item["raw"]["symbol"] for item in out["items"]] == ["F007005", "00700", "AAPL"]
    assert [item["url"] for item in out["items"]] == [
        "https://xueqiu.com/S/F007005",
        "https://xueqiu.com/S/00700",
        "https://xueqiu.com/S/AAPL",
    ]


# --- get_hot_posts: JSON-in-JSON unwrap, html strip, url build, bad data ---















# --- get_hot_stocks: ranking + code/symbol fallback ---


@pytest.mark.parametrize("text,expected", [
    ("<p>&quot;A&quot; &#39;B&#39;</p>", "\"A\" 'B'"),
    ("<p>&#20013;&#x6587; &mdash; &#x1F680;</p>", "中文 — 🚀"),
    ("&amp;lt;b&amp;gt;literal&amp;lt;/b&amp;gt;", "&lt;b&gt;literal&lt;/b&gt;"),
    ("a&#160;b&#xA0;c", "a b c"),
])
def test_strip_html_decodes_named_and_numeric_entities_once(text, expected):
    assert _strip_html(text) == expected
