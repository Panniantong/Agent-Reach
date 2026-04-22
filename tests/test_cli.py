# -*- coding: utf-8 -*-
"""Tests for Agent Reach CLI."""

import pytest
import requests
from unittest.mock import patch
import agent_reach.cli as cli
from agent_reach.cli import main


class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["agent-reach", "version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Agent Reach v" in captured.out

    def test_no_command_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["agent-reach"]):
                main()
        assert exc_info.value.code == 0

    def test_doctor_runs(self, capsys):
        with patch("sys.argv", ["agent-reach", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "Agent Reach" in captured.out
        assert "✅" in captured.out

    def test_parse_twitter_cookie_input_separate_values(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input("token123 ct0abc")
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_parse_twitter_cookie_input_cookie_header(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input(
            "auth_token=token123; ct0=ct0abc; other=value"
        )
        assert auth_token == "token123"
        assert ct0 == "ct0abc"


class TestGroqKeyValidation:
    def test_looks_like_groq_key_accepts_gsk_prefix(self):
        assert cli._looks_like_groq_key("gsk_abc123")

    def test_looks_like_groq_key_rejects_openai_prefix(self):
        assert not cli._looks_like_groq_key("sk-abc123")

    def test_looks_like_groq_key_rejects_empty(self):
        assert not cli._looks_like_groq_key("")

    def test_configure_groq_key_rejects_bad_prefix(self, capsys):
        saved = {}

        class _FakeConfig:
            def set(self, key, value):
                saved[key] = value

        fake = _FakeConfig()
        args = type(
            "Args",
            (),
            {"key": "groq-key", "value": ["sk-not-a-groq-key"], "from_browser": None},
        )()

        with patch("agent_reach.config.Config", return_value=fake):
            cli._cmd_configure(args)

        out = capsys.readouterr().out
        assert "gsk_" in out
        assert "groq_api_key" not in saved  # key must not be persisted

    def test_configure_groq_key_accepts_good_prefix(self, capsys):
        saved = {}

        class _FakeConfig:
            def set(self, key, value):
                saved[key] = value

        fake = _FakeConfig()
        args = type(
            "Args",
            (),
            {"key": "groq-key", "value": ["gsk_looksfine"], "from_browser": None},
        )()

        with patch("agent_reach.config.Config", return_value=fake):
            cli._cmd_configure(args)

        out = capsys.readouterr().out
        assert "✅ Groq key configured" in out
        assert saved["groq_api_key"] == "gsk_looksfine"


class TestCheckUpdateRetry:
    def test_retry_timeout_classification(self):
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                timeout=1,
                retries=3,
                sleeper=fake_sleep,
            )

        assert resp is None
        assert err == "timeout"
        assert attempts == 3
        assert sleeps == [1, 2]

    def test_retry_dns_classification(self):
        error = requests.exceptions.ConnectionError("getaddrinfo failed for api.github.com")
        with patch("requests.get", side_effect=error):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=1,
                sleeper=lambda _x: None,
            )
        assert resp is None
        assert err == "dns"
        assert attempts == 1

    def test_retry_rate_limit_then_success(self):
        sleeps = []

        class R:
            def __init__(self, code, payload=None, headers=None):
                self.status_code = code
                self._payload = payload or {}
                self.headers = headers or {}

            def json(self):
                return self._payload

        sequence = [
            R(429, headers={"Retry-After": "3"}),
            R(200, payload={"tag_name": "v1.4.0"}),
        ]

        with patch("requests.get", side_effect=sequence):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=3,
                sleeper=lambda s: sleeps.append(s),
            )

        assert err is None
        assert resp is not None
        assert resp.status_code == 200
        assert attempts == 2
        assert sleeps == [3.0]

    def test_classify_rate_limit_from_403(self):
        class R:
            status_code = 403
            headers = {"X-RateLimit-Remaining": "0"}

            @staticmethod
            def json():
                return {"message": "API rate limit exceeded"}

        assert cli._classify_github_response_error(R()) == "rate_limit"

    def test_check_update_reports_classified_error(self, capsys):
        with patch("agent_reach.cli._github_get_with_retry", return_value=(None, "timeout", 3)):
            result = cli._cmd_check_update()

        captured = capsys.readouterr()
        assert result == "error"
        assert "网络超时" in captured.out
        assert "已重试 3 次" in captured.out
