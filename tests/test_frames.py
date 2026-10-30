# -*- coding: utf-8 -*-
"""Tests for agent_reach.frames and the video channel's `frames` action."""

import os
import time
from pathlib import Path

import pytest

from agent_reach import frames as fr
from agent_reach.channels import video
from agent_reach.channels.video import VideoChannel
from agent_reach.runtime import state
from agent_reach.runtime.result import ReachError

REEL = "https://www.instagram.com/reel/C9xYz12AbCd/"


def test_moments_accept_seconds_clock_and_transcript_brackets():
    assert fr.parse_moments("12, 0:03,[1:05], 1:02:03, 12.0, 4.5") == [3, 4.5, 12, 65, 3723]
    assert fr.parse_moments("") == []


@pytest.mark.parametrize("bad", ["abc", "1:2:3:4", "-3", "0:1x"])
def test_moments_reject_anything_else(bad):
    with pytest.raises(ValueError):
        fr.parse_moments(bad)


def test_moments_are_capped():
    with pytest.raises(ValueError, match="at most"):
        fr.parse_moments(",".join(str(i) for i in range(fr.MAX_FRAMES + 1)))


def test_even_moments_sit_in_the_middle_of_each_slice():
    assert fr.even_moments(30) == [2.5, 7.5, 12.5, 17.5, 22.5, 27.5]
    assert fr.even_moments(2) == [0.5, 1.5]


@pytest.fixture
def fake_media(monkeypatch):
    calls = {"cut": []}

    def fake_download(url, out_dir, cookies=None):
        calls["download"] = (url, cookies)
        path = Path(out_dir) / "source.mp4"
        path.write_bytes(b"video")
        return path

    def fake_cut(video_path, second, dst):
        calls["cut"].append(second)
        dst.write_bytes(b"jpeg")
        return dst

    monkeypatch.setattr(fr, "download_video", fake_download)
    monkeypatch.setattr(fr, "cut_frame", fake_cut)
    monkeypatch.setattr(fr, "_probe_audio_duration", lambda _p: 20.0)
    return calls


def test_frames_are_kept_in_a_private_folder_reach_owns(fake_media):
    out = fr.extract_frames(REEL, "0:05, 3, 40")
    assert fake_media["cut"] == [3, 5, 19.9]  # past the end -> last frame
    assert [f["clock"] for f in out] == ["0:03", "0:05", "0:19"]
    folder = Path(out[0]["path"]).parent
    assert all(Path(f["path"]).is_file() for f in out)
    assert folder.parent == state.root() / "frames"
    assert state.owned_path(folder)


def test_without_moments_frames_spread_evenly(fake_media):
    fr.extract_frames(REEL)
    assert fake_media["cut"] == fr.even_moments(20.0)


def test_old_frame_folders_are_removed(fake_media):
    root = fr._frames_root()
    old = root / "old"
    old.mkdir()
    state.remember_path(old, "video frames")
    stale = time.time() - fr.KEEP_SECONDS - 60
    os.utime(old, (stale, stale))
    fr.extract_frames(REEL, "1")
    assert not old.exists() and not state.owned_path(old)


def test_channel_returns_one_item_per_frame(monkeypatch):
    monkeypatch.setattr(video, "_instagram_cookies", lambda: [])
    monkeypatch.setattr(fr, "extract_frames", lambda url, at, cookies=None: [
        {"second": 3.0, "clock": "0:03", "path": "/x/frame.jpg"}])
    items = VideoChannel()._ffmpeg_frames(target=REEL + "?utm_source=x", at="3", timeout=10)
    assert items[0]["title"] == "frame at 0:03" and items[0]["text"] == "/x/frame.jpg"
    assert items[0]["url"] == REEL and items[0]["raw"]["second"] == 3.0


def test_channel_rejects_bad_moments_before_downloading(monkeypatch):
    monkeypatch.setattr(fr, "extract_frames", lambda *a, **k: pytest.fail("downloaded"))
    with pytest.raises(ReachError) as err:
        VideoChannel()._ffmpeg_frames(target=REEL, at="soon", timeout=10)
    assert err.value.code == "BAD_INPUT"


def test_channel_transcribes_with_timestamps(monkeypatch):
    seen = {}
    monkeypatch.setattr(video, "whisper_transcribe",
                        lambda url, cookies, timestamps=False: seen.setdefault("ts", timestamps) and [])
    VideoChannel()._whisper_transcribe(target=REEL, timeout=10)
    assert seen["ts"] is True
