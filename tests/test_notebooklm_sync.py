# -*- coding: utf-8 -*-
"""NotebookLM sync tests — fully offline via an async FakeClient.

No notebooklm-py import anywhere (it's an optional extra); _open_client and
sync_available are monkeypatched.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import agent_reach.integrations.notebooklm_sync as nls
from agent_reach.radar import Item
from agent_reach.integrations.notebooklm_sync import load_state, run_sync

WHEN = datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc)
SOURCES = {"topics": {"ee": {"label": "EE"}}, "notebooklm_min_score": 6}


def _paper(aid, score, topic="ee"):
    return Item(
        source="arxiv", kind="paper", title=f"Paper {aid}",
        url=f"https://arxiv.org/abs/{aid}", score=score,
        extra={"arxiv_id": aid, "topic": topic, "topics": [topic]},
    )


class FakeNotebooks:
    def __init__(self, client):
        self.client = client
        self.created = []

    async def create(self, title):
        self.created.append(title)
        return SimpleNamespace(id=f"nb-{len(self.created)}", title=title)


class FakeSourcesAPI:
    def __init__(self, client, existing=None, explode=False):
        self.client = client
        self.existing = existing or []
        self.explode = explode
        self.added_urls = []
        self.added_texts = []

    async def list(self, nb_id):
        return self.existing

    async def add_url(self, nb_id, url, wait=False):
        if self.explode:
            raise RuntimeError("rate limited")
        self.added_urls.append((nb_id, url))

    async def add_text(self, nb_id, title, content, wait=False):
        if self.explode:
            raise RuntimeError("rate limited")
        self.added_texts.append((nb_id, title, content))


class FakeSettings:
    def __init__(self, source_limit=300):
        self.source_limit = source_limit

    async def get_account_limits(self):
        return SimpleNamespace(notebook_limit=100, source_limit=self.source_limit)


class FakeClient:
    def __init__(self, existing_sources=None, source_limit=300, explode=False):
        self.notebooks = FakeNotebooks(self)
        self.sources = FakeSourcesAPI(self, existing_sources, explode)
        self.settings = FakeSettings(source_limit)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _wire(monkeypatch, tmp_path, client, papers=None, deepdives=None):
    monkeypatch.setattr(nls, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(nls, "_ADD_PACING_S", 0.0)
    monkeypatch.setattr(nls, "sync_available", lambda config=None: (True, "ok"))
    monkeypatch.setattr(nls, "_open_client", lambda config: client)
    monkeypatch.setattr(nls, "_load_deepdives", lambda when: deepdives or [])
    import agent_reach.radar_wiki as rw
    monkeypatch.setattr(rw, "_load_all_papers", lambda s, c, w: papers or [])


def test_sync_pushes_urls_and_keyed_texts(monkeypatch, tmp_path):
    client = FakeClient()
    dd = {"arxiv_id": "2607.1", "topic": "ee", "title": "Paper 2607.1", "text": "深讀內容"}
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.1", 9)], deepdives=[dd])
    result = run_sync(sources=SOURCES, when=WHEN)
    assert result["ok"] and result["topics"]["ee"]["added"] == 2
    assert client.notebooks.created == ["EE-2026Q3"]
    assert client.sources.added_urls[0][1] == "https://arxiv.org/abs/2607.1"
    title = client.sources.added_texts[0][1]
    assert title.startswith("[dd:2026-07-11-2607.1]")  # stable key embedded in title
    # State persisted with both keys.
    state = load_state()
    assert set(state["pushed"]["ee"]) == {"url:2607.1", "dd:2026-07-11-2607.1"}


def test_rerun_skips_already_pushed(monkeypatch, tmp_path):
    client = FakeClient()
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.1", 9)])
    assert run_sync(sources=SOURCES, when=WHEN)["topics"]["ee"]["added"] == 1
    result2 = run_sync(sources=SOURCES, when=WHEN)
    assert result2["topics"]["ee"].get("skipped") is True
    assert len(client.sources.added_urls) == 1  # no duplicate push


def test_low_score_papers_not_pushed(monkeypatch, tmp_path):
    client = FakeClient()
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.2", 3)])
    result = run_sync(sources=SOURCES, when=WHEN)
    assert result["topics"]["ee"].get("skipped") is True
    assert client.sources.added_urls == []


def test_server_rescan_dedupes_without_local_state(monkeypatch, tmp_path):
    existing = [SimpleNamespace(title="[dd:2026-07-10-2607.1] old", url="")]
    client = FakeClient(existing_sources=existing)
    dd = {"arxiv_id": "2607.1", "topic": "ee", "title": "T", "text": "x"}
    monkeypatch.setattr(nls, "STATE_FILE", tmp_path / "state.json")
    _wire(monkeypatch, tmp_path, client, deepdives=dd and [dd])
    result = run_sync(sources=SOURCES, when=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc))
    # Key found on the server → recorded as pushed, no duplicate add_text.
    assert result["topics"]["ee"]["added"] == 0
    assert client.sources.added_texts == []


def test_shard_rotation_near_source_limit(monkeypatch, tmp_path):
    client = FakeClient(source_limit=300)
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.3", 9)])
    state_file = tmp_path / "state.json"
    state_file.write_text(
        '{"notebooks": {"ee": {"id": "nb-old", "title": "EE-2026Q3", "source_count": 297}},'
        ' "pushed": {}}', encoding="utf-8",
    )
    result = run_sync(sources=SOURCES, when=WHEN)
    # 297 + 1 > 300 - 5 → new shard created (same quarter → suffixed).
    assert result["topics"]["ee"]["added"] == 1
    assert client.notebooks.created == ["EE-2026Q3-0711"]
    assert load_state()["notebooks"]["ee"]["title"] == "EE-2026Q3-0711"


def test_run_sync_never_raises_on_client_explosion(monkeypatch, tmp_path):
    client = FakeClient(explode=True)
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.4", 9)])
    result = run_sync(sources=SOURCES, when=WHEN)
    assert result["ok"]  # per-source failures degrade
    assert result["topics"]["ee"]["added"] == 0


def test_dry_run_pushes_nothing_and_writes_no_state(monkeypatch, tmp_path):
    client = FakeClient()
    _wire(monkeypatch, tmp_path, client, papers=[_paper("2607.5", 9)])
    result = run_sync(sources=SOURCES, when=WHEN, dry_run=True)
    assert result["topics"]["ee"]["dry_run"] is True
    assert result["topics"]["ee"]["planned"] == ["url:2607.5"]
    assert client.sources.added_urls == [] and client.notebooks.created == []
    assert not (tmp_path / "state.json").exists()


def test_unavailable_reports_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(nls, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(nls, "sync_available", lambda config=None: (False, "未安裝"))
    result = run_sync(sources=SOURCES, when=WHEN)
    assert result == {"ok": False, "error": "未安裝"}
