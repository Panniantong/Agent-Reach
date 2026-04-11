# Changelog

All notable changes to this fork are documented here.

## Unreleased

## [1.10.0] - 2026-04-12

### Added

- bundled maintainer-only Codex skills for proposal review and approved-change shipping: `agent-reach-maintain-proposals` and `agent-reach-maintain-release`
- maintainer guidance references for policy-safe adoption decisions, scoped implementation, and push plus reinstall flow

### Changed

- expanded bundled skill metadata and docs to surface the new maintainer workflows alongside the existing research skills

## [1.9.0] - 2026-04-12

### Added

- `ledger query` for lightweight evidence-ledger filtering and dotted-path field projection without external tooling
- additional page extraction hygiene diagnostics such as `image_count` and `link_density` for `web` reads and browser-backed page reads

### Changed

- surfaced page extraction hygiene under item extras as well as top-level read metadata so downstream code can inspect page shape without re-reading raw payloads

## [1.8.0] - 2026-04-12

### Added

- top-level `schema_version` and `agent_reach_version` on `CollectionResult` envelopes
- packaged `collection-result` JSON Schema exposed through `agent-reach schema collection-result --json`
- normalized item diagnostics for `canonical_url`, `source_item_id`, `engagement`, `media_references`, and neutral `identifiers`
- cross-channel `error.category` taxonomy while preserving source-specific `error.code`
- `collect --raw-mode full|minimal|none` and `--raw-max-bytes` for caller-controlled raw payload retention
- `ledger validate --require-metadata` and `ledger summarize` for optional evidence metadata strictness and neutral artifact health counts
- `plan candidates --by normalized_url|source_item_id|domain|repo`
- social search time-window diagnostics under `meta.diagnostics.unbounded_time_window`
- batch plan metadata defaults for `intent`, `source_role`, and `query_id_prefix`

### Changed

- normalized GitHub repository search results from both REST snake_case and existing camelCase payloads so stars, forks, and repo identifiers are available without reading `raw`

## [1.7.0] - 2026-04-11

### Changed

- flattened the channel registry so Agent Reach no longer ships built-in core/optional source tiers
- replaced doctor's static exit policy with caller-defined readiness controls through `--require-channel`, `--require-channels`, and `--require-all`
- updated the Python SDK, integration exports, bundled skill guidance, and docs to treat channel choice and readiness gating as caller-owned policy
- generalized install planning metadata from fixed core/optional channel buckets to flat selected-channel inputs
- removed transient prompt and research-note docs so the repo ships only the external-use guides that match the current CLI surface
- aligned `README.md`, `llms.txt`, and Codex integration exports around the current channel registry and no-copy downstream workflow
- fixed `check-update` so fork builds newer than the latest upstream release are reported as ahead of upstream instead of update-available

### Fixed

- normalized adapter User-Agent strings to use the current package version instead of stale hard-coded values

## [1.6.0] - 2026-04-10

### Added

- field research improvement handoff for future Agent Reach work
- Agent Reach Nexus concept note for capability graph, scout, ledger, planner, and guard ideas
- evidence ledger persistence for raw `CollectionResult` JSONL records
- `agent-reach plan candidates` for no-model URL or ID dedupe over evidence ledgers
- conservative source hints and web extraction diagnostics
- downstream examples and a manual GitHub Actions smoke workflow for raw collection artifacts

## [1.5.3] - 2026-04-10

### Added

- Codex runtime policy metadata that spells out no-copy usage, channel choice, failure handling, and large-scale research workflow
- skill-level operating rules for arbitrary downstream repositories and high-volume information gathering

## [1.5.2] - 2026-04-10

### Added

- no-copy downstream usage guide for Codex, GitHub Actions, and Discord bot projects
- composite GitHub Action for installing Agent Reach from this repository in downstream workflows
- machine-readable `external_project_usage` metadata in Codex integration exports

## [1.5.1] - 2026-04-10

### Added

- operation-level `doctor --json` diagnostics through `operation_statuses`
- detailed Twitter/X probe diagnostics that separate live `user` and `search` readiness
- Bluesky fallback attempt diagnostics through `meta.attempted_host_results`
- `inline_payload_notes` in Codex integration exports
- Windows UTF-8 fallback guidance for raw `twitter-cli` help debugging

### Changed

- kept channel `check()` / `probe()` two-tuple compatibility while adding detailed doctor-only diagnostics
- preserved structured Twitter/X backend errors such as `not_found` instead of collapsing them into `command_failed`

## [1.5.0] - 2026-04-10

### Added

- `AgentReachClient` as the primary external Python SDK
- `agent-reach collect --json` as the thin read-only CLI collection surface
- normalized `CollectionResult` and `NormalizedItem` envelopes with backend-native `raw` payloads
- dedicated collection adapters for `web`, `exa_search`, `github`, `hatena_bookmark`, `bluesky`, `qiita`, `youtube`, `rss`, and `twitter`
- `twitter` collection operations for `user`, `user_posts`, and `tweet`
- Python SDK documentation and external usage examples for bots and CI jobs

### Changed

- positioned the fork around external integration, diagnostics, and read-only collection
- updated Codex integration exports and plugin metadata to include collection guidance
- aligned docs, skill references, and machine-readable channel metadata around supported operations
- translated common Twitter/X search tokens such as `from:`, `has:`, and `type:` into stable collect behavior
- forced UTF-8 subprocess settings for downstream CLI integrations on Windows

### Removed

- legacy `watch` command
- legacy Bash-first helper scripts and outdated docs
- legacy skill root discovery for `.claude` and `.openclaw`

## [1.4.0] - 2026-04-10

### Added

- machine-readable channel contracts through `agent-reach channels --json`
- machine-readable diagnostics through `agent-reach doctor --json`
- lightweight live checks through `agent-reach doctor --json --probe`
- non-mutating integration export through `agent-reach export-integration --client codex`
- JSON install preview through `agent-reach install --dry-run --json`
- repo-local `.codex-plugin/plugin.json` and `.mcp.json`

### Changed

- narrowed the supported surface to `web`, `exa_search`, `github`, `youtube`, `rss`, and optional `twitter`
- rewrote the Windows/Codex docs around bootstrap, registry, readiness, and integration flows
