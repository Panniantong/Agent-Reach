# -*- coding: utf-8 -*-
"""Tests for the Windows/Codex CLI surface."""

import json
from pathlib import Path
from unittest.mock import patch

import agent_reach.cli as cli
from agent_reach.cli import main


class TestCLI:
    def test_version(self, capsys):
        assert main(["version"]) == 0
        assert "Agent Reach v" in capsys.readouterr().out

    def test_no_command_shows_help(self):
        assert main([]) == 0

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
            assert main(["install", "--safe", "--channels=twitter"]) == 0
        output = capsys.readouterr().out
        assert "GitHub.cli" in output
        assert "yt-dlp.yt-dlp" in output
        assert "npm install -g mcporter" in output
        assert ".mcporter" in output
        assert "mcporter.json" in output
        assert "uv tool install twitter-cli" in output
        assert "FIX-YTDLP" in output

    def test_install_dry_run_json(self, capsys, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _name: None)
        monkeypatch.setattr("agent_reach.cli.find_command", lambda _name: None)
        with patch("agent_reach.cli.render_ytdlp_fix_command", return_value="FIX-YTDLP"):
            assert main(["install", "--dry-run", "--json", "--channels=twitter"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "install"
        assert payload["mode"] == "dry-run"
        assert payload["selected_channels"] == ["twitter"]
        assert payload["channel_specific_setup_channels"] == ["twitter"]
        assert "FIX-YTDLP" in payload["commands"]
        assert payload["execution_context"] == "checkout"
        assert payload["plugin_manifest"] is not None
        assert payload["mcp_config"] is not None

    def test_install_parses_all_channels(self, monkeypatch):
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
            "_install_reddit_deps",
            lambda: calls.append("reddit") or True,
        )
        monkeypatch.setattr(
            cli,
            "_install_twitter_deps",
            lambda: calls.append("twitter") or True,
        )
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config: {
                "web": {
                    "status": "ok",
                    "name": "web",
                    "description": "Any web page",
                    "message": "ok",
                    "backends": [],
                }
            },
        )
        monkeypatch.setattr("agent_reach.doctor.format_report", lambda _results: "report")

        assert main(["install", "--channels=all"]) == 0
        assert calls == ["reddit", "twitter"]

    def test_doctor_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config, probe=False: {
                "web": {
                    "name": "web",
                    "description": "Any web page",
                    "status": "ok",
                    "message": "ready",
                }
            },
        )
        assert main(["doctor", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["ready"] == 1
        assert payload["summary"]["readiness_mode"] == "none"
        assert payload["summary"]["required_channels"] == []
        assert payload["summary"]["exit_code"] == 0
        assert payload["channels"][0]["name"] == "web"

    def test_doctor_require_all_and_require_channel_preserve_caller_control(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.doctor.check_all",
            lambda _config, probe=False: {
                "web": {
                    "name": "web",
                    "description": "Any web page",
                    "status": "ok",
                    "message": "ready",
                },
                "crawl4ai": {
                    "name": "crawl4ai",
                    "description": "Crawl4AI",
                    "status": "off",
                    "message": "missing extra",
                },
            },
        )

        assert main(["doctor", "--json"]) == 0
        default_payload = json.loads(capsys.readouterr().out)
        assert default_payload["summary"]["readiness_mode"] == "none"
        assert default_payload["summary"]["informational_not_ready"] == ["crawl4ai"]

        assert main(["doctor", "--json", "--require-channel", "crawl4ai"]) == 2
        required_payload = json.loads(capsys.readouterr().out)
        assert required_payload["summary"]["readiness_mode"] == "selected"
        assert required_payload["summary"]["required_channels"] == ["crawl4ai"]
        assert required_payload["summary"]["required_not_ready"] == ["crawl4ai"]

        assert main(["doctor", "--json", "--require-all"]) == 2
        strict_payload = json.loads(capsys.readouterr().out)
        assert strict_payload["summary"]["readiness_mode"] == "all"
        assert strict_payload["summary"]["required_not_ready"] == ["crawl4ai"]

    def test_collect_json_success(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": {"limit": limit},
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "github",
                    "--operation",
                    "read",
                    "--input",
                    "openai/openai-python",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["channel"] == "github"
        assert payload["items"][0]["url"] == "openai/openai-python"

    def test_collect_unknown_channel_returns_exit_2(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": False,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": None,
                    "meta": {"input": value},
                    "error": {
                        "code": "unknown_channel",
                        "message": "Unknown channel",
                        "details": {},
                    },
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "nope",
                    "--operation",
                    "read",
                    "--input",
                    "value",
                ]
            )
            == 2
        )
        output = capsys.readouterr().out
        assert "unknown_channel" in output

    def test_collect_read_with_limit_stays_json_safe(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": None,
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--limit",
                    "1",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["limit"] == 1

    def test_collect_max_text_chars_adds_text_mode_snippet(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [
                        {
                            "id": "1",
                            "title": "Example",
                            "url": value,
                            "text": "abcdefghijklmnopqrstuvwxyz",
                        }
                    ],
                    "raw": None,
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--max-text-chars",
                    "5",
                ]
            )
            == 0
        )
        output = capsys.readouterr().out
        assert "Example https://example.com" in output
        assert "abcde..." in output

    def test_collect_max_text_chars_rejects_invalid_value(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                raise AssertionError("collect should not run for invalid max-text-chars")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--max-text-chars",
                    "0",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "max-text-chars must be greater than or equal to 1" in captured.err

    def test_collect_json_max_text_chars_preserves_full_text(self, capsys, monkeypatch):
        full_text = "abcdefghijklmnopqrstuvwxyz"

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value, "text": full_text}],
                    "raw": None,
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--max-text-chars",
                    "5",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["items"][0]["text"] == full_text

    def test_collect_json_item_text_mode_none_omits_text(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value, "text": "abcdefghijklmnopqrstuvwxyz"}],
                    "raw": None,
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--item-text-mode",
                    "none",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["items"][0]["text"] is None
        assert payload["meta"]["item_text_mode"] == "none"

    def test_collect_json_item_text_max_chars_enables_snippet_mode(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value, "text": "abcdefghijklmnopqrstuvwxyz"}],
                    "raw": None,
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--item-text-max-chars",
                    "5",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["items"][0]["text"] == "abcde"
        assert payload["meta"]["item_text_mode"] == "snippet"
        assert payload["meta"]["item_text_max_chars"] == 5

    def test_collect_item_text_max_chars_rejects_invalid_value(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                raise AssertionError("collect should not run for invalid item-text-max-chars")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--item-text-max-chars",
                    "0",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "item-text-max-chars must be greater than or equal to 1" in captured.err

    def test_collect_item_text_max_chars_rejects_non_snippet_mode(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                raise AssertionError("collect should not run for item-text-max-chars without snippet mode")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--item-text-mode",
                    "none",
                    "--item-text-max-chars",
                    "5",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "item-text-max-chars is only supported with item-text-mode snippet" in captured.err

    def test_collect_json_save_writes_ledger_and_preserves_stdout(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": {"limit": limit},
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_path = tmp_path / ".agent-reach" / "evidence.jsonl"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--save",
                    str(ledger_path),
                    "--run-id",
                    "run-from-cli",
                ]
            )
            == 0
        )
        stdout_payload = json.loads(capsys.readouterr().out)
        ledger_record = json.loads(ledger_path.read_text(encoding="utf-8"))

        assert stdout_payload["ok"] is True
        assert stdout_payload["channel"] == "web"
        assert ledger_record["run_id"] == "run-from-cli"
        assert ledger_record["input"] == "https://example.com"
        assert ledger_record["item_ids"] == ["1"]
        assert ledger_record["urls"] == ["https://example.com"]
        assert ledger_record["result"] == stdout_payload

    def test_collect_json_save_dir_writes_execution_shard_and_preserves_stdout(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": {"limit": limit},
                    "meta": {"count": 1, "limit": limit},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_dir = tmp_path / ".agent-reach" / "shards"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--save-dir",
                    str(ledger_dir),
                    "--run-id",
                    "run-from-cli",
                ]
            )
            == 0
        )
        stdout_payload = json.loads(capsys.readouterr().out)
        shard_paths = sorted(ledger_dir.glob("*.jsonl"))

        assert stdout_payload["ok"] is True
        assert len(shard_paths) == 1
        ledger_record = json.loads(shard_paths[0].read_text(encoding="utf-8"))
        assert ledger_record["run_id"] == "run-from-cli"
        assert ledger_record["input"] == "https://example.com"
        assert ledger_record["result"] == stdout_payload

    def test_collect_raw_mode_none_applies_to_stdout_and_saved_ledger(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": {"large": "x" * 1000},
                    "meta": {"count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_path = tmp_path / "evidence.jsonl"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--json",
                    "--save",
                    str(ledger_path),
                    "--raw-mode",
                    "none",
                    "--intent",
                    "official_docs",
                    "--query-id",
                    "q01",
                    "--source-role",
                    "web_discovery",
                ]
            )
            == 0
        )
        stdout_payload = json.loads(capsys.readouterr().out)
        ledger_record = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert stdout_payload["raw"] is None
        assert stdout_payload["meta"]["raw_payload_omitted"] is True
        assert ledger_record["result"]["raw"] is None

    def test_collect_save_records_error_envelope(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": False,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": None,
                    "meta": {"input": value, "count": 0},
                    "error": {
                        "code": "unknown_channel",
                        "message": "Unknown channel",
                        "details": {},
                    },
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_path = tmp_path / "evidence.jsonl"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "nope",
                    "--operation",
                    "read",
                    "--input",
                    "value",
                    "--save",
                    str(ledger_path),
                    "--run-id",
                    "error-run",
                ]
            )
            == 2
        )
        assert "unknown_channel" in capsys.readouterr().out
        ledger_record = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert ledger_record["run_id"] == "error-run"
        assert ledger_record["ok"] is False
        assert ledger_record["error_code"] == "unknown_channel"
        assert ledger_record["result"]["error"]["code"] == "unknown_channel"

    def test_collect_save_warns_when_evidence_metadata_missing(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": None,
                    "meta": {"count": 0},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_path = tmp_path / "evidence.jsonl"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--save",
                    str(ledger_path),
                ]
            )
            == 0
        )
        captured = capsys.readouterr()
        assert "evidence metadata" in captured.err

    def test_collect_annotations_require_save(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                raise AssertionError("collect should not run without --save or --save-dir")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--intent",
                    "official_docs",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "require --save or --save-dir" in captured.err

    def test_collect_save_records_relevance_metadata(self, capsys, monkeypatch, tmp_path):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": None,
                    "meta": {"count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)
        ledger_path = tmp_path / "evidence.jsonl"

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--save",
                    str(ledger_path),
                    "--intent",
                    "official_docs",
                    "--query-id",
                    "q01",
                    "--source-role",
                    "web_discovery",
                ]
            )
            == 0
        )
        capsys.readouterr()
        record = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert record["intent"] == "official_docs"
        assert record["query_id"] == "q01"
        assert record["source_role"] == "web_discovery"

    def test_collect_body_mode_rejects_non_qiita_search(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                raise AssertionError("collect should not run for unsupported body-mode")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--body-mode",
                    "none",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "body-mode is only supported for qiita search" in captured.err

    def test_collect_body_mode_passes_to_qiita_search(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, body_mode=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": {"body_mode": body_mode},
                    "meta": {"input": value, "limit": limit, "body_mode": body_mode},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "qiita",
                    "--operation",
                    "search",
                    "--input",
                    "python",
                    "--limit",
                    "1",
                    "--body-mode",
                    "none",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["body_mode"] == "none"

    def test_collect_query_rejects_non_crawl4ai_crawl(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, crawl_query=None):
                raise AssertionError("collect should not run for unsupported query option")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "web",
                    "--operation",
                    "read",
                    "--input",
                    "https://example.com",
                    "--query",
                    "pricing",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "query is only supported for crawl4ai crawl" in captured.err

    def test_collect_crawl4ai_crawl_requires_query(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, crawl_query=None):
                raise AssertionError("collect should not run without crawl query")

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "crawl4ai",
                    "--operation",
                    "crawl",
                    "--input",
                    "https://example.com",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "crawl4ai crawl requires --query" in captured.err

    def test_collect_crawl4ai_query_passes_to_client(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, crawl_query=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": {"crawl_query": crawl_query},
                    "meta": {"input": value, "limit": limit, "crawl_query": crawl_query},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "crawl4ai",
                    "--operation",
                    "crawl",
                    "--input",
                    "https://example.com",
                    "--limit",
                    "3",
                    "--query",
                    "pricing faq",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["crawl_query"] == "pricing faq"

    def test_collect_pagination_options_pass_to_client(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, page_size=None, max_pages=None, page=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": {"page_size": page_size, "max_pages": max_pages, "page": page},
                    "meta": {
                        "input": value,
                        "limit": limit,
                        "page_size": page_size,
                        "max_pages": max_pages,
                        "page": page,
                    },
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "github",
                    "--operation",
                    "search",
                    "--input",
                    "agent reach",
                    "--limit",
                    "5",
                    "--page-size",
                    "2",
                    "--max-pages",
                    "3",
                    "--page",
                    "4",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["page_size"] == 2
        assert payload["meta"]["max_pages"] == 3
        assert payload["meta"]["page"] == 4

    def test_collect_time_window_options_pass_to_client(self, capsys, monkeypatch):
        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, since=None, until=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": {"since": since, "until": until},
                    "meta": {"input": value, "since": since, "until": until},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.cli.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "collect",
                    "--channel",
                    "twitter",
                    "--operation",
                    "search",
                    "--input",
                    "OpenAI",
                    "--since",
                    "2026-01-01",
                    "--until",
                    "2026-12-31",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["since"] == "2026-01-01"
        assert payload["meta"]["until"] == "2026-12-31"

    def test_plan_candidates_json(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [
                {
                    "id": "item-1",
                    "kind": "page",
                    "title": "Example",
                    "url": "https://example.com/post/",
                    "text": None,
                    "author": None,
                    "published_at": None,
                    "source": "web",
                    "extras": {},
                }
            ],
            "raw": None,
            "meta": {"input": "https://example.com/post/", "count": 1},
            "error": None,
        }
        record = {
            "record_type": "collection_result",
            "run_id": "run-1",
            "input": "https://example.com/post/",
            "result": result,
        }
        ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8-sig")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--by",
                    "url",
                    "--limit",
                    "10",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "plan candidates"
        assert payload["by"] == "url"
        assert payload["limit"] == 10
        assert payload["summary"]["candidate_count"] == 1
        assert payload["candidates"][0]["title"] == "Example"
        assert payload["candidates"][0]["extras"]["seen_in"][0]["run_id"] == "run-1"

    def test_plan_candidates_summary_only_json(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [
                {
                    "id": "item-1",
                    "kind": "page",
                    "title": "Example",
                    "url": "https://example.com",
                    "text": None,
                    "author": None,
                    "published_at": None,
                    "source": "web",
                    "extras": {},
                }
            ],
            "raw": None,
            "meta": {"input": "https://example.com", "count": 1},
            "error": None,
        }
        ledger_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--summary-only",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary_only"] is True
        assert payload["summary"]["candidate_count"] == 1
        assert payload["candidates"] == []

    def test_plan_candidates_fields_json(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [
                {
                    "id": "item-1",
                    "kind": "page",
                    "title": "Example",
                    "url": "https://example.com",
                    "text": None,
                    "author": None,
                    "published_at": None,
                    "source": "web",
                    "extras": {},
                }
            ],
            "raw": None,
            "meta": {"input": "https://example.com", "count": 1, "intent": "official_docs"},
            "error": None,
        }
        ledger_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--fields",
                    "title,url,intent",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["candidates"] == [
            {"title": "Example", "url": "https://example.com", "intent": "official_docs"}
        ]

    def test_plan_candidates_unknown_field_returns_exit_2(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        ledger_path.write_text("", encoding="utf-8")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--fields",
                    "title,nope",
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["command"] == "plan candidates"
        assert payload["fields"] == ["title", "nope"]
        assert payload["candidates"] == []
        assert payload["error"]["code"] == "candidate_plan_error"
        assert "Unsupported candidate field" in payload["error"]["message"]
        assert captured.err == ""

    def test_plan_candidates_text(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [
                {
                    "id": "item-1",
                    "kind": "page",
                    "title": "Example",
                    "url": "https://example.com",
                    "text": None,
                    "author": None,
                    "published_at": None,
                    "source": "web",
                    "extras": {},
                }
            ],
            "raw": None,
            "meta": {"input": "https://example.com", "count": 1},
            "error": None,
        }
        ledger_path.write_text(json.dumps(result) + "\n", encoding="utf-8")

        assert main(["plan", "candidates", "--input", str(ledger_path)]) == 0
        output = capsys.readouterr().out
        assert "Agent Reach Candidate Plan" in output
        assert "Candidates: 1/1" in output
        assert "Example https://example.com" in output

    def test_plan_candidates_missing_input_returns_exit_2(self, capsys, tmp_path):
        missing_path = tmp_path / "missing.jsonl"

        assert main(["plan", "candidates", "--input", str(missing_path), "--json"]) == 2
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["input"] == str(missing_path)
        assert payload["by"] == "url"
        assert payload["limit"] == 20
        assert payload["summary_only"] is False
        assert payload["fields"] is None
        assert payload["candidates"] == []
        assert payload["error"]["code"] == "candidate_plan_error"
        assert "Could not read evidence input" in payload["error"]["message"]
        assert captured.err == ""

    def test_plan_candidates_invalid_jsonl_json_returns_error_envelope(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        ledger_path.write_text("{broken\n", encoding="utf-8")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--summary-only",
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert payload["summary_only"] is True
        assert payload["candidates"] == []
        assert payload["error"]["code"] == "candidate_plan_error"
        assert "Invalid JSONL" in payload["error"]["message"]
        assert captured.err == ""

    def test_plan_candidates_invalid_limit_returns_exit_2(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        ledger_path.write_text("", encoding="utf-8")

        assert (
            main(
                [
                    "plan",
                    "candidates",
                    "--input",
                    str(ledger_path),
                    "--limit",
                    "0",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "limit must be greater than or equal to 1" in captured.err

    def test_parser_does_not_expose_watch_command(self):
        parser = cli._build_parser()
        help_text = parser.format_help()
        assert "watch" not in help_text

    def test_scout_plan_only_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.scout.check_all",
            lambda _config, probe=False: {
                "github": {"status": "ok", "message": "ready"},
                "mcp_registry": {"status": "ok", "message": "ready"},
                "hacker_news": {"status": "ok", "message": "ready"},
                "exa_search": {"status": "ok", "message": "ready"},
                "web": {"status": "ok", "message": "ready"},
                "searxng": {"status": "off", "message": "configure it"},
                "crawl4ai": {"status": "off", "message": "install extra"},
                "twitter": {"status": "warn", "message": "cookies missing"},
            },
        )
        monkeypatch.setattr(
            "agent_reach.scout.get_all_channel_contracts",
            lambda: [
                {"name": "github", "description": "GitHub", "operations": ["search", "read"], "supports_probe": True},
                {"name": "mcp_registry", "description": "MCP Registry", "operations": ["search", "read"], "supports_probe": True},
                {"name": "hacker_news", "description": "Hacker News", "operations": ["search", "read", "top"], "supports_probe": True},
                {"name": "exa_search", "description": "Exa", "operations": ["search"], "supports_probe": True},
                {"name": "web", "description": "Any web page", "operations": ["read"], "supports_probe": True},
                {"name": "searxng", "description": "SearXNG", "operations": ["search"], "supports_probe": True},
                {"name": "crawl4ai", "description": "crawl4ai", "operations": ["read", "crawl"], "supports_probe": False},
                {"name": "twitter", "description": "Twitter/X", "operations": ["search"], "supports_probe": True},
            ],
        )

        assert (
            main(
                [
                    "scout",
                    "--topic",
                    "MCP security",
                    "--budget",
                    "auto",
                    "--quality",
                    "precision",
                    "--preset",
                    "oss-watch",
                    "--plan-only",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "scout"
        assert payload["plan_only"] is True
        assert payload["quality_profile"] == "precision"
        assert payload["ready_channels"] == ["github", "mcp_registry", "hacker_news", "exa_search", "web"]
        assert payload["seed_channels"] == [
            "github",
            "mcp_registry",
            "hacker_news",
            "exa_search",
            "searxng",
            "web",
            "crawl4ai",
        ]
        assert payload["available_channels"][5]["channel"] == "searxng"
        assert payload["available_channels"][5]["probe_coverage"] == "none"
        assert payload["available_channels"][5]["probe_run_coverage"] == "not_run"
        assert payload["not_ready_channels"][0]["channel"] == "searxng"

    def test_scout_requires_plan_only(self, capsys):
        assert main(["scout", "--topic", "MCP"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "requires --plan-only" in captured.err

    def test_scout_requires_plan_only_json_error_payload(self, capsys):
        assert main(["scout", "--topic", "MCP", "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["command"] == "scout"
        assert payload["plan_only"] is False
        assert payload["error"]["code"] == "scout_plan_error"
        assert "requires --plan-only" in payload["error"]["message"]

    def test_scout_validates_stale_preset_channels(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.scout.check_all",
            lambda _config, probe=False: {"web": {"status": "ok", "message": "ready"}},
        )
        monkeypatch.setattr(
            "agent_reach.scout.get_all_channel_contracts",
            lambda: [
                {
                    "name": "web",
                    "description": "Any web page",
                    "operations": ["read"],
                    "operation_contracts": {
                        "read": {
                            "name": "read",
                            "input_kind": "url",
                            "accepts_limit": True,
                            "options": [],
                        }
                    },
                    "supports_probe": True,
                },
            ],
        )

        assert (
            main(
                [
                    "scout",
                    "--topic",
                    "MCP",
                    "--preset",
                    "broad-web",
                    "--plan-only",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Preset references unknown channel" in captured.err

    def test_scout_validates_stale_preset_channels_json_error_payload(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agent_reach.scout.check_all",
            lambda _config, probe=False: {"web": {"status": "ok", "message": "ready"}},
        )
        monkeypatch.setattr(
            "agent_reach.scout.get_all_channel_contracts",
            lambda: [
                {
                    "name": "web",
                    "description": "Any web page",
                    "operations": ["read"],
                    "operation_contracts": {
                        "read": {
                            "name": "read",
                            "input_kind": "url",
                            "accepts_limit": True,
                            "options": [],
                        }
                    },
                    "supports_probe": True,
                },
            ],
        )

        assert (
            main(
                [
                    "scout",
                    "--topic",
                    "MCP",
                    "--preset",
                    "broad-web",
                    "--plan-only",
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["command"] == "scout"
        assert payload["plan_only"] is True
        assert payload["preset"] == "broad-web"
        assert payload["error"]["code"] == "scout_plan_error"
        assert "Preset references unknown channel" in payload["error"]["message"]

    def test_configure_searxng_base_url_normalizes_value(self, capsys, monkeypatch):
        saved = {}

        class _FakeConfig:
            def set(self, key, value):
                saved[key] = value

        monkeypatch.setattr("agent_reach.config.Config", lambda: _FakeConfig())

        assert main(["configure", "searxng-base-url", "search.example.com/search"]) == 0
        output = capsys.readouterr().out
        assert saved["searxng_base_url"] == "https://search.example.com"
        assert "https://search.example.com" in output

    def test_configure_reddit_oauth_keys_are_not_supported(self):
        try:
            main(["configure", "reddit-user-agent", "windows:agent-reach:v1.6.0"])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("reddit-user-agent should be rejected")

    def test_batch_resume_skips_existing_query(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        existing_result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [{"id": "old", "url": "https://example.com/old"}],
            "raw": None,
            "meta": {"input": "https://example.com/old", "limit": 1, "count": 1},
            "error": None,
        }
        existing_record = {
            "record_type": "collection_result",
            "run_id": "run-1",
            "channel": "web",
            "operation": "read",
            "input": "https://example.com/old",
            "intent": "official_docs",
            "result": existing_result,
        }
        ledger_path.write_text(json.dumps(existing_record) + "\n", encoding="utf-8")
        plan_path.write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "queries": [
                        {
                            "query_id": "q01",
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com/old",
                            "limit": 1,
                            "intent": "official_docs",
                            "source_role": "web_discovery",
                        },
                        {
                            "query_id": "q02",
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com/new",
                            "limit": 1,
                            "intent": "official_docs",
                            "source_role": "web_discovery",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "new", "title": "New", "url": value}],
                    "raw": None,
                    "meta": {"input": value, "limit": limit, "count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--resume",
                    "--concurrency",
                    "2",
                    "--checkpoint-every",
                    "1",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["skipped"] == 1
        assert payload["summary"]["ok"] == 1
        assert payload["queries"][0]["status"] == "skipped"
        assert payload["queries"][1]["status"] == "ok"
        records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        assert len(records) == 2
        assert records[1]["query_id"] == "q02"

    def test_batch_accepts_utf8_sig_plan(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com",
                            "limit": 1,
                        }
                    ]
                }
            ),
            encoding="utf-8-sig",
        )

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": "1", "title": "Example", "url": value}],
                    "raw": None,
                    "meta": {"input": value, "limit": limit, "count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["ok"] == 1
        assert payload["queries"][0]["status"] == "ok"

    def test_batch_requires_save_or_validate_only(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert main(["batch", "--plan", str(plan_path), "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "batch requires --save or --save-dir unless --validate-only is set" in captured.err

    def test_batch_validate_only_accepts_utf8_sig_plan_without_writes(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "quality_profile": "coverage",
                    "failure_policy": "strict",
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com",
                            "intent": "official_docs",
                            "source_role": "primary",
                        }
                    ],
                }
            ),
            encoding="utf-8-sig",
        )

        class _UnexpectedClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("validate-only should not instantiate AgentReachClient")

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _UnexpectedClient)

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--validate-only",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["validate_only"] is True
        assert payload["valid"] is True
        assert payload["failure_policy"] == "strict"
        assert payload["quality_profile"] == "coverage"
        assert payload["summary"]["query_count"] == 1
        assert payload["summary"]["channel_counts"] == {"web": 1}
        assert payload["summary"]["operation_counts"] == {"read": 1}
        assert payload["summary"]["intent_counts"] == {"official_docs": 1}
        assert payload["summary"]["source_role_counts"] == {"primary": 1}
        assert not ledger_path.exists()

    def test_batch_validate_only_reports_invalid_option_in_json(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com",
                            "body_mode": "snippet",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert main(["batch", "--plan", str(plan_path), "--validate-only", "--json"]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["validate_only"] is True
        assert payload["valid"] is False
        assert payload["error"]["code"] == "batch_plan_error"
        assert "body_mode" in payload["error"]["message"]

    def test_batch_validate_only_reports_missing_field_in_json(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert main(["batch", "--plan", str(plan_path), "--validate-only", "--json"]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["validate_only"] is True
        assert payload["valid"] is False
        assert "missing required field" in payload["error"]["message"]

    def test_batch_validate_only_reports_invalid_json_in_json(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        plan_path.write_text('{"queries":[', encoding="utf-8")

        assert main(["batch", "--plan", str(plan_path), "--validate-only", "--json"]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["validate_only"] is True
        assert payload["valid"] is False
        assert payload["error"]["code"] == "batch_plan_error"
        assert "Invalid batch plan JSON" in payload["error"]["message"]

    def test_batch_save_dir_writes_shards(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        save_dir = tmp_path / "ledger"
        plan_path.write_text(
            json.dumps(
                {
                    "run_id": "run-2",
                    "queries": [
                        {
                            "query_id": "q01",
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com/a",
                            "limit": 1,
                        },
                        {
                            "query_id": "q02",
                            "channel": "rss",
                            "operation": "read",
                            "input": "https://example.com/feed.xml",
                            "limit": 2,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, body_mode=None, crawl_query=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": value, "title": value, "url": value}],
                    "raw": None,
                    "meta": {"input": value, "limit": limit, "count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save-dir",
                    str(save_dir),
                    "--shard-by",
                    "channel-operation",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["save_mode"] == "sharded"
        assert payload["shard_by"] == "channel-operation"
        assert sorted(Path(path).name for path in payload["save_targets"]) == [
            "rss__read.jsonl",
            "web__read.jsonl",
        ]
        assert (save_dir / "web__read.jsonl").exists()
        assert (save_dir / "rss__read.jsonl").exists()

    def test_batch_shard_by_requires_save_dir(self, capsys):
        assert (
            main(
                [
                    "batch",
                    "--plan",
                    "plan.json",
                    "--save",
                    "evidence.jsonl",
                    "--shard-by",
                    "channel",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "shard-by is only supported with --save-dir" in captured.err

    def test_batch_validates_query_options_from_operation_contract(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com",
                            "body_mode": "snippet",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "query 1 is invalid" in captured.err
        assert "body_mode" in captured.err

    def test_batch_passes_pagination_query_options_to_client(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "github",
                            "operation": "search",
                            "input": "agent reach",
                            "limit": 5,
                            "page_size": 2,
                            "max_pages": 3,
                            "page": 4,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        captured_kwargs = {}

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None, page_size=None, max_pages=None, page=None):
                captured_kwargs.update(
                    {
                        "channel": channel,
                        "operation": operation,
                        "value": value,
                        "limit": limit,
                        "page_size": page_size,
                        "max_pages": max_pages,
                        "page": page,
                    }
                )
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [],
                    "raw": None,
                    "meta": {
                        "input": value,
                        "limit": limit,
                        "requested_page_size": page_size,
                        "requested_max_pages": max_pages,
                        "requested_page": page,
                    },
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _FakeClient)

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert captured_kwargs == {
            "channel": "github",
            "operation": "search",
            "value": "agent reach",
            "limit": 5,
            "page_size": 2,
            "max_pages": 3,
            "page": 4,
        }
        assert payload["queries"][0]["page_size"] == 2
        assert payload["queries"][0]["max_pages"] == 3
        assert payload["queries"][0]["page"] == 4

    def test_batch_requires_crawl4ai_query_from_operation_contract(self, capsys, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "queries": [
                        {
                            "channel": "crawl4ai",
                            "operation": "crawl",
                            "input": "https://example.com",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "batch",
                    "--plan",
                    str(plan_path),
                    "--save",
                    str(ledger_path),
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "crawl4ai crawl requires query" in captured.err

    def test_batch_inherits_plan_metadata_defaults(self, capsys, monkeypatch, tmp_path):
        plan_path = tmp_path / "plan.json"
        ledger_path = tmp_path / "evidence.jsonl"
        plan_path.write_text(
            json.dumps(
                {
                    "run_id": "run-plan",
                    "intent": "external_news",
                    "source_role": "web_discovery",
                    "query_id_prefix": "topic",
                    "queries": [
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com/a",
                        },
                        {
                            "channel": "web",
                            "operation": "read",
                            "input": "https://example.com/b",
                            "source_role": "followup_read",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        class _FakeClient:
            def collect(self, channel, operation, value, limit=None):
                return {
                    "ok": True,
                    "channel": channel,
                    "operation": operation,
                    "items": [{"id": value, "title": value, "url": value}],
                    "raw": None,
                    "meta": {"input": value, "count": 1},
                    "error": None,
                }

        monkeypatch.setattr("agent_reach.batch.AgentReachClient", _FakeClient)

        assert main(["batch", "--plan", str(plan_path), "--save", str(ledger_path), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        assert [query["query_id"] for query in payload["queries"]] == ["topic-01", "topic-02"]
        assert records[0]["intent"] == "external_news"
        assert records[0]["source_role"] == "web_discovery"
        assert records[1]["source_role"] == "followup_read"

    def test_ledger_merge_command(self, capsys, tmp_path):
        source_dir = tmp_path / "ledger"
        source_dir.mkdir()
        (source_dir / "web.jsonl").write_text('{"record_type":"collection_result","id":"1"}\n', encoding="utf-8")
        (source_dir / "rss.jsonl").write_text('{"record_type":"collection_result","id":"2"}\n', encoding="utf-8")
        output_path = tmp_path / "merged.jsonl"

        assert (
            main(
                [
                    "ledger",
                    "merge",
                    "--input",
                    str(source_dir),
                    "--output",
                    str(output_path),
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "ledger merge"
        assert payload["files_merged"] == 2
        assert payload["records_written"] == 2
        assert len(output_path.read_text(encoding="utf-8").splitlines()) == 2

    def test_ledger_validate_command_reports_valid_ledger(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [{"id": "1", "url": "https://example.com", "text": "hello"}],
            "raw": None,
            "meta": {"input": "https://example.com", "count": 1},
            "error": None,
        }
        record = {
            "record_type": "collection_result",
            "run_id": "run-1",
            "channel": "web",
            "operation": "read",
            "result": result,
        }
        ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        assert main(["ledger", "validate", "--input", str(ledger_path), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "ledger validate"
        assert payload["valid"] is True
        assert payload["collection_results"] == 1
        assert payload["items_seen"] == 1

    def test_ledger_validate_require_metadata_and_summarize_commands(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "web",
            "operation": "read",
            "items": [{"id": "1", "url": "https://example.com"}],
            "raw": None,
            "meta": {"input": "https://example.com", "count": 1},
            "error": None,
        }
        record = {
            "record_type": "collection_result",
            "run_id": "run-1",
            "channel": "web",
            "operation": "read",
            "result": result,
        }
        ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        assert main(["ledger", "validate", "--input", str(ledger_path), "--require-metadata", "--json"]) == 1
        validate_payload = json.loads(capsys.readouterr().out)
        assert validate_payload["require_metadata"] is True
        assert validate_payload["missing_metadata"]["records"] == 1

        assert main(["ledger", "summarize", "--input", str(ledger_path), "--json"]) == 0
        summary_payload = json.loads(capsys.readouterr().out)
        assert summary_payload["command"] == "ledger summarize"
        assert summary_payload["records"] == 1
        assert summary_payload["missing_metadata"]["records"] == 1

    def test_ledger_summarize_command_accepts_filters(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        records = [
            {
                "record_type": "collection_result",
                "run_id": "run-1",
                "channel": "web",
                "operation": "read",
                "intent": "official_docs",
                "source_role": "primary",
                "result": {
                    "ok": True,
                    "channel": "web",
                    "operation": "read",
                    "items": [{"id": "1", "url": "https://example.com"}],
                    "raw": None,
                    "meta": {"input": "https://example.com", "count": 1},
                    "error": None,
                },
            },
            {
                "record_type": "collection_result",
                "run_id": "run-1",
                "channel": "twitter",
                "operation": "search",
                "intent": "social_watch",
                "source_role": "pulse",
                "result": {
                    "ok": True,
                    "channel": "twitter",
                    "operation": "search",
                    "items": [{"id": "tweet-1", "url": "https://x.com/openai/status/1"}],
                    "raw": None,
                    "meta": {"input": "OpenAI", "count": 1},
                    "error": None,
                },
            },
        ]
        ledger_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "ledger",
                    "summarize",
                    "--input",
                    str(ledger_path),
                    "--filter",
                    "source_role == pulse",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["records_scanned"] == 2
        assert payload["records"] == 1
        assert payload["channel_counts"] == {"twitter": 1}
        assert payload["filters"][0]["expression"] == "source_role == pulse"

    def test_ledger_query_command_filters_and_projects(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        records = [
            {
                "record_type": "collection_result",
                "run_id": "run-1",
                "channel": "web",
                "operation": "read",
                "ok": True,
                "result": {
                    "ok": True,
                    "channel": "web",
                    "operation": "read",
                    "items": [{"id": "1", "url": "https://example.com"}],
                    "raw": None,
                    "meta": {"input": "https://example.com", "count": 1},
                    "error": None,
                },
            },
            {
                "record_type": "collection_result",
                "run_id": "run-1",
                "channel": "github",
                "operation": "read",
                "ok": False,
                "result": {
                    "ok": False,
                    "channel": "github",
                    "operation": "read",
                    "items": [],
                    "raw": None,
                    "meta": {"input": "openai/openai-python", "count": 0},
                    "error": {
                        "code": "not_found",
                        "message": "missing",
                        "details": {},
                        "category": "no_results",
                        "retryable": False,
                    },
                },
            },
        ]
        ledger_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "ledger",
                    "query",
                    "--input",
                    str(ledger_path),
                    "--filter",
                    "channel == github",
                    "--fields",
                    "channel,ok,source.line",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "ledger query"
        assert payload["matched_records"] == 1
        assert payload["matches"][0]["channel"] == "github"
        assert payload["matches"][0]["ok"] is False
        assert payload["matches"][0]["source.line"] == 2

    def test_ledger_query_command_projects_array_wildcard_fields(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        record = {
            "record_type": "collection_result",
            "run_id": "run-1",
            "channel": "web",
            "operation": "read",
            "ok": True,
            "result": {
                "ok": True,
                "channel": "web",
                "operation": "read",
                "items": [
                    {"id": "1", "title": "Example One", "url": "https://example.com/one"},
                    {"id": "2", "title": "Example Two", "url": "https://example.com/two"},
                ],
                "raw": None,
                "meta": {"input": "https://example.com", "count": 2},
                "error": None,
            },
        }
        ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        assert (
            main(
                [
                    "ledger",
                    "query",
                    "--input",
                    str(ledger_path),
                    "--fields",
                    "channel,result.items[*].url",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "ledger query"
        assert payload["returned_records"] == 1
        assert payload["matches"][0]["channel"] == "web"
        assert payload["matches"][0]["result.items[*].url"] == [
            "https://example.com/one",
            "https://example.com/two",
        ]

    def test_ledger_validate_command_returns_exit_1_for_invalid_records(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        ledger_path.write_text('{"record_type":"collection_result"}\nnot-json\n', encoding="utf-8")

        assert main(["ledger", "validate", "--input", str(ledger_path), "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["valid"] is False
        assert payload["invalid_lines"] == 1
        assert payload["invalid_records"] == 1

    def test_ledger_validate_missing_input_returns_exit_2(self, capsys, tmp_path):
        missing_path = tmp_path / "missing.jsonl"

        assert main(["ledger", "validate", "--input", str(missing_path), "--json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Could not validate ledger" in captured.err

    def test_ledger_query_invalid_filter_returns_exit_2(self, capsys, tmp_path):
        ledger_path = tmp_path / "evidence.jsonl"
        ledger_path.write_text(
            '{"record_type":"collection_result","channel":"web","operation":"read","ok":true,"result":{"ok":true,"channel":"web","operation":"read","items":[],"raw":null,"meta":{"input":"https://example.com"},"error":null}}\n',
            encoding="utf-8",
        )

        assert (
            main(
                [
                    "ledger",
                    "query",
                    "--input",
                    str(ledger_path),
                    "--filter",
                    "channel github",
                    "--json",
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Could not query ledger" in captured.err

    def test_ledger_append_command_writes_collection_result(self, capsys, tmp_path):
        result_path = tmp_path / "result.json"
        ledger_path = tmp_path / "evidence.jsonl"
        result = {
            "ok": True,
            "channel": "twitter",
            "operation": "search",
            "items": [{"id": "tweet-1", "url": "https://x.com/openai/status/1"}],
            "raw": None,
            "meta": {"input": "OpenAI", "count": 1},
            "error": None,
        }
        result_path.write_text(json.dumps(result), encoding="utf-8-sig")

        assert (
            main(
                [
                    "ledger",
                    "append",
                    "--input",
                    str(result_path),
                    "--output",
                    str(ledger_path),
                    "--run-id",
                    "run-from-append",
                    "--intent",
                    "external_mixed",
                    "--query-id",
                    "twitter-openai",
                    "--source-role",
                    "social_discovery",
                    "--json",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        record = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert payload["command"] == "ledger append"
        assert payload["run_id"] == "run-from-append"
        assert record["query_id"] == "twitter-openai"
        assert record["result"] == result

    def test_ledger_append_invalid_json_returns_exit_1(self, capsys, tmp_path):
        result_path = tmp_path / "result.json"
        ledger_path = tmp_path / "evidence.jsonl"
        result_path.write_text('{"ok": true}', encoding="utf-8")

        assert (
            main(
                [
                    "ledger",
                    "append",
                    "--input",
                    str(result_path),
                    "--output",
                    str(ledger_path),
                    "--json",
                ]
            )
            == 1
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "CollectionResult" in captured.err

    def test_channels_json(self, capsys):
        assert main(["channels", "github", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["channel"]["name"] == "github"
        assert payload["channel"]["entrypoint_kind"] == "cli"
        assert payload["channel"]["operation_contracts"]["read"]["input_kind"] == "repository"

    def test_schema_collection_result_json(self, capsys):
        assert main(["schema", "collection-result", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["title"] == "Agent Reach CollectionResult"
        assert "schema_version" in payload["required"]
        assert "NormalizedItem" in payload["$defs"]

    def test_export_integration_json(self, capsys):
        assert main(["export-integration", "--client", "codex", "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["client"] == "codex"
        assert payload["profile"] == "full"
        assert payload["execution_context"] == "checkout"
        assert payload["mcp_snippet"]["mcpServers"]["exa"]["url"] == "https://mcp.exa.ai/mcp"
        assert payload["python_sdk"]["availability"] == "project_env_only"
        assert payload["skill"]["names"] == [
            "agent-reach",
            "agent-reach-shape-brief",
            "agent-reach-orchestrate",
            "agent-reach-propose-improvements",
            "agent-reach-maintain-proposals",
            "agent-reach-maintain-release",
        ]
        channel_contracts = {channel["name"]: channel for channel in payload["channels"]}
        assert channel_contracts["qiita"]["operation_contracts"]["search"]["options"][0]["name"] == "body_mode"

    def test_export_integration_runtime_minimal_json(self, capsys):
        assert (
            main(
                [
                    "export-integration",
                    "--client",
                    "codex",
                    "--format",
                    "json",
                    "--profile",
                    "runtime-minimal",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["profile"] == "runtime-minimal"
        assert payload["client"] == "codex"
        assert "channels" not in payload
        assert "channel_names" in payload
        assert "codex_runtime_policy" in payload
        assert payload["verification_commands"][-1].endswith("--profile runtime-minimal")

    def test_check_update_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            cli,
            "_build_update_payload",
            lambda: {
                "schema_version": "2026-04-10",
                "generated_at": "2026-04-10T00:00:00Z",
                "command": "check-update",
                "current_version": "1.4.0",
                "upstream_repo": "Panniantong/Agent-Reach",
                "status": "up_to_date",
                "latest_version": "1.4.0",
            },
        )
        assert main(["check-update", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "up_to_date"

    def test_check_update_json_when_fork_is_ahead_of_upstream(self, capsys, monkeypatch):
        monkeypatch.setattr(
            cli,
            "_build_update_payload",
            lambda: {
                "schema_version": "2026-04-10",
                "generated_at": "2026-04-10T00:00:00Z",
                "command": "check-update",
                "current_version": "1.6.0",
                "upstream_repo": "Panniantong/Agent-Reach",
                "comparison_target": "upstream_release",
                "status": "ahead_of_upstream_release",
                "latest_version": "1.4.0",
            },
        )
        assert main(["check-update", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ahead_of_upstream_release"

    def test_render_update_payload_reports_ahead_of_upstream_release(self):
        rendered = cli._render_update_payload(
            {
                "current_version": "1.6.0",
                "status": "ahead_of_upstream_release",
                "latest_version": "1.4.0",
            }
        )

        assert "Current version: v1.6.0" in rendered
        assert "ahead of the latest upstream release" in rendered

    def test_compare_versions_handles_newer_current_release(self):
        assert cli._compare_versions("1.6.0", "1.4.0") == 1
        assert cli._compare_versions("1.4.0", "1.4.0") == 0
        assert cli._compare_versions("1.4.0", "1.6.0") == -1

    def test_build_update_payload_marks_fork_ahead_of_upstream_release(self, monkeypatch):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"tag_name": "v1.4.0", "body": "notes"}

        monkeypatch.setattr(cli, "__version__", "1.6.0")
        monkeypatch.setattr(
            cli,
            "_github_get_with_retry",
            lambda _url, timeout=10, retries=3: (Response(), None, 1),
        )

        payload = cli._build_update_payload()

        assert payload["status"] == "ahead_of_upstream_release"
        assert payload["latest_version"] == "1.4.0"


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
