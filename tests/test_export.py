# -*- coding: utf-8 -*-
"""Tests for agent-reach export command."""

import json
import sys
from unittest.mock import MagicMock

import pytest


class TestExportCommand:
    """Tests for the export command."""

    def setup_method(self):
        """Reset sys.argv before each test."""
        self.original_argv = sys.argv.copy()

    def teardown_method(self):
        """Restore sys.argv after each test."""
        sys.argv = self.original_argv

    def test_export_unknown_channel(self, capsys):
        """Test that export fails with unknown channel."""
        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "nonexistent"
        args.method = "get_hot_topics"
        args.args = "{}"
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "unknown channel" in captured.err.lower()

    def test_export_missing_method(self, capsys):
        """Test that export fails with missing method."""
        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "nonexistent_method"
        args.args = "{}"
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "no method" in captured.err.lower()

    def test_export_invalid_args_json(self, capsys):
        """Test that export fails with invalid JSON args."""
        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = "invalid json"
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "invalid --args" in captured.err.lower()

    def test_export_args_must_be_object(self, capsys):
        """Test that export fails when args is not a JSON object."""
        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = "[1, 2, 3]"  # Array, not object
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "must be a JSON object" in captured.err

    def test_export_get_hot_topics_json(self, monkeypatch, capsys):
        """Test export of get_hot_topics method to JSON."""
        from agent_reach.channels.v2ex import V2EXChannel

        # Mock the channel's get_hot_topics method
        mock_result = [
            {
                "id": 111,
                "title": "Test Topic",
                "url": "https://www.v2ex.com/t/111",
                "replies": 5,
            }
        ]

        monkeypatch.setattr(V2EXChannel, "get_hot_topics", lambda self, limit=20: mock_result)

        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = '{"limit": 1}'
        args.format = "json"
        args.output = None

        _cmd_export(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["channel"] == "v2ex"
        assert output["method"] == "get_hot_topics"
        assert output["count"] == 1
        assert len(output["data"]) == 1
        assert output["data"][0]["title"] == "Test Topic"

    def test_export_get_hot_topics_csv(self, monkeypatch, capsys):
        """Test export of get_hot_topics method to CSV."""
        from agent_reach.channels.v2ex import V2EXChannel

        # Mock the channel's get_hot_topics method
        mock_result = [
            {
                "id": 111,
                "title": "Test Topic 1",
                "url": "https://www.v2ex.com/t/111",
                "replies": 5,
            },
            {
                "id": 222,
                "title": "Test Topic 2",
                "url": "https://www.v2ex.com/t/222",
                "replies": 10,
            }
        ]

        monkeypatch.setattr(V2EXChannel, "get_hot_topics", lambda self, limit=20: mock_result)

        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = '{"limit": 2}'
        args.format = "csv"
        args.output = None

        _cmd_export(args)

        captured = capsys.readouterr()
        # Normalize line endings for cross-platform compatibility
        lines = captured.out.replace('\r\n', '\n').replace('\r', '\n').strip().split("\n")
        assert lines[0] == "id,title,url,replies"  # Header
        assert len(lines) == 3  # Header + 2 data rows
        assert "Test Topic 1" in lines[1]
        assert "Test Topic 2" in lines[2]

    def test_export_to_file(self, monkeypatch, tmp_path):
        """Test export to file."""
        from agent_reach.channels.v2ex import V2EXChannel

        mock_result = [
            {
                "id": 111,
                "title": "Test",
            }
        ]

        monkeypatch.setattr(V2EXChannel, "get_hot_topics", lambda self, limit=20: mock_result)

        from agent_reach.cli import _cmd_export

        output_file = tmp_path / "export.json"

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = '{}'
        args.format = "json"
        args.output = str(output_file)

        _cmd_export(args)

        # Check file was created
        assert output_file.exists()

        # Read and verify content
        with open(output_file, 'r', encoding='utf-8') as f:
            output = json.load(f)

        assert output["channel"] == "v2ex"
        assert len(output["data"]) == 1

    def test_export_method_not_callable(self, capsys):
        """Test that export fails when method is not callable."""
        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "__doc__"  # This is a property, not a method
        args.args = "{}"
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "not a callable" in captured.err.lower()

    def test_export_invalid_method_arguments(self, monkeypatch, capsys):
        """Test that export fails with invalid method arguments."""
        from agent_reach.channels.v2ex import V2EXChannel

        # Mock to raise TypeError for invalid args
        def mock_get_hot_topics(limit):
            raise TypeError("missing 1 required positional argument")

        monkeypatch.setattr(V2EXChannel, "get_hot_topics", mock_get_hot_topics)

        from agent_reach.cli import _cmd_export

        args = MagicMock()
        args.channel = "v2ex"
        args.method = "get_hot_topics"
        args.args = '{"invalid_param": "value"}'
        args.format = "json"
        args.output = None

        with pytest.raises(SystemExit) as excinfo:
            _cmd_export(args)

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "invalid arguments" in captured.err.lower()
