# Agent Reach

Windows-first research integration tooling with a stable JSON CLI and an optional Python SDK for downstream projects.

Agent Reach is intentionally narrow. It helps other tools collect information safely and predictably; it does not own scheduling, ranking, summarization, or publishing. In practice this fork does four jobs:

- bootstrap the Windows-friendly toolchain needed for research workflows
- expose a stable registry of supported channels
- provide readiness diagnostics and integration exports
- offer a thin read-only collection surface for external apps, bots, and CI jobs

It also ships a bundled Codex skill suite for collection, orchestration, and maintainer workflows around that surface:

- `agent-reach`: diagnostics, channel discovery, and read-only collection guidance
- `agent-reach-shape-brief`: turn rough research asks into a fixed brief
- `agent-reach-orchestrate`: take a rough ask, optionally use one intake subagent when it is actually worth it, and start the Agent Reach investigation in-session
- `agent-reach-propose-improvements`: maintainer-only skill for turning raw external findings into a clean, policy-compatible shortlist before formal review
- `agent-reach-maintain-proposals`: maintainer-only review skill for deciding adopt/reject/defer on a concrete Agent Reach proposal list before editing
- `agent-reach-maintain-release`: maintainer-only shipping skill for approved Agent Reach changes, including push and exact-ref reinstall flows

For most rough research asks, start with `agent-reach-orchestrate`. Use `agent-reach-shape-brief` only when you explicitly want to stop at brief formation before collection.

## Current channel surface

Supported channels:

- `web`
- `exa_search`
- `github`
- `hatena_bookmark`
- `bluesky`
- `qiita`
- `youtube`
- `rss`
- `searxng`
- `crawl4ai`
- `hacker_news`
- `mcp_registry`
- `reddit`
- `twitter`

Use those exact stable channel names in commands and prompts. For example, Hatena Bookmark is exposed as `hatena_bookmark`; there is no separate `hatena` channel.

The live contract is always `agent-reach channels --json`. External code should trust that surface over static README lists.

## Install The Right Build

For the latest fork build, install from the fork repo URL rather than from upstream release tags:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git
agent-reach skill --install
agent-reach version
```

To pin an exact build:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git@<commit-or-ref>
agent-reach skill --install
agent-reach version
```

For a source checkout:

```powershell
uv tool install --force .
agent-reach version
```

`agent-reach check-update --json` compares this fork against upstream `Panniantong/Agent-Reach` releases. If this fork is ahead of the latest upstream release, it reports that explicitly instead of telling you to downgrade.

## Stable External Surfaces

- `agent-reach channels --json`
- `agent-reach doctor --json`
- `agent-reach doctor --json --probe`
- `agent-reach collect --channel <name> --operation <op> --input <value> --json`
- `agent-reach schema collection-result --json`
- `agent-reach plan candidates --input .agent-reach/evidence.jsonl --json`
- `agent-reach ledger merge --input .agent-reach/shards --output .agent-reach/evidence.jsonl --json`
- `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json`
- `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json`
- `agent-reach ledger query --input .agent-reach/evidence.jsonl --filter "channel == github" --json`
- `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json`
- `agent-reach export-integration --client codex --format json`
- Python: `from agent_reach import AgentReachClient`

These are the supported machine-readable entry points for external projects. Bots, GitHub Actions, and downstream repos should not need to scrape README text or `SKILL.md`.
Use `agent-reach export-integration --client codex --format json --profile runtime-minimal` when downstream tooling only needs compact runtime guidance instead of the full bootstrap payload.

## Recommended External Flow

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json
agent-reach collect --channel web --operation read --input "https://example.com" --json --raw-mode none --item-text-mode snippet --item-text-max-chars 500
agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json
agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 3 --json
agent-reach export-integration --client codex --format json --profile runtime-minimal
```

When provenance matters:

```powershell
agent-reach schema collection-result --json
agent-reach collect --channel exa_search --operation search --input "AI agent tooling" --limit 10 --json --save .agent-reach/evidence.jsonl --run-id agent-tooling --intent discovery --query-id exa-agent-tooling --source-role web_search
agent-reach ledger validate --input .agent-reach/evidence.jsonl --require-metadata --json
agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json
agent-reach ledger query --input .agent-reach/evidence.jsonl --filter "channel == exa_search" --fields channel,query_id,source.file,result.items[*].url --json
agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json
```

For parallel or per-command shard-first collection, prefer `agent-reach collect ... --save-dir .agent-reach/shards` and merge with `agent-reach ledger merge --input .agent-reach/shards --output .agent-reach/evidence.jsonl --json` before `ledger summarize`, `ledger query`, or `plan candidates`.

Collection output includes top-level `schema_version` and `agent_reach_version`. Normalized items expose common raw signals such as `canonical_url`, `source_item_id`, `engagement`, `media_references`, and neutral `identifiers` when the source provides them. Twitter/X post items may also expose `extras.engagement_complete` and `extras.media_complete` as operation completeness hints. Page-like reads also expose diagnostic extraction hygiene such as `text_length`, `link_count`, `image_count`, `link_density`, and `extraction_warning`. `error.category` gives a stable cross-channel taxonomy while `error.code` preserves the source-specific or contract-specific detail. These are diagnostics only, not ranking or publishing policy.

Use `--raw-mode minimal`, `--raw-mode none`, or `--raw-max-bytes N` only when the caller wants smaller JSON artifacts. The default remains full raw payload retention. `--max-text-chars N` only affects the human text renderer; use `--item-text-mode snippet|none` plus `--item-text-max-chars N` when machine-readable output should carry less normalized item text.

## No-Copy Downstream Use

External projects do not need to vendor this repo. Use one of these patterns:

- Codex and other shell-first tools: `agent-reach collect --json`
- Python apps that intentionally depend on the package: `AgentReachClient`
- GitHub Actions: `iwachacha/Agent-Reach/.github/actions/setup-agent-reach@main`

Downstream projects do not need `.codex-plugin`, `.mcp.json`, or `agent_reach/skills` files when they are using the CLI.

## Caller-Control Policy

- Agent Reach does not choose investigation scope, routes, source mix, ranking, summarization, or posting.
- The caller chooses scope. Keep lightweight asks lightweight instead of trying to auto-escalate them into large-scale research.
- `agent-reach collect --json` is the default thin interface for downstream collection.
- `batch` and `scout` are explicit opt-in helpers. They are not the default route for everyday collection.
- `agent-reach doctor --json` is diagnostic-only by default; use `--require-channel`, `--require-channels`, or `--require-all` only when the caller wants readiness to gate a run.
- Inspect `agent-reach channels --json` `operation_contracts` before choosing bounded pagination or time-window options such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`.
- `agent-reach plan candidates` keeps its default `--limit 20`; raise it only when the caller explicitly wants a wider candidate review set. Use `--by normalized_url`, `--by source_item_id`, `--by domain`, or `--by repo` only for caller-selected candidate grouping.
- Large-scale research is explicit opt-in. When a saved batch plan is involved, run `agent-reach batch --plan PLAN.json --validate-only --json` before the write-producing batch execution.
- For large JSON handoffs, prefer `--raw-mode minimal|none` plus `--item-text-mode snippet|none`; keep full item text for shortlisted deep reads.
- Keep ranking, summarization, scheduling, Discord publishing, and state in the downstream project.

## Docs

- Install guide: [docs/install.md](docs/install.md)
- Downstream usage: [docs/downstream-usage.md](docs/downstream-usage.md)
- Codex integration: [docs/codex-integration.md](docs/codex-integration.md)
- Python SDK: [docs/python-sdk.md](docs/python-sdk.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)

## Examples And Artifacts

- Downstream examples live under `examples/`
- GitHub Actions smoke validation lives at `.github/workflows/agent-reach-smoke.yml`
- Repo-local integration artifacts are `.codex-plugin/plugin.json`, `.mcp.json`, and `agent_reach/skills/`

In tool installs, `export-integration` falls back to inline payloads and suggested destinations instead of returning dead checkout paths.
