---
name: agent-reach
description: Windows-first research integration tooling for Codex. Use when the user needs to inspect research channel capabilities, verify readiness, export Codex integration settings, or run thin read-only collection over `web`, `exa_search`, `github`, `hatena_bookmark`, `bluesky`, `qiita`, `youtube`, `rss`, `searxng`, `crawl4ai`, `hacker_news`, `mcp_registry`, `reddit`, or `twitter`.
---

# Agent Reach

Use this skill when the task benefits from Agent Reach's Windows/Codex integration surface.

## Positioning

This fork is intentionally narrow. Treat it as:

- a bootstrapper for the local research toolchain
- a machine-readable channel registry
- a readiness and diagnostics layer
- an integration helper for downstream projects
- a thin read-only collection surface

Do not assume this fork owns scheduling, ranking, summarization, or publishing. Those remain responsibilities of the host project.
Do not assume this fork chooses investigation scope. The caller chooses scale, routes, source mix, ranking, summarization, and posting.

## Operating Rules For Codex

- Default to the globally installed `agent-reach` CLI in any downstream repository.
- Do not ask the user to copy `.codex-plugin`, `.mcp.json`, `agent_reach/skills`, or Agent Reach source files into the downstream repository unless they explicitly ask for repo-local plugin artifacts.
- Use `agent-reach collect --json` as the stable handoff. Preserve the returned `CollectionResult` JSON when another system will rank, summarize, dedupe, or publish it.
- Use `--item-text-mode snippet` or `--item-text-mode none` plus `--item-text-max-chars` when machine-readable output should carry less normalized item text. `--max-text-chars` still affects text mode only.
- When naming channels in prompts or commands, use the exact stable names from `agent-reach channels --json`. For example, use `hatena_bookmark`, not `hatena`.
- Keep lightweight asks lightweight. Do not auto-escalate a narrow request into large-scale research.
- Inspect `agent-reach channels --json` `operation_contracts` before choosing per-channel options such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`.
- Use `agent-reach collect --json --save .agent-reach/evidence.jsonl` when a research run needs one shared evidence ledger.
- Use `agent-reach collect --json --save-dir .agent-reach/shards` when per-command shards or parallel collection are easier than appending into one file.
- Merge sharded ledgers with `agent-reach ledger merge --input .agent-reach/shards --output .agent-reach/evidence.jsonl --json` before `ledger summarize`, `ledger query`, or `plan candidates`.
- Use `agent-reach plan candidates --input .agent-reach/evidence.jsonl --json` for lightweight URL or ID dedupe before selected follow-up reads.
- Keep `agent-reach plan candidates` at the default `--limit 20` unless the caller explicitly wants a broader candidate set.
- Use `agent-reach schema collection-result --json` when downstream code needs a contract-testable schema.
- Use `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json` when downstream automation needs to prove the evidence ledger is parseable.
- Add `--require-metadata` to `ledger validate` only when missing `intent`, `query_id`, or `source_role` should fail the run.
- Use `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json` when automation needs neutral channel, operation, metadata, item, and error counts.
- Add `--filter` to `ledger summarize` when the caller wants narrowed counts such as one `intent` or `source_role`.
- Use `agent-reach ledger query --input .agent-reach/evidence.jsonl --filter "channel == github" --json` for lightweight record filtering or field projection over saved evidence.
- Use `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json` when a successful conditional collection was captured without `--save`.
- Treat `engagement`, `media_references`, `identifiers`, `extras.source_hints`, `extras.engagement_complete`, `extras.media_complete`, `error.category`, social time-window warnings, and page extraction hygiene fields such as `text_length`, `link_count`, `image_count`, `link_density`, and `extraction_warning` as diagnostics only, not ranking or trust scores.
- Treat `doctor --json` as flat diagnostics by default. Add `--require-channel`, `--require-channels`, or `--require-all` only when the caller wants readiness to affect the exit code.
- Inspect `doctor.summary.probe_attention` when a channel has partial probe coverage or a probe run left operations unprobed.
- Treat `batch` and `scout` as explicit opt-in helpers. They are not the default route for everyday collection.
- For large research tasks, only use bounded fan-out when the caller explicitly opts in; then use `plan candidates` for no-model dedupe and deep-read only selected URLs.
- Treat non-required channel failures as partial results unless the user asked for strict completeness.

## Discovery First

Start with the integration surface before reaching for backend-specific commands.

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach schema collection-result --json
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json
agent-reach collect --channel web --operation read --input "https://example.com" --json --raw-mode none --item-text-mode snippet --item-text-max-chars 500
agent-reach export-integration --client codex --format json --profile runtime-minimal
```

## Supported channels

- `web`: generic page reading through Jina Reader
- `exa_search`: wide web search through `mcporter`
- `github`: repository and code search through `gh`
- `hatena_bookmark`: URL-centric Hatena Bookmark reactions and related entries
- `bluesky`: public Bluesky post search
- `qiita`: public Qiita article search
- `youtube`: video metadata, subtitle availability, captions, and thumbnail references through `yt-dlp`
- `rss`: RSS and Atom feeds through `feedparser`
- `searxng`: configurable metasearch through a user-provided SearXNG instance
- `crawl4ai`: optional browser-backed page reads and bounded same-origin crawls
- `hacker_news`: Hacker News search, story lists, and discussion reads
- `mcp_registry`: public MCP Registry server discovery and reads
- `reddit`: public Reddit search and discussion reads through `rdt-cli`
- `twitter`: Twitter/X search through `twitter-cli`

Use those exact identifiers in commands and handoffs. Service names are fine in prose, but stable channel names should stay in backticks.

## Workflow

1. Run `agent-reach channels --json` if the available surfaces are unclear.
2. Run `agent-reach doctor --json` when readiness matters.
3. Inspect `summary.required_not_ready`, `summary.informational_not_ready`, and `summary.probe_attention`; let the caller choose `--require-channel`, `--require-channels`, or `--require-all` when readiness should gate the run.
4. Use `--probe` only when a lightweight live check is useful.
5. Use `agent-reach collect --json` by default when external code needs normalized results, add `--save .agent-reach/evidence.jsonl` when one shared ledger is fine, and prefer `--save-dir .agent-reach/shards` when per-command shards or parallel runs are easier.
6. For large machine-readable handoffs, prefer `--raw-mode minimal|none` plus `--item-text-mode snippet|none`; keep full item text for shortlisted deep reads.
7. Prefer `--run-id`, `--intent`, `--query-id`, and `--source-role` on saved evidence. Treat missing metadata warnings as advisory unless the caller chose `ledger validate --require-metadata`.
8. Merge shard directories before `ledger summarize`, `ledger query`, or `plan candidates`.
9. Use `agent-reach plan candidates` when a saved ledger needs no-model URL or ID dedupe.
10. Use diagnostic hints only to explain provenance or extraction shape; downstream code owns ranking and selection.
11. Use `AgentReachClient` only when the host Python environment has Agent Reach installed into it directly.
12. Choose channels from the live `channels --json` contract for the user's task; Agent Reach does not own ranking, routing, or source policy.
13. Choose advanced collection controls such as page, cursor, and time-window options from the live `operation_contracts`; Agent Reach does not choose collection scope for you.
14. Treat `scout` as a planning helper and capability snapshot, not the default route for a lightweight ask.
15. Treat large-scale research as explicit opt-in. Keep narrow asks on `collect --json` unless the caller clearly wants a broader run.
16. Use `searxng` only after `searxng-base-url` is configured or `SEARXNG_BASE_URL` is set, and treat placeholder example hosts as misconfiguration warnings.
17. Use `crawl4ai` only when the optional extra and browser runtime are available; `crawl` requires an explicit `--query` goal.
18. Use `reddit` through `rdt-cli`; it does not need Reddit OAuth, client credentials, or a User-Agent config.
19. Treat Twitter/X as opt-in and cookie-based; authenticated-but-unprobed `warn` means collect may work, but operation readiness is unverified.
20. In arbitrary downstream repositories, use the globally installed `agent-reach` CLI. Do not require copying Agent Reach repo files into the downstream project unless the user explicitly asks for repo-local plugin artifacts.

## Large-Scale Research Pattern

Use this pattern only when the caller explicitly opts into a broader run. Do not auto-escalate a lightweight ask into this path.

1. Run `agent-reach doctor --json` and inspect `operation_statuses` when readiness matters.
2. Start with 2-4 caller-chosen discovery queries at `--limit 5` to `--limit 10`.
3. When a channel supports pagination or time windows, choose `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` from the live contract instead of assuming one fixed route.
4. If a saved batch plan exists, run `agent-reach batch --plan PLAN.json --validate-only --json` before the write-producing batch run.
5. Add source-specific searches such as `github`, `qiita`, `bluesky`, `rss`, `hacker_news`, `mcp_registry`, `reddit`, `searxng`, or `twitter` only when they match the task and are ready.
6. Save raw `CollectionResult` envelopes with `--save .agent-reach/evidence.jsonl` or `--save-dir .agent-reach/shards` when the run needs an evidence trail.
7. If the run produced shards, merge them before summary or candidate planning.
8. Run `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json` when CI or downstream automation needs health counts.
9. Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json` before deeper reads.
10. Prefer `--raw-mode minimal|none` plus `--item-text-mode snippet|none` for broad JSON handoffs; keep full item text for shortlisted deep reads.
11. Use `web read` for selected URLs, not every search result.
12. Inspect source hints and web hygiene only as non-authoritative diagnostics.
13. Return partial results with clear channel failures instead of blocking on one non-required backend.

## Command Routing

- General search: read [references/search.md](references/search.md)
- GitHub work: read [references/dev.md](references/dev.md)
- Web pages and RSS: read [references/web.md](references/web.md)
- YouTube: read [references/video.md](references/video.md)
- Social and forums: read [references/social.md](references/social.md)
