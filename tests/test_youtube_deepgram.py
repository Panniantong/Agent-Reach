# -*- coding: utf-8 -*-
"""youtube transcribe 接 Deepgram 的测试"""
import pytest

from agent_reach.channels.youtube import YouTubeChannel


def test_transcribe_prefers_deepgram():
    ch = YouTubeChannel()
    action = [a for a in ch.actions if a.name == "transcribe"][0]
    labels = [b[0] for b in action.backends]
    assert labels[0] == "deepgram"
    assert "whisper" in labels


def test_transcribe_declares_lang_param():
    ch = YouTubeChannel()
    action = [a for a in ch.actions if a.name == "transcribe"][0]
    p = [x for x in action.params if x.name == "lang"]
    assert p and p[0].required is False


def test_transcribe_has_live_test():
    ch = YouTubeChannel()
    action = [a for a in ch.actions if a.name == "transcribe"][0]
    assert action.live_test and "target" in action.live_test


def test_language_override_roundtrip():
    from agent_reach.transcribe import _LANGUAGE_OVERRIDE, _set_language_override
    assert _LANGUAGE_OVERRIDE[0] is None
    prev = _set_language_override("zh")
    try:
        assert _LANGUAGE_OVERRIDE[0] == "zh"
        assert prev is None
    finally:
        _set_language_override(None)
    assert _LANGUAGE_OVERRIDE[0] is None


def test_deepgram_empty_transcript_raises(monkeypatch):
    """空 transcript 不能静默成功 —— 必须抛错让 fallback 接手。"""
    from pathlib import Path

    import agent_reach.transcribe as tr

    class FakeResp:
        ok = True
        def json(self):
            return {"results": {"channels": [{"detected_language": "en",
                                              "alternatives": [{"transcript": "  "}]}]}}

    monkeypatch.setattr(tr.requests, "post", lambda *a, **k: FakeResp())
    tmp = Path("/tmp/_fake_chunk.m4a")
    tmp.write_bytes(b"x")
    with pytest.raises(tr.TranscribeError) as ei:
        tr._post_deepgram(tr.PROVIDERS["deepgram"], "k", tmp, 10)
    assert "empty transcript" in str(ei.value)


def test_deepgram_defaults_to_multilingual(monkeypatch):
    from pathlib import Path

    import agent_reach.transcribe as tr
    seen = {}

    class FakeResp:
        ok = True
        def json(self):
            return {"results": {"channels": [{"alternatives": [{"transcript": "hello"}]}]}}

    def fake_post(url, params=None, headers=None, data=None, timeout=None):
        seen["params"] = params
        return FakeResp()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    tmp = Path("/tmp/_fake_chunk2.m4a")
    tmp.write_bytes(b"x")
    tr._set_language_override(None)
    tr._post_deepgram(tr.PROVIDERS["deepgram"], "k", tmp, 10)
    # detect_language 会把 30 秒的中文片段判成 id 然后返回空转写，所以默认走 multi
    assert seen["params"].get("language") == "multi"
    assert "detect_language" not in seen["params"]


def test_deepgram_sends_forced_language(monkeypatch):
    from pathlib import Path

    import agent_reach.transcribe as tr
    seen = {}

    class FakeResp:
        ok = True
        def json(self):
            return {"results": {"channels": [{"alternatives": [{"transcript": "你好"}]}]}}

    def fake_post(url, params=None, headers=None, data=None, timeout=None):
        seen["params"] = params
        return FakeResp()

    monkeypatch.setattr(tr.requests, "post", fake_post)
    tmp = Path("/tmp/_fake_chunk3.m4a")
    tmp.write_bytes(b"x")
    tr._set_language_override("zh")
    try:
        tr._post_deepgram(tr.PROVIDERS["deepgram"], "k", tmp, 10)
    finally:
        tr._set_language_override(None)
    assert seen["params"].get("language") == "zh"
    assert "detect_language" not in seen["params"]
