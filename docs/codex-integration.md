# Agent Reach Codex Integration

Agent Reach is a Windows-first integration layer for research tooling. It exposes a thin read-only collection surface while keeping scheduling and publishing outside the repo.

## What it provides

- a stable channel registry through `agent-reach channels --json`
- per-operation option contracts through `channels --json` `operation_contracts`, so downstream code can choose pagination and time-window inputs itself
- readiness diagnostics through `agent-reach doctor --json`, including `operation_statuses`, `probed_operations`, `probe_run_coverage`, and `summary.probe_attention`
- a thin read-only collector through `agent-reach collect --json`
- a packaged `CollectionResult` contract through `agent-reach schema collection-result --json`
- ledger validation, summary, query, and append helpers through `agent-reach ledger validate --json`, `agent-reach ledger summarize --json`, `agent-reach ledger query --json`, and `agent-reach ledger append --json`
- a non-mutating Codex export through `agent-reach export-integration --client codex`
- bundled Codex skills for diagnostics, brief shaping, and in-session orchestration
- repo-local Codex artifacts through `.codex-plugin/plugin.json`, `.mcp.json`, and `agent_reach/skills/` when running from a source checkout

## Recommended flow

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach export-integration --client codex --format json
```

`doctor --json` is diagnostic-only by default. When a workflow wants readiness to affect the exit code, the caller chooses `--require-channel`, `--require-channels`, or `--require-all`, then inspects `summary.required_channels`, `summary.required_not_ready`, `summary.informational_not_ready`, and `summary.probe_attention`.

## No-Copy External Project Mode

For everyday Codex usage in arbitrary repositories, install Agent Reach globally instead of copying files into each project:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git
agent-reach skill --install
agent-reach version
agent-reach doctor --json --probe
```

If you need a reproducible build, pin a commit or ref:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git@<commit-or-ref>
agent-reach skill --install
agent-reach version
```

After that, Codex can call `agent-reach collect --json` from any working directory. The downstream project does not need `.codex-plugin`, `.mcp.json`, or `agent_reach/skills` files unless it explicitly wants repo-local plugin artifacts.

`agent-reach skill --install` installs the bundled skill suite:

- `agent-reach`
- `agent-reach-shape-brief`
- `agent-reach-orchestrate`
- `agent-reach-maintain-proposals` (maintainer-only)
- `agent-reach-maintain-release` (maintainer-only)

Use `agent-reach-shape-brief` when a research ask is still underspecified and you want a fixed brief before execution. Use `agent-reach-orchestrate` when you want the same Codex session to move from intake to actual Agent Reach collection start.

The bundled suite also includes two maintainer-only skills for this repository itself: `agent-reach-maintain-proposals` for proposal review and `agent-reach-maintain-release` for approved change shipping.

For most rough asks, `agent-reach-orchestrate` is the default entrypoint. Reach for `agent-reach-shape-brief` only when you want to stop before collection starts.

Subagents are optional and conservative in this model. If delegation is available and authorized, use at most one intake-only subagent to shape a vague ask into an executable brief. Keep `channels --json`, `doctor --json`, channel choice, collection start, and final synthesis on the main agent.

`export-integration --format json` also includes `codex_runtime_policy`, which is the machine-readable version of this rule set. Downstream setup tools should prefer `agent-reach collect --json`, should not vendor Agent Reach files by default, and should treat large-scale research as explicit opt-in rather than auto-escalating lightweight asks.

`agent-reach check-update --json` compares the installed build to upstream `Panniantong/Agent-Reach` releases. It is useful for upstream awareness, but the current fork build should still be chosen from the fork repo URL or a pinned commit.

When `agent-reach` is running from a tool install instead of a source checkout, `export-integration` will not point at nonexistent repo-root files. In that mode it returns:

- `execution_context: tool_install`
- `plugin_manifest` / `mcp_config` as `null`
- inline payloads for the plugin manifest and MCP config
- `inline_payload_notes` that explain how the relative `plugin_manifest_inline.mcpServers` reference is meant to resolve after writing both files
- suggested write locations for downstream projects
- a documentation summary instead of dead doc paths

## Supported channels

- `web`
- `exa_search`
- `github`
- `hatena_bookmark`
- `bluesky`
- `qiita`
- `youtube`
- `rss`
- `searxng` (optional configured instance)
- `crawl4ai` (optional browser-backed dependency)
- `hacker_news`
- `mcp_registry`
- `reddit` (optional `rdt-cli`, no Reddit OAuth config)
- `twitter` (optional)

These channels are exposed as metadata, setup guidance, diagnostics, and read-only collection operations so downstream tools can wire their own workflows without scraping repo docs. YouTube returns video metadata, subtitle/caption availability, thumbnail references, and normalized linked media references; Agent Reach does not perform media binary analysis.

When a channel supports bounded pagination or time windows, those controls are exposed as machine-readable option descriptors. Downstream code decides whether to use `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`; Agent Reach only forwards them and records pagination metadata in the returned `meta`.

## Compatibility Snapshot

| Surface | Status | Notes |
| --- | --- | --- |
| Native Windows PowerShell | Supported | Primary target |
| Codex skill install | Supported | Uses `CODEX_HOME/skills` or `~/.codex/skills` |
| Codex plugin manifest | Supported | Repo-local in checkouts, inline export in tool installs |
| MCP wiring for Exa | Supported | Repo-local in checkouts, inline export in tool installs |
| Python SDK | Supported | `AgentReachClient` works after install into the caller project environment |
| Read-only collect CLI | Supported | `agent-reach collect --json` |
| Caller-defined doctor readiness policy | Supported | `doctor --json` stays diagnostic by default; callers opt into `--require-channel`, `--require-channels`, or `--require-all` |
| CollectionResult schema | Supported | `schema collection-result --json` exposes a contract-testable schema for downstream systems |
| Evidence ledger validation | Supported | `ledger validate --json` checks saved JSONL artifacts, `ledger validate --require-metadata --json` optionally gates provenance metadata, `ledger summarize --json` reports neutral health counts, `ledger query --json` filters or projects saved records, and `ledger append --json` can add a captured `CollectionResult` later |
| macOS/Linux installer automation | Not first-class | Use `install --safe` for guidance only |
| Full workflow orchestration | Deferred | Scheduling, ranking, summarization, and publishing stay downstream |
