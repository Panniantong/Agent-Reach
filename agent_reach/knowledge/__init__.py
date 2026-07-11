# -*- coding: utf-8 -*-
"""Distilled methodology knowledge bases (committed, human-reviewed).

Raw backfill material lives under ``~/.agent-reach/radar/backfill`` (never
committed); what lands here is the distilled essence — regenerate with
``agent-reach radar-backfill --distill``, review, then commit.
"""

from __future__ import annotations

import re
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).parent


def load_knowledge(name: str = "karpathy") -> str:
    """Full knowledge-base markdown; empty string when absent (never raises)."""
    path = _KNOWLEDGE_DIR / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def knowledge_rules(name: str = "karpathy") -> str:
    """Only the ``## 精要規則`` section — terse, fact-free rules safe to feed
    into a mentor system prompt (the full KB stays out of small students'
    context so they can't plagiarize it)."""
    text = load_knowledge(name)
    if not text:
        return ""
    m = re.search(r"^## 精要規則\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def list_wiki_topics() -> list[str]:
    """Topics that have a committed wiki page under ``knowledge/wiki/``."""
    wiki = _KNOWLEDGE_DIR / "wiki"
    if not wiki.is_dir():
        return []
    return sorted(p.stem for p in wiki.glob("*.md"))
