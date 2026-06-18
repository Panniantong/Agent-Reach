# -*- coding: utf-8 -*-
"""Tests for TelegramChannel — URL routing, health check, and post parsing."""

from unittest.mock import patch, Mock, MagicMock
import io

from agent_reach.channels.telegram import TelegramChannel


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

SAMPLE_HTML = """\
<html><body>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message " data-post="durov/301">
    <div class="tgme_widget_message_text">First post content</div>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message " data-post="durov/302">
    <div class="tgme_widget_message_text">Second post content</div>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message " data-post="durov/303">
    <div class="tgme_widget_message_text">Third post content</div>
  </div>
</div>
</body></html>
"""


def _mock_urlopen(html: str = SAMPLE_HTML):
    """Return a context-manager mock for urllib.request.urlopen."""
    resp = MagicMock()
    resp.read.return_value = html.encode("utf-8")
    resp.__enter__ = Mock(return_value=resp)
    resp.__exit__ = Mock(return_value=False)
    return resp


# ------------------------------------------------------------------ #
# can_handle() tests
# ------------------------------------------------------------------ #

def test_can_handle_t_me():
    ch = TelegramChannel()
    assert ch.can_handle("https://t.me/durov") is True


def test_can_handle_t_me_with_post():
    ch = TelegramChannel()
    assert ch.can_handle("https://t.me/durov/123") is True


def test_can_handle_telegram_me():
    ch = TelegramChannel()
    assert ch.can_handle("https://telegram.me/some_channel") is True


def test_can_handle_t_me_s_preview():
    ch = TelegramChannel()
    assert ch.can_handle("https://t.me/s/durov") is True


def test_cannot_handle_github():
    ch = TelegramChannel()
    assert ch.can_handle("https://github.com/user/repo") is False


def test_cannot_handle_youtube():
    ch = TelegramChannel()
    assert ch.can_handle("https://youtube.com/watch?v=abc") is False


# ------------------------------------------------------------------ #
# check() tests
# ------------------------------------------------------------------ #

def test_check_ok_html_preview():
    """Direct HTML preview works → status ok, backend = Telegram Web Preview."""
    ch = TelegramChannel()
    mock_resp = _mock_urlopen('<div class="tgme_widget_message">test</div>')
    with patch("urllib.request.urlopen", return_value=mock_resp):
        status, msg = ch.check()
    assert status == "ok"
    assert "公开频道预览可用" in msg
    assert ch.active_backend == "Telegram Web Preview"


def test_check_fallback_to_jina():
    """HTML preview fails → fall back to Jina Reader."""
    ch = TelegramChannel()
    call_count = 0

    def side_effect(req, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("blocked")
        return _mock_urlopen("x" * 200)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        status, msg = ch.check()
    assert status == "ok"
    assert "Jina Reader" in msg
    assert ch.active_backend == "Jina Reader"


def test_check_all_fail():
    """Both backends fail → warn."""
    ch = TelegramChannel()
    with patch("urllib.request.urlopen", side_effect=ConnectionError("blocked")):
        status, msg = ch.check()
    assert status == "warn"
    assert ch.active_backend is None


# ------------------------------------------------------------------ #
# read_channel() tests
# ------------------------------------------------------------------ #

def test_read_channel_parses_posts():
    """Parses message text and post IDs from sample HTML."""
    ch = TelegramChannel()
    mock_resp = _mock_urlopen(SAMPLE_HTML)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        posts = ch.read_channel("durov", limit=10)

    assert len(posts) == 3
    # Newest first (reversed)
    assert posts[0]["post_id"] == "303"
    assert posts[0]["text"] == "Third post content"
    assert posts[0]["url"] == "https://t.me/durov/303"

    assert posts[2]["post_id"] == "301"
    assert posts[2]["text"] == "First post content"


def test_read_channel_respects_limit():
    """Limit caps the number of returned posts."""
    ch = TelegramChannel()
    mock_resp = _mock_urlopen(SAMPLE_HTML)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        posts = ch.read_channel("durov", limit=2)

    assert len(posts) == 2


def test_read_channel_strips_at_sign():
    """Channel name with @ prefix is handled correctly."""
    ch = TelegramChannel()
    mock_resp = _mock_urlopen(SAMPLE_HTML)
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        ch.read_channel("@durov", limit=5)
    # Verify the URL does not contain @
    call_args = mock_open.call_args
    req_obj = call_args[0][0]
    assert "@" not in req_obj.full_url


# ------------------------------------------------------------------ #
# read_post() tests
# ------------------------------------------------------------------ #

def test_read_post_via_jina():
    """read_post fetches through Jina Reader."""
    ch = TelegramChannel()
    mock_resp = _mock_urlopen("Post content in markdown")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = ch.read_post("durov", 123)

    assert result["post_id"] == "123"
    assert result["channel"] == "durov"
    assert result["url"] == "https://t.me/durov/123"


# ------------------------------------------------------------------ #
# search() tests
# ------------------------------------------------------------------ #

def test_search_returns_error_suggestion():
    """search() returns a helpful error with Exa suggestion."""
    ch = TelegramChannel()
    results = ch.search("crypto news")
    assert len(results) == 1
    assert "error" in results[0]
    assert "Exa" in results[0]["error"]
    assert "site:t.me" in results[0]["error"]


# ------------------------------------------------------------------ #
# Channel metadata tests
# ------------------------------------------------------------------ #

def test_channel_metadata():
    ch = TelegramChannel()
    assert ch.name == "telegram"
    assert ch.tier == 0
    assert len(ch.backends) == 2
    assert "Telegram Web Preview" in ch.backends
    assert "Jina Reader" in ch.backends
