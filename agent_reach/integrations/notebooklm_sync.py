# -*- coding: utf-8 -*-
"""NotebookLM per-topic sync (optional extra: ``pip install "agent-reach[notebooklm]"``).

Pushes each topic's high-scoring arXiv papers (``add_url``) and completed
deep-dive reports (``add_text``) into a long-lived NotebookLM notebook per
topic, sharding to a new ``TOPIC-YYYYQn`` notebook when the account's
per-notebook source limit approaches.

Dedupe is dual-keyed because ``add_text`` is NOT idempotent upstream:
stable keys (``url:<arxiv_id>`` / ``dd:<date>-<arxiv_id>``) live in the
local state file AND are embedded in the source title, and existing
sources are rescanned at sync start — worst case is a duplicate source,
never data loss.

All ``notebooklm`` imports stay inside functions (the module itself is
always importable; evolve's pytest gate never needs the extra). Auth is a
one-time user step: ``notebooklm login --master-token --account <you>``.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from agent_reach.config import Config
from agent_reach.radar import RADAR_DIR, Item, load_sources

STATE_FILE = RADAR_DIR / "notebooklm" / "state.json"
# NotebookLM rate limiting is strict — pace every add. Module-level so tests zero it.
_ADD_PACING_S = 2.0
_KEY_RE = re.compile(r"\[(dd:[^\]]+|url:[^\]]+)\]")


# ── availability / state ──────────────────────────────────────────────────


def sync_available(config: Optional[Config] = None) -> tuple[bool, str]:
    """(ok, reason). Import + profile presence; no network."""
    try:
        import notebooklm  # noqa: F401
    except ImportError:
        return False, '未安裝 notebooklm-py — pip install "agent-reach[notebooklm]"'
    config = config or Config()
    if not config.get("notebooklm_profile"):
        return False, (
            "未設 notebooklm_profile — 先 notebooklm login --master-token --account <帳號>，"
            "再 agent-reach 設定 notebooklm_profile（通常是 default）"
        )
    return True, "ready"


def _open_client(config: Config):
    """The ONLY place notebooklm is imported for API calls (async CM)."""
    from notebooklm import NotebookLMClient

    profile = config.get("notebooklm_profile") or "default"
    return NotebookLMClient.from_storage(profile=profile)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("notebooks", {})
            data.setdefault("pushed", {})
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning(f"notebooklm state unreadable, starting fresh: {e}")
    return {"notebooks": {}, "pushed": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ── notebook lifecycle ────────────────────────────────────────────────────


def _quarter_title(topic: str, when: datetime) -> str:
    return f"{topic.upper()}-{when:%Y}Q{(when.month - 1) // 3 + 1}"


async def _ensure_notebook(client, state: dict, topic: str, planned_adds: int,
                           when: datetime, margin: int) -> str:
    """Current topic notebook id; shard to a fresh one near the source limit."""
    nb = state["notebooks"].get(topic)
    source_limit = 300  # conservative default when limits are unavailable
    try:
        limits = await client.settings.get_account_limits()
        source_limit = int(getattr(limits, "source_limit", None) or source_limit)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"account limits unavailable, assuming {source_limit}: {e}")
    if nb and nb.get("source_count", 0) + planned_adds <= source_limit - margin:
        return nb["id"]
    title = _quarter_title(topic, when)
    if nb:
        logger.info(f"notebooklm[{topic}]: near source limit, sharding to a new notebook")
        if nb.get("title", "").startswith(title):
            title = f"{title}-{when:%m%d}"  # same-quarter overflow shard
    created = await client.notebooks.create(title)
    state["notebooks"][topic] = {"id": created.id, "title": title, "source_count": 0}
    return created.id


async def _rebuild_pushed(client, nb_id: str) -> set[str]:
    """Rescan existing sources → stable keys (cross-machine dedupe)."""
    keys: set[str] = set()
    try:
        for src in await client.sources.list(nb_id):
            title = str(getattr(src, "title", "") or "")
            m = _KEY_RE.search(title)
            if m:
                keys.add(m.group(1))
            url = str(getattr(src, "url", "") or "")
            m2 = re.search(r"arxiv\.org/abs/([\w.\-/]+)", url or title)
            if m2:
                keys.add(f"url:{m2.group(1)}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notebooklm source rescan failed: {e}")
    return keys


# ── per-topic sync ────────────────────────────────────────────────────────


async def _sync_topic(client, state: dict, topic: str, papers: list[Item],
                      deepdives: list[dict], when: datetime, min_score: float,
                      margin: int, dry_run: bool) -> dict:
    pushed = set(state["pushed"].get(topic) or [])
    jobs: list[tuple[str, str, object]] = []
    for p in papers:
        aid = str(p.extra.get("arxiv_id") or "")
        if p.score >= min_score and aid and f"url:{aid}" not in pushed:
            jobs.append(("url", f"url:{aid}", p))
    for dd in deepdives:
        key = f"dd:{when:%Y-%m-%d}-{dd.get('arxiv_id', '')}"
        if key not in pushed:
            jobs.append(("text", key, dd))
    if not jobs:
        return {"topic": topic, "ok": True, "added": 0, "skipped": True}
    if dry_run:
        return {"topic": topic, "ok": True, "dry_run": True,
                "planned": [k for _, k, _ in jobs]}

    nb_id = await _ensure_notebook(client, state, topic, len(jobs), when, margin)
    server_keys = await _rebuild_pushed(client, nb_id)
    added = 0
    for i, (kind, key, payload) in enumerate(jobs):
        if key in server_keys:
            pushed.add(key)
            continue
        if i and _ADD_PACING_S:
            await asyncio.sleep(_ADD_PACING_S)
        try:
            if kind == "url":
                await client.sources.add_url(nb_id, payload.url)
            else:
                title = f"[{key}] {payload.get('title', '')}"[:180]
                await client.sources.add_text(nb_id, title, payload.get("text", ""))
            pushed.add(key)
            added += 1
            state["notebooks"][topic]["source_count"] = (
                state["notebooks"][topic].get("source_count", 0) + 1
            )
        except Exception as e:  # noqa: BLE001 - one source failing must not kill the topic
            logger.warning(f"notebooklm add failed ({key}): {e}")
    state["pushed"][topic] = sorted(pushed)
    return {"topic": topic, "ok": True, "added": added,
            "notebook": state["notebooks"][topic]["title"]}


# ── inputs ────────────────────────────────────────────────────────────────


def _load_deepdives(when: datetime) -> list[dict]:
    """Today's completed deep-dive reports (index.json entries + text)."""
    from agent_reach.radar_arxiv import DEEPDIVE_DIR

    idx = DEEPDIVE_DIR / f"{when:%Y-%m-%d}-index.json"
    if not idx.exists():
        return []
    try:
        entries = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for e in entries:
        p = DEEPDIVE_DIR / str(e.get("file") or "")
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            if "status: PENDING" not in text:
                out.append({**e, "text": text})
    return out


def _topic_of(entry: dict | Item, topic: str) -> bool:
    extra = entry.extra if isinstance(entry, Item) else entry
    return extra.get("topic") == topic or topic in (extra.get("topics") or [])


# ── orchestration ─────────────────────────────────────────────────────────


def run_sync(
    topics: Optional[list[str]] = None,
    sources: Optional[dict] = None,
    config: Optional[Config] = None,
    dry_run: bool = False,
    when: Optional[datetime] = None,
) -> dict:
    """Sync topics into NotebookLM. Never raises — errors come back in the dict."""
    config = config or Config()
    ok, msg = sync_available(config)
    if not ok:
        return {"ok": False, "error": msg}
    when = when or datetime.now(timezone.utc).astimezone()
    sources = sources or load_sources()
    wanted = list(topics) if topics else sorted(sources.get("topics") or {})
    if not wanted:
        return {"ok": False, "error": "沒有配置任何 topics（radar.yaml）"}
    min_score = float(sources.get("notebooklm_min_score", 6))
    margin = int(sources.get("notebooklm_shard_margin", 5))

    from agent_reach.radar_wiki import _load_all_papers

    papers = _load_all_papers(sources, config, when)
    deepdives = _load_deepdives(when)
    state = load_state()

    async def _run() -> dict:
        results: dict[str, dict] = {}
        async with _open_client(config) as client:
            for t in wanted:
                try:
                    results[t] = await _sync_topic(
                        client, state, t,
                        [p for p in papers if _topic_of(p, t)],
                        [d for d in deepdives if d.get("topic") == t],
                        when, min_score, margin, dry_run,
                    )
                except Exception as e:  # noqa: BLE001 - one topic must not kill the run
                    logger.warning(f"notebooklm sync failed for {t}: {e}")
                    results[t] = {"topic": t, "ok": False, "error": str(e)}
        return results

    try:
        results = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001 - auth/session failures degrade gracefully
        logger.warning(f"notebooklm sync aborted: {e}")
        return {"ok": False, "error": str(e)}
    if not dry_run:
        save_state(state)
    return {"ok": True, "topics": results, "state_file": str(STATE_FILE)}


def sync_status() -> dict:
    """Local state summary for CLI/UI."""
    state = load_state()
    return {
        "state_file": str(STATE_FILE),
        "notebooks": state.get("notebooks", {}),
        "pushed_counts": {t: len(v) for t, v in (state.get("pushed") or {}).items()},
    }
