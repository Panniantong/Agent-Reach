"""The JSON CLI works with redirected output in non-UTF-8 locales."""

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize("errors", ["strict", "replace"])
@pytest.mark.parametrize("args", [["channels"], ["unknown-\U0001f600"]])
def test_json_output_preserves_unicode_with_legacy_encoding(monkeypatch, errors, args):
    monkeypatch.setenv("PYTHONIOENCODING", f"cp1252:{errors}")
    result = subprocess.run(
        [sys.executable, "-m", "agent_reach.cli", *args],
        capture_output=True,
        check=False,
    )
    assert result.returncode == (0 if args == ["channels"] else 1), result.stderr
    payload = json.loads(result.stdout.decode("cp1252"))
    if args == ["channels"]:
        assert any("GitHub" in channel["description"] for channel in payload["channels"])
        assert any("网页" in channel["description"] for channel in payload["channels"])
    else:
        assert "unknown-\U0001f600" in payload["error"]["message"]


def test_json_output_keeps_readable_utf8(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "agent_reach.cli", "channels"],
        capture_output=True,
        check=True,
    )
    assert "网页" in result.stdout.decode("utf-8")
