"""Probe real PATH executables before promising podcast transcription."""

import os

import pytest

from agent_reach.channels.xiaoyuzhou import XiaoyuzhouChannel


@pytest.mark.skipif(os.name == "nt", reason="native POSIX executable PATH fixture")
@pytest.mark.parametrize(
    "unusable,broken",
    [("ffprobe", False), ("curl", False), ("perl", False), ("ffprobe", True), (None, False)],
)
def test_mandatory_script_tools_are_checked(tmp_path, monkeypatch, isolated_home, unusable, broken):
    bins = tmp_path / "bin"
    bins.mkdir()
    for tool in ("ffmpeg", "ffprobe", "curl", "perl"):
        if tool == unusable and not broken:
            continue
        executable = bins / tool
        exit_code = 127 if tool == unusable else 0
        executable.write_text(f"#!/bin/sh\nprintf 'test version\\n'\nexit {exit_code}\n")
        executable.chmod(0o755)
    script = isolated_home / ".agent-reach/tools/xiaoyuzhou/transcribe.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bins))
    monkeypatch.setenv("GROQ_API_KEY", "test-only-explicit-key")

    channel = XiaoyuzhouChannel()
    status, message = channel.check()
    if unusable is None:
        assert status == "ok"
        assert channel.active_backend == "groq-whisper"
    else:
        assert status == ("error" if broken else "off")
        assert unusable in message
        assert channel.active_backend is None
