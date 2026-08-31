# -*- coding: utf-8 -*-
"""Read-only adapter for the documented x_subs_downloader JSONL archive.

The upstream downloader remains an independently operated collector.  Agent
Reach consumes only its documented ``posts.jsonl`` output and never imports or
patches the downloader's Python internals.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_reach.radar import Item

SERENITY_HANDLE = "aleabitoreddit"
_POST_ID = re.compile(r"^[0-9]{5,30}$")


@dataclass(frozen=True)
class SerenityArchive:
    """Normalized archive records plus non-evidentiary translations."""

    items: list[Item]
    translations: dict[str, dict[str, str]]
    manifest: dict[str, Any]


def load_x_subs_jsonl(
    path: Path | str,
    *,
    handle: str = SERENITY_HANDLE,
    max_records: int = 10_000,
) -> SerenityArchive:
    """Load the upstream archive without writing beside it.

    ``en`` is the downloader's documented original-text field and is therefore
    the only text admitted to the evidence path. ``zh`` remains a translation
    display field. Records whose two fields are identical retain the text but
    are marked as having an uncertain source language.
    """

    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() != ".jsonl":
        raise ValueError("Serenity archive must be a .jsonl file")
    if not source.is_file():
        raise FileNotFoundError(f"Serenity archive not found: {source}")
    if not 1 <= int(max_records) <= 100_000:
        raise ValueError("max_records must be between 1 and 100000")

    items: list[Item] = []
    translations: dict[str, dict[str, str]] = {}
    malformed = 0
    skipped = 0
    lines = 0
    digest = hashlib.sha256()

    with source.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            lines += 1
            if len(items) >= int(max_records):
                continue
            try:
                row = json.loads(raw_line.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                malformed += 1
                continue
            if not isinstance(row, dict):
                malformed += 1
                continue
            post_id = str(row.get("id") or "").strip()
            timestamp = str(row.get("timestamp") or "").strip()
            original = str(row.get("en") or "").strip()
            translated_zh = str(row.get("zh") or "").strip()
            if not _POST_ID.fullmatch(post_id) or not timestamp or not original:
                skipped += 1
                continue
            url = f"https://x.com/{handle.lstrip('@')}/status/{post_id}"
            source_language = "en" if original != translated_zh else "und"
            images = row.get("images") if isinstance(row.get("images"), list) else []
            items.append(
                Item(
                    source=f"x-subs:@{handle.lstrip('@')}",
                    kind="tweet",
                    title=f"Serenity subscription post {post_id}",
                    url=url,
                    text=original,
                    author=f"@{handle.lstrip('@')}",
                    ts=timestamp,
                    extra={
                        "isRetweet": False,
                        "subscriberOnly": True,
                        "archiveRecordId": post_id,
                        "images": [str(value) for value in images if value],
                        "sourceLanguage": source_language,
                        "originalTextVerified": source_language == "en",
                        "backend": "x_subs_downloader_jsonl",
                    },
                )
            )
            translations[url] = {
                "zh_hant": translated_zh if translated_zh != original else "",
                "en": original,
            }

    return SerenityArchive(
        items=items,
        translations=translations,
        manifest={
            "backend": "x_subs_downloader_jsonl",
            "filename": source.name,
            "sha256": digest.hexdigest(),
            "lines": lines,
            "valid_records": len(items),
            "malformed_records": malformed,
            "skipped_records": skipped,
            "truncated": lines > int(max_records),
            "read_only": True,
            "archive_complete": False,
            "original_text_rule": "verified only when en and zh differ",
        },
    )
