# -*- coding: utf-8 -*-
"""Tests for the Windows/Codex CLI surface."""

from unittest.mock import patch

import pytest

import agent_reach.cli as cli
from agent_reach.cli import main


class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["version"])
        assert exc_info.value.code == 0
        assert "Agent Reach v" in capsys.readouterr().out

    def test_no_command_shows_help(self):
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0

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

    def test_safe_install_lists_windows_commands(self, capsys, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _name: None)
        monkeypatch.setattr("agent_reach.cli.find_command", lambda _name: None)
        with patch("agent_reach.cli.render_ytdlp_fix_command", return_value="FIX-YTDLP"):
            main(["install", "--safe", "--channels=twitter"])
        output = capsys.readouterr().out
        assert "GitHub.cli" in output
        assert "yt-dlp.yt-dlp" in output
        assert "npm install -g mcporter" in output
        assert ".mcporter\\mcporter.json" in output
        assert "uv tool install twitter-cli" in output
        assert "FIX-YTDLP" in output

    def test_install_parses_all_as_twitter(self, monkeypatch):
        calls = []

        monkeypatch.setattr(cli, "_ensure_gh_cli", lambda: True)
        monkeypatch.setattr(cli, "_ensure_ytdlp", lambda: True)
        monkeypatch.setattr(cli, "_ensure_nodejs", lambda: True)
        monkeypatch.setattr(cli, "_ensure_mcporter", lambda: True)
        monkeypatch.setattr(cli, "_ensure_exa_config", lambda: True)
        monkeypatch.setattr(cli, "_ensure_ytdlp_js_runtime", lambda: True)
        monkeypatch.setattr(cli, "_install_skill", lambda: [])
        monkeypatch.setattr(cli, "_detect_environment", lambda: "local")
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(
            cli,
            "_install_twitter_deps",
            lambda: calls.append("twitter") or True,
        )
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config: {
                "web": {"status": "ok", "name": "Any web page", "message": "ok", "tier": 0, "backends": []}
            },
        )
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _results: "report")

        main(["install", "--channels=all"])
        assert calls == ["twitter"]


class TestCheckUpdateRetry:
    def test_retry_timeout_classification(self):
        sleeps = []
        requests = cli._import_requests()

        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                timeout=1,
                retries=3,
                sleeper=lambda seconds: sleeps.append(seconds),
            )

        assert resp is None
        assert err == "timeout"
        assert attempts == 3
        assert sleeps == [1, 2]

    def test_retry_dns_classification(self):
        requests = cli._import_requests()
        error = requests.exceptions.ConnectionError("getaddrinfo failed for api.github.com")
        with patch("requests.get", side_effect=error):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=1,
                sleeper=lambda _seconds: None,
            )
        assert resp is None
        assert err == "dns"
        assert attempts == 1

    def test_retry_rate_limit_then_success(self):
        sleeps = []

        class Response:
            def __init__(self, code, payload=None, headers=None):
                self.status_code = code
                self._payload = payload or {}
                self.headers = headers or {}

            def json(self):
                return self._payload

        sequence = [
            Response(429, headers={"Retry-After": "3"}),
            Response(200, payload={"tag_name": "v1.4.0"}),
        ]

        with patch("requests.get", side_effect=sequence):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=3,
                sleeper=lambda seconds: sleeps.append(seconds),
            )

        assert err is None
        assert resp is not None
        assert resp.status_code == 200
        assert attempts == 2
        assert sleeps == [3.0]

    def test_classify_rate_limit_from_403(self):
        class Response:
            status_code = 403
            headers = {"X-RateLimit-Remaining": "0"}

            @staticmethod
            def json():
                return {"message": "API rate limit exceeded"}

        assert cli._classify_github_response_error(Response()) == "rate_limit"
