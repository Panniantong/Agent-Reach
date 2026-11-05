"""Save a verified Kuaishou video's media stream without exposing signed CDN URLs."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from agent_reach.runtime.result import BAD_INPUT, RATE_LIMITED, TIMEOUT, UPSTREAM_BROKEN, ReachError
from agent_reach.utils.paths import PrivatePathError, ensure_no_symlink_path, home_dir

_CDN_DOMAINS = ("kwaicdn.com", "yximgs.com")


def download_path(work_id: str, output: str = "") -> Path:
    """Validate the requested MP4 destination before opening a browser or writing files."""
    path = (Path(output).expanduser() if output else
            home_dir() / ".agent-reach" / "downloads" / "kuaishou" / f"{work_id}.mp4")
    try:
        path = ensure_no_symlink_path(path.absolute(), "Kuaishou download")
    except (OSError, ValueError, PrivatePathError):
        raise ReachError(BAD_INPUT, "output must be a valid file path without symlinks") from None
    if path.suffix.lower() != ".mp4":
        raise ReachError(BAD_INPUT, "output must name an .mp4 file")
    if path.exists():
        raise ReachError(BAD_INPUT, "output already exists; choose another filename")
    if any(parent.exists() and not parent.is_dir() for parent in path.parents):
        raise ReachError(BAD_INPUT, "output parent must be a directory")
    return path


def _media_url(value: object) -> str:
    """Unwrap the string, list or URL object shapes verified by KuaiShou-Spider."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _media_url(value[0]) if value else ""
    if isinstance(value, dict):
        return _media_url(value.get("url"))
    return ""


def _video_url(photo: dict) -> str:
    """Follow the baseline's photoUrl/mainMvUrls/first-manifest-stream preference."""
    direct = _media_url(photo.get("photoUrl")) or _media_url(photo.get("mainMvUrls"))
    if direct:
        return direct
    manifest = photo.get("manifest") or photo.get("manifestH265")
    if isinstance(manifest, list):
        return _media_url(manifest)
    if isinstance(manifest, dict):
        sets = manifest.get("adaptationSet")
        first = sets[0] if isinstance(sets, list) and sets else None
        representations = first.get("representation") if isinstance(first, dict) else None
        if isinstance(representations, list):
            for representation in representations:
                candidate = _media_url(representation)
                if candidate:
                    return candidate
    raise ReachError(UPSTREAM_BROKEN, "Kuaishou did not supply a downloadable video stream")


def _cdn_url(value: str) -> str:
    """Validate each initial/redirected URL against Kuaishou's verified media hosts."""
    try:
        parsed = urlsplit("https:" + value if value.startswith("//") else value)
        host = parsed.hostname or ""
        if (parsed.scheme not in {"http", "https"} or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 80, 443}
                or not any(host == domain or host.endswith("." + domain) for domain in _CDN_DOMAINS)):
            raise ValueError
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an unsupported media URL") from None
    return parsed._replace(scheme="https", netloc=host).geturl()


def download_video(photo: dict, destination: Path, *, timeout: float) -> dict:
    """Stream one MP4 into a temporary file, verify it, then publish without replacing files."""
    deadline = time.monotonic() + timeout

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise ReachError(TIMEOUT, "Kuaishou video download timed out")
        return left

    target = download_path("", str(destination))
    url = _cdn_url(_video_url(photo))
    staging: Path | None = None
    try:
        for _redirect in range(6):
            budget = remaining()
            with requests.get(
                url, stream=True, allow_redirects=False,
                timeout=(min(10.0, budget / 2), min(10.0, budget / 2)),
                headers={"Referer": "https://www.kuaishou.com/", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise ReachError(UPSTREAM_BROKEN, "Kuaishou media redirect has no destination")
                    url = _cdn_url(urljoin(url, location))
                    continue
                if response.status_code == 429:
                    raise ReachError(RATE_LIMITED, "Kuaishou media download was rate-limited")
                if response.status_code != 200:
                    raise ReachError(UPSTREAM_BROKEN,
                                     f"Kuaishou media download failed (HTTP {response.status_code})")
                if "text/html" in response.headers.get("Content-Type", "").lower():
                    raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned HTML instead of video")
                try:
                    expected = int(response.headers.get("Content-Length", "0"))
                except ValueError:
                    raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an invalid media length") from None
                ensure_no_symlink_path(target.parent, "Kuaishou download directory")
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
                staging = Path(name)
                size, prefix, digest = 0, b"", hashlib.sha256()
                with os.fdopen(fd, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        remaining()
                        if chunk:
                            handle.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                            prefix = (prefix + chunk)[:12]
                if prefix[4:8] != b"ftyp" or (expected and size != expected):
                    raise ReachError(UPSTREAM_BROKEN, "Kuaishou returned an incomplete or invalid MP4")
                remaining()
                try:
                    os.link(staging, target)
                except FileExistsError:
                    raise ReachError(BAD_INPUT, "output already exists; choose another filename") from None
                return {"path": str(target), "bytes": size, "sha256": digest.hexdigest()}
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou media redirected too many times")
    except requests.Timeout:
        raise ReachError(TIMEOUT, "Kuaishou video download timed out") from None
    except requests.RequestException:
        # Requests exceptions may embed the signed media URL; keep it out of JSON/logs.
        raise ReachError(UPSTREAM_BROKEN, "Kuaishou media download connection failed") from None
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
