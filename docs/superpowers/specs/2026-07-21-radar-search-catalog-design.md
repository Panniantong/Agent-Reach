# Radar Local Search Catalog and TurboVec-Ready Retrieval Design

**Date:** 2026-07-21
**Status:** Approved for implementation planning
**Scope:** Agent Reach Radar data only

## 1. Summary

Agent Reach will gain a persistent local search catalog for data produced by Radar. The first phase uses SQLite and FTS5, deterministic rule labels, and conservative article clustering. It does not run a local language model, generate embeddings, or install TurboVec.

The catalog separates two signals that must not be conflated:

- **Heat** measures how much an event is being mentioned and propagated.
- **Corroboration** measures how many independent external source families and domains report the event.

Repeated copies of one press release can increase heat but must not materially increase corroboration. The UI and CLI use the term **corroboration / 交叉佐證**, never “truth,” because source agreement is useful evidence but is not proof.

The schema assigns stable integer chunk IDs and defines a vector-index adapter boundary so a later phase can add embeddings and TurboVec without replacing the catalog or changing its public search interfaces.

## 2. Goals

1. Persist and search Radar output across runs instead of limiting users to the latest digest.
2. Generate reproducible labels from existing metadata and deterministic rules.
3. Cluster likely reports of the same event conservatively.
4. Rank and display heat separately from independent-source corroboration.
5. Support local Chinese and English keyword search through a CLI and the existing Radar UI.
6. Update the index automatically after successful Radar, deep-dive, and Wiki-promotion writes without making those workflows fragile.
7. Prepare stable identifiers, filtering, and adapter interfaces for a later TurboVec integration.

## 3. Non-goals

Phase 1 will not:

- install or call TurboVec;
- choose or run an embedding model;
- run a local LLM or retrieval-augmented generation pipeline;
- use Grok or another hosted model at runtime for labeling, clustering, or ranking;
- claim that corroboration proves factual truth;
- perform semantic contradiction or stance detection;
- index arbitrary files outside the Radar data directory;
- refactor unrelated Agent Reach providers or upstream tools.

Grok Build CLI may be used by a developer to review implementation ideas or code. It is not a runtime dependency, build dependency, required test service, or source of persisted labels.

## 4. Chosen Architecture

The design uses **SQLite + FTS5 as the source of truth**, with a future optional TurboVec sidecar:

```text
Radar outputs
  latest-items.json / digest history / deep dives / promoted Wiki pages
        |
        v
normalization -> deterministic labels -> chunking -> event clustering
        |                                      |
        +------------------+-------------------+
                           v
                SQLite catalog + FTS5
                           |
                    CLI and Radar UI

Future phase only:
query embedding -> TurboVec candidate IDs -> SQLite filters/hydration -> local RAG
```

SQLite owns documents, metadata, labels, cluster membership, scores, and full-text content. TurboVec will only own a compressed vector index keyed by the stable SQLite `chunk_id`. This keeps exact filtering, persistence, and recovery independent of the vector library.

The catalog path is:

```text
~/.agent-reach/radar/search/catalog.sqlite3
```

The database contains both durable local history and rebuildable search projections. Radar files remain authoritative for artifacts still present on disk; for external items that later disappear from rolling files such as `latest-items.json`, the catalog's retained observation record is the durable local copy. A rebuild uses the union of retained observations and currently available Radar artifacts.

## 5. Source Scope and Provenance

The indexer ingests these Radar-owned artifacts:

1. Raw external items represented in `latest-items.json` and retained digest history.
2. Deep-dive reports and their date indexes.
3. Wiki pages promoted through the Radar workflow.

Each document records its provenance and one of two evidence roles:

- `external`: a crawled or fetched item representing an external source. Eligible to contribute to event heat and corroboration.
- `derived`: a digest, deep dive, or promoted Wiki page generated from other material. Searchable, but never counted as independent external evidence.

If the same external item appears in several Radar artifacts or Radar runs, normalization maps it to one logical document and multiple idempotent provenance observations. Derived pages remain separate searchable documents linked to their source artifacts where that relationship is known.

## 6. Catalog Data Model

### 6.1 `documents`

Stores one normalized logical document.

Key fields:

- `document_key TEXT PRIMARY KEY`: SHA-256 of the canonical source identity.
- `source_id TEXT NULL`: upstream stable identifier when available.
- `canonical_url TEXT NULL` and `original_url TEXT NULL`.
- `canonical_target_url TEXT NULL`: normalized outbound article/repository/paper URL for propagation analysis.
- `source_family TEXT NOT NULL`: normalized provider/platform family.
- `source_domain TEXT NULL`: registrable or normalized host.
- `kind TEXT NOT NULL`: the existing Radar item kind or a derived-document kind.
- `evidence_role TEXT NOT NULL`: `external` or `derived`.
- `title TEXT NOT NULL`, `body TEXT NOT NULL`, `author TEXT NULL`.
- `published_at TEXT NULL`, `first_seen_at TEXT NOT NULL`, `last_seen_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
- `radar_score REAL NULL` and `raw_metadata_json TEXT NOT NULL`.
- `content_hash TEXT NOT NULL`.
- `rule_version INTEGER NOT NULL`.
- `is_deleted INTEGER NOT NULL DEFAULT 0`.

`document_key` is computed from the first available stable identity in this order:

1. normalized source family plus upstream source ID;
2. canonical URL;
3. normalized source family, author, publication timestamp, and normalized title.

The fallback identity is deterministic. A changed article keeps its `document_key` when its stable source identity is unchanged, while `content_hash` changes.

### 6.2 `observations`

Stores idempotent provenance records for ingestion without letting polling frequency inflate event heat.

Key fields:

- `observation_key TEXT PRIMARY KEY`: SHA-256 of artifact identity plus stable source record identity;
- `document_key TEXT NOT NULL`;
- `artifact_kind TEXT NOT NULL` and `artifact_identity TEXT NOT NULL`;
- `source_record_id TEXT NULL`;
- `observed_at TEXT NOT NULL`;
- `raw_record_json TEXT NOT NULL`.

Re-reading the same artifact or source record updates its observation rather than inserting another mention. Heat counts distinct external documents in a cluster, not the number of indexing runs or provenance rows. The retained raw record lets a rebuild reapply newer normalization and label rules even after a rolling source artifact has been replaced.

### 6.3 `chunks`

Stores searchable text units and reserves IDs for a future vector sidecar.

Key fields:

- `chunk_id INTEGER PRIMARY KEY AUTOINCREMENT`;
- `document_key TEXT NOT NULL`;
- `ordinal INTEGER NOT NULL`;
- `heading TEXT NULL`, `content TEXT NOT NULL`;
- `content_hash TEXT NOT NULL`;
- `token_estimate INTEGER NOT NULL`;
- uniqueness on `(document_key, ordinal, content_hash)`.

Short Radar items normally produce one chunk. Longer deep dives and Wiki pages split on headings and paragraph boundaries to a configurable target size. Chunk IDs are never manually reused. If content changes, obsolete chunks are deleted and replacement chunks receive new IDs. A rebuild copies the prior ID for every unchanged `(document_key, ordinal, content_hash)` and allocates new IDs above the old high-water mark. This makes stale vectors detectable in phase 2 while preserving valid vector mappings.

### 6.4 `labels`

Stores deterministic labels as rows rather than a single denormalized string.

Key fields:

- `document_key TEXT NOT NULL`;
- `namespace TEXT NOT NULL`;
- `value TEXT NOT NULL`;
- `rule_id TEXT NOT NULL`;
- `rule_version INTEGER NOT NULL`;
- `confidence REAL NOT NULL DEFAULT 1.0`;
- uniqueness on `(document_key, namespace, value, rule_id, rule_version)`.

Confidence describes rule specificity, not model probability. Because phase 1 labels are deterministic, the same inputs and rule version must produce the same rows.

### 6.5 `clusters` and `cluster_members`

`clusters` stores the event-level summary:

- `cluster_id INTEGER PRIMARY KEY AUTOINCREMENT`;
- representative title and document key;
- normalized topic and kind;
- first and last observation times;
- mention count, unique external domain count, and unique source-family count;
- `heat_score REAL NOT NULL`;
- `corroboration_score REAL NOT NULL`;
- clustering and scoring rule versions.

`cluster_members` maps `document_key` to `cluster_id` and stores the matching reason and similarity signals used when the membership was assigned.

### 6.6 `index_runs`

Records update/rebuild observability:

- run ID, mode, start/end timestamps, and status;
- scanned, inserted, updated, skipped, deleted, and failed counts;
- active rule/schema versions;
- a bounded error summary.

### 6.7 `chunks_fts`

An FTS5 virtual table indexes chunk title, heading, body, author, labels, source family, and topic. SQLite row linkage is kept explicit so FTS results hydrate through `chunks` and `documents`.

The indexer probes FTS5 tokenizer support when initializing the database:

1. use the FTS5 `trigram` tokenizer when available;
2. otherwise use `unicode61`;
3. for very short CJK queries that cannot produce useful FTS tokens, use a bounded `LIKE` fallback over indexed catalog rows.

The selected tokenizer is recorded in catalog metadata and remains stable until a rebuild.

## 7. URL and Content Normalization

Canonical URL normalization is deterministic:

- lowercase the scheme and host;
- remove fragments;
- remove default ports;
- normalize empty paths to `/`;
- sort retained query parameters;
- remove a configurable set of tracking parameters such as `utm_*`, `fbclid`, and `gclid`;
- preserve source-specific identity parameters when required by a provider rule;
- do not follow network redirects during indexing.

Text normalization for hashing and similarity:

- Unicode NFKC normalization;
- whitespace collapse;
- case folding where applicable;
- removal of predictable Radar rendering wrappers;
- preservation of CJK characters, identifiers, numbers, and punctuation needed for meaning.

Raw source metadata is retained in JSON for auditability, but ranking and labeling use normalized typed fields.

## 8. Deterministic Rule Labels

Labels use namespaced values. Initial namespaces are:

- `kind`: existing Radar kind;
- `source`: source family/platform;
- `domain`: canonical source domain;
- `author`: normalized author or account;
- `topic`: existing `topic` and `topics` plus configured topic-rule matches;
- `entity`: companies and configured named entities;
- `ticker`: normalized market symbols matched by bounded regular expressions;
- `paper`: arXiv identifiers and paper-like source metadata;
- `repo`: normalized GitHub owner/repository pairs;
- `language`: `zh`, `en`, `mixed`, or `unknown` from deterministic Unicode-script ratios;
- `score_band`: configurable bands derived from the original Radar score;
- `url_class`: source-specific URL patterns when useful.

Rule precedence is explicit:

1. typed fields already present on the Radar item;
2. canonical URL and source metadata;
3. configured topic keyword rules from `radar.yaml`;
4. bounded regular expressions and configured dictionaries over title and body.

No phase-1 label calls an LLM. Every label stores the rule ID and version that produced it. Changing rules increments `rule_version`; `radar-index rebuild` recomputes all labels with the current version.

Ambiguous regex matches are rejected rather than guessed. For example, a ticker rule requires a recognized prefix/syntax or membership in a configured ticker dictionary so ordinary uppercase words are not labeled as symbols.

## 9. Conservative Event Clustering

Clustering groups likely reports of the same event within a default seven-day sliding window. The window applies to all cross-document cluster assignments, including exact-content matches; repeated observations of an already known logical document do not create a new membership. The algorithm favors precision over recall: uncertain items remain separate.

### 9.1 Exact matches

Documents join the same cluster immediately when either condition holds:

- equal canonical URLs; or
- equal normalized content hashes.

### 9.2 Candidate generation

Non-exact comparisons are limited to documents with compatible evidence characteristics:

- observation/publication times within seven days;
- compatible Radar kind;
- at least one shared normalized topic, entity, repository, paper ID, or ticker.

The time window and thresholds are configurable in `radar.yaml`, with seven days as the default.

### 9.3 Similarity signals

Candidates are compared using deterministic signals:

- normalized title token overlap;
- character 3-gram SimHash distance, which remains useful for CJK text;
- keyword and extracted-entity overlap;
- canonical target-link agreement for social posts;
- publication-time proximity.

A weighted score above a strict configured threshold assigns the candidate to the best existing cluster. Ties or borderline scores create a new cluster. Membership records retain the score components and match reason so behavior is auditable.

This phase does not attempt semantic conflict detection. Two sources discussing the same event can be clustered even if their interpretation differs; the UI therefore presents the underlying source list instead of asserting consensus on every claim.

## 10. Heat and Corroboration

Both scores are normalized to the range 0–100. Component normalization constants and weights are configurable in `radar.yaml`; defaults are versioned and recorded on each cluster.

### 10.1 Heat score

```text
heat = 0.35 * mention_volume
     + 0.25 * source_coverage
     + 0.25 * recency
     + 0.15 * engagement
```

- `mention_volume`: logarithmically scaled count of distinct external documents, so repost floods have diminishing returns while repeated indexing of one item has no effect.
- `source_coverage`: logarithmically scaled count of distinct external domains and source families.
- `recency`: exponential decay from publication time, falling back to first-seen time, with a configurable half-life. Re-crawling an old item does not refresh the event.
- `engagement`: normalized aggregate of original Radar scores where available; missing scores contribute a neutral zero component and do not cause failure.

Derived documents never contribute to these components.

### 10.2 Corroboration score

```text
corroboration = 0.45 * independent_domains
              + 0.35 * independent_source_families
              + 0.20 * originality
```

- `independent_domains`: logarithmically scaled unique external domains after canonicalization.
- `independent_source_families`: unique provider/platform families.
- `originality`: the proportion of materially distinct external content after exact and near-duplicate penalties.

Independence rules:

- reposts or syndicated copies of the same press release increase mention volume but are treated as one content lineage for originality;
- multiple social accounts pointing to the same target URL describe propagation and do not become separate independent-domain evidence;
- a source family and its subdomains are counted once unless explicit configuration declares genuinely separate publishers;
- Radar digests, deep dives, and promoted Wiki pages add no corroboration;
- no threshold or score is labeled as “true,” “verified,” or a probability of truth.

Scores are recomputed whenever cluster membership or configuration changes.

## 11. Indexing Lifecycle

### 11.1 Automatic incremental updates

The index update hook runs after each workflow has successfully written its authoritative artifact:

1. after `run_radar()` writes the latest item data and digest;
2. after a deep-dive report and its date index are written;
3. after a draft is promoted to the Wiki.

Automatic indexing is best-effort. A catalog failure logs a warning with the failed run ID but does not turn a successfully completed Radar/deep-dive/promotion operation into a failure.

### 11.2 Transactions and concurrency

- Enable WAL mode and a bounded `busy_timeout`.
- Perform one artifact batch per transaction.
- Update documents, observations, labels, chunks, FTS rows, cluster membership, and scores atomically for that batch.
- Roll back the batch on an indexing exception and record a failed `index_runs` entry when possible.
- Serialize schema migration and full rebuild operations with an application-level lock file.

Incremental updates are idempotent: reprocessing unchanged artifacts changes no catalog content and creates no duplicate rows.

### 11.3 Deletions and retention

Catalog retention is permanent by default. Ordinary incremental runs do not infer deletion merely because an item is absent from `latest-items.json` or because an artifact was removed. Explicit deletion of a retained external record requires a future maintenance command and is outside phase 1. Superseded chunks are physically removed from FTS and `chunks`; their integer IDs are never reused. Derived documents may be replaced when their authoritative file is rewritten at the same artifact identity, but their prior observation remains available for audit and rebuild accounting.

### 11.4 Rebuild

`radar-index rebuild`:

1. obtains the rebuild lock;
2. opens the current catalog read-only when present and collects retained observations plus the chunk-ID high-water mark;
3. scans all currently supported Radar artifacts and merges them idempotently with retained observations;
4. reapplies current normalization, labels, chunking, clustering, and scoring into a temporary database in the same filesystem;
5. preserves IDs for unchanged chunks and allocates all new chunk IDs above the previous high-water mark;
6. validates the temporary database, then closes active connections under the process lock;
7. atomically replaces the catalog;
8. retains the previous catalog as a bounded backup until the new catalog passes its integrity checks, then removes it on a later successful rebuild or explicit maintenance policy.

If the current catalog cannot be read safely, the rebuild refuses to discard retained history and explains how to restore its backup. A separate recovery mode is not part of phase 1. If temporary-catalog validation fails, the current catalog remains active.

## 12. Search API and Ranking

The internal search service accepts:

- text query;
- topic, kind, source family, domain, label, and evidence-role filters;
- relative or absolute time bounds;
- sort mode;
- limit and cursor/offset as appropriate for the existing UI pattern.

Default relevance combines normalized components:

```text
rank = 0.60 * full_text_relevance
     + 0.25 * heat
     + 0.15 * corroboration
```

Explicit `--sort heat` or `--sort corroboration` uses that primary score with recency and stable identity as deterministic tie-breakers. Full-text ranking remains the primary component for default search, preventing a popular but weakly matching event from overwhelming the query.

Results can be returned as individual documents or grouped event clusters. A grouped result includes the representative document, matching snippets, heat, corroboration, mention count, unique domain count, source-family count, and expandable members.

## 13. CLI Design

Add these commands through the existing `argparse` command structure:

```text
agent-reach radar-index update
agent-reach radar-index rebuild
agent-reach radar-index status

agent-reach radar-search "query"
  [--topic TOPIC]
  [--kind KIND]
  [--source SOURCE]
  [--since 30d]
  [--sort relevance|heat|corroboration]
  [--limit 20]
  [--json]
```

Behavior:

- human output uses Rich and follows existing CLI conventions;
- `--json` writes a stable machine-readable result object and sends diagnostics to stderr;
- an empty query is allowed only when filters or a non-relevance sort provide a bounded browse operation;
- invalid durations, filters, and limits fail with an actionable argument error;
- `status` reports catalog path, schema/rule versions, tokenizer, last successful/failed run, document/chunk/cluster counts, and whether a rebuild is required.

## 14. Radar UI Design

Extend the existing FastAPI Radar UI rather than adding a second server.

The UI provides:

- a search bar with topic, kind, source, time, and sort filters;
- article and event-grouped views;
- event cards showing **熱度**, **交叉佐證**, mention count, and unique external domain count;
- an expandable list of sources/reposts that explains why the scores differ;
- visible deterministic rule labels and provenance;
- catalog status and a background reindex action following the existing background-action pattern.

Endpoints:

```text
GET  /api/search
GET  /api/clusters/{cluster_id}
GET  /api/search/status
POST /api/search/reindex
```

The reindex endpoint starts a bounded background job and returns job state; it does not hold the request open for a full rebuild. Existing UI authentication/exposure assumptions are preserved. The endpoint must reject concurrent rebuilds with a clear conflict response.

## 15. Configuration

Add a `search` section to Radar configuration with defaults that require no user changes. It controls:

- enabled/automatic indexing flags;
- catalog path override;
- clustering window and thresholds;
- topic keywords and entity/ticker dictionaries;
- tracking-query-parameter removal rules;
- score weights, caps, and recency half-life;
- chunk target size;
- default search limit and maximum limit.

Configuration parsing validates that each score weight set sums to 1.0 within a small numerical tolerance. Invalid search configuration fails explicit CLI operations, while automatic hooks log a warning and preserve the successful parent workflow.

## 16. Error Handling and Observability

- Use Loguru for structured diagnostic messages and Rich only for human CLI presentation.
- Include run IDs, artifact paths, counts, and exception categories without logging full sensitive content.
- Treat malformed individual source records as item-level failures; continue the batch when isolation is safe and report their count.
- Treat schema, transaction, integrity, or lock failures as batch failures and roll back.
- Detect unavailable FTS5 at catalog initialization and return an actionable environment error; do not silently create an unsearchable catalog.
- Validate database integrity and expected row relationships before atomic rebuild replacement.
- Keep API errors stable and avoid exposing local filesystem paths unless the caller requests status locally.

## 17. TurboVec Phase 2 Boundary

TurboVec is a compressed full-scan vector index, not the catalog database. Phase 2 will implement a vector adapter with operations equivalent to:

```text
build(manifest, vectors)
open(manifest)
search(query_vector, k, allowed_chunk_ids?) -> [(chunk_id, distance)]
status() -> index metadata
```

The manifest records:

- embedding provider/model identifier;
- vector dimension and normalization policy;
- distance metric;
- TurboVec version and quantization bits;
- catalog schema version;
- maximum indexed `chunk_id` and a digest of indexed chunk hashes;
- build timestamp and source catalog identity.

The future retrieval flow is:

```text
query
 -> SQLite metadata/time filters
 -> query embedding
 -> TurboVec nearest-neighbor candidates
 -> SQLite hydration and FTS/metadata reranking
 -> optional local-model context
```

If TurboVec cannot efficiently accept an allowlist for the installed version, the adapter over-fetches candidates and applies SQLite-backed filtering before hydration. The catalog API remains unchanged.

TurboVec can accelerate semantic retrieval and reduce the amount of context sent to a later local model. It does **not** increase the local model’s token-generation speed. Phase 2 should begin only after an embedding backend is selected or the catalog reaches a scale where semantic retrieval is justified, with approximately 50,000 chunks used as an operational review point rather than a hard requirement.

## 18. Testing Strategy

### 18.1 Unit tests

- canonical URL normalization and tracking-parameter handling;
- stable `document_key` generation and changed-content behavior;
- observation-key idempotence and repeated-crawl behavior;
- deterministic label precedence, namespaces, and rule versions;
- language, ticker, paper, repository, and topic rules;
- chunk stability and non-reuse of replaced IDs;
- SimHash/title/entity similarity threshold boundaries;
- heat normalization and recency decay;
- duplicate/repost behavior increasing heat but not independent corroboration;
- independent domains/source families increasing corroboration;
- derived documents excluded from both evidence scores;
- configuration validation.

### 18.2 Integration tests

- schema creation and migration;
- incremental update idempotence;
- content updates replacing chunks and FTS rows correctly;
- permanent retention when items disappear from the latest snapshot and across rebuilds;
- rebuild atomicity and preservation of the prior catalog on validation failure;
- concurrent lock and busy-timeout behavior;
- Chinese and English FTS queries;
- trigram detection and short-CJK fallback;
- CLI human and JSON contracts;
- UI search, cluster detail, status, and reindex endpoints;
- automatic hook failures remaining non-fatal to their parent workflows.

Fixtures use synthetic Radar records and local temporary directories. Tests do not require Grok, TurboVec, network access, or a local model.

## 19. Acceptance Criteria

Phase 1 is complete when:

1. A user can rebuild a catalog from existing Radar artifacts and search it locally from both CLI and UI.
2. Re-running an incremental update over unchanged data produces no duplicate documents, observations, labels, chunks, or cluster memberships and does not change heat.
3. Each visible label can be traced to a deterministic rule ID and version.
4. Similar reports are grouped conservatively and expose their match rationale.
5. A repost flood increases heat with diminishing returns but does not count as many independent corroborating sources.
6. Independent external domains and source families increase the separately displayed corroboration score.
7. Deep dives, digests, and promoted Wiki pages are searchable but add no external evidence.
8. Automatic indexing failures are observable and do not fail an otherwise successful Radar workflow.
9. Rebuild preserves retained external history and unchanged chunk IDs; rebuild failure leaves the previous searchable catalog intact.
10. Stable integer chunk IDs and a documented adapter/manifest boundary are ready for a later TurboVec phase.
11. All new unit and integration tests pass without network or model dependencies.

## 20. Delivery Boundaries

Implementation planning should divide the work into reviewable increments without changing the approved architecture:

- catalog schema and repository boundary;
- normalization, labeling, and chunking;
- clustering and scoring;
- incremental/rebuild lifecycle and hooks;
- CLI search/index commands;
- Radar UI endpoints and controls;
- verification, documentation, and TurboVec adapter contract.

Actual TurboVec installation, embeddings, semantic search, and local-model RAG remain a separately approved phase after phase-1 usage data is available.
