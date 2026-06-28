# -*- coding: utf-8 -*-
"""Whisper audio transcription with Groq → OpenAI fallback.

Downloads audio (yt-dlp), compresses + chunks (ffmpeg), and posts to a
Whisper-compatible API. Defaults to Groq's free `whisper-large-v3` and falls
back to OpenAI's `whisper-1` on HTTP error.

Public entry point:
    transcribe(source, *, provider="auto", out_dir=None, config=None) -> str

Designed to be importable from channels (e.g. YouTubeChannel.transcribe).
"""

from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import requests

from agent_reach.config import Config

# Whisper API limit is 25MB; leave headroom for multipart overhead.
SIZE_LIMIT_BYTES = 24 * 1024 * 1024
CHUNK_SECONDS = 600  # 10 min — small enough that boundary cuts rarely lose meaning

PROVIDERS = {
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/audio/transcriptions",
        "model": "whisper-large-v3",
        "key_field": "groq_api_key",
    },
    "openai": {
        "endpoint": "https://api.openai.com/v1/audio/transcriptions",
        "model": "whisper-1",
        "key_field": "openai_api_key",
    },
}


class TranscribeError(RuntimeError):
    """Raised when transcription cannot complete."""


class MissingDependency(TranscribeError):
    """Raised when a required external binary is missing."""


class SsrfBlocked(TranscribeError):
    """Raised when the target URL points to a private/internal address."""


class NoProviderConfigured(TranscribeError):
    """Raised when no provider has an API key configured."""


# SSRF blocklist: hostnames that always resolve to private/internal services.
_SSRF_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "metadata.goog",
})

# Cloud metadata IPs — the #1 SSRF target in cloud environments.
_SSRF_METADATA_IPS = frozenset({
    "169.254.169.254",
    "169.254.170.2",
    "169.254.169.253",
    "100.100.100.200",
    "fd00:ec2::254",
})

# Private IP range string prefixes (fast-path check before ipaddress).
_SSRF_PRIVATE_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.", "127.",
)


def _check_ssrf(url: str) -> None:
    """Validate *url* does not target a private/internal host.

    Raises *SsrfBlocked* (a ``TranscribeError`` subclass) when the URL
    hostname is a known private name, resolves to a private IP, or is a
    cloud metadata endpoint.

    DNS failures are **not** raised — the caller (yt-dlp) is better
    positioned to retry or report transient errors.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()

    if not host:
        raise SsrfBlocked("URL has no hostname")

    # 1. Static hostname blocklist (fast, no DNS)
    if host in _SSRF_BLOCKED_HOSTNAMES:
        raise SsrfBlocked(f"SSRF blocked: '{host}' is not allowed")

    # 2. Cloud metadata IP blocklist (fast-path string match)
    if host in _SSRF_METADATA_IPS:
        raise SsrfBlocked(f"SSRF blocked: '{host}' is a cloud metadata endpoint")

    # 3. Scheme validation — only HTTP/S for download_audio
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SsrfBlocked(f"SSRF blocked: scheme '{scheme}' is not supported")

    # 4. DNS resolution + IP check — only when the host is not already an IP
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        # Already an IP literal — check it directly
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise SsrfBlocked(f"SSRF blocked: '{host}' is a private/reserved IP")
    else:
        # Hostname — resolve and check
        try:
            addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    raise SsrfBlocked(
                        f"SSRF blocked: '{host}' resolves to private IP '{ip_str}'"
                    )
                if ip_str in _SSRF_METADATA_IPS:
                    raise SsrfBlocked(
                        f"SSRF blocked: '{host}' resolves to metadata IP '{ip_str}'"
                    )
        except OSError:
            # DNS failure — let yt-dlp handle it
            pass


def _require(binary: str) -> None:
    if not shutil.which(binary):
        raise MissingDependency(f"{binary} not found in PATH")


def _run(cmd: List[str], timeout: int = 600) -> None:
    """Run a subprocess, raising TranscribeError on nonzero exit or timeout.

    cmd carries user-supplied URLs/paths into yt-dlp/ffmpeg — a stalled
    network read or a hung probe must not block the CLI forever.
    """
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TranscribeError(f"{cmd[0]} timed out after {timeout}s")
    if proc.returncode != 0:
        raise TranscribeError(
            f"{cmd[0]} failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}"
        )


def download_audio(url: str, out_dir: Path) -> Path:
    """Download audio with yt-dlp into out_dir; return the resulting file path."""
    _check_ssrf(url)  # Block SSRF to private/internal hosts
    _require("yt-dlp")
    template = out_dir / "source.%(ext)s"
    _run(
        [
            "yt-dlp",
            "-x",
            "--audio-format",
            "m4a",
            "--audio-quality",
            "0",
            "-o",
            str(template),
            url,
        ],
        timeout=1800,  # long podcasts over slow networks — generous but bounded
    )
    files = sorted(out_dir.glob("source.*"))
    if not files:
        raise TranscribeError("yt-dlp produced no output file")
    return files[0]


def compress_audio(src: Path, out_dir: Path) -> Path:
    """Re-encode to mono / 16kHz / 32kbps m4a — keeps most content under 25MB."""
    _require("ffmpeg")
    dst = out_dir / "compressed.m4a"
    _run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            str(dst),
        ]
    )
    return dst


def chunk_audio(src: Path, out_dir: Path, segment_seconds: int = CHUNK_SECONDS) -> List[Path]:
    """Split src into segments. Re-encodes each segment so cuts align to keyframes."""
    _require("ffmpeg")
    pattern = out_dir / "chunk_%03d.m4a"
    _run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "32k",
            str(pattern),
        ]
    )
    chunks = sorted(out_dir.glob("chunk_*.m4a"))
    if not chunks:
        raise TranscribeError("ffmpeg produced no chunks")
    return chunks


def _provider_key(provider: str, config: Config) -> Optional[str]:
    field = PROVIDERS[provider]["key_field"]
    val = config.get(field)
    return val or None


def transcribe_chunk(
    chunk: Path,
    provider: str,
    *,
    config: Optional[Config] = None,
    timeout: int = 120,
) -> str:
    """Transcribe one chunk via the named provider. Raises TranscribeError on failure."""
    if provider not in PROVIDERS:
        raise TranscribeError(f"unknown provider: {provider}")
    cfg = config or Config()
    key = _provider_key(provider, cfg)
    if not key:
        raise NoProviderConfigured(
            f"{provider}: missing {PROVIDERS[provider]['key_field']} "
            f"(configure with `agent-reach configure {provider}-key ...`)"
        )

    info = PROVIDERS[provider]
    with chunk.open("rb") as fh:
        try:
            resp = requests.post(
                info["endpoint"],
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (chunk.name, fh, "audio/m4a")},
                data={"model": info["model"], "response_format": "text"},
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise TranscribeError(f"{provider}: network error: {e}") from e

    if not resp.ok:
        raise TranscribeError(f"{provider}: HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.text


def _provider_order(provider: str) -> List[str]:
    if provider == "auto":
        return ["groq", "openai"]
    if provider in PROVIDERS:
        return [provider]
    raise TranscribeError(f"unknown provider: {provider} (use groq|openai|auto)")


def transcribe(
    source: str,
    *,
    provider: str = "auto",
    out_dir: Optional[Path] = None,
    config: Optional[Config] = None,
) -> str:
    """Transcribe a URL or local file path. Returns the joined transcript text.

    `provider` is one of `auto` (groq → openai), `groq`, or `openai`.
    `out_dir` defaults to a fresh temp directory; intermediate files stay there.
    """
    cfg = config or Config()
    order = _provider_order(provider)

    # Validate at least one provider is configured before doing expensive work.
    if not any(_provider_key(p, cfg) for p in order):
        names = ", ".join(PROVIDERS[p]["key_field"] for p in order)
        raise NoProviderConfigured(f"no provider key configured (need one of: {names})")

    work_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="transcribe-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    src_path = Path(source)
    if src_path.is_file():
        audio = src_path
    else:
        audio = download_audio(source, work_dir)

    compressed = compress_audio(audio, work_dir)
    if compressed.stat().st_size <= SIZE_LIMIT_BYTES:
        chunks = [compressed]
    else:
        chunks = chunk_audio(compressed, work_dir)

    pieces: List[str] = []
    for chunk in chunks:
        text = _transcribe_with_fallback(chunk, order, cfg)
        pieces.append(text.strip())
    return "\n".join(p for p in pieces if p)


def _transcribe_with_fallback(chunk: Path, order: List[str], config: Config) -> str:
    """Try each provider in order; return first success or raise the last error."""
    last_err: Optional[Exception] = None
    for p in order:
        if not _provider_key(p, config):
            # Skip silently — caller already validated at least one is configured.
            continue
        try:
            return transcribe_chunk(chunk, p, config=config)
        except TranscribeError as e:
            last_err = e
            continue
    raise TranscribeError(f"all providers failed for {chunk.name}: {last_err}")
