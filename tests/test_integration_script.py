"""Regression tests for the read-only checks embedded in test.sh."""
import json
import shlex
import subprocess
import sys
from pathlib import Path


def _embedded_channels_check():
    script = Path(__file__).resolve().parents[1] / "test.sh"
    for line in script.read_text(encoding="utf-8").splitlines():
        if "channels.json" in line and "json.load" in line:
            parts = shlex.split(line)
            return parts[parts.index("-c") + 1]
    raise AssertionError("test.sh does not contain its channels JSON check")


def _run_channels_check(tmp_path, payload):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", _embedded_channels_check(), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_integration_script_accepts_nonempty_channel_payload(tmp_path):
    result = _run_channels_check(tmp_path, {"ok": True, "channels": ["web"]})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "channels OK: 1"


def test_integration_script_rejects_empty_channel_payload(tmp_path):
    result = _run_channels_check(tmp_path, {"ok": True, "channels": []})

    assert result.returncode != 0
