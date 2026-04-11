# Agent Reach External Test Prompt

Use this prompt in a separate Codex session or downstream repository after installing the latest Agent Reach CLI and skill.

```text
You are testing Agent Reach from outside its source repository. Treat Agent Reach as an external CLI capability layer. Do not inspect, import, or edit the Agent Reach source checkout unless the test explicitly discovers that the installed CLI is stale and you are asked to diagnose installation.

Goal:
Verify that the externally installed `agent-reach` CLI, installed Codex skill, channel registry, readiness diagnostics, integration export, and live collection commands are current and usable. You must prove actual information retrieval with machine-readable evidence, not just say that commands succeeded.

Hard rules:
- Work from a directory outside the Agent Reach source repository.
- Prefer PowerShell commands on Windows.
- Use the globally installed `agent-reach` command from PATH.
- Do not copy `.codex-plugin`, `.mcp.json`, `agent_reach/skill`, or Agent Reach source files into the downstream test directory.
- Do not rank, summarize, or judge source quality inside Agent Reach. Only inspect returned JSON envelopes and report what was collected.
- Keep external API usage bounded: use `--limit 1` to `--limit 3` for live collection.
- Save raw collection envelopes to `.agent-reach/evidence.jsonl` for at least four successful live collection commands.
- If an optional channel is not configured or a backend command is missing, capture the JSON error envelope and classify it as an expected readiness issue instead of silently skipping it.
- Treat `doctor --json` as core-blocking by default. Do not fail solely because optional setup gaps appear under `summary.advisory_not_ready`.
- Redact any tokens, cookies, or local secrets if they appear in command output.

Setup:
1. Create and enter a clean external test directory, for example:
   `New-Item -ItemType Directory -Force C:\agent-reach-external-smoke | Out-Null; Set-Location C:\agent-reach-external-smoke`
2. Record:
   - `Get-Location`
   - `Get-Command agent-reach`
   - `agent-reach version`
   - `agent-reach --version`
3. If `rdt` is missing and `uv` is available, install Reddit's optional backend with:
   `uv tool install rdt-cli`
   Then record `Get-Command rdt` or the failure.

Registry and readiness checks:
1. Run `agent-reach channels --json > channels.json`.
2. Parse `channels.json` and verify that all of these channel names are present:
   `web`, `exa_search`, `github`, `hatena_bookmark`, `bluesky`, `qiita`, `youtube`, `rss`, `searxng`, `crawl4ai`, `hacker_news`, `mcp_registry`, `reddit`, `twitter`.
3. For each of these contracts, report the exact fields:
   - `reddit`: `auth_kind`, `entrypoint_kind`, `required_commands`, `operations`, first two `install_hints`.
   - `hacker_news`: `auth_kind`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`.
   - `mcp_registry`: `auth_kind`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`.
   - `searxng`: `auth_kind`, `operations`, first two `install_hints`.
   - `crawl4ai`: `operations`, `supports_probe`, `probe_operations`, `probe_coverage`, and the `crawl` option named `query`.
   - `qiita`: the `body_mode` option for search.
4. Run `agent-reach doctor --json > doctor.json`.
   Record the exit code and verify `doctor.json.summary.exit_policy`, `doctor.json.summary.exit_code`, `doctor.json.summary.blocking_not_ready`, and `doctor.json.summary.advisory_not_ready`.
5. Run `agent-reach export-integration --client codex --format json > export-integration.json`.
6. Parse `export-integration.json` and verify:
   - `external_project_usage.copy_files_required` is `false`.
   - `external_project_usage.preferred_interface` is `agent-reach collect --json`.
   - `channels` contains the same expected names as `channels.json`.
   - `required_commands` includes `rdt` if the Reddit channel contract declares it.
   - `verification_commands` includes at least one `hacker_news` or `mcp_registry` collect command.

Live collection evidence:
Run the commands below. For every command, capture exit code and JSON output. For successful commands, append with `--save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id <short-id> --source-role <role>`. If a command fails, keep the full error envelope.

Required live success targets:
1. Web:
   `agent-reach collect --channel web --operation read --input "https://example.com" --limit 1 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id web-example --source-role page_anchor`
2. Hacker News:
   `agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id hn-agent-frameworks --source-role forum_discovery`
3. MCP Registry:
   `agent-reach collect --channel mcp_registry --operation search --input "mcp" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id mcp-registry --source-role registry_anchor`
4. Qiita:
   `agent-reach collect --channel qiita --operation search --input "Python" --limit 3 --body-mode snippet --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id qiita-python --source-role article_discovery`
5. Reddit, if `rdt` is available after setup:
   `agent-reach collect --channel reddit --operation search --input "agent frameworks" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id reddit-agent-frameworks --source-role forum_discovery`
6. RSS:
   `agent-reach collect --channel rss --operation read --input "https://hnrss.org/frontpage" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id rss-hn-frontpage --source-role feed_discovery`
7. Bluesky:
   `agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-smoke-2026-04-11 --intent external_smoke --query-id bluesky-openai --source-role social_discovery`

Optional readiness/error targets:
1. SearXNG:
   - If `SEARXNG_BASE_URL` or config is available, run a live search with `--limit 3`.
   - If not configured, run:
     `agent-reach collect --channel searxng --operation search --input "agent tools" --limit 3 --json`
     and report the `missing_configuration` error envelope.
2. Crawl4AI:
   - If the optional extra and browser runtime are available, run:
     `agent-reach collect --channel crawl4ai --operation read --input "https://example.com" --limit 1 --json`
   - Otherwise run the same command and report the `missing_dependency` or runtime error envelope.
3. Twitter/X:
   - Do not configure new cookies.
   - If `doctor.json` says Twitter/X is ready, run one small search.
   - If Twitter/X is `warn` with `usability_hint=authenticated_but_unprobed`, run one small search and report that operation readiness was unverified.
   - Otherwise report the readiness status and skip live Twitter collection.

Ledger and candidate checks:
1. Confirm `.agent-reach/evidence.jsonl` exists and count its lines.
2. Run:
   `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json > ledger-validate.json`
3. Run:
   `agent-reach plan candidates --input .agent-reach/evidence.jsonl --summary-only --json > candidates-summary.json`
4. Run:
   `agent-reach plan candidates --input .agent-reach/evidence.jsonl --fields id,title,url,source,intent,query_id,source_role --json > candidates-fields.json`
5. Report ledger validation, candidate counts, and include two sample candidates if present.

Evidence output format:
Return a structured report with these sections:
1. Environment:
   - working directory
   - `agent-reach` executable path
   - Agent Reach version
   - whether `rdt` was installed or already present
2. Registry contract proof:
   - expected channel presence table
   - exact contract details for `reddit`, `hacker_news`, `mcp_registry`, `searxng`, `crawl4ai`, and `qiita`
3. Readiness proof:
   - doctor summary
   - `summary.exit_policy`, `summary.exit_code`, `summary.blocking_not_ready`, and `summary.advisory_not_ready`
   - any non-ready optional channels with exact status and message
4. Live collection proof:
   For each command, include:
   - command
   - exit code
   - `ok`
   - `channel`
   - `operation`
   - `meta.input`
   - item count
   - first one or two items with exact `id`, `kind`, `title`, `url`, `source`, `published_at`, and `extras.source_hints` when present
   - for failures, exact `error.code`, `error.message`, and relevant `meta`
5. Ledger proof:
   - evidence JSONL path
   - line count
   - ledger validation result
   - candidates summary
   - two candidate samples if present
6. Problems found:
   - stale installed CLI or skill
   - missing channel contract
   - command not found
   - setup/config confusion
   - live collection zero items
   - JSON parse failures
   - error messages that do not clearly explain the next action
   - docs or integration export text that points to old channels or old auth routes
7. Improvement recommendations for Agent Reach:
   - group each recommendation as `install`, `docs`, `channel_contract`, `adapter`, `doctor`, `ledger`, or `external_integration`
   - include the exact command or JSON field that motivated it
   - distinguish blocker, high, medium, and low severity

Pass/fail criteria:
- Fail if `agent-reach channels --json` does not include `hacker_news`, `mcp_registry`, and `reddit`.
- Fail if `reddit` still advertises Reddit OAuth, client ID/secret, or User-Agent configuration.
- Fail if fewer than four live collection commands return `ok: true` with non-empty `items`.
- Fail if `.agent-reach/evidence.jsonl` is not created or candidate planning cannot read it.
- Fail if `ledger validate` cannot parse the saved evidence ledger.
- Warn, but do not fail, if `searxng`, `crawl4ai`, or Twitter/X are not configured.
- Warn, but do not fail, if a public live source returns zero items while the JSON envelope is otherwise valid.
```
