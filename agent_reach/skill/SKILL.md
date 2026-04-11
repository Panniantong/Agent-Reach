---
name: agent-reach
description: Windows-first research integration tooling for Codex. Use when the user needs to inspect research channel capabilities, verify readiness, export Codex integration settings, or run thin read-only collection over web, Exa, GitHub, Hatena Bookmark, Bluesky, Qiita, YouTube, RSS, SearXNG, Crawl4AI, Hacker News, MCP Registry, Reddit, or optional Twitter/X.
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

## Operating Rules For Codex

- Default to the globally installed `agent-reach` CLI in any downstream repository.
- Do not ask the user to copy `.codex-plugin`, `.mcp.json`, `agent_reach/skill`, or Agent Reach source files into the downstream repository unless they explicitly ask for repo-local plugin artifacts.
- Use `agent-reach collect --json` as the stable handoff. Preserve the returned `CollectionResult` JSON when another system will rank, summarize, dedupe, or publish it.
- Inspect `agent-reach channels --json` `operation_contracts` before choosing per-channel options such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`.
- Use `agent-reach collect --json --save .agent-reach/evidence.jsonl` when a research run needs provenance across multiple commands.
- Use `agent-reach plan candidates --input .agent-reach/evidence.jsonl --json` for lightweight URL or ID dedupe before selected follow-up reads.
- Use `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json` when downstream automation needs to prove the evidence ledger is parseable.
- Use `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json` when a successful conditional collection was captured without `--save`.
- Treat `extras.source_hints`, `extras.media_references`, and web extraction hygiene fields as diagnostics only, not ranking or trust scores.
- Treat `doctor --json` as core-blocking by default: tier 0 failures affect the exit code, while optional setup gaps appear under `summary.advisory_not_ready`.
- For large research tasks, fan out bounded searches, use `plan candidates` for no-model dedupe, then deep-read only selected URLs.
- Treat optional channel failures as partial results unless the user asked for strict completeness.

## Discovery First

Start with the integration surface before reaching for backend-specific commands.

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json
agent-reach export-integration --client codex --format json
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
- `twitter`: optional Twitter/X search through `twitter-cli`

## Workflow

1. Run `agent-reach channels --json` if the available surfaces are unclear.
2. Run `agent-reach doctor --json` when readiness matters.
3. Inspect `summary.blocking_not_ready` and `summary.advisory_not_ready`; add `--exit-policy all` only when every optional channel must be ready.
4. Use `--probe` only when a lightweight live check is useful.
5. Use `agent-reach collect --json` by default when external code needs normalized results, and add `--save .agent-reach/evidence.jsonl` when provenance matters.
6. Use `agent-reach plan candidates` when a saved ledger needs no-model URL or ID dedupe.
7. Use diagnostic hints only to explain provenance or extraction shape; downstream code owns ranking and selection.
8. Use `AgentReachClient` only when the host Python environment has Agent Reach installed into it directly.
9. Choose channels from the live `channels --json` contract for the user's task; Agent Reach does not own ranking, routing, or source policy.
10. Choose advanced collection controls such as page, cursor, and time-window options from the live `operation_contracts`; Agent Reach does not choose collection scope for you.
11. Use `searxng` only after `searxng-base-url` is configured or `SEARXNG_BASE_URL` is set.
12. Use `crawl4ai` only when the optional extra and browser runtime are available; `crawl` requires an explicit `--query` goal.
13. Use `reddit` through `rdt-cli`; it does not need Reddit OAuth, client credentials, or a User-Agent config.
14. Treat Twitter/X as opt-in and cookie-based; authenticated-but-unprobed `warn` means collect may work, but operation readiness is unverified.
15. In arbitrary downstream repositories, use the globally installed `agent-reach` CLI. Do not require copying Agent Reach repo files into the downstream project unless the user explicitly asks for repo-local plugin artifacts.

## Large-Scale Research Pattern

1. Run `agent-reach doctor --json` and inspect `operation_statuses` when readiness matters.
2. Start with 2-4 caller-chosen discovery queries at `--limit 5` to `--limit 10`.
3. When a channel supports pagination or time windows, choose `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until` from the live contract instead of assuming one fixed route.
4. Add source-specific searches such as `github`, `qiita`, `bluesky`, `rss`, `hacker_news`, `mcp_registry`, `reddit`, `searxng`, or `twitter` only when they match the task and are ready.
5. Save raw `CollectionResult` envelopes with `--save .agent-reach/evidence.jsonl` when the run needs an evidence trail.
6. Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by url --limit 20 --json` before deeper reads.
7. Use `web read` for selected URLs, not every search result.
8. Inspect source hints and web hygiene only as non-authoritative diagnostics.
9. Return partial results with clear channel failures instead of blocking on one optional backend.

## Command Routing

- General search: read [references/search.md](references/search.md)
- GitHub work: read [references/dev.md](references/dev.md)
- Web pages and RSS: read [references/web.md](references/web.md)
- YouTube: read [references/video.md](references/video.md)
- Social and forums: read [references/social.md](references/social.md)
