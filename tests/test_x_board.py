# -*- coding: utf-8 -*-
"""Tests for the standalone X Board helper (scripts/x_board.py).

``scripts/`` is placed on sys.path by tests/conftest.py, so ``x_board`` imports
as a top-level module here.
"""

from datetime import datetime, timezone

import pytest
import x_board
from x_board import (
    AccountResult,
    Post,
    XBoardError,
    extract_display_name,
    fetch_handle,
    filter_original_posts,
    format_relative_time,
    load_cookies,
    main,
    normalize_post,
    parse_follow_list,
    render_html,
)

from agent_reach.config import Config

# ── Helpers / fixtures ───────────────────────────────────────────────────────


def _tweet(
    tid="111",
    text="hello world",
    name="Display Name",
    screen="someone",
    likes=5,
    retweets=2,
    created="2026-06-05T10:00:00+00:00",
    **extra,
):
    """Build a twitter-cli-shaped (camelCase) tweet dict."""
    d = {
        "id": tid,
        "text": text,
        "author": {"id": "1", "name": name, "screenName": screen, "verified": False},
        "metrics": {"likes": likes, "retweets": retweets, "replies": 0, "quotes": 0},
        "createdAt": "Fri Jun 05 10:00:00 +0000 2026",
        "createdAtISO": created,
        "isRetweet": False,
        "retweetedBy": None,
        "lang": "en",
    }
    d.update(extra)
    return d


def _envelope(items):
    """Wrap items in the twitter-cli success envelope."""
    return {"ok": True, "schema_version": "1", "data": items}


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ── U1: parse_follow_list ────────────────────────────────────────────────────


class TestParseFollowList:
    def test_strips_at_ignores_blanks_and_comments(self, tmp_path):
        f = tmp_path / "follow.txt"
        f.write_text(
            "@OpenAI\n"
            "\n"
            "# a comment\n"
            "  AnthropicAI  \n"
            "@sama\n",
            encoding="utf-8",
        )
        assert parse_follow_list(f) == ["OpenAI", "AnthropicAI", "sama"]

    def test_dedupes_case_insensitive_preserving_first_spelling(self, tmp_path):
        f = tmp_path / "follow.txt"
        f.write_text("OpenAI\n@openai\nSama\nsama\n", encoding="utf-8")
        assert parse_follow_list(f) == ["OpenAI", "Sama"]

    def test_preserves_case(self, tmp_path):
        f = tmp_path / "follow.txt"
        f.write_text("@CamelCaseHandle\n", encoding="utf-8")
        assert parse_follow_list(f) == ["CamelCaseHandle"]

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "follow.txt"
        f.write_text("\n#only comments\n  \n", encoding="utf-8")
        assert parse_follow_list(f) == []

    def test_missing_file_raises_with_path_and_sample(self, tmp_path):
        missing = tmp_path / "nope.txt"
        with pytest.raises(XBoardError) as exc:
            parse_follow_list(missing)
        msg = str(exc.value)
        assert str(missing) in msg
        assert "follow.sample.txt" in msg


# ── U1: load_cookies ─────────────────────────────────────────────────────────


class TestLoadCookies:
    def test_returns_pair_from_config(self, tmp_path):
        cfg = Config(config_path=tmp_path / "config.yaml")
        cfg.set("twitter_auth_token", "AUTHVALUE")
        cfg.set("twitter_ct0", "CT0VALUE")
        assert load_cookies(cfg) == ("AUTHVALUE", "CT0VALUE")

    def test_env_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TWITTER_AUTH_TOKEN", "env_auth")
        monkeypatch.setenv("TWITTER_CT0", "env_ct0")
        cfg = Config(config_path=tmp_path / "config.yaml")  # empty file
        assert load_cookies(cfg) == ("env_auth", "env_ct0")

    def test_missing_raises_with_hint(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TWITTER_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("TWITTER_CT0", raising=False)
        cfg = Config(config_path=tmp_path / "config.yaml")
        with pytest.raises(XBoardError) as exc:
            load_cookies(cfg)
        assert "configure twitter-cookies" in str(exc.value)


# ── U2: filter_original_posts ────────────────────────────────────────────────


class TestFilterOriginalPosts:
    def test_keeps_originals(self):
        items = [_tweet(tid="1", text="an original post")]
        assert filter_original_posts(items) == items

    def test_drops_isretweet_flag(self):
        items = [_tweet(tid="1"), _tweet(tid="2", isRetweet=True)]
        out = filter_original_posts(items)
        assert [i["id"] for i in out] == ["1"]

    def test_drops_retweeted_by(self):
        items = [_tweet(tid="1"), _tweet(tid="2", retweetedBy="someoneelse")]
        assert [i["id"] for i in filter_original_posts(items)] == ["1"]

    def test_drops_rt_text_prefix(self):
        items = [_tweet(tid="2", text="RT @other: look at this")]
        assert filter_original_posts(items) == []

    def test_drops_replies_via_raw_markers(self):
        # Defensive: raw x.com legacy shape (twitter-cli discards these, but be safe).
        items = [_tweet(tid="2", in_reply_to_status_id_str="999")]
        assert filter_original_posts(items) == []

    def test_drops_replies_via_leading_mention(self):
        items = [_tweet(tid="2", text="@friend totally agree")]
        assert filter_original_posts(items) == []

    def test_empty_input(self):
        assert filter_original_posts([]) == []


# ── U2: normalize_post ───────────────────────────────────────────────────────


class TestNormalizePost:
    def test_maps_fields_and_permalink(self):
        post = normalize_post(_tweet(tid="12345", text="hi", likes=7, retweets=3), "OpenAI")
        assert isinstance(post, Post)
        assert post.text == "hi"
        assert post.likes == 7
        assert post.retweets == 3
        assert post.permalink == "https://x.com/OpenAI/status/12345"

    def test_prefers_full_text_over_text(self):
        item = _tweet(text="short")
        item["full_text"] = "the longer canonical text"
        assert normalize_post(item, "x").text == "the longer canonical text"

    def test_missing_counts_default_zero(self):
        item = {"id": "1", "text": "no metrics here"}
        post = normalize_post(item, "x")
        assert post.likes == 0
        assert post.retweets == 0

    def test_uses_iso_created_at_when_present(self):
        post = normalize_post(_tweet(created="2026-06-05T10:00:00+00:00"), "x")
        assert post.created_at == "2026-06-05T10:00:00+00:00"

    def test_url_encodes_handle_in_permalink(self):
        # An unusual follow-list entry must not produce a malformed link.
        post = normalize_post(_tweet(tid="9"), "weird name/with#chars")
        assert post.permalink == "https://x.com/weird%20name%2Fwith%23chars/status/9"


class TestExtractDisplayName:
    def test_from_author(self):
        items = [_tweet(name="Sam A", screen="sama")]
        assert extract_display_name(items, "sama") == "Sam A"

    def test_fallback_to_handle(self):
        assert extract_display_name([], "ghost") == "@ghost"


# ── U2: fetch_handle (mocked subprocess) ─────────────────────────────────────


class TestFetchHandle:
    def test_success_normalizes_and_trims(self, monkeypatch):
        items = [_tweet(tid=str(i), text=f"post {i}") for i in range(12)]
        proc = _FakeProc(stdout=__import__("json").dumps(_envelope(items)))
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("OpenAI", 5, {"TWITTER_AUTH_TOKEN": "a", "TWITTER_CT0": "b"}, twitter_exe="twitter")
        assert res.error is None
        assert len(res.posts) == 5
        assert res.fetched_count == 5
        assert res.display_name == "Display Name"

    def test_filters_reposts_before_trim(self, monkeypatch):
        items = [_tweet(tid="1", text="orig")] + [_tweet(tid=str(i), isRetweet=True) for i in range(2, 8)]
        proc = _FakeProc(stdout=__import__("json").dumps(_envelope(items)))
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 10, {}, twitter_exe="twitter")
        assert [p.text for p in res.posts] == ["orig"]

    def test_passes_cookie_env(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            return _FakeProc(stdout=__import__("json").dumps(_envelope([_tweet()])))

        monkeypatch.setattr(x_board.subprocess, "run", fake_run)
        env = {"TWITTER_AUTH_TOKEN": "secret-auth", "TWITTER_CT0": "secret-ct0"}
        fetch_handle("OpenAI", 3, env, twitter_exe="twitter")
        assert captured["env"]["TWITTER_AUTH_TOKEN"] == "secret-auth"
        assert captured["env"]["TWITTER_CT0"] == "secret-ct0"
        assert "user-posts" in captured["cmd"]
        assert "OpenAI" in captured["cmd"]
        assert "--json" in captured["cmd"]

    def test_nonzero_exit_sets_error(self, monkeypatch):
        proc = _FakeProc(stdout="", stderr="boom", returncode=1)
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter")
        assert res.error is not None
        assert res.posts == []

    def test_api_error_envelope_sets_error(self, monkeypatch):
        env_err = {"ok": False, "schema_version": "1", "error": {"code": "api_error", "message": "rate limited"}}
        proc = _FakeProc(stdout=__import__("json").dumps(env_err), returncode=1)
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter")
        assert "rate limited" in res.error

    def test_nonzero_exit_with_parseable_json_sets_error(self, monkeypatch):
        # CLI exits non-zero but stdout is parseable, non-success JSON (a bare
        # list, no ok:true envelope). Must be treated as a failure, not success.
        proc = _FakeProc(stdout=__import__("json").dumps([_tweet()]), stderr="warn", returncode=1)
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter")
        assert res.error is not None
        assert res.posts == []
        assert res.fetched_count == 0

    def test_timeout_sets_error(self, monkeypatch):
        def boom(*a, **k):
            raise x_board.subprocess.TimeoutExpired(cmd="twitter", timeout=60)

        monkeypatch.setattr(x_board.subprocess, "run", boom)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter", timeout=60)
        assert res.error is not None
        assert "time" in res.error.lower()

    def test_invalid_json_sets_error(self, monkeypatch):
        proc = _FakeProc(stdout="not json at all", returncode=0)
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter")
        assert res.error is not None

    def test_empty_list_flagged(self, monkeypatch):
        proc = _FakeProc(stdout=__import__("json").dumps(_envelope([])))
        monkeypatch.setattr(x_board.subprocess, "run", lambda *a, **k: proc)
        res = fetch_handle("x", 5, {}, twitter_exe="twitter")
        assert res.error is not None
        assert res.posts == []

    def test_missing_twitter_exe(self, monkeypatch):
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: None)
        res = fetch_handle("x", 5, {}, twitter_exe=None)
        assert res.error is not None
        assert "twitter" in res.error.lower()


# ── U3: format_relative_time ─────────────────────────────────────────────────


class TestFormatRelativeTime:
    NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)

    def test_seconds_to_now(self):
        dt = "2026-06-05T11:59:30+00:00"
        assert format_relative_time(dt, self.NOW) == "now"

    def test_minutes(self):
        assert format_relative_time("2026-06-05T11:30:00+00:00", self.NOW) == "30m"

    def test_hours(self):
        assert format_relative_time("2026-06-05T09:00:00+00:00", self.NOW) == "3h"

    def test_days(self):
        assert format_relative_time("2026-06-03T12:00:00+00:00", self.NOW) == "2d"

    def test_old_returns_absolute_date(self):
        out = format_relative_time("2026-01-01T12:00:00+00:00", self.NOW)
        assert "2026" in out and out not in ("now",) and "d" != out[-1:]

    def test_twitter_native_format(self):
        out = format_relative_time("Fri Jun 05 09:00:00 +0000 2026", self.NOW)
        assert out == "3h"

    def test_unparseable_falls_back_to_raw(self):
        assert format_relative_time("garbage-timestamp", self.NOW) == "garbage-timestamp"

    def test_empty_returns_empty(self):
        assert format_relative_time("", self.NOW) == ""


# ── U3: render_html ──────────────────────────────────────────────────────────


def _result(handle="OpenAI", name="OpenAI", posts=None, error=None):
    posts = posts or []
    return AccountResult(
        handle=handle,
        display_name=name,
        posts=posts,
        error=error,
        fetched_count=len(posts),
    )


GEN_AT = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)


class TestRenderHtml:
    def test_structure_and_badge(self):
        post = Post(text="hello board", created_at="2026-06-05T11:00:00+00:00",
                    likes=10, retweets=2, permalink="https://x.com/OpenAI/status/1")
        html_doc = render_html([_result(posts=[post])], GEN_AT)
        assert "<!DOCTYPE html>" in html_doc
        assert "@OpenAI" in html_doc
        assert "1 posts fetched" in html_doc
        assert "hello board" in html_doc
        assert "https://x.com/OpenAI/status/1" in html_doc

    def test_escapes_dangerous_content(self):
        post = Post(text="<script>alert(1)</script> & \"quotes\"",
                    created_at="2026-06-05T11:00:00+00:00", likes=0, retweets=0,
                    permalink="https://x.com/x/status/1")
        html_doc = render_html([_result(handle="ev<il", name="<b>boom</b>", posts=[post])], GEN_AT)
        assert "<script>alert(1)</script>" not in html_doc
        assert "&lt;script&gt;" in html_doc
        assert "<b>boom</b>" not in html_doc

    def test_partial_failure_status_and_error_card(self):
        ok = _result(handle="OpenAI", posts=[Post("hi", "2026-06-05T11:00:00+00:00", 1, 1, "https://x.com/OpenAI/status/1")])
        bad = _result(handle="ghost", name="@ghost", error="rate limited")
        html_doc = render_html([ok, bad], GEN_AT)
        assert "rate limited" in html_doc
        assert "configure twitter-cookies" in html_doc  # remediation hint
        assert "1 of 2" in html_doc  # M of N

    def test_all_ok_status(self):
        ok = _result(posts=[Post("hi", "2026-06-05T11:00:00+00:00", 1, 1, "https://x.com/OpenAI/status/1")])
        html_doc = render_html([ok], GEN_AT)
        assert "All 1" in html_doc or "All accounts OK" in html_doc

    def test_no_credentials_in_output(self):
        # render_html only ever receives AccountResult — never cookies. Even if a
        # token-like value lived in a post, it would be escaped, but structurally
        # the renderer cannot leak cookies. Assert the known token sentinel is absent.
        ok = _result(posts=[Post("normal post", "2026-06-05T11:00:00+00:00", 0, 0, "https://x.com/OpenAI/status/1")])
        html_doc = render_html([ok], GEN_AT)
        assert "auth_token" not in html_doc
        assert "ct0" not in html_doc


# ── U4: main / CLI orchestration ─────────────────────────────────────────────


class TestMain:
    def _setup_follow(self, tmp_path, handles=("OpenAI", "AnthropicAI")):
        f = tmp_path / "follow.txt"
        f.write_text("\n".join(handles) + "\n", encoding="utf-8")
        return f

    def test_happy_path_writes_and_opens(self, tmp_path, monkeypatch):
        follow = self._setup_follow(tmp_path)
        out = tmp_path / "board.html"
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: "twitter")
        monkeypatch.setattr(
            x_board, "fetch_handle",
            lambda h, *a, **k: _result(handle=h, posts=[Post("hi", "2026-06-05T11:00:00+00:00", 1, 1, f"https://x.com/{h}/status/1")]),
        )
        opened = {}
        monkeypatch.setattr(x_board.webbrowser, "open", lambda url: opened.setdefault("url", url))
        rc = main(["--file", str(follow), "--out", str(out)])
        assert rc == 0
        assert out.exists()
        assert "OpenAI" in out.read_text(encoding="utf-8")
        assert "url" in opened

    def test_no_open_suppresses_browser(self, tmp_path, monkeypatch):
        follow = self._setup_follow(tmp_path)
        out = tmp_path / "board.html"
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: "twitter")
        monkeypatch.setattr(x_board, "fetch_handle", lambda h, *a, **k: _result(handle=h, posts=[Post("hi", "2026-06-05T11:00:00+00:00", 0, 0, "https://x.com/x/status/1")]))
        called = {"n": 0}
        monkeypatch.setattr(x_board.webbrowser, "open", lambda url: called.__setitem__("n", called["n"] + 1))
        rc = main(["--file", str(follow), "--out", str(out), "--no-open"])
        assert rc == 0
        assert called["n"] == 0

    def test_partial_returns_1(self, tmp_path, monkeypatch):
        follow = self._setup_follow(tmp_path, handles=("good", "bad"))
        out = tmp_path / "board.html"
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: "twitter")

        def fake_fetch(h, *a, **k):
            if h == "bad":
                return _result(handle=h, name="@bad", error="boom")
            return _result(handle=h, posts=[Post("hi", "2026-06-05T11:00:00+00:00", 0, 0, "https://x.com/good/status/1")])

        monkeypatch.setattr(x_board, "fetch_handle", fake_fetch)
        monkeypatch.setattr(x_board.webbrowser, "open", lambda url: None)
        rc = main(["--file", str(follow), "--out", str(out), "--no-open"])
        assert rc == 1
        assert out.exists()

    def test_missing_follow_file_returns_2(self, tmp_path, monkeypatch):
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        rc = main(["--file", str(tmp_path / "nope.txt"), "--out", str(tmp_path / "o.html"), "--no-open"])
        assert rc == 2

    def test_missing_cookies_returns_2(self, tmp_path, monkeypatch):
        follow = self._setup_follow(tmp_path)

        def boom(*a, **k):
            raise XBoardError("No Twitter/X cookies found")

        monkeypatch.setattr(x_board, "load_cookies", boom)
        rc = main(["--file", str(follow), "--out", str(tmp_path / "o.html"), "--no-open"])
        assert rc == 2

    def test_empty_follow_file_returns_2(self, tmp_path, monkeypatch):
        follow = tmp_path / "follow.txt"
        follow.write_text("# only comments\n\n", encoding="utf-8")
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        rc = main(["--file", str(follow), "--out", str(tmp_path / "o.html"), "--no-open"])
        assert rc == 2

    def test_respects_count_argument(self, tmp_path, monkeypatch):
        follow = self._setup_follow(tmp_path, handles=("OpenAI",))
        out = tmp_path / "board.html"
        seen = {}
        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: "twitter")

        def fake_fetch(h, count, env, **k):
            seen["count"] = count
            return _result(handle=h, posts=[])

        monkeypatch.setattr(x_board, "fetch_handle", fake_fetch)
        monkeypatch.setattr(x_board.webbrowser, "open", lambda url: None)
        main(["--file", str(follow), "--out", str(out), "-n", "3", "--no-open"])
        assert seen["count"] == 3


class TestIntegration:
    def test_end_to_end_with_mocked_subprocess(self, tmp_path, monkeypatch):
        """No mocks on the filter/normalize/render chain — only the subprocess."""
        follow = tmp_path / "follow.txt"
        follow.write_text("OpenAI\nAnthropicAI\n", encoding="utf-8")
        out = tmp_path / "board.html"

        def fake_run(cmd, **kwargs):
            # cmd is [exe, "user-posts", handle, "-n", N, "--json"]
            handle = cmd[2]
            items = [
                _tweet(tid="1", text=f"{handle} original post", name=handle, screen=handle),
                _tweet(tid="2", text="RT @x: a repost", isRetweet=True),
            ]
            return _FakeProc(stdout=__import__("json").dumps(_envelope(items)))

        monkeypatch.setattr(x_board, "load_cookies", lambda *a, **k: ("a", "b"))
        monkeypatch.setattr(x_board, "resolve_twitter_exe", lambda: "twitter")
        monkeypatch.setattr(x_board.subprocess, "run", fake_run)
        monkeypatch.setattr(x_board.webbrowser, "open", lambda url: None)

        rc = main(["--file", str(follow), "--out", str(out), "--no-open"])
        doc = out.read_text(encoding="utf-8")
        assert rc == 0
        assert "OpenAI original post" in doc
        assert "AnthropicAI original post" in doc
        assert "a repost" not in doc  # repost filtered out
        assert "1 posts fetched" in doc
