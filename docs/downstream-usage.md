# Downstream Usage

Agent Reach is designed to be used from other projects without copying this repository's files into them.

Use one of these integration modes:

- `agent-reach` CLI: best for Codex sessions, GitHub Actions, bots, and any project that can shell out to a stable JSON command.
- `AgentReachClient`: best when the host Python environment intentionally depends on Agent Reach as a package.
- Codex skill install: best for local Codex usage across many projects. The skill is installed once under the user's Codex home, not into each downstream repo.

## Codex Without Project Files

Install the tool and global skill once:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git
agent-reach skill --install
agent-reach version
agent-reach doctor --json --probe
```

`agent-reach skill --install` installs the bundled Codex skill suite: `agent-reach`, `agent-reach-shape-brief`, `agent-reach-orchestrate`, plus maintainer-only skills `agent-reach-maintain-proposals` and `agent-reach-maintain-release`.

When you need an exact build, pin a commit or ref instead of relying on upstream release tags:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git@<commit-or-ref>
agent-reach skill --install
agent-reach version
```

To refresh a global install to an exact pushed ref, use:

```powershell
uv tool install --force git+<remote-url>@<ref>
agent-reach skill --install
agent-reach version
```

After that, Codex can use Agent Reach from any project by calling the CLI:

```powershell
agent-reach collect --channel exa_search --operation search --input "latest AI agent frameworks" --limit 5 --json
agent-reach collect --channel web --operation read --input "https://example.com" --json
agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 5 --json
agent-reach collect --channel qiita --operation search --input "python user:Qiita" --limit 5 --json
agent-reach collect --channel qiita --operation search --input "python user:Qiita" --limit 6 --page-size 3 --max-pages 2 --body-mode snippet --json
agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 5 --json
agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 5 --json
```

When provenance matters, append each raw collection envelope to a JSONL ledger:

```powershell
agent-reach collect --channel exa_search --operation search --input "latest AI agent frameworks" --limit 5 --json --save .agent-reach/evidence.jsonl --run-id agent-frameworks --intent discovery --query-id exa-agent-frameworks --source-role web_search
agent-reach ledger validate --input .agent-reach/evidence.jsonl --require-metadata --json
agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json
agent-reach ledger query --input .agent-reach/evidence.jsonl --filter "channel == exa_search" --fields channel,query_id,source.file --json
agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json
```

This does not require `.codex-plugin`, `.mcp.json`, or `agent_reach/skills` files inside the downstream project.

`agent-reach check-update --json` compares this fork to upstream `Panniantong/Agent-Reach` releases. Treat it as upstream awareness, not as the source of truth for the latest fork commit.

Treat `extras.source_hints`, item-level `engagement`, `media_references`, neutral `identifiers`, `error.category`, and page extraction hygiene fields such as `text_length`, `link_count`, `image_count`, `link_density`, and `extraction_warning` as diagnostics only. They can help downstream code explain provenance or flag suspicious extraction shape, but they are not ranking, trust scoring, summarization, or publishing instructions. Inspect `agent-reach channels --json` `operation_contracts` before choosing per-channel controls such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`; Agent Reach does not choose those inputs for the caller. Social search responses may set `meta.diagnostics.unbounded_time_window` so the caller can notice missing time bounds. `collect --max-text-chars N` is only for human text-mode snippets and does not truncate `--json` output or saved ledgers. Use `--raw-mode minimal`, `--raw-mode none`, or `--raw-max-bytes N` when the caller wants smaller machine-readable artifacts.

If a conditional command was captured without `--save`, append it later with:

```powershell
agent-reach ledger append --input live-results/result.json --output .agent-reach/evidence.jsonl --run-id agent-frameworks --json
```

## Codex Operating Policy

When Codex is working inside an arbitrary project:

- Use the globally installed `agent-reach` CLI by default.
- Do not copy Agent Reach repo files into the project unless the user explicitly asks for repo-local plugin artifacts.
- Use `agent-reach-shape-brief` to normalize vague research asks when needed.
- Use `agent-reach-orchestrate` when the user wants to go from a rough ask to actual Agent Reach collection start in the same session.
- The bundled suite also includes maintainer-only skills for Agent Reach repo work: `agent-reach-maintain-proposals` and `agent-reach-maintain-release`.
- If delegation is available and explicitly allowed, use at most one intake-only subagent when ambiguity would materially change the research route.
- Agent Reach does not choose request scale, investigation routes, source mix, ranking, summarization, or posting.
- The caller chooses scope. Do not auto-escalate a lightweight request into large-scale research.
- Use `agent-reach collect --json` as the stable handoff to project code.
- Use `agent-reach schema collection-result --json` when a downstream project wants a contract-testable JSON Schema.
- Inspect `agent-reach channels --json` `operation_contracts` before choosing per-channel pagination or time-window options.
- Add `--save .agent-reach/evidence.jsonl` when the run needs an auditable evidence trail.
- Prefer `--run-id`, `--intent`, `--query-id`, and `--source-role` with saved ledgers; use `ledger validate --require-metadata --json` when metadata completeness should gate automation.
- Validate ledgers with `agent-reach ledger validate --json` before treating them as CI artifacts.
- Use `agent-reach ledger summarize --json` for channel, operation, intent, query, source-role, item, error, and metadata health counts.
- Use `agent-reach ledger query --json` for lightweight record filtering and field projection without leaving Agent Reach.
- Use `agent-reach plan candidates` for lightweight URL or ID dedupe before follow-up reads.
- Keep `agent-reach plan candidates` at the default `--limit 20` unless the caller explicitly wants a broader candidate set.
- Treat `batch` and `scout` as explicit opt-in helpers rather than the default route for everyday collection.
- Keep ranking, summarization, scheduling, Discord publishing, and state in the downstream project.
- Treat non-required channel failures as partial results unless the caller explicitly marked those channels required.

Large-scale research is explicit opt-in. When the caller asks for it, use bounded fan-out:

1. Start with 2-4 broad discovery queries at `--limit 5` to `--limit 10`.
2. Choose page, cursor, and time-window inputs from the live channel contract when a task needs bounded multi-page collection.
3. If a saved batch plan is involved, run `agent-reach batch --plan PLAN.json --validate-only --json` before any write-producing batch execution.
4. Save raw `CollectionResult` JSONL with `--save .agent-reach/evidence.jsonl`.
5. Run `agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json`.
6. Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json`.
7. Use specialist channels when the source is known.
8. Deep-read only selected URLs with `web`.
9. Persist raw ledgers and candidate plans as artifacts in CI when traceability matters.

## GitHub Actions

Use the composite action from this repository:

```yaml
jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - uses: iwachacha/Agent-Reach/.github/actions/setup-agent-reach@main
        with:
          install-twitter-cli: "false"
          install-reddit-cli: "false"
          install-ytdlp: "false"
          install-mcporter: "false"
      - name: Smoke test Agent Reach
        run: |
          agent-reach version
          agent-reach doctor --json
          agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 3 --json --save .agent-reach/evidence.jsonl --run-id smoke --intent discovery --query-id bluesky-openai --source-role social_search > agent-reach-results.json
          agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json > agent-reach-summary.json
          agent-reach plan candidates --input .agent-reach/evidence.jsonl --by normalized_url --limit 20 --json > agent-reach-candidates.json
```

Enable optional backends only when the workflow needs them:

```yaml
      - uses: iwachacha/Agent-Reach/.github/actions/setup-agent-reach@main
        with:
          install-twitter-cli: "true"
          install-reddit-cli: "true"
          install-ytdlp: "true"
          install-mcporter: "true"
          configure-exa: "true"
        env:
          TWITTER_AUTH_TOKEN: ${{ secrets.TWITTER_AUTH_TOKEN }}
          TWITTER_CT0: ${{ secrets.TWITTER_CT0 }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`install-reddit-cli` installs `rdt-cli` for the no-auth `reddit` channel. SearXNG needs an instance URL through `agent-reach configure searxng-base-url` or `SEARXNG_BASE_URL`. Crawl4AI needs `agent-reach[crawl4ai]` in the Python environment that performs browser-backed reads plus `python -m playwright install chromium`, so treat it as a separate job when a workflow needs it.

For reproducible automation, pin `uses:` to a tag or commit instead of `@main`.

## Discord Bot Pattern

For a Discord digest bot such as `ai-news`, keep scheduling, ranking, summarization, dedupe, state, and publishing in the bot project. Use Agent Reach only as the source collection layer.

Recommended collector shape:

```yaml
sources:
  - id: openai_bluesky
    type: agent_reach
    channel: bluesky
    operation: search
    input: OpenAI
    limit: 5
  - id: qiita_llm
    type: agent_reach
    channel: qiita
    operation: search
    input: "LLM user:Qiita"
    limit: 5
```

Recommended subprocess contract:

```python
import json
import subprocess


def collect_with_agent_reach(channel: str, operation: str, value: str, limit: int = 10) -> dict:
    result = subprocess.run(
        [
            "agent-reach",
            "collect",
            "--channel",
            channel,
            "--operation",
            operation,
            "--input",
            value,
            "--limit",
            str(limit),
            "--json",
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(result.stdout or "{}")
    if not payload.get("ok"):
        error = payload.get("error") or {}
        raise RuntimeError(f"agent-reach {channel}/{operation} failed: {error.get('code')}: {error.get('message')}")
    return payload
```

Map `payload["items"]` to the bot's normalized item type:

- `id` -> external item ID
- `title` -> digest title
- `url` -> link target
- `text` -> summary candidate or body snippet
- `author` -> source author
- `published_at` -> item timestamp
- `canonical_url` -> normalized URL for caller-selected dedupe
- `source_item_id` -> source-native item ID when available
- `engagement` -> raw source metrics normalized to common names such as likes, comments, stars, forks, points, or views
- `media_references` -> linked images, thumbnails, videos, icons, screenshots, or avatars when discoverable
- `identifiers` -> neutral source identifiers such as `domain` or `repo_full_name`
- `extras` -> channel-specific details, source hints, and diagnostics

Use `agent-reach doctor --json --probe` in CI or scheduled workflows when readiness matters. By default, `doctor --json` is diagnostic-only; callers decide whether to add `--require-channel`, `--require-channels`, or `--require-all` for the channels that matter to a given run. Treat Twitter/X authenticated-but-unprobed status as `warn` with `usability_hint=authenticated_but_unprobed`, while `doctor --json --probe` separates live `user` and `search` readiness under `operation_statuses`. Use `channels --json` fields such as `probe_operations` and `probe_coverage`, plus doctor fields such as `probed_operations`, `unprobed_operations`, `probe_run_coverage`, `summary.required_not_ready`, `summary.informational_not_ready`, and `summary.probe_attention`, when downstream automation needs to know whether a probe covered every operation or only a subset.

When a channel exposes bounded pagination or time-window controls, `channels --json` `operation_contracts` now lists those options directly. Downstream code should decide whether to use `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`; Agent Reach only forwards them and records the resulting pagination metadata under both flat `meta` keys and `meta.pagination`.

The repository examples `examples/research-ledger.ps1` and `examples/discord_news_collect.ps1` show collect-only ledger and candidate planning flows. They intentionally stop at raw artifacts so the downstream project keeps ownership of ranking, summarization, posting, and state.
