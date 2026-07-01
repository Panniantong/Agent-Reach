# -*- coding: utf-8 -*-
"""Tests for WebChannel SSRF protection on read().

WebChannel.read() fetches arbitrary URLs via Jina Reader. Before the SSRF
fix, any URL was passed directly — including private IPs and cloud metadata
endpoints. These tests verify that _assert_safe_public_url is called before
fetching, blocking internal/private/metadata URLs.
"""

import pytest
from unittest.mock import patch, MagicMock

from agent_reach.channels.web import WebChannel
from agent_reach.transcribe import TranscribeError


class TestWebChannelSSRF:
    """Verify WebChannel.read() rejects private/internal URLs before fetching."""

    def test_rejects_cloud_metadata_url(self):
        """169.254.169.254 (AWS/GCP metadata) must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal"):
            channel.read("http://169.254.169.254/latest/meta-data/")

    def test_rejects_localhost(self):
        """localhost must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|internal"):
            channel.read("http://localhost:8080/admin")

    def test_rejects_127_loopback(self):
        """127.0.0.1 must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal"):
            channel.read("http://127.0.0.1:8080/")

    def test_rejects_private_ip_10_range(self):
        """10.x.x.x (private) must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal"):
            channel.read("http://10.0.0.1/internal-service")

    def test_rejects_private_ip_192_168_range(self):
        """192.168.x.x (private) must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal"):
            channel.read("http://192.168.1.1/router")

    def test_rejects_private_ip_172_range(self):
        """172.16-31.x.x (private) must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal"):
            channel.read("http://172.16.0.1/internal")

    def test_rejects_google_metadata_host(self):
        """metadata.google.internal must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|internal"):
            channel.read("http://metadata.google.internal/computeMetadata/v1/")

    def test_rejects_0000(self):
        """0.0.0.0 must be blocked."""
        channel = WebChannel()
        with pytest.raises(TranscribeError, match="SSRF|private|internal|unspecified"):
            channel.read("http://0.0.0.0/")

    def test_allows_public_url(self):
        """Public URLs must pass the SSRF check and proceed to fetch."""
        channel = WebChannel()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"# Page content"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = channel.read("https://example.com/article")

            assert "Page content" in result
            # Verify the Jina Reader URL was constructed correctly
            called_url = mock_urlopen.call_args[0][0].full_url
            assert "r.jina.ai" in called_url
            assert "example.com/article" in called_url

    def test_allows_public_url_without_scheme(self):
        """URLs without http:// prefix should get https:// prepended and pass."""
        channel = WebChannel()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"# Content"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = channel.read("example.com/page")

            assert "Content" in result

    def test_does_not_fetch_before_ssrf_check(self):
        """urlopen must NOT be called when URL is blocked (SSRF check runs first)."""
        channel = WebChannel()
        with patch("urllib.request.urlopen") as mock_urlopen:
            with pytest.raises(TranscribeError):
                channel.read("http://169.254.169.254/latest/meta-data/")
            mock_urlopen.assert_not_called()
