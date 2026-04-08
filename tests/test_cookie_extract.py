# -*- coding: utf-8 -*-
"""Tests for browser cookie import helpers."""

from http.cookiejar import Cookie

from agent_reach.cookie_extract import _extract_twitter_tokens


def _cookie(name: str, value: str, domain: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def test_extract_twitter_tokens_ignores_other_domains():
    cookies = [
        _cookie("auth_token", "abc", ".x.com"),
        _cookie("ct0", "xyz", ".twitter.com"),
        _cookie("auth_token", "wrong", ".example.com"),
    ]

    assert _extract_twitter_tokens(cookies) == {
        "auth_token": "abc",
        "ct0": "xyz",
    }
