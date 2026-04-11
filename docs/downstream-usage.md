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

After that, Codex can use Agent Reach from any project by calling the CLI:

```powershell
agent-reach collect --channel exa_search --operation search --input "latest AI agent frameworks" --limit 5 --json
agent-reach collect --channel web --operation read --input "https://example.com" --json
agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 5 --json
agent-reach collect --channel qiita --operation search --input "python user:Qiita" --limit 5 --json
agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 5 --json
agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 5 --json
```

When provenance matters, append each raw collection envelope to a JSONL ledger:

```powershell
agent-reach collect --channel exa_search --operation search --input "latest AI agent frameworks" --limit 5 --json --save .agent-reach/evidence.jsonl --run-id agent-frameworks
agent-reach ledger validate --input .agent-reach/evidence.jsonl --json
agent-reach plan candidates --input .agent-reach/evidence.jsonl --by url --limit 20 --json
```

This does not require `.codex-plugin`, `.mcp.json`, or `agent_reach/skill` files inside the downstream project.

Treat `extras.source_hints`, `extras.media_references`, and web `meta` hygiene fields as diagnostics only. They can help downstream code explain provenance or flag suspicious extraction shape, but they are not ranking, trust scoring, summarization, or publishing instructions. `collect --max-text-chars N` is only for human text-mode snippets and does not truncate `--json` output or saved ledgers.

If a conditional command was captured without `--save`, append it later with:

```powershell
agent-reach ledger append --input live-results/result.json --output .agent-reach/evidence.jsonl --run-id agent-frameworks --json
```

## Codex Operating Policy

When Codex is working inside an arbitrary project:

- Use the globally installed `agent-reach` CLI by default.
- Do not copy Agent Reach repo files into the project unless the user explicitly asks for repo-local plugin artifacts.
- Use `agent-reach collect --json` as the stable handoff to project code.
- Add `--save .agent-reach/evidence.jsonl` when the run needs an auditable evidence trail.
- Validate ledgers with `agent-reach ledger validate --json` before treating them as CI artifacts.
- Use `agent-reach plan candidates` for lightweight URL or ID dedupe before follow-up reads.
- Keep ranking, summarization, scheduling, Discord publishing, and state in the downstream project.
- Treat optional channel failures as partial results unless strict completeness is required.

Large-scale research should use bounded fan-out:

1. Start with 2-4 broad discovery queries at `--limit 5` to `--limit 10`.
2. Save raw `CollectionResult` JSONL with `--save .agent-reach/evidence.jsonl`.
3. Run `agent-reach plan candidates --input .agent-reach/evidence.jsonl --by url --limit 20 --json`.
4. Use specialist channels when the source is known.
5. Deep-read only selected URLs with `web`.
6. Persist raw ledgers and candidate plans as artifacts in CI when traceability matters.

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
          agent-reach collect --channel bluesky --operation search --input "OpenAI" --limit 3 --json --save .agent-reach/evidence.jsonl > agent-reach-results.json
          agent-reach plan candidates --input .agent-reach/evidence.jsonl --by url --limit 20 --json > agent-reach-candidates.json
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
- `extras.metrics` / channel-specific extras -> engagement, linked media references, labels, source hints, or diagnostics

Use `agent-reach doctor --json --probe` in CI or scheduled workflows when readiness matters. By default, `doctor --json` uses the `core` exit policy: optional gaps appear in `summary.advisory_not_ready` rather than failing the command. Use `--exit-policy all` for strict all-channel readiness. Treat Twitter/X as optional: authenticated-but-unprobed status is a `warn` with `usability_hint=authenticated_but_unprobed`, while `doctor --json --probe` separates live `user` and `search` readiness under `operation_statuses`. Use `channels --json` fields such as `probe_operations` and `probe_coverage`, plus doctor fields such as `probed_operations`, `unprobed_operations`, and `probe_run_coverage`, when downstream automation needs to know whether a probe covered every operation or only a subset.

The repository examples `examples/research-ledger.ps1` and `examples/discord_news_collect.ps1` show collect-only ledger and candidate planning flows. They intentionally stop at raw artifacts so the downstream project keeps ownership of ranking, summarization, posting, and state.
