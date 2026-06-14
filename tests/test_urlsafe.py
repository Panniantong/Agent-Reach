# -*- coding: utf-8 -*-
"""Tests for agent_reach.utils.urlsafe — scheme allowlist + SSRF guard."""

import pytest

from agent_reach.utils import urlsafe as us


class TestIsHttpUrl:
    def test_true_for_http_https(self):
        assert us.is_http_url("http://example.com")
        assert us.is_http_url("https://example.com")
        assert us.is_http_url("HTTPS://EXAMPLE.COM")

    def test_false_for_bare_or_other_scheme(self):
        assert not us.is_http_url("example.com")
        assert not us.is_http_url("file:///etc/passwd")
        assert not us.is_http_url("--exec=touch pwned")
        assert not us.is_http_url(None)


class TestAssertSafePublicURL:
    def test_accepts_public_literal_ip(self):
        # 1.1.1.1 is public; literal IPs skip DNS resolution.
        assert us.assert_safe_public_url("https://1.1.1.1/path") == "https://1.1.1.1/path"

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "data:text/plain,hi",
            "gopher://evil/",
            "ftp://example.com/x",
        ],
    )
    def test_rejects_non_http_scheme(self, url):
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url(url)

    @pytest.mark.parametrize(
        "value",
        ["--exec=touch pwned", "-J", "--config-locations=/tmp/x"],
    )
    def test_rejects_argument_injection_strings(self, value):
        # yt-dlp flags have no scheme → rejected before they reach argv.
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url(value)

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://localhost/",         # resolves to loopback
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://[::1]/",
        ],
    )
    def test_rejects_internal_ssrf_targets(self, url):
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url(url)

    def test_rejects_crlf_and_whitespace(self):
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url("https://example.com/\r\nHost: evil")
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url("https://exa mple.com/")

    def test_rejects_empty(self):
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url("")

    def test_resolve_false_skips_dns(self):
        # With resolve=False we only check scheme/host shape, not the address.
        assert us.assert_safe_public_url("https://example.com", resolve=False)

    def test_resolved_private_address_blocked(self, monkeypatch):
        # A public-looking name that resolves to a private address is blocked.
        monkeypatch.setattr(
            us.socket,
            "getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))],
        )
        with pytest.raises(us.UnsafeURLError):
            us.assert_safe_public_url("https://sneaky.example")

    def test_private_literal_ip_rejected_without_dns(self, monkeypatch):
        # Regression: the literal-IP guard must reject on its own, not rely on
        # getaddrinfo re-resolving the literal. Break DNS to prove it.
        def boom(*a, **k):
            raise AssertionError("getaddrinfo must not be called for a literal IP")

        monkeypatch.setattr(us.socket, "getaddrinfo", boom)
        with pytest.raises(us.UnsafeURLError, match="not a public address"):
            us.assert_safe_public_url("http://10.0.0.5/")

    def test_resolved_public_address_allowed(self, monkeypatch):
        monkeypatch.setattr(
            us.socket,
            "getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
        )
        assert us.assert_safe_public_url("https://example.com") == "https://example.com"
