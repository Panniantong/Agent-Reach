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
