# -*- coding: utf-8 -*-
"""Tests for the shared host_matches() URL-safety helper.

can_handle() routing must not be fooled by lookalike domains. A substring
check (`"x.com" in netloc`) matches attacker-controlled hosts like
`notx.com`, `x.com.evil.test`, or `x.com@evil.test`, which would cause a
credentialed channel to attach the user's auth cookies to an attacker URL.
host_matches() must accept only the exact host or a real subdomain.
"""

from agent_reach.utils.urls import domain_covers, host_matches


class TestHostMatchesAccepts:
    def test_exact_host(self):
        assert host_matches("https://x.com/foo", "x.com")

    def test_www_subdomain(self):
        assert host_matches("https://www.x.com/foo", "x.com")

    def test_deep_subdomain(self):
        assert host_matches("https://a.b.youtube.com/watch", "youtube.com")

    def test_mobile_subdomain(self):
        assert host_matches("https://mobile.twitter.com/user", "twitter.com")

    def test_case_insensitive(self):
        assert host_matches("HTTPS://X.COM/Foo", "x.com")

    def test_port_is_stripped(self):
        assert host_matches("https://x.com:443/foo", "x.com")

    def test_trailing_dot_fqdn(self):
        assert host_matches("https://x.com./foo", "x.com")

    def test_any_of_multiple_allowed_hosts(self):
        assert host_matches("https://youtu.be/abc", "youtube.com", "youtu.be")


class TestHostMatchesRejects:
    def test_prefix_lookalike(self):
        assert not host_matches("https://notx.com/foo", "x.com")

    def test_suffix_lookalike(self):
        assert not host_matches("https://x.com.evil.test/foo", "x.com")

    def test_userinfo_spoof(self):
        # Real host is evil.test; x.com is only the userinfo part.
        assert not host_matches("https://x.com@evil.test/foo", "x.com")

    def test_userinfo_and_port_spoof(self):
        assert not host_matches("https://x.com:443@evil.test/foo", "x.com")

    def test_host_only_in_path(self):
        assert not host_matches("https://evil.test/x.com", "x.com")

    def test_unrelated_host(self):
        assert not host_matches("https://github.com/user/repo", "x.com", "twitter.com")

    def test_empty_url(self):
        assert not host_matches("", "x.com")

    def test_no_host(self):
        assert not host_matches("not a url", "x.com")

    def test_substring_of_allowed(self):
        # allowed host longer than the actual host must not match
        assert not host_matches("https://com/foo", "x.com")


class TestDomainCovers:
    """Bare host/cookie-domain matcher — no URL parsing, handles leading dots."""

    def test_exact(self):
        assert domain_covers("xueqiu.com", "xueqiu.com")

    def test_leading_dot_cookie_domain(self):
        assert domain_covers(".xueqiu.com", "xueqiu.com")

    def test_subdomain(self):
        assert domain_covers("stock.xueqiu.com", ".xueqiu.com")

    def test_prefix_lookalike_rejected(self):
        assert not domain_covers("notxueqiu.com", "xueqiu.com")
        assert not domain_covers("evilxueqiu.com", ".xueqiu.com")

    def test_suffix_lookalike_rejected(self):
        assert not domain_covers("xueqiu.com.evil.test", "xueqiu.com")

    def test_empty(self):
        assert not domain_covers("", "xueqiu.com")

    def test_any_of_multiple(self):
        assert domain_covers(".x.com", "twitter.com", "x.com")
