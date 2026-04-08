# -*- coding: utf-8 -*-
"""Tests for Agent Reach CLI."""

from pathlib import Path
import pytest
import requests
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
import agent_reach.cli as cli
from agent_reach.cli import main
from agent_reach.config import Config


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

    def test_doctor_runs(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "CONFIG_DIR", Path(tmp_path) / ".agent-reach")
        monkeypatch.setattr(Config, "CONFIG_FILE", Path(tmp_path) / ".agent-reach" / "config.yaml")
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
            R(200, payload={"tag_name": "v1.3.0"}),
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


class TestCliXianyuFlows:
    def test_install_mcporter_mentions_optional_xianyu_setup(self, monkeypatch, capsys):
        def fake_which(cmd):
            return f"/usr/bin/{cmd}" if cmd in {"mcporter", "npx"} else None

        def fake_run(cmd, **kwargs):
            if cmd == ["mcporter", "config", "list"]:
                return subprocess.CompletedProcess(cmd, 0, "exa\n", "")
            raise AssertionError(f"unexpected command: {cmd}")

        monkeypatch.setattr("shutil.which", fake_which)
        monkeypatch.setattr("subprocess.run", fake_run)

        cli._install_mcporter()

        captured = capsys.readouterr()
        assert "Xianyu MCP not configured yet" in captured.out
        assert "cookies/session" in captured.out

    def test_uninstall_removes_xianyu_mcporter_entries(self, monkeypatch, capsys):
        commands = []

        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/mcporter" if cmd == "mcporter" else None)
        monkeypatch.setattr("os.path.isdir", lambda path: False)
        monkeypatch.setattr("os.path.expanduser", lambda path: path)

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            if cmd == ["mcporter", "list"]:
                return subprocess.CompletedProcess(cmd, 0, "exa\nxianyu\ngoofish\n", "")
            if cmd[:3] == ["mcporter", "config", "remove"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise AssertionError(f"unexpected command: {cmd}")

        monkeypatch.setattr("subprocess.run", fake_run)

        cli._cmd_uninstall(SimpleNamespace(dry_run=False, keep_config=False))

        captured = capsys.readouterr()
        assert "Removed mcporter entry: xianyu" in captured.out
        assert "Removed mcporter entry: goofish" in captured.out
        assert ["mcporter", "config", "remove", "xianyu"] in commands
        assert ["mcporter", "config", "remove", "goofish"] in commands
