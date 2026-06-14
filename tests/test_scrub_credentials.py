# -*- coding: utf-8 -*-
"""Tests for agent_reach.utils.text.scrub_url_credentials."""

import pytest

from agent_reach.utils.text import scrub_url_credentials


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "proxy error: http://user:pass@1.2.3.4:8080 refused",
            "proxy error: http://***@1.2.3.4:8080 refused",
        ),
        (
            "https://alice:s3cret@proxy.example.com/path",
            "https://***@proxy.example.com/path",
        ),
        # userinfo without password
        ("socks5://token@host:1080", "socks5://***@host:1080"),
        # no credentials — left untouched
        ("https://example.com/no-creds", "https://example.com/no-creds"),
        ("plain error with no url", "plain error with no url"),
    ],
)
def test_scrub_url_credentials(raw, expected):
    assert scrub_url_credentials(raw) == expected


def test_accepts_non_str():
    err = ValueError("connect to http://u:p@10.0.0.1:3128 failed")
    out = scrub_url_credentials(err)
    assert "u:p@" not in out
    assert "http://***@10.0.0.1:3128" in out


def test_multiple_urls_all_scrubbed():
    raw = "http://a:b@h1 and https://c:d@h2"
    out = scrub_url_credentials(raw)
    assert "a:b@" not in out and "c:d@" not in out
    assert out.count("***@") == 2
