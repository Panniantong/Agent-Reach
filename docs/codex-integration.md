# Agent Reach Codex Integration

Agent Reach is a Windows-first integration layer for research tooling. It now exposes a thin read-only collection surface, while keeping scheduling and publishing outside the repo.

## What it provides

- a stable channel registry through `agent-reach channels --json`
- per-operation option contracts through `channels --json` `operation_contracts`, so downstream code can choose pagination and time-window inputs itself
- readiness diagnostics through `agent-reach doctor --json`, including `operation_statuses`, `probed_operations`, and `probe_run_coverage` for downstream routing
- a thin read-only collector through `agent-reach collect --json`
- ledger validation and append helpers through `agent-reach ledger validate --json` and `agent-reach ledger append --json`
- a non-mutating Codex export through `agent-reach export-integration --client codex`
- repo-local Codex artifacts through `.codex-plugin/plugin.json` and `.mcp.json` when running from a source checkout

## Recommended flow

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach collect --channel qiita --operation search --input "python" --limit 4 --page-size 2 --max-pages 2 --body-mode snippet --json
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach export-integration --client codex --format json
```

`doctor --json` defaults to `--exit-policy core`: tier 0 channel failures affect the exit code, while optional gaps are reported under `summary.advisory_not_ready`. Use `--exit-policy all` for strict all-channel readiness.

## No-Copy External Project Mode

For everyday Codex usage in arbitrary repositories, install Agent Reach globally instead of copying files into each project:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git
agent-reach skill --install
agent-reach doctor --json --probe
```

After that, Codex can call `agent-reach collect --json` from any working directory. The downstream project does not need `.codex-plugin`, `.mcp.json`, or `agent_reach/skill` files unless it explicitly wants repo-local plugin artifacts.

`export-integration --format json` also includes `codex_runtime_policy`, which is the machine-readable version of this rule set. Downstream setup tools should prefer `agent-reach collect --json` and should not vendor Agent Reach files by default.

## Repo artifacts

- Plugin manifest: `.codex-plugin/plugin.json`
- MCP config snippet: `.mcp.json`
- Bundled skill source: `agent_reach/skill`
- Python SDK docs: `docs/python-sdk.md`
- Field research improvements: `docs/field-research-improvements-2026-04-10.md`
- Agent Reach Nexus concept: `docs/agent-reach-nexus-concept.md`

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
