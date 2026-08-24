# -*- coding: utf-8 -*-
"""Manual ingestion and upstream-tool discovery for narrative evidence."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import requests

from agent_reach.narrative.store import NarrativeStore

MAX_IMPORT_BYTES = 25 * 1024 * 1024
ALLOWED_SUFFIXES = {".md", ".txt", ".pdf", ".csv", ".json", ".vtt"}
_CAUSAL_TERMS = (
    "導致",
    "帶動",
    "因為",
    "因此",
    "所以",
    "造成",
    "風險",
    "機會",
    "預計",
    "將會",
    "增長",
    "下降",
    "上升",
    "because",
    "therefore",
    "risk",
    "growth",
    "decline",
    "increase",
    "forecast",
    "expect",
)
_SOURCE_PATTERNS = (
    ("half_latte_liufei", ("halflatte", "半拿鐵")),
    ("miula", ("miula", "m觀點")),
    ("techwav", ("techwav", "科技浪")),
    ("stratechery", ("stratechery",)),
    ("valley101", ("valley101", "矽谷101", "硅谷101")),
    ("serenity_aleabitoreddit", ("aleabitoreddit", "serenity")),
    ("huang_jingzhe", ("黃靖哲",)),
    ("bonnie_blockchain", ("邦妮區塊鏈", "bonnieblockchain")),
    ("youtubercrypto", ("youtubercrypto", "科幣託")),
)


def infer_source_id(value: str) -> str:
    lowered = str(value or "").lower()
    for source_id, patterns in _SOURCE_PATTERNS:
        if any(pattern.lower() in lowered for pattern in patterns):
            return source_id
    return ""


def validate_public_url(
    url: str,
    resolver: Callable[..., list] = socket.getaddrinfo,
) -> str:
    """Allow HTTP(S) URLs only and reject addresses that can reach local/private networks."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    host = parsed.hostname.rstrip(".")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(row[4][0])
                for row in resolver(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            }
        except (OSError, ValueError) as exc:
            raise ValueError(f"URL host cannot be resolved: {host}") from exc
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("private, local, reserved, and link-local URLs are blocked")
    return parsed.geturl()


def _run(command: list[str], timeout: int = 90) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "upstream tool failed").strip()
        raise RuntimeError(detail[:1000])
    return result.stdout.strip()


def _fetch_jina(url: str, timeout: int = 45) -> tuple[str, dict]:
    endpoint = f"https://r.jina.ai/{url}"
    current = endpoint
    for _ in range(5):
        response = requests.get(
            current,
            timeout=timeout,
            allow_redirects=False,
            headers={"User-Agent": "agent-reach-narrative/1.0"},
        )
        if response.is_redirect or response.is_permanent_redirect:
            target = urljoin(current, response.headers.get("Location", ""))
            parsed = urlparse(target)
            if parsed.hostname != "r.jina.ai" or parsed.scheme != "https":
                raise ValueError("reader redirect left the allowed upstream host")
            current = target
            continue
        response.raise_for_status()
        if len(response.content) > MAX_IMPORT_BYTES:
            raise ValueError("download exceeds 25 MiB import limit")
        return response.text, {
            "fetch_backend": "jina_reader",
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
        }
    raise ValueError("too many reader redirects")


def _fetch_youtube(url: str) -> tuple[str, dict]:
    if not shutil.which("yt-dlp"):
        return _fetch_jina(url)
    with tempfile.TemporaryDirectory(prefix="agent-reach-narrative-") as tmp:
        template = str(Path(tmp) / "%(id)s.%(ext)s")
        command = [
            "yt-dlp",
            "--write-sub",
            "--write-auto-sub",
            "--skip-download",
            "--sub-lang",
            "zh-Hant,zh-Hans,zh,en",
            "--sub-format",
            "vtt",
            "--no-playlist",
            "--print-json",
            "-o",
            template,
            url,
        ]
        output = _run(command, timeout=120)
        files = sorted(Path(tmp).glob("*.vtt"))
        if files:
            text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)
        else:
            text = output
        return text, {"fetch_backend": "yt-dlp", "subtitle_files": len(files)}


def fetch_url(url: str) -> tuple[str, dict]:
    safe_url = validate_public_url(url)
    host = (urlparse(safe_url).hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}:
        return _fetch_youtube(safe_url)
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"} and shutil.which("twitter"):
        try:
            return _run(["twitter", "tweet", safe_url]), {"fetch_backend": "twitter-cli"}
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
    return _fetch_jina(safe_url)


def extract_text(content: bytes, suffix: str) -> str:
    suffix = suffix.lower()
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError("file exceeds 25 MiB import limit")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError('PDF import needs: pip install "agent-reach[narrative]"') from exc
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(content)
            tmp.flush()
            reader = PdfReader(tmp.name)
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return content.decode("utf-8-sig", errors="replace")


def _clean_text(text: str) -> str:
    text = re.sub(r"^WEBVTT.*?$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> .*?$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[(?:cite|source):[^\]]+\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_claim_candidates(text: str, limit: int = 40) -> list[str]:
    """Deterministic extraction; candidates remain GUESS until claim-level review."""
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。！？!?])\s+|(?<=[.;])\s+(?=[A-Z0-9])", cleaned)
    candidates: list[str] = []
    seen: set[str] = set()
    for part in parts:
        sentence = part.strip(" -*#\t\r\n")
        if len(sentence) < 20 or len(sentence) > 800:
            continue
        has_signal = bool(re.search(r"\d", sentence)) or any(
            term in sentence.lower() for term in _CAUSAL_TERMS
        )
        if not has_signal:
            continue
        key = re.sub(r"\s+", " ", sentence).lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(sentence)
        if len(candidates) >= limit:
            break
    if not candidates and len(cleaned) >= 20:
        candidates.append(cleaned[:800])
    return candidates


def _source_flags(store: NarrativeStore, source_id: str) -> list[str]:
    source = store.get_source(source_id) if source_id else None
    return list(source.get("conflict_flags") or []) if source else []


def ingest_text(
    store: NarrativeStore,
    *,
    text: str,
    title: str = "",
    source_url: str = "",
    source_id: str = "",
    domain: str = "",
    ticker: str = "",
    published_at: str = "",
    as_of: str = "",
    media_type: str = "text/plain",
    suffix: str = ".txt",
    metadata: Optional[dict] = None,
) -> dict:
    if not text.strip():
        raise ValueError("import text is empty")
    source_id = source_id or infer_source_id(" ".join((title, source_url, text[:300])))
    metadata = dict(metadata or {})
    report_name = Path(title).name.lower()
    if report_name in {"aibubble.md", "light.md", "musk.md", "robots.md"}:
        metadata["quarantine"] = True
        metadata["quarantine_reason"] = (
            "user research seed; claim-level provenance not yet verified"
        )
    document, created = store.add_document(
        content=text.encode("utf-8"),
        title=title,
        source_url=source_url,
        source_id=source_id,
        media_type=media_type,
        published_at=published_at,
        as_of=as_of,
        domain=domain,
        metadata=metadata,
        suffix=suffix,
    )
    claims = []
    if created:
        flags = _source_flags(store, source_id)
        for sentence in extract_claim_candidates(text):
            claims.append(
                store.add_claim(
                    document_id=document["id"],
                    source_id=source_id,
                    text=sentence,
                    excerpt=sentence[:500],
                    ticker=ticker,
                    domain=domain,
                    tag="GUESS",
                    confidence="LOW",
                    published_at=published_at,
                    as_of=as_of,
                    source_url=source_url,
                    conflict_flags=flags,
                    evidence=[],
                )
            )
    else:
        claims = store.list_claims(limit=1000)
        claims = [c for c in claims if c["document_id"] == document["id"]]
    return {"document": document, "claims": claims, "created": created}


def ingest_file(
    store: NarrativeStore,
    path: Path,
    *,
    source_id: str = "",
    domain: str = "",
    ticker: str = "",
    published_at: str = "",
    as_of: str = "",
) -> dict:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix}")
    content = file_path.read_bytes()
    text = extract_text(content, suffix)
    media = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".json": "application/json",
        ".vtt": "text/vtt",
    }[suffix]
    return ingest_text(
        store,
        text=text,
        title=file_path.name,
        source_id=source_id,
        domain=domain,
        ticker=ticker,
        published_at=published_at,
        as_of=as_of,
        media_type=media,
        suffix=suffix,
        metadata={
            "original_path": str(file_path),
            "original_sha256": hashlib.sha256(content).hexdigest(),
        },
    )


def ingest_url(
    store: NarrativeStore,
    url: str,
    *,
    title: str = "",
    source_id: str = "",
    domain: str = "",
    ticker: str = "",
    published_at: str = "",
    as_of: str = "",
) -> dict:
    safe_url = validate_public_url(url)
    text, metadata = fetch_url(safe_url)
    return ingest_text(
        store,
        text=text,
        title=title or safe_url,
        source_url=safe_url,
        source_id=source_id,
        domain=domain,
        ticker=ticker,
        published_at=published_at,
        as_of=as_of,
        media_type="text/markdown",
        suffix=".md",
        metadata=metadata,
    )


def _find_result_rows(value: object) -> list[dict]:
    if isinstance(value, list):
        rows = [
            row for row in value if isinstance(row, dict) and (row.get("url") or row.get("link"))
        ]
        if rows:
            return rows
        for row in value:
            nested = _find_result_rows(row)
            if nested:
                return nested
    if isinstance(value, dict):
        for key in ("results", "items", "data", "content"):
            nested = _find_result_rows(value.get(key))
            if nested:
                return nested
        if value.get("url") or value.get("link"):
            return [value]
    return []


def discover(query: str, *, domain: str = "", num_results: int = 8) -> list[dict]:
    """Manually triggered Exa discovery. Results are candidates, never evidence."""
    if not query.strip():
        raise ValueError("discovery query is empty")
    if not shutil.which("mcporter"):
        raise RuntimeError("mcporter is unavailable; run agent-reach doctor")
    full_query = f"{query.strip()} {domain.strip()}".strip()
    expr = (
        "exa.web_search_exa(query: "
        + json.dumps(full_query, ensure_ascii=False)
        + f", numResults: {max(1, min(int(num_results), 20))})"
    )
    output = _run(["mcporter", "call", expr], timeout=120)
    try:
        payload = json.loads(output)
        rows = _find_result_rows(payload)
    except json.JSONDecodeError:
        rows = []
    if not rows:
        url_pattern = re.compile(r"https?://[^\s<>()\]\[\"']+")
        rows = [{"url": url, "title": "", "text": ""} for url in url_pattern.findall(output)]
    candidates = []
    seen = set()
    for row in rows:
        url = str(row.get("url") or row.get("link") or "").strip()
        if not url or url in seen:
            continue
        try:
            validate_public_url(url)
        except ValueError:
            continue
        seen.add(url)
        candidates.append(
            {
                "url": url,
                "title": str(row.get("title") or row.get("name") or ""),
                "snippet": str(
                    row.get("text") or row.get("snippet") or row.get("description") or ""
                )[:4000],
                "source": "exa",
                "metadata": {"raw": {k: v for k, v in row.items() if k not in {"text", "snippet"}}},
            }
        )
    return candidates[: max(1, min(int(num_results), 20))]
