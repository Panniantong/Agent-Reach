# -*- coding: utf-8 -*-
"""Tests for Agent Reach CLI."""

import shutil
import subprocess
from argparse import Namespace
from unittest.mock import patch

import pytest
import requests

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

    def test_doctor_runs(self, capsys):
        with patch("sys.argv", ["agent-reach", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "Agent Reach" in captured.out
        assert "✅" in captured.out

    def test_doctor_is_read_only_no_skill_install(self, monkeypatch, capsys):
        """doctor is read-only diagnostics: it must never install the skill."""
        called = {"install": False}

        def _spy(*a, **k):
            called["install"] = True

        monkeypatch.setattr(cli, "_install_skill", _spy)
        monkeypatch.setattr("agent_reach.doctor.check_all", lambda config: {})
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda results: "report")

        cli._cmd_doctor(Namespace(json=False))

        assert called["install"] is False

    def test_transcribe_command_prints_text(self, capsys):
        with patch("agent_reach.transcribe.transcribe", return_value="hello transcript"):
            with patch("sys.argv", ["agent-reach", "transcribe", "audio.mp3"]):
                main()
        captured = capsys.readouterr()
        assert "hello transcript" in captured.out

    def test_transcribe_command_writes_output_file(self, capsys, tmp_path):
        out_file = tmp_path / "t.txt"
        with patch("agent_reach.transcribe.transcribe", return_value="saved text"):
            with patch("sys.argv", ["agent-reach", "transcribe", "audio.mp3", "-o", str(out_file)]):
                main()
        assert out_file.read_text(encoding="utf-8").strip() == "saved text"
        assert "Transcript written" in capsys.readouterr().out

    def test_configure_from_browser_without_channels_imports_all(self, monkeypatch, capsys):
        """Softer landing: omitting --channels keeps the original import-all flow,
        so existing `configure --from-browser chrome` invocations don't break."""
        captured = {}

        def _spy(browser, config, config_keys):
            captured["targets"] = set(config_keys)
            return [("Twitter/X", True, "auth_token + ct0")]

        monkeypatch.setattr("agent_reach.cookie_extract.configure_from_browser", _spy)
        cli._cmd_configure(
            Namespace(from_browser="chrome", channels="", key=None, value=[])
        )
        assert captured["targets"] == {"twitter", "xhs", "bilibili", "xueqiu"}

    def test_configure_from_browser_scopes_to_requested_channels(self, monkeypatch, capsys):
        """--channels twitter must pass only {'twitter'} targets to the importer."""
        captured = {}

        def _spy(browser, config, config_keys):
            captured["browser"] = browser
            captured["targets"] = set(config_keys)
            return [("Twitter/X", True, "auth_token + ct0")]

        monkeypatch.setattr("agent_reach.cookie_extract.configure_from_browser", _spy)
        cli._cmd_configure(
            Namespace(from_browser="chrome", channels="twitter", key=None, value=[])
        )
        assert captured["targets"] == {"twitter"}
        assert captured["browser"] == "chrome"

    def test_install_mcporter_pins_exa_add_to_home_scope(self, monkeypatch):
        """config add must target home scope so Exa persists for the agent,
        not the cwd's project config. config list must NOT get --scope
        (mcporter's config list does not support that flag)."""
        calls = []

        monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/mcporter")

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        cli._install_mcporter()

        add_cmds = [c for c in calls if "config" in c and "add" in c]
        assert add_cmds, "expected a 'mcporter config add' call"
        for c in add_cmds:
            assert "--scope" in c and c[c.index("--scope") + 1] == "home"

        list_cmds = [c for c in calls if c[:3] == ["mcporter", "config", "list"]]
        assert list_cmds, "expected a 'mcporter config list' call"
        for c in list_cmds:
            assert "--scope" not in c

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

    def test_install_rdt_cli_prefers_github_source(self, monkeypatch, capsys):
        state = {"rdt_installed": False}
        commands = []

        def fake_which(name):
            if name == "rdt":
                return "/usr/local/bin/rdt" if state["rdt_installed"] else None
            if name == "pipx":
                return "/usr/local/bin/pipx"
            return None

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            state["rdt_installed"] = True
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(shutil, "which", fake_which)
        monkeypatch.setattr(subprocess, "run", fake_run)

        cli._install_rdt_cli()

        out = capsys.readouterr().out
        assert commands == [["pipx", "install", cli._RDT_GIT_SOURCE]]
        assert "✅ rdt-cli installed" in out

    def test_install_reddit_deps_routes_by_environment(self, monkeypatch):
        """桌面 → OpenCLI;服务器 → rdt-cli(钉 git 源)。"""
        calls = []
        monkeypatch.setattr(cli, "_install_opencli_deps", lambda: calls.append("opencli"))
        monkeypatch.setattr(cli, "_install_rdt_cli", lambda: calls.append("rdt"))
        monkeypatch.setattr(shutil, "which", lambda _: None)

        monkeypatch.setattr(cli, "_detect_environment", lambda: "local")
        cli._install_reddit_deps()
        assert calls == ["opencli"]

        calls.clear()
        monkeypatch.setattr(cli, "_detect_environment", lambda: "server")
        cli._install_reddit_deps()
        assert calls == ["rdt"]

    def test_install_facebook_instagram_routes_to_opencli_once(self, monkeypatch, capsys):
        calls = []

        monkeypatch.setattr(cli, "_detect_environment", lambda: "local")
        monkeypatch.setattr(cli, "_install_system_deps", lambda: None)
        monkeypatch.setattr(cli, "_install_mcporter", lambda: None)
        monkeypatch.setattr(cli, "_install_opencli_deps", lambda: calls.append("opencli"))
        monkeypatch.setattr(cli, "_install_skill", lambda: None)
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda config: {
                "facebook": {
                    "status": "ok",
                    "name": "Facebook",
                    "message": "ok",
                    "tier": 1,
                    "backends": ["OpenCLI"],
                    "active_backend": "OpenCLI",
                }
            },
        )
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda results: "report")

        cli._cmd_install(
            Namespace(
                env="auto",
                proxy="",
                safe=False,
                dry_run=False,
                channels="facebook,instagram,opencli",
            )
        )

        assert calls == ["opencli"]
        assert "Installation complete" in capsys.readouterr().out

    def test_install_server_dry_run_skips_opencli_only_channels(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "_install_system_deps_dryrun", lambda: None)

        cli._cmd_install(
            Namespace(
                env="server",
                proxy="",
                safe=False,
                dry_run=True,
                channels="facebook,instagram,opencli,bilibili",
            )
        )

        out = capsys.readouterr().out
        assert "服务器环境跳过：facebook, instagram, opencli" in out
        assert "[dry-run] Would install optional channels: bilibili" in out
        assert "facebook, instagram, opencli, bilibili" not in out


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
            R(200, payload={"tag_name": "v1.5.0"}),
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


class TestVersionCompare:
    def test_newer_remote_triggers_update(self):
        assert cli._is_newer_version("1.5.0", "1.4.2") is True

    def test_equal_versions_no_update(self):
        assert cli._is_newer_version("1.5.0", "1.5.0") is False

    def test_local_ahead_of_release_no_downgrade_prompt(self):
        """发版窗口期本地装了 main(更新)时,不能提示"有更新"诱导降级。"""
        assert cli._is_newer_version("1.4.2", "1.5.0") is False

    def test_unparseable_falls_back_to_inequality(self):
        assert cli._is_newer_version("2026.06-beta", "1.5.0") is True
        assert cli._is_newer_version("1.5.0", "1.5.0-dev") is True


class TestWatchVersionCompare:
    def test_watch_does_not_prompt_downgrade(self, monkeypatch, capsys):
        """watch 与 check-update 同语义:本地领先远端 release 时不提示更新。"""
        class R:
            status_code = 200
            headers = {}

            @staticmethod
            def json():
                return {"tag_name": "v1.4.2", "body": ""}

        monkeypatch.setattr(cli, "_github_get_with_retry", lambda *a, **k: (R(), None, 1))
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda config: {"web": {"status": "ok", "name": "任意网页", "message": "ok",
                            "tier": 0, "backends": ["Jina Reader"], "active_backend": "Jina Reader"}},
        )
        cli._cmd_watch()
        out = capsys.readouterr().out
        assert "新版本可用" not in out
        assert "全部正常" in out
