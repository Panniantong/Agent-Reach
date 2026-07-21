# Radar Local Search Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent Radar-only SQLite/FTS5 catalog with deterministic labels, conservative event clustering, separate heat/corroboration scores, CLI/UI search, and a TurboVec-ready adapter boundary without installing a model or TurboVec.

**Architecture:** A new `agent_reach.radar_search` package owns configuration, normalization, durable observations, SQLite schema, clustering, scoring, search, rebuilds, and the future vector contract. Existing Radar producers call one best-effort hook after their authoritative writes; the CLI and FastAPI UI open short-lived catalog connections through the package's public service functions.

**Tech Stack:** Python 3.10+, stdlib `sqlite3`, `hashlib`, `urllib.parse`, `dataclasses`, `pathlib`, `json`, `math`, `re`, existing PyYAML/Loguru/Rich, pytest, FastAPI test client for the optional UI suite.

## Global Constraints

- Scope is only data produced by Agent Reach Radar: external sidecar items, digest history, deep dives, and promoted Wiki pages.
- The default catalog path is `~/.agent-reach/radar/search/catalog.sqlite3`, resolved from the existing `RADAR_DIR`.
- Phase 1 must not install/import TurboVec, choose/generate embeddings, run a local LLM, or call Grok at runtime.
- Grok Build CLI is development-review-only. No `grok*` executable was detected locally while writing this plan, so execution must not depend on it or invent a command. If the user later installs/configures it, its review is advisory and all repository tests remain authoritative.
- Labels are deterministic and store `rule_id` plus `rule_version`; no model-generated labels are persisted.
- UI/CLI wording is `corroboration` / `交叉佐證`, never a truth probability or verification claim.
- Derived digests, deep dives, and Wiki pages are searchable but never contribute external heat or corroboration evidence.
- Reprocessing the same source record must not duplicate observations or change heat.
- Rebuilds preserve retained observations and unchanged `chunk_id` values; changed chunks get new IDs above the prior high-water mark.
- Use FTS5 `trigram` when available, fall back to `unicode61`, and use a bounded `LIKE` query only for short CJK input that FTS cannot represent.
- Do not add a runtime dependency: use Python's bundled SQLite and standard library for phase 1.
- Follow existing conventions: Python 3.10+ type hints, Loguru diagnostics, Rich human CLI output, JSON diagnostics on stderr, `argparse` dispatch.
- Tests use synthetic records and temporary directories; they must not access the network, Grok, TurboVec, an embedding service, or a local model.
- Before every commit, run the targeted tests and then `python -m pytest tests/ -v` because `CLAUDE.md` requires the full suite before committing.
- Preserve the user's untracked `.claude/` and `agents/` directories; stage only files named by the current task.
- Do not bump the package version for this feature.

## File Map

New production files:

- `agent_reach/radar_search/__init__.py` — stable public imports for catalog update/rebuild/search/status and the safe hook.
- `agent_reach/radar_search/config.py` — validated `SearchConfig` and Radar YAML defaults.
- `agent_reach/radar_search/schema.py` — SQLite connection policy, versioned schema, tokenizer detection, transactions.
- `agent_reach/radar_search/models.py` — artifact, normalized document, chunk, request/result, status dataclasses.
- `agent_reach/radar_search/normalize.py` — canonical URLs/domains/text, stable keys, language and entity primitives.
- `agent_reach/radar_search/labels.py` — deterministic rule-label generation.
- `agent_reach/radar_search/chunking.py` — short-item and Markdown heading/paragraph chunking.
- `agent_reach/radar_search/artifacts.py` — Radar sidecar/digest/deep-dive/Wiki artifact readers.
- `agent_reach/radar_search/catalog.py` — idempotent ingestion, durable observations, FTS synchronization, update/status.
- `agent_reach/radar_search/clustering.py` — candidate selection, SimHash similarity, deterministic cluster assignment.
- `agent_reach/radar_search/scoring.py` — 0–100 heat and corroboration calculations.
- `agent_reach/radar_search/lifecycle.py` — catalog lock, full rebuild, atomic replacement, bounded backup.
- `agent_reach/radar_search/search.py` — filters, FTS/LIKE retrieval, ranking, cluster hydration.
- `agent_reach/radar_search/hooks.py` — non-fatal automatic indexing adapter for producer workflows.
- `agent_reach/radar_search/vector.py` — TurboVec-independent `Protocol`, match, and manifest JSON contract.

New tests:

- `tests/test_radar_search_schema.py`
- `tests/test_radar_search_rules.py`
- `tests/test_radar_search_catalog.py`
- `tests/test_radar_search_clustering.py`
- `tests/test_radar_search_lifecycle.py`
- `tests/test_radar_search_query.py`
- `tests/test_radar_search_hooks.py`
- `tests/test_radar_search_vector.py`
- `tests/fixtures/radar_search/latest-items.json` — tracked model-free smoke input.

Existing files modified:

- `agent_reach/radar.py:70-320,988-1016` — default `search` config and post-write hook.
- `agent_reach/radar_arxiv.py:330-384` — post-deep-dive hook.
- `agent_reach/radar_wiki.py:274-291` — post-promotion hook.
- `agent_reach/cli.py:50-310` and command-handler area — `radar-index` and `radar-search` commands.
- `agent_reach/radar_ui/jobs.py:57-77` — active-job query used to reject concurrent rebuilds.
- `agent_reach/radar_ui/server.py:89-211` — search/status/cluster/reindex endpoints.
- `agent_reach/radar_ui/static/index.html` — search navigation, filters, event cards, source expansion, index status/rebuild control.
- `tests/test_cli.py` — command routing, JSON/human output, validation.
- `tests/test_radar.py`, `tests/test_radar_arxiv.py`, `tests/test_radar_wiki.py` — producer hook placement and non-fatal behavior.
- `tests/test_radar_ui.py` — new API/background-job contracts.
- `agent_reach/guides/radar.md` — indexing/search commands, score semantics, phase-2 boundary.

---

### Task 1: Catalog Configuration and Versioned SQLite Schema

**Files:**
- Create: `agent_reach/radar_search/__init__.py`
- Create: `agent_reach/radar_search/config.py`
- Create: `agent_reach/radar_search/schema.py`
- Modify: `agent_reach/radar.py:70-320`
- Test: `tests/test_radar_search_schema.py`

**Interfaces:**
- Produces: `SearchConfig`, `load_search_config(sources: Mapping[str, Any], radar_dir: Path) -> SearchConfig`.
- Produces: `connect_catalog(path: Path, *, read_only: bool = False) -> sqlite3.Connection`.
- Produces: `initialize_schema(conn: sqlite3.Connection) -> str`, returning `trigram` or `unicode61`.
- Produces constants `SCHEMA_VERSION = 1`, `RULE_VERSION = 1`, `CLUSTER_VERSION = 1`, `SCORE_VERSION = 1`.

- [ ] **Step 1: Write failing configuration and schema tests**

```python
# tests/test_radar_search_schema.py
import sqlite3

import pytest

from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.schema import SCHEMA_VERSION, connect_catalog, initialize_schema


def test_search_config_defaults_and_path(tmp_path):
    cfg = load_search_config({}, tmp_path)
    assert cfg.enabled is True
    assert cfg.automatic is True
    assert cfg.catalog_path == tmp_path / "search" / "catalog.sqlite3"
    assert cfg.cluster_window_days == 7
    assert cfg.cluster_threshold == pytest.approx(0.84)
    assert sum(cfg.heat_weights.values()) == pytest.approx(1.0)
    assert sum(cfg.corroboration_weights.values()) == pytest.approx(1.0)


def test_search_config_rejects_invalid_weight_sum(tmp_path):
    with pytest.raises(ValueError, match="heat_weights"):
        load_search_config({"search": {"heat_weights": {"mentions": 1.0}}}, tmp_path)


def test_schema_creates_all_tables_and_records_tokenizer(tmp_path):
    conn = connect_catalog(tmp_path / "catalog.sqlite3")
    tokenizer = initialize_schema(conn)
    names = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    )}
    assert {"catalog_meta", "documents", "observations", "chunks", "labels",
            "clusters", "cluster_members", "index_runs", "chunks_fts"} <= names
    assert tokenizer in {"trigram", "unicode61"}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_schema_rejects_newer_catalog_version(tmp_path):
    conn = connect_catalog(tmp_path / "future.sqlite3")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="newer catalog schema"):
        initialize_schema(conn)
```

- [ ] **Step 2: Run the test and verify the missing package failure**

Run: `python -m pytest tests/test_radar_search_schema.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'agent_reach.radar_search'`.

- [ ] **Step 3: Add exact search defaults and validation**

Define the single source of defaults in `agent_reach/radar_search/config.py`, then reference it from `DEFAULT_SOURCES` instead of duplicating nested mappings:

```python
# agent_reach/radar_search/config.py
DEFAULT_SEARCH_CONFIG: dict[str, Any] = {
    "enabled": True,
    "automatic": True,
    "catalog_path": "",
    "cluster_window_days": 7,
    "cluster_threshold": 0.84,
    "chunk_chars": 1800,
    "chunk_overlap_chars": 200,
    "recency_half_life_hours": 72.0,
    "engagement_cap": 100000.0,
    "default_limit": 20,
    "max_limit": 100,
    "heat_weights": {
        "mentions": 0.35,
        "source_coverage": 0.25,
        "recency": 0.25,
        "engagement": 0.15,
    },
    "corroboration_weights": {
        "independent_domains": 0.45,
        "independent_source_families": 0.35,
        "originality": 0.20,
    },
    "tracking_params": ["fbclid", "gclid", "mc_cid", "mc_eid"],
    "domain_aliases": {},
    "entities": {},
    "tickers": [],
    "score_bands": {"high": 20.0, "medium": 5.0},
}

# agent_reach/radar.py
from copy import deepcopy
from agent_reach.radar_search.config import DEFAULT_SEARCH_CONFIG

# inside DEFAULT_SOURCES
"search": deepcopy(DEFAULT_SEARCH_CONFIG),
```

Create the exact immutable config surface:

```python
@dataclass(frozen=True)
class SearchConfig:
    enabled: bool
    automatic: bool
    catalog_path: Path
    cluster_window_days: int
    cluster_threshold: float
    chunk_chars: int
    chunk_overlap_chars: int
    recency_half_life_hours: float
    engagement_cap: float
    default_limit: int
    max_limit: int
    heat_weights: Mapping[str, float]
    corroboration_weights: Mapping[str, float]
    tracking_params: frozenset[str]
    domain_aliases: Mapping[str, str]
    entities: Mapping[str, tuple[str, ...]]
    tickers: frozenset[str]
    score_bands: Mapping[str, float]
```

`load_search_config` merges nested weight dictionaries over the defaults, resolves a blank catalog path under `radar_dir / "search"`, requires positive window/chunk/limit/cap values, requires `0 <= cluster_threshold <= 1`, requires `chunk_overlap_chars < chunk_chars`, normalizes collection fields into the types above, and validates each weight dictionary has exactly the approved keys and sums to 1.0 within `1e-9`.

- [ ] **Step 4: Create the schema with all approved tables**

Implement `schema.py` with this connection policy and complete table set:

```python
SCHEMA_VERSION = 1
RULE_VERSION = 1
CLUSTER_VERSION = 1
SCORE_VERSION = 1


def connect_catalog(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=5.0)
    else:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if not read_only:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  document_key TEXT PRIMARY KEY,
  source_id TEXT,
  canonical_url TEXT,
  original_url TEXT,
  canonical_target_url TEXT,
  source_family TEXT NOT NULL,
  source_domain TEXT,
  kind TEXT NOT NULL,
  evidence_role TEXT NOT NULL CHECK (evidence_role IN ('external', 'derived')),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  author TEXT,
  published_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  radar_score REAL,
  raw_metadata_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  rule_version INTEGER NOT NULL,
  is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1))
);
CREATE TABLE IF NOT EXISTS observations (
  observation_key TEXT PRIMARY KEY,
  document_key TEXT NOT NULL REFERENCES documents(document_key) ON DELETE CASCADE,
  artifact_kind TEXT NOT NULL,
  artifact_identity TEXT NOT NULL,
  source_record_id TEXT,
  observed_at TEXT NOT NULL,
  raw_record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_key TEXT NOT NULL REFERENCES documents(document_key) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  heading TEXT,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  UNIQUE(document_key, ordinal, content_hash)
);
CREATE TABLE IF NOT EXISTS labels (
  document_key TEXT NOT NULL REFERENCES documents(document_key) ON DELETE CASCADE,
  namespace TEXT NOT NULL,
  value TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  rule_version INTEGER NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  UNIQUE(document_key, namespace, value, rule_id, rule_version)
);
CREATE TABLE IF NOT EXISTS clusters (
  cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
  representative_document_key TEXT NOT NULL REFERENCES documents(document_key),
  representative_title TEXT NOT NULL,
  topic TEXT,
  kind TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  mention_count INTEGER NOT NULL,
  unique_domain_count INTEGER NOT NULL,
  unique_source_family_count INTEGER NOT NULL,
  heat_score REAL NOT NULL,
  corroboration_score REAL NOT NULL,
  cluster_version INTEGER NOT NULL,
  score_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cluster_members (
  cluster_id INTEGER NOT NULL REFERENCES clusters(cluster_id) ON DELETE CASCADE,
  document_key TEXT NOT NULL REFERENCES documents(document_key) ON DELETE CASCADE,
  match_reason TEXT NOT NULL,
  similarity_json TEXT NOT NULL,
  PRIMARY KEY(cluster_id, document_key),
  UNIQUE(document_key)
);
CREATE TABLE IF NOT EXISTS index_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  scanned INTEGER NOT NULL DEFAULT 0,
  inserted INTEGER NOT NULL DEFAULT 0,
  updated INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  deleted INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  schema_version INTEGER NOT NULL,
  rule_version INTEGER NOT NULL,
  error_summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documents_time ON documents(published_at, first_seen_at);
CREATE INDEX IF NOT EXISTS idx_documents_filters ON documents(kind, source_family, evidence_role);
CREATE INDEX IF NOT EXISTS idx_observations_document ON observations(document_key);
CREATE INDEX IF NOT EXISTS idx_labels_lookup ON labels(namespace, value, document_key);
CREATE INDEX IF NOT EXISTS idx_cluster_members_document ON cluster_members(document_key);
"""
```

Probe FTS5 by creating and dropping a temporary trigram table. If trigram fails but FTS5 works, choose `unicode61`; if FTS5 itself fails, raise `RuntimeError("SQLite FTS5 is unavailable")`. Create `chunks_fts` with unindexed `chunk_id`/`document_key` plus `title`, `heading`, `content`, `author`, `labels`, `source`, and `topic`. Store tokenizer and all four versions in `catalog_meta`, set `PRAGMA user_version = 1`, and reject a database whose `user_version` is greater than the supported version.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_schema.py -v`

Expected: PASS with 4 tests.

Run: `python -m pytest tests/ -v`

Expected: all existing and new tests PASS.

- [ ] **Step 6: Commit the foundation**

```bash
git add agent_reach/radar.py agent_reach/radar_search/__init__.py agent_reach/radar_search/config.py agent_reach/radar_search/schema.py tests/test_radar_search_schema.py
git commit -m "feat(radar-search): add catalog schema and config"
```

---

### Task 2: Deterministic Normalization, Labels, and Chunking

**Files:**
- Create: `agent_reach/radar_search/models.py`
- Create: `agent_reach/radar_search/normalize.py`
- Create: `agent_reach/radar_search/labels.py`
- Create: `agent_reach/radar_search/chunking.py`
- Test: `tests/test_radar_search_rules.py`

**Interfaces:**
- Produces `ArtifactRecord`, `NormalizedDocument`, `Label`, and `ChunkDraft` immutable dataclasses.
- Produces `normalize_record(record: ArtifactRecord, config: SearchConfig) -> NormalizedDocument`.
- Produces `generate_labels(document: NormalizedDocument, sources: Mapping[str, Any], config: SearchConfig) -> tuple[Label, ...]`.
- Produces `chunk_document(document: NormalizedDocument, config: SearchConfig) -> tuple[ChunkDraft, ...]`.

- [ ] **Step 1: Write failing rule tests with Chinese and English fixtures**

```python
# tests/test_radar_search_rules.py
from agent_reach.radar_search.chunking import chunk_document
from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.labels import generate_labels
from agent_reach.radar_search.models import ArtifactRecord
from agent_reach.radar_search.normalize import canonicalize_url, normalize_record


def _record(**overrides):
    base = dict(
        artifact_kind="sidecar", artifact_identity="latest-items.json",
        source_record_id="42", observed_at="2026-07-21T10:00:00+08:00",
        evidence_role="external", source="twitter:@alice", kind="tweet",
        title="TSMC 與 NVIDIA 推出新 HBM 平台", url="HTTPS://Example.COM:443/a?utm_source=x&b=2&a=1#frag",
        text="這是晶片與人工智慧新聞，包含資料中心與先進封裝。 paper arXiv:2607.01234 repo github.com/acme/turbovec $NVDA",
        author="Alice", score=30.0, published_at="2026-07-21T09:00:00+08:00",
        extra={"topic": "ee", "topics": ["ai", "ee"], "target_url": "https://news.example.com/story"},
    )
    base.update(overrides)
    return ArtifactRecord(**base)


def test_url_identity_and_rule_labels_are_deterministic(tmp_path):
    cfg = load_search_config({}, tmp_path)
    doc = normalize_record(_record(), cfg)
    assert canonicalize_url(_record().url, cfg.tracking_params) == "https://example.com/a?a=1&b=2"
    assert doc.document_key == normalize_record(_record(), cfg).document_key
    labels = {(x.namespace, x.value, x.rule_id) for x in generate_labels(doc, {"topic_keywords": ["hbm"]}, cfg)}
    assert ("topic", "ee", "field.topic") in labels
    assert ("paper", "2607.01234", "regex.arxiv") in labels
    assert ("repo", "acme/turbovec", "regex.github") in labels
    assert ("ticker", "NVDA", "regex.ticker") in labels
    assert ("language", "mixed", "unicode.script_ratio") in labels


def test_changed_content_keeps_document_key_but_changes_hash(tmp_path):
    cfg = load_search_config({}, tmp_path)
    before = normalize_record(_record(text="old"), cfg)
    after = normalize_record(_record(text="new"), cfg)
    assert before.document_key == after.document_key
    assert before.content_hash != after.content_hash


def test_configured_entity_dictionary(tmp_path):
    cfg = load_search_config({"search": {"entities": {"NVIDIA": ["nvidia", "輝達"]}}}, tmp_path)
    doc = normalize_record(_record(text="輝達發表新平台"), cfg)
    labels = generate_labels(doc, {}, cfg)
    assert any(x.namespace == "entity" and x.value == "NVIDIA" for x in labels)


def test_markdown_chunking_is_bounded_and_stable(tmp_path):
    cfg = load_search_config({"search": {"chunk_chars": 120, "chunk_overlap_chars": 20}}, tmp_path)
    doc = normalize_record(_record(evidence_role="derived", kind="deepdive",
        source_record_id=None, text="# A\n\n" + "甲乙丙丁" * 50 + "\n\n## B\n\nending"), cfg)
    chunks = chunk_document(doc, cfg)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(c.content and len(c.content) <= 140 for c in chunks)
    assert chunks == chunk_document(doc, cfg)
```

- [ ] **Step 2: Run the tests and verify missing modules fail**

Run: `python -m pytest tests/test_radar_search_rules.py -v`

Expected: FAIL during collection because `models`, `normalize`, `labels`, and `chunking` do not exist.

- [ ] **Step 3: Define the immutable records and normalization rules**

Implement the dataclasses with these exact fields:

```python
@dataclass(frozen=True)
class ArtifactRecord:
    artifact_kind: str
    artifact_identity: str
    source_record_id: str | None
    observed_at: str
    evidence_role: Literal["external", "derived"]
    source: str
    kind: str
    title: str
    url: str
    text: str
    author: str
    score: float | None
    published_at: str | None
    extra: Mapping[str, Any]


@dataclass(frozen=True)
class NormalizedDocument:
    document_key: str
    observation_key: str
    source_id: str | None
    canonical_url: str
    original_url: str
    canonical_target_url: str
    source_family: str
    source_domain: str
    kind: str
    evidence_role: Literal["external", "derived"]
    title: str
    body: str
    author: str
    published_at: str | None
    observed_at: str
    radar_score: float | None
    content_hash: str
    raw_record_json: str


@dataclass(frozen=True, order=True)
class Label:
    namespace: str
    value: str
    rule_id: str
    rule_version: int
    confidence: float = 1.0


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    heading: str
    content: str
    content_hash: str
    token_estimate: int
```

`canonicalize_url` must lowercase scheme/host, remove fragments/default ports, sort retained query pairs, drop every `utm_*` key and configured tracking key, preserve blank path as `/`, and return an empty string for invalid/empty input. Compute `document_key` from source family plus `source_record_id`, else canonical URL, else source/author/published/title. Compute `observation_key` from artifact kind/identity plus source record ID or document key. Normalize `source_family` to the lowercase prefix before the first colon. Use SHA-256 hexadecimal digests, NFKC text normalization, whitespace collapse, and a built-in registrable-domain approximation for `co.uk`, `org.uk`, `com.tw`, `com.cn`, `com.au`, and `co.jp`, overridden by `domain_aliases`. Language ratios count only CJK/Latin letters: emit `mixed` when each is at least 20%, otherwise `zh` or `en` when that script is at least 60%, and `unknown` for no qualifying script.

- [ ] **Step 4: Implement explicit deterministic label precedence and chunks**

`generate_labels` must add typed-field labels first, then URL/source labels, configured topic keyword labels, and bounded regex/dictionary labels. Use these rule IDs: `field.kind`, `field.source`, `field.author`, `field.topic`, `url.domain`, `url.class`, `keyword.topic`, `dictionary.entity`, `regex.arxiv`, `regex.github`, `regex.ticker`, `unicode.script_ratio`, `score.band`. Treat `search.entities` as `canonical_name -> list[alias]` and match aliases case-insensitively to their canonical entity values. Reject bare uppercase words as tickers; accept `$NVDA`, exchange-prefixed forms, or values in optional `search.tickers`. De-duplicate by the full `Label` value and return sorted output.

For chunks, return one chunk for external short items. For derived Markdown, split first at ATX headings and blank-line paragraph boundaries, then pack paragraphs to `chunk_chars`; carry at most `chunk_overlap_chars` of the previous chunk at a paragraph boundary. Estimate tokens as `max(1, ceil(len(content) / 4))` and hash normalized heading plus content.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_rules.py -v`

Expected: all rule/chunk tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit deterministic rules**

```bash
git add agent_reach/radar_search/models.py agent_reach/radar_search/normalize.py agent_reach/radar_search/labels.py agent_reach/radar_search/chunking.py tests/test_radar_search_rules.py
git commit -m "feat(radar-search): add deterministic document rules"
```

---

### Task 3: Artifact Readers and Idempotent Incremental Catalog

**Files:**
- Create: `agent_reach/radar_search/artifacts.py`
- Create: `agent_reach/radar_search/catalog.py`
- Create: `tests/fixtures/radar_search/latest-items.json`
- Modify: `agent_reach/radar_search/models.py`
- Modify: `agent_reach/radar_search/__init__.py`
- Test: `tests/test_radar_search_catalog.py`

**Interfaces:**
- Consumes: Task 1 schema/config and Task 2 normalization/labels/chunks.
- Produces: `discover_artifacts(radar_dir: Path, wiki_dir: Path) -> tuple[Path, ...]`.
- Produces: `read_artifact(path: Path, radar_dir: Path, wiki_dir: Path) -> tuple[ArtifactRecord, ...]`.
- Produces: `update_catalog(config: SearchConfig, sources: Mapping[str, Any], artifacts: Sequence[Path]) -> IndexStatus`.
- Produces: `catalog_status(config: SearchConfig) -> IndexStatus`.

- [ ] **Step 1: Write failing artifact and idempotence tests**

```json
{
  "generated_at": "2026-07-21T10:00:00+08:00",
  "items": {
    "web": [{
      "source": "exa", "kind": "web", "title": "TurboVec local search",
      "url": "https://example.com/turbovec", "text": "AI 晶片本地搜尋資料",
      "author": "Fixture", "score": 10,
      "ts": "2026-07-21T09:00:00+08:00", "extra": {"topic": "ee"}
    }]
  }
}
```

Save the JSON above as `tests/fixtures/radar_search/latest-items.json`, then add the catalog tests:

```python
# tests/test_radar_search_catalog.py
import json

from agent_reach.radar_search.artifacts import read_artifact
from agent_reach.radar_search.catalog import catalog_status, update_catalog
from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.schema import connect_catalog


def test_sidecar_update_is_idempotent_and_replaces_changed_chunks(tmp_path):
    sidecar = tmp_path / "latest-items.json"
    payload = {"generated_at": "2026-07-21T10:00:00+08:00", "items": {"web": [{
        "source": "exa", "kind": "web", "title": "TurboVec release",
        "url": "https://a.example/turbovec", "text": "first", "author": "A",
        "score": 10, "ts": "2026-07-21T09:00:00+08:00", "extra": {"topic": "ai"},
    }]}}
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    cfg = load_search_config({}, tmp_path)
    first = update_catalog(cfg, {"topic_keywords": ["turbovec"]}, [sidecar])
    second = update_catalog(cfg, {"topic_keywords": ["turbovec"]}, [sidecar])
    assert (first.inserted, second.skipped) == (1, 1)
    conn = connect_catalog(cfg.catalog_path, read_only=True)
    assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    old_chunk = conn.execute("SELECT chunk_id FROM chunks").fetchone()[0]
    conn.close()

    payload["items"]["web"][0]["text"] = "changed"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    update_catalog(cfg, {"topic_keywords": ["turbovec"]}, [sidecar])
    conn = connect_catalog(cfg.catalog_path, read_only=True)
    new_chunk = conn.execute("SELECT chunk_id FROM chunks").fetchone()[0]
    assert new_chunk > old_chunk
    assert conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 1


def test_digest_deepdive_and_wiki_are_derived(tmp_path):
    digest = tmp_path / "2026-07-21-1000.md"
    digest.write_text("# Digest\n\nmaterial", encoding="utf-8")
    records = read_artifact(digest, tmp_path, tmp_path / "wiki")
    assert len(records) == 1
    assert records[0].evidence_role == "derived"
    assert records[0].kind == "digest"
```

- [ ] **Step 2: Run tests and verify the catalog modules are absent**

Run: `python -m pytest tests/test_radar_search_catalog.py -v`

Expected: FAIL during collection for missing `artifacts` or `catalog`.

- [ ] **Step 3: Implement exhaustive Radar artifact routing**

`discover_artifacts` returns sorted unique paths for:

- `RADAR_DIR/latest-items.json` when present;
- timestamped root digest Markdown files, excluding `latest.md` when timestamped digests exist and using `latest.md` only as a fallback;
- `RADAR_DIR/deepdive/*-index.json` plus referenced report Markdown files;
- every promoted `agent_reach/knowledge/wiki/*.md` page.

`read_artifact` must reject paths outside `radar_dir` and `wiki_dir`. Sidecar entries become `external` records with `source_record_id` from `extra.id`, `extra.tweet_id`, `extra.arxiv_id`, or canonical item URL in that order. Digest/deep-dive/Wiki Markdown becomes one `derived` record whose artifact-relative path is its stable identity. A deep-dive index supplies title/topic/score/source URL to its referenced Markdown. Malformed JSON items log a warning and are skipped; a structurally invalid whole artifact raises `ValueError` so the batch can roll back.

- [ ] **Step 4: Implement transactional upsert and FTS synchronization**

Add `IndexStatus` to `models.py`:

```python
@dataclass(frozen=True)
class IndexStatus:
    run_id: str
    mode: str
    status: str
    catalog_path: str
    tokenizer: str
    documents: int
    observations: int
    chunks: int
    clusters: int
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    last_success_at: str = ""
    last_failure_at: str = ""
    schema_version: int = 1
    rule_version: int = 1
    cluster_version: int = 1
    score_version: int = 1
    rebuild_required: bool = False
    error_summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Commit the initial `index_runs` row in a short transaction before the artifact batch so a later rollback cannot erase failure evidence. Within one transaction per artifact batch, insert/update `documents`, upsert `observations`, replace labels, and replace chunks only when `content_hash` changes. Before deleting old chunks, delete matching FTS rows by rowid; insert replacement FTS rows with `rowid = chunk_id`. Re-reading an unchanged record updates `last_seen_at` without changing its first-seen time, chunks, or evidence counts. After success or rollback, finalize the run row in a separate short transaction and truncate `error_summary` to 500 characters. `catalog_status` returns an `empty` status when no database exists and sets `rebuild_required` when stored schema/rule/cluster/score versions differ from current versions.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_catalog.py -v`

Expected: all catalog tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit incremental catalog ingestion**

```bash
git add agent_reach/radar_search/__init__.py agent_reach/radar_search/models.py agent_reach/radar_search/artifacts.py agent_reach/radar_search/catalog.py tests/test_radar_search_catalog.py tests/fixtures/radar_search/latest-items.json
git commit -m "feat(radar-search): index Radar artifacts idempotently"
```

---

### Task 4: Conservative Event Clustering and Evidence Scores

**Files:**
- Create: `agent_reach/radar_search/clustering.py`
- Create: `agent_reach/radar_search/scoring.py`
- Modify: `agent_reach/radar_search/catalog.py`
- Test: `tests/test_radar_search_clustering.py`

**Interfaces:**
- Produces `simhash64(text: str) -> int`, `hamming_similarity(left: int, right: int) -> float`.
- Produces `rebuild_clusters(conn: sqlite3.Connection, config: SearchConfig, now: datetime) -> int`.
- Produces `score_cluster(members: Sequence[EvidenceMember], config: SearchConfig, now: datetime) -> ClusterScore`.

- [ ] **Step 1: Write failing similarity and score-separation tests**

```python
# tests/test_radar_search_clustering.py
from datetime import datetime, timezone

from agent_reach.radar_search.clustering import hamming_similarity, simhash64
from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.scoring import EvidenceMember, score_cluster


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def _member(key, domain, family, content_hash, score=10.0, fingerprint_text=None):
    return EvidenceMember(
        document_key=key, evidence_role="external", source_domain=domain,
        source_family=family, content_hash=content_hash,
        content_simhash=simhash64(fingerprint_text or content_hash),
        published_at="2026-07-21T10:00:00+00:00", first_seen_at="2026-07-21T10:00:00+00:00",
        radar_score=score,
    )


def test_cjk_simhash_prefers_near_duplicate():
    near = hamming_similarity(simhash64("台積電推出新晶片平台"), simhash64("台積電推出全新晶片平台"))
    far = hamming_similarity(simhash64("台積電推出新晶片平台"), simhash64("量子糾錯研究進展"))
    assert near > far


def test_reposts_raise_heat_but_not_independent_corroboration(tmp_path):
    cfg = load_search_config({}, tmp_path)
    one = score_cluster([_member("a", "wire.example", "rss", "same")], cfg, NOW)
    reposts = score_cluster([
        _member("a", "wire.example", "rss", "same"),
        _member("b", "wire.example", "twitter", "same"),
        _member("c", "wire.example", "web", "same"),
    ], cfg, NOW)
    independent = score_cluster([
        _member("a", "wire.example", "rss", "one"),
        _member("b", "lab.example", "web", "two"),
        _member("c", "paper.example", "paper", "three"),
    ], cfg, NOW)
    assert reposts.heat > one.heat
    assert independent.corroboration > reposts.corroboration


def test_derived_member_never_changes_evidence_score(tmp_path):
    cfg = load_search_config({}, tmp_path)
    external = _member("a", "news.example", "web", "one")
    derived = EvidenceMember(
        document_key="wiki", evidence_role="derived", source_domain="",
        source_family="wiki", content_hash="derived", content_simhash=0,
        published_at=None, first_seen_at="2026-07-21T11:00:00+00:00", radar_score=None,
    )
    assert score_cluster([external], cfg, NOW) == score_cluster([external, derived], cfg, NOW)


def test_near_duplicate_content_lineage_is_penalized(tmp_path):
    cfg = load_search_config({}, tmp_path)
    near = [
        _member("a", "a.example", "rss", "one", fingerprint_text="same release"),
        _member("b", "b.example", "web", "two", fingerprint_text="same release"),
    ]
    distinct = [
        _member("a", "a.example", "rss", "one", fingerprint_text="release alpha"),
        _member("b", "b.example", "web", "two", fingerprint_text="different report"),
    ]
    assert score_cluster(distinct, cfg, NOW).corroboration > score_cluster(near, cfg, NOW).corroboration
```

- [ ] **Step 2: Run tests and verify clustering/scoring modules are absent**

Run: `python -m pytest tests/test_radar_search_clustering.py -v`

Expected: FAIL during collection for missing modules.

- [ ] **Step 3: Implement exact normalized score equations**

Define the score input/output types and deterministic component functions, each clamped to 0–100:

```python
@dataclass(frozen=True)
class EvidenceMember:
    document_key: str
    evidence_role: Literal["external", "derived"]
    source_domain: str
    source_family: str
    content_hash: str
    content_simhash: int
    published_at: str | None
    first_seen_at: str
    radar_score: float | None


@dataclass(frozen=True)
class ClusterScore:
    heat: float
    corroboration: float
    mention_count: int
    unique_domain_count: int
    unique_source_family_count: int
    unique_content_lineages: int


def log_component(value: int, cap: int) -> float:
    return 100.0 * math.log1p(min(max(value, 0), cap)) / math.log1p(cap)


mention_volume = log_component(unique_external_documents, 100)
domain_coverage = log_component(unique_domains, 20)
family_coverage = log_component(unique_source_families, 8)
source_coverage = (domain_coverage + family_coverage) / 2.0
recency = 100.0 * (0.5 ** (age_hours / config.recency_half_life_hours))
engagement = 100.0 * math.log1p(min(max(mean_radar_score, 0.0), config.engagement_cap)) / math.log1p(config.engagement_cap)
independent_domains = log_component(unique_domains, 8)
independent_source_families = log_component(unique_source_families, 4)
originality = 100.0 * unique_content_lineages / unique_external_documents
```

Form content lineages greedily in stable document-key order: equal content hashes share a lineage, and different hashes share a lineage when `hamming_similarity(content_simhash) >= 0.95`. Apply the approved weights from config. If no external documents exist, return zero for both scores and all counts. Use publication time, falling back to first-seen time, for recency. Missing engagement contributes zero. Round stored scores to four decimals.

- [ ] **Step 4: Implement deterministic seven-day cluster assignment**

For each non-deleted document ordered by event time then `document_key`, consider clusters whose latest member is within `cluster_window_days`. Exact canonical URL/content/target URL scores 1.0 but still respects the time window. Otherwise require kinds in the same explicit bucket (`news` = tweet/web/rss/market, `paper` = paper, `trend` = trend, and each derived kind is its own bucket) and one shared topic/entity/repo/paper/ticker label. Calculate:

```python
similarity = (
    0.35 * title_jaccard
    + 0.30 * title_simhash_similarity
    + 0.20 * label_jaccard
    + 0.10 * target_url_match
    + 0.05 * time_proximity
)
```

Assign only when `similarity >= config.cluster_threshold`; choose the highest score and then smallest cluster ID. Otherwise create a cluster. Save every component as sorted JSON in `cluster_members.similarity_json`, with `match_reason` equal to `canonical_url`, `content_hash`, `target_url`, or `weighted`. Choose the representative by highest Radar score, then earliest event time, then `document_key`. Recompute cluster counts and scores after membership is complete. Invoke `rebuild_clusters` at the end of each successful catalog update transaction.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_clustering.py tests/test_radar_search_catalog.py -v`

Expected: all clustering and catalog tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit clustering and scores**

```bash
git add agent_reach/radar_search/clustering.py agent_reach/radar_search/scoring.py agent_reach/radar_search/catalog.py tests/test_radar_search_clustering.py
git commit -m "feat(radar-search): cluster events and score evidence"
```

---

### Task 5: Atomic Rebuild Lifecycle and TurboVec-Ready Contract

**Files:**
- Create: `agent_reach/radar_search/lifecycle.py`
- Create: `agent_reach/radar_search/vector.py`
- Modify: `agent_reach/radar_search/schema.py`
- Modify: `agent_reach/radar_search/catalog.py`
- Modify: `agent_reach/radar_search/__init__.py`
- Test: `tests/test_radar_search_lifecycle.py`
- Test: `tests/test_radar_search_vector.py`

**Interfaces:**
- Produces `rebuild_catalog(config: SearchConfig, sources: Mapping[str, Any], radar_dir: Path, wiki_dir: Path) -> IndexStatus`.
- Produces `catalog_lock(path: Path) -> ContextManager[None]` and `catalog_access(path: Path) -> ContextManager[None]`.
- Produces `VectorIndex` protocol, `VectorMatch`, `VectorManifest`, `write_manifest`, and `read_manifest` without importing TurboVec.

- [ ] **Step 1: Write failing rebuild and vector-manifest tests**

```python
# tests/test_radar_search_lifecycle.py
import json
import sqlite3

import pytest

from agent_reach.radar_search.catalog import update_catalog
from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.lifecycle import catalog_lock, rebuild_catalog
from agent_reach.radar_search.schema import connect_catalog


@pytest.fixture()
def seeded_catalog(tmp_path):
    radar_dir = tmp_path / "radar"
    wiki_dir = tmp_path / "wiki"
    radar_dir.mkdir()
    wiki_dir.mkdir()
    sidecar = radar_dir / "latest-items.json"
    sidecar.write_text(json.dumps({
        "generated_at": "2026-07-21T10:00:00+00:00",
        "items": {"web": [{"source": "exa", "kind": "web", "title": "kept",
            "url": "https://example.com/kept", "text": "body", "author": "A",
            "score": 1, "ts": "2026-07-21T09:00:00+00:00", "extra": {}}]},
    }), encoding="utf-8")
    cfg = load_search_config({}, radar_dir)
    update_catalog(cfg, {}, [sidecar])
    conn = connect_catalog(cfg.catalog_path, read_only=True)
    old_chunk = conn.execute("SELECT chunk_id FROM chunks").fetchone()[0]
    conn.close()
    sidecar.unlink()
    return cfg, radar_dir, wiki_dir, old_chunk


def test_rebuild_preserves_observations_and_unchanged_chunk_ids(seeded_catalog):
    cfg, radar_dir, wiki_dir, old_chunk = seeded_catalog
    status = rebuild_catalog(cfg, {}, radar_dir, wiki_dir)
    assert status.status == "success"
    conn = connect_catalog(cfg.catalog_path, read_only=True)
    assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    assert conn.execute("SELECT chunk_id FROM chunks").fetchone()[0] == old_chunk


def test_rebuild_lock_rejects_concurrent_writer(tmp_path):
    target = tmp_path / "catalog.sqlite3"
    with catalog_lock(target):
        with pytest.raises(RuntimeError, match="already in progress"):
            with catalog_lock(target):
                pass
```

```python
# tests/test_radar_search_vector.py
from agent_reach.radar_search.vector import VectorManifest, read_manifest, write_manifest


def test_vector_manifest_round_trip(tmp_path):
    manifest = VectorManifest(
        provider="local", model="future-model", dimension=768,
        normalized=True, metric="cosine", engine="turbovec",
        engine_version="future", quantization_bits=3, schema_version=1,
        max_chunk_id=44, chunk_digest="abc", catalog_identity="catalog-1",
        built_at="2026-07-21T12:00:00+08:00",
    )
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    assert read_manifest(path) == manifest
```

- [ ] **Step 2: Run tests and verify missing lifecycle/vector modules**

Run: `python -m pytest tests/test_radar_search_lifecycle.py tests/test_radar_search_vector.py -v`

Expected: FAIL during collection for missing modules.

- [ ] **Step 3: Implement lock, retained-record rebuild, and atomic replacement**

Add a process-local `threading.RLock` registry keyed by resolved catalog path in `schema.py`; `catalog_access(path)` holds that lock around every connection lifetime. `update_catalog`, `catalog_status`, `search_catalog`, `get_cluster`, and rebuild replacement must use it, so the in-process UI cannot keep a database handle open during `os.replace`.

Use `os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` for a catalog-specific `.lock`, write PID/time for diagnostics, and always unlink it in `finally`. Rebuild in a temporary file created in the catalog directory. When the current catalog exists, open it read-only and copy retained `observations.raw_record_json` plus unchanged `(document_key, ordinal, content_hash) -> chunk_id` mappings and the `sqlite_sequence` high-water mark. Merge current disk artifacts idempotently, apply current rules, then run:

```python
def validate_rebuild(conn: sqlite3.Connection) -> None:
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("temporary catalog integrity check failed")
    orphan_chunks = conn.execute(
        "SELECT count(*) FROM chunks c LEFT JOIN documents d USING(document_key) "
        "WHERE d.document_key IS NULL"
    ).fetchone()[0]
    if orphan_chunks:
        raise RuntimeError(f"temporary catalog has {orphan_chunks} orphan chunks")
```

Copy the current catalog to `catalog.sqlite3.bak` only after the temporary catalog validates; then `os.replace(temp_path, catalog_path)`. If current history cannot be read, fail without replacing it. Preserve unchanged chunk IDs explicitly and set the new `sqlite_sequence` to at least the old high-water mark. Clean temporary files in `finally`.

- [ ] **Step 4: Define the exact future vector boundary**

```python
@dataclass(frozen=True)
class VectorMatch:
    chunk_id: int
    distance: float


@dataclass(frozen=True)
class VectorManifest:
    provider: str
    model: str
    dimension: int
    normalized: bool
    metric: str
    engine: str
    engine_version: str
    quantization_bits: int
    schema_version: int
    max_chunk_id: int
    chunk_digest: str
    catalog_identity: str
    built_at: str


class VectorIndex(Protocol):
    def build(self, path: Path, chunk_ids: Sequence[int],
              vectors: Sequence[Sequence[float]], manifest: VectorManifest) -> None: ...
    def open(self, path: Path) -> VectorManifest: ...
    def search(self, query_vector: Sequence[float], k: int,
               allowed_chunk_ids: AbstractSet[int] | None = None) -> list[VectorMatch]: ...
    def status(self) -> Mapping[str, Any]: ...
```

The ellipses above are protocol method bodies (`...`) and not missing plan content. `write_manifest` must use a temporary sibling plus `os.replace`; `read_manifest` rejects non-positive dimensions, unsupported metrics outside `cosine|dot|l2`, invalid quantization bits outside `2|3|4`, and negative chunk IDs. Do not add a TurboVec implementation or dependency.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_lifecycle.py tests/test_radar_search_vector.py -v`

Expected: all lifecycle/vector tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit lifecycle and vector boundary**

```bash
git add agent_reach/radar_search/__init__.py agent_reach/radar_search/schema.py agent_reach/radar_search/catalog.py agent_reach/radar_search/lifecycle.py agent_reach/radar_search/vector.py tests/test_radar_search_lifecycle.py tests/test_radar_search_vector.py
git commit -m "feat(radar-search): add atomic rebuild lifecycle"
```

---

### Task 6: Filtered FTS Search, CJK Fallback, and Ranking

**Files:**
- Create: `agent_reach/radar_search/search.py`
- Modify: `agent_reach/radar_search/models.py`
- Modify: `agent_reach/radar_search/catalog.py`
- Modify: `agent_reach/radar_search/__init__.py`
- Test: `tests/test_radar_search_query.py`

**Interfaces:**
- Produces `SearchRequest`, `SearchMember`, `SearchHit`, `SearchResponse`.
- Produces `search_catalog(config: SearchConfig, request: SearchRequest) -> SearchResponse`.
- Produces `get_cluster(config: SearchConfig, cluster_id: int) -> SearchHit | None`.

- [ ] **Step 1: Write failing English/CJK/filter/ranking tests**

```python
# tests/test_radar_search_query.py
import json

import pytest

from agent_reach.radar_search.catalog import update_catalog
from agent_reach.radar_search.config import load_search_config
from agent_reach.radar_search.models import SearchRequest
from agent_reach.radar_search.search import search_catalog


@pytest.fixture()
def seeded_search_catalog(tmp_path):
    sidecar = tmp_path / "latest-items.json"
    sidecar.write_text(json.dumps({
        "generated_at": "2026-07-21T10:00:00+00:00",
        "items": {"rss": [{"source": "rss:Lab", "kind": "rss",
            "title": "AI 晶片 TurboVec 搜尋", "url": "https://lab.example/story",
            "text": "本地搜尋與晶片資料", "author": "Lab", "score": 10,
            "ts": "2026-07-21T09:00:00+00:00", "extra": {"topic": "ee"}}]},
    }), encoding="utf-8")
    cfg = load_search_config({}, tmp_path)
    update_catalog(cfg, {"topic_keywords": ["ai", "晶片"]}, [sidecar])
    return cfg


def test_search_finds_english_and_chinese(seeded_search_catalog):
    cfg = seeded_search_catalog
    english = search_catalog(cfg, SearchRequest(query="TurboVec", limit=20))
    chinese = search_catalog(cfg, SearchRequest(query="晶片", limit=20))
    assert english.hits[0].title
    assert chinese.hits[0].title


def test_search_filters_and_explicit_sort(seeded_search_catalog):
    cfg = seeded_search_catalog
    response = search_catalog(cfg, SearchRequest(
        query="AI", topic="ee", source="rss", since="30d",
        sort="corroboration", limit=10, view="clusters",
    ))
    assert all(hit.topic == "ee" for hit in response.hits)
    assert [hit.corroboration_score for hit in response.hits] == sorted(
        [hit.corroboration_score for hit in response.hits], reverse=True
    )


def test_empty_relevance_query_requires_filter_or_browse_sort():
    with pytest.raises(ValueError, match="empty query"):
        SearchRequest(query="", sort="relevance")


def test_fts_metacharacters_are_treated_as_text(seeded_search_catalog):
    response = search_catalog(seeded_search_catalog,
                              SearchRequest(query='" OR *', limit=20))
    assert response.total >= 0
```

- [ ] **Step 2: Run tests and verify search API is absent**

Run: `python -m pytest tests/test_radar_search_query.py -v`

Expected: FAIL during collection for missing `SearchRequest` or `search` module.

- [ ] **Step 3: Define stable result dataclasses and validation**

Add these exact dataclasses; each result type returns `dataclasses.asdict(self)` from `to_dict()`:

```python
@dataclass(frozen=True)
class SearchRequest:
    query: str = ""
    topic: str = ""
    kind: str = ""
    source: str = ""
    domain: str = ""
    label: str = ""
    evidence_role: str = ""
    since: str = ""
    sort: str = "relevance"
    limit: int = 20
    view: str = "clusters"

    def __post_init__(self) -> None:
        if self.sort not in {"relevance", "heat", "corroboration"}:
            raise ValueError("invalid sort")
        if self.view not in {"clusters", "documents"}:
            raise ValueError("invalid view")
        has_filter = any((self.topic, self.kind, self.source, self.domain,
                          self.label, self.evidence_role, self.since))
        if not self.query.strip() and not has_filter and self.sort == "relevance":
            raise ValueError("empty query requires a filter or browse sort")


@dataclass(frozen=True)
class SearchMember:
    document_key: str
    title: str
    url: str
    source_family: str
    source_domain: str
    author: str
    published_at: str
    match_reason: str


@dataclass(frozen=True)
class SearchHit:
    cluster_id: int | None
    document_key: str
    title: str
    url: str
    snippet: str
    kind: str
    topic: str
    source_family: str
    author: str
    published_at: str
    heat_score: float
    corroboration_score: float
    mention_count: int
    unique_domain_count: int
    unique_source_family_count: int
    labels: tuple[str, ...]
    match_reason: str
    members: tuple[SearchMember, ...]
    rank: float


@dataclass(frozen=True)
class SearchResponse:
    query: str
    tokenizer: str
    view: str
    total: int
    hits: tuple[SearchHit, ...]
```

`SearchRequest` fields are `query`, `topic`, `kind`, `source`, `domain`, `label`, `evidence_role`, `since`, `sort`, `limit`, and `view`. Validate sort in `relevance|heat|corroboration`, view in `clusters|documents`, evidence role in blank/`external`/`derived`, `1 <= limit <= config.max_limit` inside the service, and `since` as either `^[1-9][0-9]*[hdw]$` or an ISO-8601 date/datetime accepted by `datetime.fromisoformat`. Require labels in `namespace:value` form. Empty query is allowed only with a filter or heat/corroboration sort.

Each `SearchHit` contains representative document key/title/URL/snippet/kind/topic/source/author/published time, `heat_score`, `corroboration_score`, mention/domain/family counts, labels, match reason, and a tuple of `SearchMember` source rows. `SearchResponse` contains query, tokenizer, view, total candidate count, and ordered hits; each dataclass implements `to_dict()` returning JSON-native values.

- [ ] **Step 4: Implement bounded retrieval and deterministic rank**

Hold `catalog_access(config.catalog_path)` for the complete connection lifetime. Build SQL filter clauses with bound parameters only. Convert user text to a literal FTS expression by splitting on whitespace, doubling embedded quotes, quoting each token, and joining tokens with `AND`; invalid FTS syntax must return zero matches rather than a server error. For ordinary text, query `chunks_fts MATCH ?`, fetch at most `min(max(limit * 10, 100), 1000)` candidates, and compute raw relevance as `-bm25(chunks_fts)`. For a one/two-character CJK query under `trigram`, use escaped `LIKE '%query%'` over title/content because no trigram can be formed; `unicode61` continues through FTS. Keep the same 1000-candidate bound. Normalize candidate FTS relevance by the maximum positive raw relevance, or 100 for a LIKE match.

Default rank is:

```python
rank = 0.60 * fts_relevance + 0.25 * heat_score + 0.15 * corroboration_score
```

For `sort=heat` or `sort=corroboration`, sort by that score, then latest event time, then document/cluster ID. For relevance, sort by blended rank, then latest event time, then stable ID. Group cluster results without letting multiple matching chunks duplicate one event. Generate plain-text snippets of at most 240 characters and let UI/CLI escape them.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_query.py -v`

Expected: all search tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit the search service**

```bash
git add agent_reach/radar_search/__init__.py agent_reach/radar_search/models.py agent_reach/radar_search/catalog.py agent_reach/radar_search/search.py tests/test_radar_search_query.py
git commit -m "feat(radar-search): add filtered local search"
```

---

### Task 7: Non-Fatal Automatic Producer Hooks

**Files:**
- Create: `agent_reach/radar_search/hooks.py`
- Modify: `agent_reach/radar.py:988-1016`
- Modify: `agent_reach/radar_arxiv.py:330-384`
- Modify: `agent_reach/radar_wiki.py:274-291`
- Test: `tests/test_radar_search_hooks.py`
- Modify: `tests/test_radar.py`
- Modify: `tests/test_radar_arxiv.py`
- Modify: `tests/test_radar_wiki.py`

**Interfaces:**
- Produces `safe_update_catalog(trigger: str, artifacts: Sequence[Path], *, sources: Mapping[str, Any] | None = None) -> IndexStatus | None`.
- Consumes `update_catalog`, `load_sources`, `load_search_config`, and the producer paths.

- [ ] **Step 1: Write failing hook isolation tests**

```python
# tests/test_radar_search_hooks.py
from agent_reach.radar_search import hooks


def test_safe_hook_returns_none_and_warns_on_failure(monkeypatch, tmp_path):
    warnings = []
    monkeypatch.setattr(hooks.logger, "warning", warnings.append)
    monkeypatch.setattr(hooks, "update_catalog", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    assert hooks.safe_update_catalog("radar", [tmp_path / "latest-items.json"], sources={}) is None
    assert warnings and "locked" in warnings[0]


def test_safe_hook_skips_when_automatic_disabled(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(hooks, "update_catalog", lambda *a, **k: calls.append(1))
    hooks.safe_update_catalog("radar", [tmp_path / "x"], sources={"search": {"automatic": False}})
    assert calls == []
```

Also add producer tests that monkeypatch `safe_update_catalog` and assert:

```python
assert hook_calls == [
    ("radar", [digest_path, radar_dir / "latest-items.json"]),
]
```

Deep-dive passes written report paths plus the dated index JSON. Wiki promotion passes the promoted page. A hook exception must not change the producer's successful return value.

- [ ] **Step 2: Run hook and producer tests and verify failure**

Run: `python -m pytest tests/test_radar_search_hooks.py tests/test_radar.py tests/test_radar_arxiv.py tests/test_radar_wiki.py -v`

Expected: FAIL because the hook module/calls do not exist.

- [ ] **Step 3: Implement the single best-effort hook**

`safe_update_catalog` loads current Radar sources only when not supplied, validates config, returns immediately if disabled/automatic false, invokes `update_catalog`, and catches every exception at this boundary. Log one warning containing trigger and exception category/message; never log article bodies or raw metadata. Return `IndexStatus` on success and `None` on skip/failure.

- [ ] **Step 4: Call the hook only after authoritative writes complete**

In `run_radar`, call after both digest and `latest-items.json` writes. In `run_deep_dive`, call after report files, `latest-index.md`, and dated JSON index are written. In `promote_draft`, call after `page.write_text`. Import the hook inside each function to avoid module import cycles and keep producer startup light.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_search_hooks.py tests/test_radar.py tests/test_radar_arxiv.py tests/test_radar_wiki.py -v`

Expected: all hook/producer tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit producer integration**

```bash
git add agent_reach/radar.py agent_reach/radar_arxiv.py agent_reach/radar_wiki.py agent_reach/radar_search/hooks.py tests/test_radar_search_hooks.py tests/test_radar.py tests/test_radar_arxiv.py tests/test_radar_wiki.py
git commit -m "feat(radar-search): index producer outputs automatically"
```

---

### Task 8: `radar-index` and `radar-search` CLI Commands

**Files:**
- Modify: `agent_reach/cli.py:50-310` and command-handler area
- Modify: `tests/test_cli.py`

**Interfaces:**
- Adds `agent-reach radar-index update|rebuild|status`.
- Adds `agent-reach radar-search [query] --topic --kind --source --since --sort --limit --json`.
- Consumes only public imports from `agent_reach.radar_search`.

- [ ] **Step 1: Write failing CLI routing and JSON contract tests**

```python
# add with the existing test imports
import json
from agent_reach.radar_search.models import IndexStatus, SearchResponse


def _fake_status():
    return IndexStatus(
        run_id="run", mode="status", status="success", catalog_path="catalog.sqlite3",
        tokenizer="trigram", documents=0, observations=0, chunks=0, clusters=0,
    )


def test_radar_search_json_contract(monkeypatch, capsys):

    monkeypatch.setattr("agent_reach.radar_search.search_catalog",
                        lambda config, request: SearchResponse(query=request.query,
                            tokenizer="trigram", view="clusters", total=0, hits=()))
    with patch("sys.argv", ["agent-reach", "radar-search", "TurboVec", "--json"]):
        main()
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"query": "TurboVec", "tokenizer": "trigram",
                       "view": "clusters", "total": 0, "hits": []}


def test_radar_index_routes_rebuild(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("agent_reach.radar_search.rebuild_catalog", lambda *a, **k: calls.append("rebuild") or _fake_status())
    with patch("sys.argv", ["agent-reach", "radar-index", "rebuild"]):
        main()
    assert calls == ["rebuild"]
    assert "catalog" in capsys.readouterr().out.lower()


def test_radar_search_rejects_invalid_limit():
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["agent-reach", "radar-search", "x", "--limit", "0"]):
            main()
    assert exc.value.code == 2
```

- [ ] **Step 2: Run CLI tests and verify parser rejects new commands**

Run: `python -m pytest tests/test_cli.py -k "radar_search or radar_index" -v`

Expected: FAIL with `invalid choice: 'radar-search'` or missing handlers.

- [ ] **Step 3: Add parser definitions and dispatch**

Add `radar-index` with positional `index_action` choices `update|rebuild|status`. Add `radar-search` with optional positional query defaulting to empty string, exact filters from the spec, sort choices `relevance|heat|corroboration`, positive integer limit default 20, and `--json`. Dispatch to `_cmd_radar_index` and `_cmd_radar_search` before `radar-ui`.

- [ ] **Step 4: Implement stable JSON and Rich human output**

`_cmd_radar_index` loads sources/config, discovers artifacts for update, calls update/rebuild/status, and renders the full `IndexStatus`. `_cmd_radar_search` creates `SearchRequest`, calls `search_catalog`, prints `json.dumps(response.to_dict(), ensure_ascii=False)` for JSON mode, and otherwise renders a Rich table with title, topic/kind, heat, `交叉佐證`, domains, mentions, and source URL. Convert validation errors into `SystemExit` with a concise stderr message; never mix logs into stdout JSON.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_cli.py -v`

Expected: all CLI tests PASS.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit CLI commands**

```bash
git add agent_reach/cli.py tests/test_cli.py
git commit -m "feat(radar-search): expose index and search CLI"
```

---

### Task 9: FastAPI Search, Cluster, Status, and Reindex Endpoints

**Files:**
- Modify: `agent_reach/radar_ui/jobs.py:57-77`
- Modify: `agent_reach/radar_ui/server.py:89-211`
- Modify: `tests/test_radar_ui.py`

**Interfaces:**
- Adds `GET /api/search`.
- Adds `GET /api/clusters/{cluster_id}`.
- Adds `GET /api/search/status`.
- Adds `POST /api/search/reindex` with `{ "mode": "update" | "rebuild" }`.
- Adds `JobManager.has_active(kind: str) -> bool`.

- [ ] **Step 1: Write failing API and concurrency tests**

```python
class StubValue:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def test_search_status_and_cluster_endpoints(client, monkeypatch):
    status = StubValue({"status": "success", "catalog_path": "catalog.sqlite3"})
    response = StubValue({"query": "晶片", "tokenizer": "trigram", "view": "clusters",
                          "total": 1, "hits": [{"cluster_id": 7, "title": "晶片"}]})
    hit = StubValue({"cluster_id": 7, "title": "晶片", "members": []})
    monkeypatch.setattr(srv, "catalog_status", lambda cfg: status)
    monkeypatch.setattr(srv, "search_catalog", lambda cfg, req: response)
    monkeypatch.setattr(srv, "get_cluster", lambda cfg, cluster_id: hit if cluster_id == 7 else None)
    assert client.get("/api/search/status").status_code == 200
    assert client.get("/api/search", params={"q": "晶片", "sort": "heat"}).json()["hits"]
    assert client.get("/api/clusters/7").status_code == 200
    assert client.get("/api/clusters/8").status_code == 404


def test_reindex_rejects_concurrent_job(client, monkeypatch):
    monkeypatch.setattr(client.app.state.jobs, "has_active", lambda kind: True)
    response = client.post("/api/search/reindex", json={"mode": "rebuild"})
    assert response.status_code == 409


def test_reindex_rejects_bad_mode(client):
    assert client.post("/api/search/reindex", json={"mode": "drop"}).status_code == 400
```

- [ ] **Step 2: Run UI tests and verify 404/missing methods**

Run: `python -m pytest tests/test_radar_ui.py -v`

Expected: FAIL because the endpoints and `has_active` do not exist.

- [ ] **Step 3: Add active-job inspection and short-lived catalog services**

Implement:

```python
def has_active(self, kind: str) -> bool:
    with self._lock:
        return any(job.kind == kind and job.status in ("queued", "running")
                   for job in self._jobs.values())
```

In the server module, import public search functions at module scope so tests can monkeypatch them. Build config per request from `load_sources()` and `RADAR_DIR`; each service opens/closes its own SQLite connection, avoiding cross-thread connection reuse.

- [ ] **Step 4: Add exact endpoint validation and background work**

Map query parameters to `SearchRequest`, convert `ValueError` to HTTP 400, return 404 for an unknown cluster, and return `to_dict()` values. `POST /api/search/reindex` rejects a second active `radar-search-reindex` job with 409, submits update or rebuild through `JobManager`, and returns its job dictionary immediately. Do not expose article bodies in error responses or hold the HTTP request until indexing completes.

- [ ] **Step 5: Run targeted and full tests**

Run: `python -m pytest tests/test_radar_ui.py -v`

Expected: all UI server tests PASS, or the module remains skipped when the `ui` extra is unavailable.

Run: `python -m pytest tests/ -v`

Expected: all installed tests PASS with only the existing optional-UI skip allowed.

- [ ] **Step 6: Commit UI API support**

```bash
git add agent_reach/radar_ui/jobs.py agent_reach/radar_ui/server.py tests/test_radar_ui.py
git commit -m "feat(radar-search): add console search API"
```

---

### Task 10: Radar Search Console, Documentation, and End-to-End Verification

**Files:**
- Modify: `agent_reach/radar_ui/static/index.html`
- Modify: `tests/test_radar_ui.py`
- Modify: `agent_reach/guides/radar.md`

**Interfaces:**
- Consumes Task 9 endpoints without adding another server or frontend dependency.
- Produces a searchable event/article console with explicit heat/corroboration explanations and reindex status.

- [ ] **Step 1: Add failing static contract tests**

```python
def test_console_contains_search_controls_and_safe_score_copy():
    html = (srv.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'data-view="search"' in html
    assert 'id="search-query"' in html
    assert 'id="search-results"' in html
    assert "/api/search/status" in html
    assert "/api/search/reindex" in html
    assert "交叉佐證" in html
    assert "真實性分數" not in html
```

- [ ] **Step 2: Run the static contract and verify it fails**

Run: `python -m pytest tests/test_radar_ui.py::test_console_contains_search_controls_and_safe_score_copy -v`

Expected: FAIL on the first missing search marker.

- [ ] **Step 3: Add a search navigation mode and accessible controls**

Add `SEARCH` as the first nav item. When active, render controls for query, topic, kind, source, since, sort, and `clusters|documents`; keep existing digest/file navigation unchanged. Add status text and `UPDATE INDEX` / `REBUILD INDEX` buttons. All query values go through `URLSearchParams`; all server-provided text goes through `esc()` or `textContent` before insertion.

- [ ] **Step 4: Render explainable event cards and source expansion**

Each result card displays title/link, snippet, topic/kind, labels, `熱度`, `交叉佐證`, mentions, unique domains, and source families. Use `<details>` to show member source/author/time/link and match reason so repost propagation is visible. Add one static help line: `熱度反映討論量；交叉佐證反映獨立外部來源，不代表事實已被證明。` On a reindex response, reuse `followJob`; on completion refresh status and rerun the active query.

- [ ] **Step 5: Document operation and phase boundaries**

Add a `本地搜尋 Catalog` section to `agent_reach/guides/radar.md` containing the exact CLI commands, default path, automatic hook behavior, permanent retention, rebuild backup behavior, rule-label provenance, heat versus corroboration explanation, and the statement that TurboVec can later accelerate semantic retrieval/context selection but does not increase local-model token generation speed. State that phase 1 has no model/TurboVec/Grok runtime dependency.

- [ ] **Step 6: Run static, focused, and full verification**

Run: `python -m pytest tests/test_radar_ui.py -v`

Expected: all UI tests PASS or the existing optional-UI skip applies.

Run: `python -m pytest tests/test_radar_search_schema.py tests/test_radar_search_rules.py tests/test_radar_search_catalog.py tests/test_radar_search_clustering.py tests/test_radar_search_lifecycle.py tests/test_radar_search_vector.py tests/test_radar_search_query.py tests/test_radar_search_hooks.py tests/test_cli.py tests/test_radar_ui.py -v`

Expected: all feature tests PASS; optional UI tests may skip only when dependencies are absent.

Run: `python -m pytest tests/ -v`

Expected: complete suite PASS with zero failures.

Run: `python -m ruff check agent_reach/radar_search agent_reach/radar.py agent_reach/radar_arxiv.py agent_reach/radar_wiki.py agent_reach/cli.py agent_reach/radar_ui tests`

Expected: exit 0 with no lint errors.

Run: `python -m mypy agent_reach/radar_search`

Expected: exit 0 with no type errors.

- [ ] **Step 7: Inspect generated local behavior without network calls**

Run the tracked synthetic fixture in an explicitly named temporary `radar_output_dir`:

```powershell
$taskSmokeRoot = 'C:\tmp\agentreach-radar-search-smoke'
New-Item -ItemType Directory -Force -Path $taskSmokeRoot
Copy-Item -LiteralPath 'tests\fixtures\radar_search\latest-items.json' -Destination "$taskSmokeRoot\latest-items.json" -Force
$env:RADAR_OUTPUT_DIR = $taskSmokeRoot
python -m agent_reach.cli radar-index rebuild
python -m agent_reach.cli radar-index status
python -m agent_reach.cli radar-search "TurboVec" --sort corroboration --json
```

Expected: rebuild/status exit 0, JSON is valid, no model/TurboVec/Grok process starts, and the catalog path remains under the temporary Radar directory. Remove only this explicitly named smoke directory after confirming its resolved path.

- [ ] **Step 8: Commit UI and documentation**

```bash
git add agent_reach/radar_ui/static/index.html tests/test_radar_ui.py agent_reach/guides/radar.md
git commit -m "feat(radar-search): add searchable Radar console"
```

---

## Completion Review

Before declaring phase 1 complete:

1. Compare implementation behavior against every acceptance criterion in `docs/superpowers/specs/2026-07-21-radar-search-catalog-design.md`.
2. Confirm `git status --short` lists no staged or modified files outside this plan and still preserves the user's `.claude/` and `agents/` directories.
3. Confirm the final full pytest, Ruff, and mypy commands were run after the last code change.
4. Confirm `rg -n "turbovec|embedding|grok" agent_reach/radar_search agent_reach/radar.py agent_reach/radar_arxiv.py agent_reach/radar_wiki.py` shows only documentation/protocol references and no phase-1 runtime import/call.
5. Use `superpowers:requesting-code-review` before integration, then `superpowers:finishing-a-development-branch` to present merge/PR choices.
