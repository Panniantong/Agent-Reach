# -*- coding: utf-8 -*-
"""为 --max-seconds 补充的单元测试"""
import os, subprocess, sys

import pytest
from agent_reach.channels.xiaoyuzhou import XiaoyuzhouChannel
from agent_reach.runtime.result import ReachError

from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parents[1] / "agent_reach/scripts/transcribe_xiaoyuzhou.sh")


def _help(args):
    return subprocess.run(["bash", SCRIPT] + args, capture_output=True, text=True, input="")


def test_help_mentions_max_seconds():
    r = _help(["--help"])
    assert "--max-seconds" in r.stdout
    assert r.returncode == 0


def test_missing_value_rejected():
    r = _help(["--max-seconds"])
    assert r.returncode == 1
    assert "需要一个正整数秒数" in r.stderr


def test_non_numeric_rejected():
    r = _help(["--max-seconds", "abc", "https://www.xiaoyuzhoufm.com/episode/x"])
    assert r.returncode == 1
    assert "必须是正整数" in r.stderr


def test_zero_rejected():
    r = subprocess.run(["bash", SCRIPT, "--max-seconds", "0",
                        "https://www.xiaoyuzhoufm.com/episode/x"],
                       capture_output=True, text=True, input="",
                       env={**os.environ, "GROQ_API_KEY": "k"})
    assert r.returncode == 1
    assert "必须大于 0" in r.stderr


def test_channel_declares_param():
    ch = XiaoyuzhouChannel()
    action = [a for a in ch.actions if a.name == "transcribe"][0]
    names = [p.name for p in action.params]
    assert "max-seconds" in names
    p = [x for x in action.params if x.name == "max-seconds"][0]
    assert p.required is False and p.type is int


def test_channel_rejects_bad_value():
    ch = XiaoyuzhouChannel()
    with pytest.raises(ReachError) as ei:
        ch._script_transcribe(target="https://www.xiaoyuzhoufm.com/episode/x",
                              timeout=10, **{"max-seconds": "abc"})
    assert ei.value.code == "BAD_INPUT"


def test_channel_rejects_non_positive():
    ch = XiaoyuzhouChannel()
    with pytest.raises(ReachError) as ei:
        ch._script_transcribe(target="https://www.xiaoyuzhoufm.com/episode/x",
                              timeout=10, **{"max-seconds": -5})
    assert ei.value.code == "BAD_INPUT"


# ── Deepgram 后端 ──

def test_deepgram_is_preferred_backend():
    ch = XiaoyuzhouChannel()
    action = [a for a in ch.actions if a.name == "transcribe"][0]
    labels = [b[0] for b in action.backends]
    assert labels[0] == "deepgram"
    assert "groq-whisper" in labels


def test_deepgram_registered_in_providers():
    from agent_reach.transcribe import PROVIDERS
    assert "deepgram" in PROVIDERS
    dg = PROVIDERS["deepgram"]
    assert dg["kind"] == "deepgram"
    assert dg["key_field"] == "deepgram_api_key"
    assert dg["endpoint"].startswith("https://api.deepgram.com/")


def test_deepgram_key_configurable():
    from agent_reach.runtime.manage import CONFIG_KEYS
    assert CONFIG_KEYS["deepgram-key"] == "deepgram_api_key"


def test_setup_problems_accepts_deepgram_only(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "k")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ch = XiaoyuzhouChannel()
    assert ch.setup_problems() == []
