# Agent Reach External Large-Scale Research Prompt

Suggested theme: **Browser-use, web extraction, crawling, search, and MCP research tooling for AI agents in 2025-2026**

Why this theme is a good external stress test:

- It naturally spans repository, registry, article, forum, social, feed, page, and video evidence.
- It benefits from the current `channels --json` operation contracts, probe coverage fields, media-reference normalization, and pagination/window controls.
- It creates room for `batch`, `ledger merge`, `ledger validate`, `plan candidates`, follow-up reads, and external audit artifacts to all matter in one run.
- It is broad enough to surface next development ideas for Agent Reach without forcing a fixed research route.

Use this prompt in a separate Codex session or downstream repository after installing the latest Agent Reach CLI and skill.

```text
You are running a large-scale external research exercise for Agent Reach from outside its source repository. Treat Agent Reach as an external CLI capability layer. Do not inspect, import, or edit the Agent Reach source checkout unless the run explicitly discovers that the installed CLI or installed skill is stale and you are asked to diagnose installation.

Theme:
Investigate the 2025-2026 ecosystem around browser-use, web extraction, crawling, search, and MCP-enabled research tooling for AI agents.

This run is both:
1. a real mixed-source research task on the theme above, and
2. an external integration test for Agent Reach's capability-layer design.

Agent Reach rules:
- Agent Reach does not own routing, ranking, summarization, posting, or fixed source policy.
- You must choose channels, query wording, pagination/window controls, and deep-read targets yourself based on the live `channels --json` contract, readiness, and intermediate evidence.
- Do not turn Agent Reach into a fixed pipeline. Use it as a bounded, read-only collection substrate.
- Treat `extras.source_hints`, `extras.media_references`, `meta.pagination`, doctor probe fields, and ledger diagnostics as machine-readable evidence about collection shape. They are not relevance scores or trust scores.

Primary goals:
1. Prove that the installed `agent-reach` CLI and installed skill are current enough for broad external research.
2. Use the live channel contract and readiness diagnostics to build a dynamic, theme-aware research plan.
3. Run a large, evidence-heavy mixed-source investigation with auditable ledgers and candidate plans.
4. Exercise and evaluate:
   - `channels --json`
   - `doctor --json`
   - `doctor --json --probe`
   - `export-integration --client codex --format json`
   - `batch`
   - `ledger merge`
   - `ledger validate`
   - `plan candidates --summary-only --json`
   - `plan candidates --fields ... --json`
   - `collect --save`
   - per-channel options such as `body_mode`, `page_size`, `max_pages`, `cursor`, `page`, `since`, and `until` when supported
5. Produce a final research report plus concrete next development ideas for Agent Reach.

Hard rules:
- Work from a directory outside the Agent Reach source repository.
- Prefer PowerShell commands on Windows.
- Use the globally installed `agent-reach` command from PATH.
- Do not copy `.codex-plugin`, `.mcp.json`, `agent_reach/skill`, or Agent Reach source files into the downstream research directory.
- Keep everything read-only with respect to external sources. Do not post, mutate, or log in to new services during this run.
- Do not create new Twitter/X cookies, new API credentials, new SearXNG instances, or new hosted services during this run.
- If `rdt` is missing and `uv` is available, you may install `rdt-cli`, because Reddit is intentionally no-auth in this fork.
- If optional channels are not configured or not installed, record the JSON error envelope or doctor status and classify it clearly instead of silently skipping them.
- Save machine-readable artifacts at every stage.
- Redact tokens, cookies, or local secrets if they appear anywhere in captured output.
- Prefer bounded collection. Use large scale through many bounded queries and selective expansion, not one uncontrolled fetch.

PowerShell file-capture guidance:
- If you are on Windows PowerShell 5.1, prefer UTF-8-safe capture such as:
  - `agent-reach channels --json | Out-File -Encoding utf8 artifacts/channels.json`
  - `agent-reach doctor --json | Out-File -Encoding utf8 artifacts/doctor.json`
  - `Get-Content -Encoding UTF8 .agent-reach/evidence.jsonl`
- Avoid assuming plain `>` is always the safest way to persist JSON artifacts on Windows.

Research expectations:
- Build the route dynamically from the live channel contract and the theme. Do not blindly use every channel.
- Use multiple evidence roles such as:
  - `official_docs`
  - `repo_discovery`
  - `registry_discovery`
  - `article_discovery`
  - `forum_discovery`
  - `social_discovery`
  - `feed_discovery`
  - `video_anchor`
  - `followup_read`
  - `maintainer_signal`
  - `community_signal`
- Use `intent`, `query_id`, and `source_role` consistently so the ledger is easy to audit later.
- Prefer official docs, maintainer-owned repos, registries, and direct product pages as anchors.
- Treat social and forum sources as signal, not authority.
- Include at least one Japanese-language branch if a relevant ready source exists, such as Qiita or Hatena-adjacent URLs.

Theme framing guidance:
You are researching questions such as:
- Which tools, repos, registries, APIs, videos, and community discussions matter most for AI-agent browser-use and web research?
- Which projects or server types appear repeatedly across multiple source classes?
- Where do MCP servers, search APIs, browser-control tools, and crawling/extraction tools meet or overlap?
- Which sources look official or maintainer-adjacent, and which are commentary only?
- What evidence exists in Japanese-language developer sources?
- What demos, screenshots, thumbnails, subtitle metadata, or other linked media appear in evidence?
- What unanswered questions or conflicting signals remain?

Suggested seed vocabulary:
Use these only as a starting pool. You must adapt them based on intermediate results.
- English:
  - `browser use ai agents`
  - `browser automation for agents`
  - `web extraction for llm agents`
  - `agent web crawling`
  - `agent research tooling`
  - `mcp browser`
  - `mcp search`
  - `mcp crawler`
  - `crawl4ai`
  - `firecrawl`
  - `browser-use`
  - `playwright agents`
- Japanese:
  - `AIエージェント ブラウザ操作`
  - `AIエージェント Web抽出`
  - `AIエージェント クローリング`
  - `MCP ブラウザ`
  - `MCP 検索`
  - `LLM スクレイピング`
  - `AIエージェント 調査ツール`

Setup:
1. Create and enter a clean external directory, for example:
   `New-Item -ItemType Directory -Force C:\agent-reach-external-large-scale | Out-Null; Set-Location C:\agent-reach-external-large-scale`
2. Create output directories:
   `New-Item -ItemType Directory -Force artifacts,live-results,deep-reads,.agent-reach,.agent-reach\runs | Out-Null`
3. Record:
   - `Get-Location`
   - `Get-Command agent-reach`
   - `agent-reach version`
   - `agent-reach --version`
   - `Test-Path "$HOME\.codex\skills\agent-reach\SKILL.md"`
4. If `rdt` is missing and `uv` is available, run:
   `uv tool install rdt-cli`
   Then record `Get-Command rdt` or the failure.
5. Save:
   - `agent-reach channels --json | Out-File -Encoding utf8 artifacts/channels.json`
   - `agent-reach doctor --json | Out-File -Encoding utf8 artifacts/doctor.json`
   - `agent-reach doctor --json --probe | Out-File -Encoding utf8 artifacts/doctor-probe.json`
   - `agent-reach export-integration --client codex --format json | Out-File -Encoding utf8 artifacts/export-integration.json`

Contract and readiness proof:
1. Parse `artifacts/channels.json` and verify that these channel names exist:
   `web`, `exa_search`, `github`, `hatena_bookmark`, `bluesky`, `qiita`, `youtube`, `rss`, `searxng`, `crawl4ai`, `hacker_news`, `mcp_registry`, `reddit`, `twitter`
2. Report exact contract details for:
   - `github`: search options `page_size`, `max_pages`, `page`
   - `bluesky`: search options `page_size`, `max_pages`, `cursor`
   - `qiita`: search options `body_mode`, `page_size`, `max_pages`, `page`
   - `twitter`: search options `since`, `until`, plus `supports_probe`, `probe_operations`, `probe_coverage`
   - `youtube`: `operations`, `supports_probe`, `probe_operations`, `probe_coverage`
   - `reddit`: auth contract and install hints proving no Reddit OAuth is required
   - `hacker_news`: `operations`, `supports_probe`, `probe_operations`, `probe_coverage`
   - `mcp_registry`: `operations`, `supports_probe`, `probe_operations`, `probe_coverage`
   - `crawl4ai`: `operations`, probe support, and the `crawl` option named `query`
3. From `artifacts/doctor.json` and `artifacts/doctor-probe.json`, report:
   - summary
   - `summary.exit_policy`
   - `summary.exit_code`
   - `summary.blocking_not_ready`
   - `summary.advisory_not_ready`
   - exact statuses and messages for `github`, `qiita`, `bluesky`, `youtube`, `reddit`, `twitter`, `searxng`, and `crawl4ai`
   - if present, `operation_statuses`, `probed_operations`, `unprobed_operations`, and `probe_run_coverage` for `twitter`
4. From `artifacts/export-integration.json`, verify:
   - `external_project_usage.copy_files_required` is `false`
   - `external_project_usage.preferred_interface` is `agent-reach collect --json`
   - `channels` contains the same expected names
   - `verification_commands` still make sense for the current contract

Execution model:
You must work in four phases and save artifacts after each phase.

Phase 1: Pilot plan
1. Build `artifacts/pilot-plan.json` yourself. Do not use a fixed route.
2. First define 4 to 7 sub-questions for the theme, for example:
   - official and maintainer-owned anchors
   - browser-control or browser-use tooling
   - crawling and extraction tooling
   - MCP registry and MCP server overlap
   - Japanese-language community evidence
   - social/forum trend signals
   - demos or video explainers
3. The pilot plan should:
   - include 8 to 16 bounded queries
   - cover at least 5 evidence roles if the current machine readiness allows it
   - use at least 4 distinct channels if the current machine readiness allows it
   - include at least one Japanese-language or Japan-community query when a relevant channel is ready
   - keep every query auditable with `intent`, `query_id`, and `source_role`
4. When a channel contract supports them, use bounded pagination/window controls:
   - `page_size`
   - `max_pages`
   - `cursor`
   - `page`
   - `since`
   - `until`
5. For high-volume text search, prefer `body_mode=snippet` or `body_mode=none` instead of full text.
6. Do not use every ready channel just because it exists. Choose channels because they fit a sub-question or evidence role.
7. Use a batch plan shape like:

   ```json
   {
     "run_id": "external-large-scale-2026-04-11",
     "quality_profile": "precision",
     "failure_policy": "partial",
     "queries": [
       {
         "query_id": "github-browser-tools",
         "channel": "github",
         "operation": "search",
         "input": "browser use ai agents",
         "limit": 10,
         "page_size": 5,
         "max_pages": 2,
         "intent": "oss_candidates",
         "source_role": "repo_discovery"
       }
     ]
   }
   ```
8. Run:
   `agent-reach batch --plan artifacts/pilot-plan.json --save-dir .agent-reach/runs --shard-by channel-operation --checkpoint-every 5 --json | Out-File -Encoding utf8 artifacts/pilot-batch.json`

Phase 2: Pilot audit
1. Merge and validate the pilot ledger:
   - `agent-reach ledger merge --input .agent-reach/runs --output .agent-reach/pilot-evidence.jsonl --json | Out-File -Encoding utf8 artifacts/pilot-merge.json`
   - `agent-reach ledger validate --input .agent-reach/pilot-evidence.jsonl --json | Out-File -Encoding utf8 artifacts/pilot-validate.json`
2. Build pilot candidate views:
   - `agent-reach plan candidates --input .agent-reach/pilot-evidence.jsonl --summary-only --json | Out-File -Encoding utf8 artifacts/pilot-candidates-summary.json`
   - `agent-reach plan candidates --input .agent-reach/pilot-evidence.jsonl --fields id,title,url,source,intent,query_id,source_role --json | Out-File -Encoding utf8 artifacts/pilot-candidates-fields.json`
3. Perform a relevance audit:
   - identify which channels and queries produced high-signal candidates
   - identify noise, duplication, zero-result paths, weak source roles, or readiness-limited branches
   - decide what to expand, what to stop, and what to deep-read
4. Save your audit decisions as:
   - `artifacts/pilot-audit.md`
   - `artifacts/pilot-audit.json`

Phase 3: Expansion plan
1. Build `artifacts/expansion-plan.json` based on the pilot audit.
2. The expansion plan should:
   - expand only promising branches
   - avoid channels that proved noisy or irrelevant
   - use more pagination/window controls where supported and useful
   - add direct reads for high-signal known resources such as specific repos, registry entries, pages, videos, or threads
   - stay bounded; do not create an uncontrolled crawl
3. Run:
   `agent-reach batch --plan artifacts/expansion-plan.json --save-dir .agent-reach/runs --shard-by channel-operation --resume --checkpoint-every 5 --json | Out-File -Encoding utf8 artifacts/expansion-batch.json`
4. Merge the full sharded ledger:
   - `agent-reach ledger merge --input .agent-reach/runs --output .agent-reach/evidence.jsonl --json | Out-File -Encoding utf8 artifacts/final-merge.json`
   - `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json | Out-File -Encoding utf8 artifacts/final-validate.json`
5. Build final candidate views:
   - `agent-reach plan candidates --input .agent-reach/evidence.jsonl --summary-only --json | Out-File -Encoding utf8 artifacts/final-candidates-summary.json`
   - `agent-reach plan candidates --input .agent-reach/evidence.jsonl --fields id,title,url,source,intent,query_id,source_role,extras --json | Out-File -Encoding utf8 artifacts/final-candidates-fields.json`

Phase 4: Deep reads and media proof
1. Select 8 to 15 high-signal follow-up targets from the final candidates, depending on evidence quality and time.
2. Mix these follow-up types when available:
   - `web read` for normal external pages
   - `github read` for repos found in search
   - `mcp_registry read` for specific servers
   - `youtube read` for videos or demos
   - `reddit read` or `hacker_news read` for discussions worth inspecting
   - `hatena_bookmark read` for reaction context around an external page
3. Save every deep read to `live-results/` and append successful ones to `.agent-reach/evidence.jsonl`.
4. If you capture a successful JSON result without `--save`, append it later with:
   `agent-reach ledger append --input RESULT.json --output .agent-reach/evidence.jsonl --json`
5. Re-run:
   - `agent-reach ledger validate --input .agent-reach/evidence.jsonl --json | Out-File -Encoding utf8 artifacts/post-deep-validate.json`
   - `agent-reach plan candidates --input .agent-reach/evidence.jsonl --summary-only --json | Out-File -Encoding utf8 artifacts/post-deep-candidates-summary.json`

Required evidence properties:
You must try to produce all of the following, while respecting live readiness:
- official or maintainer-owned anchors
- OSS implementation evidence
- registry evidence
- community/forum evidence
- social evidence
- at least one feed or temporal evidence source
- at least one media-bearing or video-bearing source if available
- at least one Japanese-language or Japan-community branch if available

Required pagination/window proof:
You must execute at least two successful commands whose contracts use the new options, if the current machine has those channels ready. Good examples:
- GitHub search with `page_size`, `max_pages`, `page`
- Qiita search with `body_mode`, `page_size`, `max_pages`, `page`
- Bluesky search with `page_size`, `max_pages`, `cursor`
- Twitter search with `since`, `until`

For each successful pagination/window command, report the exact `meta.pagination` object and any relevant flat `meta` mirrors.

Required media proof:
You must explicitly answer:
1. Which channels returned useful media-like evidence such as:
   - `extras.media_references`
   - social `extras.media`
   - Hatena screenshot fields
   - YouTube thumbnails and subtitle/caption metadata
2. If YouTube is ready, can Agent Reach treat a video as a research object?
3. If Twitter/X is usable, did time-windowed or media-heavy search produce useful post-level evidence?
4. If a channel only partially succeeded, what did it still prove?

Required output artifacts:
At minimum, save:
- `artifacts/channels.json`
- `artifacts/doctor.json`
- `artifacts/doctor-probe.json`
- `artifacts/export-integration.json`
- `artifacts/pilot-plan.json`
- `artifacts/pilot-batch.json`
- `artifacts/pilot-merge.json`
- `artifacts/pilot-validate.json`
- `artifacts/pilot-candidates-summary.json`
- `artifacts/pilot-candidates-fields.json`
- `artifacts/pilot-audit.md`
- `artifacts/pilot-audit.json`
- `artifacts/expansion-plan.json`
- `artifacts/expansion-batch.json`
- `artifacts/final-merge.json`
- `artifacts/final-validate.json`
- `artifacts/final-candidates-summary.json`
- `artifacts/final-candidates-fields.json`
- `artifacts/post-deep-validate.json`
- `artifacts/post-deep-candidates-summary.json`
- `artifacts/final-summary.json`
- `artifacts/final-report.md`

Final report format:
Return a structured report with these sections:
1. Theme and why it was a good stress test for Agent Reach
2. Environment
   - working directory
   - `agent-reach` executable path
   - Agent Reach version
   - installed skill presence
   - whether `rdt` was already present or installed
3. Contract and readiness proof
   - expected channel presence
   - important operation contracts
   - doctor summary
   - probe summary
4. Pilot plan
   - sub-questions
   - why each source role was chosen
   - why some channels were skipped
5. Pilot results and audit
   - query counts
   - successful non-empty collections
   - pilot ledger validity
   - pilot candidate counts
   - what expanded and what stopped
6. Expansion results
   - additional query counts
   - final ledger validity
   - final candidate counts
   - high-signal source clusters
7. Deep reads
   - chosen targets
   - why they were chosen
   - what each one added beyond the search/discovery layer
8. Media and pagination proof
   - exact successful pagination/window examples with `meta.pagination`
   - exact media-bearing examples
9. Research findings
   - grouped by sub-question
   - distinguish official/primary evidence from community signal
   - explicitly list unresolved questions and conflicting signals
10. Problems found in Agent Reach
   - stale install or skill issues
   - contract gaps
   - readiness confusion
   - pagination edge cases
   - batch/ledger issues
   - candidate planning pain points
   - media evidence inconsistencies
   - anything that made external execution or audit harder
11. Next development ideas for Agent Reach
   - group by `channel_contract`, `adapter`, `doctor`, `ledger`, `batch`, `media_support`, `external_integration`, `docs`, or `install`
   - include concrete evidence from saved artifacts
   - rank as `blocker`, `high`, `medium`, or `low`
12. Artifact manifest
   - file path
   - short purpose

Final summary JSON:
Write `artifacts/final-summary.json` with fields such as:
- `theme`
- `overall_result`
- `ready_channels`
- `pilot_query_count`
- `expansion_query_count`
- `successful_nonempty_commands`
- `distinct_channels_used`
- `final_ledger_valid`
- `final_candidate_count`
- `paginated_commands`
- `media_evidence_channels`
- `japanese_branch_used`
- `issues`
- `recommendations`

Success / partial / fail rules:
- `success` if:
  - all registry/readiness/export artifacts parse correctly
  - final ledger validates
  - final candidate planning works
  - at least 12 successful non-empty collection commands were completed, unless live readiness makes that impossible
  - at least 5 distinct channels were used successfully, unless live readiness makes that impossible
  - at least 2 pagination/window examples succeeded
  - the final report includes actionable Agent Reach improvement ideas
- `partial` if:
  - core artifacts are valid and meaningful research was completed,
  - but optional readiness gaps, rate limits, or platform behavior prevented some intended evidence roles
- `fail` if:
  - the installed CLI or skill is clearly stale relative to the contract
  - `channels --json`, `doctor --json`, or `export-integration` cannot be used as machine-readable artifacts
  - the final ledger cannot be validated
  - `plan candidates` cannot read the final ledger
  - the run produces too little evidence to support the theme and no clear reason is documented

Important behavior reminders:
- Let the theme and intermediate evidence decide the route.
- Use Agent Reach's features aggressively, but do not force a fixed source path.
- Use downstream judgment for query refinement, expansion, and synthesis.
- Keep the final report grounded in saved evidence, not impressions.
```
