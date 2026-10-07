# -*- coding: utf-8 -*-
"""Whisper audio transcription with explicit provider routing.

Downloads audio (yt-dlp), compresses + chunks (ffmpeg), and posts to a
Whisper-compatible API. Auto mode selects the first configured provider and
only sends audio to another provider when the caller explicitly opts in.

Public entry point:
    transcribe(
        source,
        *,
        provider="auto",
        out_dir=None,
        config=None,
        allow_provider_fallback=False,
    ) -> str

Designed to be importable from channels (e.g. YouTubeChannel.transcribe).
"""

from __future__ import annotations

import ipaddress
import logging
import math
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Final, NamedTuple, Optional, Sequence
from urllib.parse import urlsplit

import requests

from agent_reach.config import Config

__all__ = [
    "MissingDependency",
    "NoProviderConfigured",
    "TranscribeError",
    "chunk_audio",
    "compress_audio",
    "download_audio",
    "transcribe",
    "transcribe_chunk",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limits and configuration
# ---------------------------------------------------------------------------

# Whisper API limit is 25 MiB; leave headroom for multipart overhead.
SIZE_LIMIT_BYTES: Final[int] = 24 * 1024 * 1024
# 10 min — small enough that boundary cuts rarely lose meaning.
CHUNK_SECONDS: Final[int] = 600
MAX_SOURCE_BYTES: Final[int] = 512 * 1024 * 1024
# 4 hours at the standard 10-minute segment size.
MAX_CHUNKS: Final[int] = 24
MAX_TOTAL_CHUNK_BYTES: Final[int] = 96 * 1024 * 1024
MAX_AUDIO_SECONDS: Final[int] = MAX_CHUNKS * CHUNK_SECONDS
FFPROBE_TIMEOUT_SECONDS: Final[int] = 30


class _ProviderInfo(NamedTuple):
    endpoint: str
    model: str
    key_field: str


PROVIDERS: Final[dict[str, _ProviderInfo]] = {
    "groq": _ProviderInfo(
        endpoint="https://api.groq.com/openai/v1/audio/transcriptions",
        model="whisper-large-v3",
        key_field="groq_api_key",
    ),
    "openai": _ProviderInfo(
        endpoint="https://api.openai.com/v1/audio/transcriptions",
        model="whisper-1",
        key_field="openai_api_key",
    ),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TranscribeError(RuntimeError):
    """Raised when transcription cannot complete."""


class MissingDependency(TranscribeError):
    """Raised when a required external binary is missing."""


class NoProviderConfigured(TranscribeError):
    """Raised when no provider has an API key configured."""


# ---------------------------------------------------------------------------
# External binary helpers
# ---------------------------------------------------------------------------

def _require(binary: str) -> None:
    if not shutil.which(binary):
        raise MissingDependency(f"{binary} not found in PATH")


def _run(cmd: Sequence[str], timeout: int = 600) -> None:
    """Run a subprocess, raising TranscribeError on nonzero exit or timeout.

    ``cmd`` carries user-supplied URLs/paths into yt-dlp/ffmpeg — a stalled
    network read or a hung probe must not block the CLI forever.
    """
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise TranscribeError(f"{cmd[0]} timed out after {timeout}s") from None
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:300] or "no stderr"
        raise TranscribeError(
            f"{cmd[0]} failed (exit {proc.returncode}): {detail}"
        )


def _require_size_at_most(path: Path, limit: int, label: str) -> int:
    """Return file size or fail before expensive downstream processing."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TranscribeError(f"could not stat {label} ({path}): {exc}") from exc
    if size > limit:
        limit_mib = limit / (1024 * 1024)
        raise TranscribeError(f"{label} exceeds safety limit of {limit_mib:g} MiB")
    return size


def _probe_audio_duration(path: Path) -> float:
    """Return duration in seconds or fail closed before media generation."""
    _require("ffprobe")
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        "-i", str(path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise TranscribeError(
            "ffprobe timed out while reading audio duration "
            f"after {FFPROBE_TIMEOUT_SECONDS}s"
        ) from None
    except OSError as exc:
        raise TranscribeError(
            f"ffprobe could not read audio duration: {exc}"
        ) from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:300] or "unknown ffprobe error"
        raise TranscribeError(
            f"ffprobe failed while reading audio duration: {detail}"
        )

    raw_duration = proc.stdout.strip()
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        raise TranscribeError(
            "ffprobe could not parse a valid audio duration"
        ) from None
    if not math.isfinite(duration) or duration <= 0:
        raise TranscribeError(
            "ffprobe could not parse a valid positive audio duration"
        )
    return duration


def _require_duration_within_budget(path: Path) -> float:
    """Reject audio that cannot fit within the bounded chunk budget."""
    duration = _probe_audio_duration(path)
    if duration > MAX_AUDIO_SECONDS:
        max_minutes = MAX_AUDIO_SECONDS // 60
        raise TranscribeError(
            f"audio duration exceeds safety limit of {max_minutes} minutes"
        )
    return duration


# ---------------------------------------------------------------------------
# SSRF hardening
# ---------------------------------------------------------------------------

_BLOCKED_HOSTS: Final[frozenset[str]] = frozenset({
    "localhost",
    "metadata.google.internal",
})
_BLOCKED_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    ".localhost",
    ".local",      # mDNS / link-local by definition
    ".internal",   # split-horizon DNS commonly used by cloud providers
)


def _literal_ip(
    host: str,
) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Return the address a literal host denotes, or None for a real hostname.

    ``ipaddress`` only accepts the canonical dotted-quad form, but the C
    resolver behind yt-dlp accepts the whole ``inet_aton`` grammar: ``127.1``,
    ``2130706433``, ``0x7f000001`` and ``0177.0.0.1`` all reach 127.0.0.1, and
    ``0xA9FEA9FE`` reaches the cloud metadata endpoint. Parsing with the same
    grammar keeps those shorthands from slipping past the private-address
    check. This is literal parsing only — no name is resolved here.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)


def _is_private_ip(value: str) -> bool:
    ip = _literal_ip(value)
    if ip is None:
        return False
    return any((
        ip.is_private,
        ip.is_loopback,
        ip.is_link_local,
        ip.is_reserved,
        ip.is_multicast,
        ip.is_unspecified,
    ))


def _assert_safe_public_url(url: str) -> None:
    """Reject literal local/internal URLs without DNS-resolving public hosts."""
    candidate = url if "://" in url else f"https://{url}"
    parsed = urlsplit(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise TranscribeError(
            "SSRF blocked: only public http(s) URLs are allowed"
        )

    # Inspect the raw authority before urlsplit normalizes it, so that
    # backslashes and percent-encoding cannot hide a private host.
    raw_authority = candidate.split("://", 1)[1]
    for sep in ("/", "?", "#"):
        raw_authority = raw_authority.split(sep, 1)[0]
    if "\\" in raw_authority or "%" in raw_authority:
        raise TranscribeError("SSRF blocked: encoded or ambiguous URL host")

    try:
        port = parsed.port
    except ValueError:
        raise TranscribeError("SSRF blocked: invalid URL port") from None
    if port is not None and not (0 < port < 65536):
        raise TranscribeError("SSRF blocked: invalid URL port")

    raw_host = (parsed.hostname or "").strip().rstrip(".")
    if not raw_host:
        raise TranscribeError("SSRF blocked: URL host is missing")
    try:
        host = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise TranscribeError("SSRF blocked: URL host is invalid") from None
    if not host:
        raise TranscribeError("SSRF blocked: URL host is missing")
    if host in _BLOCKED_HOSTS or any(
        host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES
    ):
        raise TranscribeError("SSRF blocked: internal host is not allowed")
    if _is_private_ip(host):
        raise TranscribeError("SSRF blocked: private/internal IP is not allowed")


# ---------------------------------------------------------------------------
# Media pipeline
# ---------------------------------------------------------------------------

def download_audio(url: str, out_dir: Path) -> Path:
    """Download audio with yt-dlp into ``out_dir/download``; return the path."""
    _assert_safe_public_url(url)
    _require("yt-dlp")

    download_dir = out_dir / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    template = download_dir / "source.%(ext)s"

    logger.info("Downloading audio from %s", url)
    _run(
        [
            "yt-dlp",
            "-x",
            "--audio-format", "m4a",
            "--audio-quality", "0",
            "--no-playlist",
            "--no-part",
            "--max-filesize", str(MAX_SOURCE_BYTES),
            "-o", str(template),
            "--",
            url,
        ],
        timeout=1800,  # long podcasts over slow networks — generous but bounded
    )
    files = sorted(download_dir.glob("source.*"))
    if not files:
        limit_mib = MAX_SOURCE_BYTES // (1024 * 1024)
        raise TranscribeError(
            f"yt-dlp produced no output file "
            f"(source may exceed {limit_mib} MiB limit)"
        )
    audio = files[0]
    _require_size_at_most(audio, MAX_SOURCE_BYTES, "downloaded source")
    return audio


def compress_audio(src: Path, out_dir: Path) -> Path:
    """Re-encode to mono / 16kHz / 32kbps m4a — keeps most content under 25MB."""
    _require("ffmpeg")
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "compressed.m4a"
    _run([
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-i", str(src),
        "-t", str(MAX_AUDIO_SECONDS),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "32k",
        str(dst),
    ])
    return dst


def chunk_audio(
    src: Path,
    out_dir: Path,
    segment_seconds: int = CHUNK_SECONDS,
) -> list[Path]:
    """Split ``src`` into segments; re-encodes so cuts align to keyframes."""
    if segment_seconds <= 0:
        raise TranscribeError("chunk segment duration must be positive")
    possible_chunks = (MAX_AUDIO_SECONDS + segment_seconds - 1) // segment_seconds
    if possible_chunks > MAX_CHUNKS:
        raise TranscribeError(
            f"chunk generation safety limit is {MAX_CHUNKS}; "
            f"segment duration {segment_seconds}s could create "
            f"{possible_chunks} chunks"
        )
    _require("ffmpeg")
    chunk_dir = out_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunk_dir / "chunk_%03d.m4a"
    _run([
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-i", str(src),
        "-t", str(MAX_AUDIO_SECONDS),
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "32k",
        str(pattern),
    ])
    chunks = sorted(chunk_dir.glob("chunk_*.m4a"))
    if not chunks:
        raise TranscribeError("ffmpeg produced no chunks")
    return chunks


# ---------------------------------------------------------------------------
# Provider API
# ---------------------------------------------------------------------------

def _provider_key(provider: str, config: Config) -> Optional[str]:
    info = PROVIDERS.get(provider)
    if info is None:
        return None
    return config.get(info.key_field) or None


def transcribe_chunk(
    chunk: Path,
    provider: str,
    *,
    config: Optional[Config] = None,
    timeout: int = 120,
) -> str:
    """Transcribe one chunk via the named provider.

    Raises :class:`TranscribeError` on failure.
    """
    info = PROVIDERS.get(provider)
    if info is None:
        raise TranscribeError(f"unknown provider: {provider}")
    cfg = config or Config()
    key = _provider_key(provider, cfg)
    if not key:
        raise NoProviderConfigured(
            f"{provider}: missing {info.key_field} "
            f"(configure with `agent-reach configure {provider}-key ...`)"
        )

    with chunk.open("rb") as fh:
        try:
            resp = requests.post(
                info.endpoint,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (chunk.name, fh, "audio/m4a")},
                data={"model": info.model, "response_format": "text"},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise TranscribeError(f"{provider}: network error: {exc}") from exc

    if not resp.ok:
        body = (resp.text or "")[:300]
        raise TranscribeError(f"{provider}: HTTP {resp.status_code}: {body}")
    return resp.text


def _provider_order(provider: str) -> list[str]:
    if provider == "auto":
        return ["groq", "openai"]
    if provider in PROVIDERS:
        return [provider]
    raise TranscribeError(f"unknown provider: {provider} (use groq|openai|auto)")


def _transcribe_with_fallback(
    chunk: Path,
    order: Sequence[str],
    config: Config,
) -> str:
    """Try each provider in order; return first success or raise a summary."""
    errors: list[str] = []
    for provider in order:
        if not _provider_key(provider, config):
            # Skip silently — the caller already validated at least one.
            continue
        try:
            return transcribe_chunk(chunk, provider, config=config)
        except TranscribeError as exc:
            logger.warning(
                "Provider %s failed on %s: %s", provider, chunk.name, exc
            )
            errors.append(f"{provider}: {exc}")
    if not errors:
        raise TranscribeError(f"no configured provider available for {chunk.name}")
    raise TranscribeError(
        f"all providers failed for {chunk.name}: " + "; ".join(errors)
    )


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def transcribe(
    source: str,
    *,
    provider: str = "auto",
    out_dir: Optional[Path] = None,
    config: Optional[Config] = None,
    allow_provider_fallback: bool = False,
) -> str:
    """Transcribe a URL or local file path. Returns the joined transcript text.

    ``provider`` is one of ``auto``, ``groq``, or ``openai``. Auto mode selects
    the first configured provider (Groq, then OpenAI). In auto mode only, set
    ``allow_provider_fallback=True`` to permit sending failed chunks to the
    next configured provider; using the flag with an explicit provider is
    rejected. ``out_dir`` defaults to a fresh temp directory; intermediate
    files stay there.
    """
    if allow_provider_fallback and provider != "auto":
        raise TranscribeError("allow_provider_fallback requires provider='auto'")

    cfg = config or Config()
    candidates = _provider_order(provider)
    configured = [p for p in candidates if _provider_key(p, cfg)]

    # Validate before doing expensive work.
    if not configured:
        names = ", ".join(PROVIDERS[p].key_field for p in candidates)
        raise NoProviderConfigured(
            f"no provider key configured (need one of: {names})"
        )

    order = configured
    if provider == "auto" and not allow_provider_fallback:
        order = configured[:1]

    if out_dir is not None:
        return _transcribe_in_dir(source, order, cfg, Path(out_dir))

    with tempfile.TemporaryDirectory(prefix="transcribe-") as tmp:
        return _transcribe_in_dir(source, order, cfg, Path(tmp))


def _transcribe_in_dir(
    source: str,
    order: Sequence[str],
    cfg: Config,
    work_dir: Path,
) -> str:
    work_dir.mkdir(parents=True, exist_ok=True)

    src_path = Path(source)
    if src_path.is_file():
        audio = src_path
    else:
        audio = download_audio(source, work_dir)

    _require_size_at_most(audio, MAX_SOURCE_BYTES, "source")
    _require_duration_within_budget(audio)

    compressed = compress_audio(audio, work_dir)
    if compressed.stat().st_size <= SIZE_LIMIT_BYTES:
        chunks = [compressed]
    else:
        chunks = chunk_audio(compressed, work_dir)

    if len(chunks) > MAX_CHUNKS:
        max_minutes = MAX_CHUNKS * CHUNK_SECONDS // 60
        raise TranscribeError(
            f"audio produced {len(chunks)} chunks; safety limit is "
            f"{MAX_CHUNKS} (~{max_minutes} minutes)"
        )

    chunk_sizes = [
        _require_size_at_most(chunk, SIZE_LIMIT_BYTES, f"chunk {chunk.name}")
        for chunk in chunks
    ]
    total_chunk_bytes = sum(chunk_sizes)
    if total_chunk_bytes > MAX_TOTAL_CHUNK_BYTES:
        limit_mib = MAX_TOTAL_CHUNK_BYTES / (1024 * 1024)
        raise TranscribeError(
            f"audio chunks total {total_chunk_bytes} bytes; "
            f"safety limit is {limit_mib:g} MiB"
        )

    logger.info(
        "Transcribing %d chunk(s) via %s", len(chunks), " -> ".join(order)
    )
    pieces: list[str] = []
    for chunk in chunks:
        pieces.append(_transcribe_with_fallback(chunk, order, cfg).strip())
    return "\n".join(p for p in pieces if p)
