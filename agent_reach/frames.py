# -*- coding: utf-8 -*-
"""Still frames of a video at chosen moments, for the agent to look at.

The agent reads the timestamped transcript, picks the moments whose image would
explain what is being said (a chart, on-screen text, a product, a change of
scene) and asks for those. Without moments, frames are spread evenly.

Downloads the video (yt-dlp, 720p at most) into a temporary directory, cuts one
JPEG per moment (ffmpeg) into a private folder under the Reach root and keeps
that folder so the agent can open the images. Folders older than a day are
removed on the next call.

Public entry point:
    extract_frames(url, at="", *, cookies=None) -> list[dict]
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from agent_reach.transcribe import (
    MAX_SOURCE_BYTES,
    TranscribeError,
    _assert_safe_public_url,
    _bin,
    _probe_audio_duration,
    _require,
    _require_size_at_most,
    _run,
)

MAX_FRAMES = 12
EVEN_FRAMES = 6
FRAME_WIDTH = 768
KEEP_SECONDS = 24 * 3600

_MOMENT_RE = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parse_moments(at: str) -> List[float]:
    """Seconds from `12`, `12.5`, `0:12` or `1:02:03`, comma separated; sorted, unique."""
    moments = set()
    for raw in str(at or "").replace(";", ",").split(","):
        token = raw.strip().strip("[]")
        if not token:
            continue
        m = _MOMENT_RE.match(token)
        if not m:
            raise ValueError(f"not a moment: {token!r} (use seconds or m:ss)")
        first, second, seconds = m.groups()
        hours, minutes = (first, second) if second is not None else (None, first)
        moments.add(int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds))
    if len(moments) > MAX_FRAMES:
        raise ValueError(f"at most {MAX_FRAMES} moments per call")
    return sorted(moments)


def even_moments(duration: float, count: int = EVEN_FRAMES) -> List[float]:
    """Middle of each of `count` equal slices of the video."""
    count = max(1, min(count, int(duration) or 1))
    step = duration / count
    return [round(step * (i + 0.5), 2) for i in range(count)]


def _frames_root() -> Path:
    from agent_reach.runtime import state
    from agent_reach.utils.paths import make_private_dir

    return make_private_dir(state.root() / "frames")


def _prune(root: Path) -> None:
    """Remove frame folders older than KEEP_SECONDS and forget that Reach owned them."""
    from agent_reach.runtime import state

    cutoff = time.time() - KEEP_SECONDS
    for folder in root.iterdir():
        try:
            if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        relative = folder.relative_to(state.root()).as_posix()
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            state.mutate(lambda data: data.get("owned_paths", {}).pop(relative, None))


def download_video(url: str, out_dir: Path, cookies: Optional[str] = None) -> Path:
    """Download the video stream (720p at most) with yt-dlp; return the file path."""
    _assert_safe_public_url(url)
    _run(
        [
            sys.executable, "-m", "yt_dlp",
            "-f", "bv*[height<=720]/b[height<=720]/bv*/b",
            "--no-playlist",
            "--ffmpeg-location", _bin("ffmpeg"),
            "--max-filesize", str(MAX_SOURCE_BYTES),
            "-o", str(out_dir / "source.%(ext)s"),
            *(["--cookies", cookies] if cookies else []),
            "--",
            url,
        ],
        timeout=900,
    )
    files = sorted(f for f in out_dir.glob("source.*") if not f.name.endswith(".part"))
    if not files:
        raise TranscribeError("yt-dlp produced no video file")
    _require_size_at_most(files[0], MAX_SOURCE_BYTES, "downloaded video")
    return files[0]


def cut_frame(video: Path, second: float, dst: Path) -> Path:
    """One JPEG of `video` at `second`, at most FRAME_WIDTH pixels wide."""
    _require("ffmpeg")
    _run(
        [
            _bin("ffmpeg"), "-loglevel", "error", "-y",
            "-ss", f"{second:.2f}", "-i", str(video),
            "-frames:v", "1",
            "-vf", f"scale='min({FRAME_WIDTH},iw)':-2",
            "-q:v", "3",
            str(dst),
        ],
        timeout=60,
    )
    if not dst.is_file():
        raise TranscribeError(f"ffmpeg produced no frame at {second:g}s")
    return dst


def extract_frames(url: str, at: str = "", *, cookies: Optional[str] = None) -> List[dict]:
    """Frames of `url` at the moments in `at` (evenly spread when empty).

    Returns one dict per frame: {"second", "clock", "path"}. Moments past the
    end of the video are moved to its last frame.
    """
    from agent_reach.runtime import state
    from agent_reach.transcribe import _clock

    moments = parse_moments(at)
    root = _frames_root()
    _prune(root)
    out = Path(tempfile.mkdtemp(prefix=time.strftime("%Y%m%d-%H%M%S-"), dir=root))
    state.remember_path(out, "video frames")

    from agent_reach.utils.paths import private_temporary_directory

    with private_temporary_directory(prefix="agent-reach-video-") as tmp:
        video = download_video(url, Path(tmp), cookies)
        duration = _probe_audio_duration(video)
        if not moments:
            moments = even_moments(duration)
        last = max(0.0, duration - 0.1)
        frames = []
        for second in sorted({min(m, last) for m in moments}):
            name = f"frame_{int(second * 1000):08d}.jpg"
            path = cut_frame(video, second, out / name)
            frames.append({"second": round(second, 2), "clock": _clock(second), "path": str(path)})
    return frames
