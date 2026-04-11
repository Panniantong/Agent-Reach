# Agent Reach External Mixed Collection Prompt

Use this prompt in a separate Codex session or downstream repository after installing the latest Agent Reach CLI and skill.

```text
You are running an evidence-heavy external integration and mixed-collection test for Agent Reach from outside its source repository. Treat Agent Reach as an external CLI capability layer. Do not inspect, import, or edit the Agent Reach source checkout unless the test explicitly discovers that the installed CLI is stale and you are asked to diagnose installation.

Goal:
1. Verify that the externally installed `agent-reach` CLI, installed Codex skill, channel registry, readiness diagnostics, and integration export are current.
2. Verify whether Twitter/X and YouTube are usable research surfaces from the current machine.
3. Prove whether Agent Reach can collect media-bearing evidence such as post-level media references, video metadata, subtitle availability, thumbnails, or other linked media fields, even if it does not download or analyze the binary assets themselves.
4. Collect a broader mixed-source snapshot across developer, registry, social, forum, feed, page, and video surfaces without turning Agent Reach into a policy engine.
5. Produce machine-readable artifacts plus a structured list of problems and improvement recommendations for Agent Reach.

Hard rules:
- Work from a directory outside the Agent Reach source repository.
- Prefer PowerShell commands on Windows.
- Use the globally installed `agent-reach` command from PATH.
- Do not copy `.codex-plugin`, `.mcp.json`, `agent_reach/skill`, or Agent Reach source files into the downstream test directory.
- Keep API usage bounded. Prefer `--limit 1` to `--limit 3`, except `twitter user_posts` may use `--limit 5`.
- Save every live `collect --json` result to `live-results/<short-name>.json`.
- Save raw collection envelopes to `.agent-reach/evidence.jsonl` for every successful live collection command that returns non-empty `items`.
- If an optional channel is not configured or a backend command is missing, capture the JSON error envelope and classify it as an expected readiness issue instead of silently skipping it.
- Do not create new Twitter/X cookies or new API credentials during this run.
- You may install `rdt-cli` if missing and `uv` is available, because Reddit is intentionally no-auth in this fork.
- Redact any tokens, cookies, or local secrets if they appear in command output.
- Treat `doctor --json` exit code carefully. With the default core policy, optional gaps should appear under `summary.advisory_not_ready`; use the JSON summary as the source of truth.

Setup:
1. Create and enter a clean external test directory, for example:
   `New-Item -ItemType Directory -Force C:\agent-reach-external-mixed | Out-Null; Set-Location C:\agent-reach-external-mixed`
2. Create output folders:
   `New-Item -ItemType Directory -Force live-results,.agent-reach | Out-Null`
3. Record:
   - `Get-Location`
   - `Get-Command agent-reach`
   - `agent-reach version`
   - `agent-reach --version`
   - `Test-Path "$HOME\.codex\skills\agent-reach\SKILL.md"`
4. If `rdt` is missing and `uv` is available, install Reddit's optional backend:
   `uv tool install rdt-cli`
   Then record `Get-Command rdt` or the failure.
5. Do not install or configure Twitter/X cookies, YouTube runtimes, SearXNG instances, or Crawl4AI during this run. The point is to test what an external user sees from the current machine state.

Registry and readiness checks:
1. Run `agent-reach channels --json > channels.json`.
2. Run `agent-reach doctor --json > doctor.json` and record the exit code.
3. Run `agent-reach export-integration --client codex --format json > export-integration.json`.
4. Parse `channels.json` and verify that all of these channel names are present:
   `web`, `exa_search`, `github`, `hatena_bookmark`, `bluesky`, `qiita`, `youtube`, `rss`, `searxng`, `crawl4ai`, `hacker_news`, `mcp_registry`, `reddit`, `twitter`.
5. For these contracts, report the exact fields:
   - `twitter`: `auth_kind`, `entrypoint_kind`, `required_commands`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`, first two `install_hints`
   - `youtube`: `auth_kind`, `entrypoint_kind`, `required_commands`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`, first two `install_hints`
   - `reddit`: `auth_kind`, `entrypoint_kind`, `required_commands`, `operations`, first two `install_hints`
   - `hacker_news`: `auth_kind`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`
   - `mcp_registry`: `auth_kind`, `operations`, `supports_probe`, `probe_operations`, `probe_coverage`
   - `qiita`: the `body_mode` option for search
6. Parse `doctor.json` and report:
   - top-level summary
   - `summary.exit_policy`
   - `summary.exit_code`
   - `summary.blocking_not_ready`
   - `summary.advisory_not_ready`
   - exact status and message for `twitter`, `youtube`, `reddit`, `searxng`, `crawl4ai`, `github`, and `exa_search`
   - if present, `operation_statuses`, `probed_operations`, `unprobed_operations`, and `probe_run_coverage` for `twitter`
7. Parse `export-integration.json` and verify:
   - `external_project_usage.copy_files_required` is `false`
   - `external_project_usage.preferred_interface` is `agent-reach collect --json`
   - `channels` contains the same expected names as `channels.json`
   - `required_commands` includes `rdt` if the Reddit contract declares it
   - `verification_commands` includes at least one `web`, one `hacker_news` or `mcp_registry`, and one `doctor --json`

Required baseline live collection targets:
Run the commands below. For every command, save stdout JSON to `live-results/<short-name>.json`, record the exit code, and keep the exact command text in the final report.

1. Web page anchor:
   `agent-reach collect --channel web --operation read --input "https://example.com" --limit 1 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id web-example --source-role page_anchor > live-results/web-example.json`
2. Hacker News forum discovery:
   `agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id hn-agent-frameworks --source-role forum_discovery > live-results/hn-agent-frameworks.json`
3. MCP Registry anchor:
   `agent-reach collect --channel mcp_registry --operation search --input "mcp" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id mcp-registry --source-role registry_anchor > live-results/mcp-registry.json`
4. Qiita article discovery:
   `agent-reach collect --channel qiita --operation search --input "Python" --limit 3 --body-mode snippet --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id qiita-python --source-role article_discovery > live-results/qiita-python.json`
5. RSS feed discovery:
   `agent-reach collect --channel rss --operation read --input "https://hnrss.org/frontpage" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id rss-hn-frontpage --source-role feed_discovery > live-results/rss-hn-frontpage.json`
6. Bluesky social discovery:
   `agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id bluesky-openai --source-role social_discovery > live-results/bluesky-openai.json`
7. Hatena Bookmark reactions:
   `agent-reach collect --channel hatena_bookmark --operation read --input "https://example.com" --limit 2 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id hatena-example --source-role reaction_anchor > live-results/hatena-example.json`
8. Reddit forum discovery, if `rdt` is available after setup:
   `agent-reach collect --channel reddit --operation search --input "agent frameworks" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id reddit-agent-frameworks --source-role forum_discovery > live-results/reddit-agent-frameworks.json`
   If `rdt` is still unavailable, report that as a setup issue.

Conditional live collection targets:
Run these only when the readiness state or current machine setup makes sense. If they are not ready, capture the JSON error envelope or doctor status and classify it clearly instead of hand-waving.

1. Twitter/X media-heavy check:
   - If `doctor.json` shows Twitter/X ready, run:
     `agent-reach collect --channel twitter --operation search --input "from:openai has:media type:photos" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id twitter-openai-media --source-role social_media_discovery > live-results/twitter-openai-media.json`
   - Also run:
     `agent-reach collect --channel twitter --operation user_posts --input "openai" --limit 5 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id twitter-openai-posts --source-role account_activity > live-results/twitter-openai-posts.json`
   - If Twitter/X is `warn` with `usability_hint=authenticated_but_unprobed`, run one tiny collect and report that readiness was unprobed:
     `agent-reach collect --channel twitter --operation search --input "OpenAI" --limit 1 --json > live-results/twitter-openai-unprobed.json`
   - If Twitter/X is not ready, do not create new cookies. Instead, report the exact readiness status/message and, if useful, one error envelope from:
     `agent-reach collect --channel twitter --operation search --input "OpenAI" --limit 1 --json > live-results/twitter-openai-error.json`
2. YouTube video capability check:
   - If `doctor.json` shows YouTube ready, run:
     `agent-reach collect --channel youtube --operation read --input "https://www.youtube.com/watch?v=jNQXAC9IVRw" --limit 1 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id youtube-capability --source-role video_anchor > live-results/youtube-capability.json`
   - If YouTube is not ready, run the same command once without `--save`, capture the JSON error envelope, and report the exact readiness status/message.
3. GitHub developer anchor:
   - If GitHub is ready, run:
     `agent-reach collect --channel github --operation read --input "openai/openai-python" --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id github-openai-python --source-role repo_anchor > live-results/github-openai-python.json`
   - Otherwise report the exact readiness status/message from `doctor.json`.
4. Exa discovery:
   - If Exa is ready, run:
     `agent-reach collect --channel exa_search --operation search --input "agent reach" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id exa-agent-reach --source-role broad_discovery > live-results/exa-agent-reach.json`
   - Otherwise report the exact readiness status/message from `doctor.json`.
5. SearXNG and Crawl4AI:
   - If ready, run one small live request each.
   - If not ready, run one command each and report the error envelope:
     `agent-reach collect --channel searxng --operation search --input "agent tools" --limit 3 --json > live-results/searxng-agent-tools.json`
     `agent-reach collect --channel crawl4ai --operation read --input "https://example.com" --limit 1 --json > live-results/crawl4ai-example.json`

Cross-source follow-up:
1. From one successful discovery result in Hacker News, Reddit, RSS, Bluesky, Exa, or SearXNG, choose one non-platform URL that looks like a normal web page.
2. Read that URL through:
   `agent-reach collect --channel web --operation read --input "<chosen-url>" --limit 1 --json --save .agent-reach/evidence.jsonl --run-id external-mixed-2026-04-11 --intent external_mixed --query-id web-followup --source-role followup_read > live-results/web-followup.json`
3. In the report, explain exactly which earlier command produced the URL and why it was chosen as the follow-up deep read.

Candidate and ledger checks:
1. Confirm `.agent-reach/evidence.jsonl` exists and count its lines.
2. Run:
   `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json > ledger-validate.json`
3. Run:
   `agent-reach plan candidates --input .agent-reach/evidence.jsonl --summary-only --json > candidates-summary.json`
4. Run:
   `agent-reach plan candidates --input .agent-reach/evidence.jsonl --fields id,title,url,source,intent,query_id,source_role --json > candidates-fields.json`
5. Report:
   - evidence line count
   - ledger validation result
   - collection result count
   - item count seen
   - candidate count
   - at least three sample candidates from different sources if available

Media capability proof requirements:
You must explicitly answer these questions with evidence from the saved JSON files:
1. Can Twitter/X return post-level media references through Agent Reach on this machine?
   - If yes, quote the exact `extras.media` and `extras.media_references` shape for one item when present.
   - If no, explain whether the reason was readiness, auth, zero results, or missing media fields.
2. Can YouTube return enough metadata to treat a video page as a research object?
   - Report exact `id`, `kind`, `title`, `url`, `published_at`, `extras.duration_seconds`, and `extras.subtitle_languages`.
   - Report normalized `extras.thumbnail_url`, `extras.thumbnail_count`, `extras.automatic_caption_languages`, `extras.has_subtitles`, `extras.has_automatic_captions`, `extras.requested_subtitle_languages`, and `extras.source_hints`.
   - Also report whether the raw payload exposed fields such as `thumbnail`, `subtitles`, or related caption metadata.
3. Did any other channel expose image/video-like evidence?
   - Check at least Bluesky `extras.media`, normalized `extras.media_references`, Hatena screenshot-related fields, or any other obvious media references in saved payloads.

Evidence output format:
Return a structured report with these sections:
1. Environment
   - working directory
   - `agent-reach` executable path
   - Agent Reach version
   - installed skill presence
   - whether `rdt` was already present or installed during setup
2. Registry contract proof
   - expected channel presence table
   - exact contract details for `twitter`, `youtube`, `reddit`, `hacker_news`, `mcp_registry`, and `qiita`
3. Readiness proof
   - `doctor --json` exit code
   - doctor summary
   - `summary.exit_policy`, `summary.exit_code`, `summary.blocking_not_ready`, and `summary.advisory_not_ready`
   - exact statuses/messages for `twitter`, `youtube`, `reddit`, `searxng`, `crawl4ai`, `github`, and `exa_search`
4. Live collection proof
   For each attempted command, include:
   - command
   - output file path
   - exit code
   - `ok`
   - `channel`
   - `operation`
   - `meta.input`
   - item count
   - first one or two items with exact `id`, `kind`, `title`, `url`, `source`, `published_at`, and `extras.source_hints` when present
   - for failures, exact `error.code`, `error.message`, and relevant `meta`
5. Media capability proof
   - explicit answer for Twitter/X media
   - explicit answer for YouTube video metadata/subtitles
   - explicit answer for any other media-like evidence from other channels
6. Cross-source follow-up proof
   - source command that produced the chosen URL
   - chosen URL
   - follow-up `web read` result summary
7. Ledger proof
   - evidence JSONL path
   - line count
   - candidates summary
   - three candidate samples from different sources if available
8. Problems found
   - stale installed CLI or skill
   - missing channel contract
   - command not found
   - readiness or setup confusion
   - live collection zero items
   - JSON parse failures
   - machine-readable fields that are inconsistent across channels
   - error messages that do not clearly explain the next action
   - anything that makes downstream automation or evidence review harder
9. Improvement recommendations for Agent Reach
   - group each recommendation as `install`, `docs`, `channel_contract`, `adapter`, `doctor`, `ledger`, `external_integration`, or `media_support`
   - include the exact command, saved JSON path, or field that motivated it
   - distinguish `blocker`, `high`, `medium`, and `low`

Pass/fail criteria:
- Fail if `agent-reach channels --json` does not include `twitter`, `youtube`, `hacker_news`, `mcp_registry`, and `reddit`.
- Fail if `reddit` still advertises Reddit OAuth, client ID/secret, or User-Agent configuration.
- Fail if fewer than six live collection commands return `ok: true` with non-empty `items`.
- Fail if `.agent-reach/evidence.jsonl` is not created or `plan candidates` cannot read it.
- Fail if the installed CLI or skill is clearly stale relative to the exported channel contract.
- Warn, but do not fail, if Twitter/X, YouTube, Exa, SearXNG, GitHub, or Crawl4AI are not ready on this machine.
- Warn, but do not fail, if a valid JSON envelope returns zero items for a public source.
- Warn, but do not fail, if Twitter/X or YouTube cannot prove media-bearing evidence because readiness is missing.
```
