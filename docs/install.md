# Agent Reach Install Guide

This fork targets native Windows installs for Codex, GitHub Actions, and other downstream tooling that needs a predictable read-only collection surface.

## Install the latest fork build

For the latest fork state, install from the fork repo URL:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git
agent-reach skill --install
agent-reach version
```

`agent-reach skill --install` installs the bundled Codex skill suite: `agent-reach`, `agent-reach-shape-brief`, and `agent-reach-orchestrate`.

To pin a specific build, install an exact commit or ref:

```powershell
uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git@<commit-or-ref>
agent-reach skill --install
agent-reach version
```

This fork may be ahead of the latest upstream release tag. Use `agent-reach check-update --json` as an upstream release check, not as the canonical source of the latest fork commit.

## Local install from source

```powershell
uv tool install .
agent-reach install --env=auto
```

This path installs the `agent-reach` CLI. If another Python project wants `AgentReachClient`, install Agent Reach into that project's Python environment separately.

## Update an existing source install

After pulling a new commit, reinstall the tool so `agent-reach.exe` points at the updated package:

```powershell
uv tool install --force .
agent-reach version
```

For the current collection and ledger surface, `agent-reach version` should report `Agent Reach v1.8.0` or newer.

## Preview mode

Use preview mode when you want to inspect commands or consume the plan from another tool.

```powershell
agent-reach install --env=auto --safe
agent-reach install --env=auto --dry-run --json
```

The installer only automates these Windows-friendly steps:

- `winget install --id GitHub.cli -e`
- `winget install --id yt-dlp.yt-dlp -e`
- `winget install --id OpenJS.NodeJS.LTS -e` when Node.js is missing
- `npm install -g mcporter`
- `mcporter --config "$HOME\\.mcporter\\mcporter.json" config add exa https://mcp.exa.ai/mcp`
- `uv tool install rdt-cli` for the optional no-auth Reddit channel
- `uv tool install twitter-cli` for the optional Twitter channel

## Authentication options

GitHub:

```powershell
gh auth login
agent-reach configure github-token YOUR_TOKEN
```

Environment-only execution is also supported:

```powershell
$env:GITHUB_TOKEN = "YOUR_TOKEN"
```

Twitter/X is optional and cookie-based:

```powershell
agent-reach install --env=auto --channels=twitter
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
agent-reach doctor --json --probe
```

Use `doctor --json --probe` before depending on Twitter/X search in downstream automation. `twitter status` confirms authentication, but it does not guarantee that live search is still working.

You can also import Twitter/X cookies from a local browser:

```powershell
agent-reach configure --from-browser chrome
```

Browser import assumptions:

- `browser-cookie3` is already installed with the package
- the selected browser is closed
- you are already logged into `x.com`

Environment-only Twitter/X execution is supported too:

```powershell
$env:TWITTER_AUTH_TOKEN = "..."
$env:TWITTER_CT0 = "..."
```

Reddit is optional and uses `rdt-cli` without Reddit OAuth, client credentials, or User-Agent config:

```powershell
agent-reach install --env=auto --channels=reddit
agent-reach collect --channel reddit --operation search --input "agent frameworks" --limit 5 --json
```

SearXNG is optional and requires a JSON-enabled SearXNG instance:

```powershell
agent-reach configure searxng-base-url "https://searx.example.org"
agent-reach collect --channel searxng --operation search --input "agent tools" --limit 5 --json
```

Crawl4AI is optional and should be installed into the environment that needs browser-backed reads. For external projects, install the package with the `crawl4ai` extra into that project environment:

```powershell
uv pip install "agent-reach[crawl4ai] @ git+https://github.com/iwachacha/Agent-Reach.git"
python -m playwright install chromium
agent-reach collect --channel crawl4ai --operation read --input "https://example.com" --json
agent-reach collect --channel crawl4ai --operation crawl --input "https://example.com" --query "pricing and faq" --limit 10 --json
```

For checkout development, use `uv pip install -e .[crawl4ai]` instead.

## Integration discovery

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --require-channel github
agent-reach doctor --json --require-all
agent-reach doctor --json --probe
agent-reach export-integration --client codex --format json
```

By default, `doctor` is diagnostic-only: it reports flat readiness across all channels and leaves exit-code gating to the caller. Use `--require-channel`, `--require-channels`, or `--require-all` when automation wants a specific readiness policy.

## Read-only collection smoke commands

```powershell
agent-reach collect --channel web --operation read --input "https://example.com" --json
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach collect --channel rss --operation read --input "https://hnrss.org/frontpage" --limit 1 --json
agent-reach collect --channel hacker_news --operation search --input "agent frameworks" --limit 3 --json
agent-reach collect --channel mcp_registry --operation search --input "docs mcp" --limit 3 --json
```

These commands are the supported integration surface for downstream tools. They are non-interactive by default and keep errors in JSON when collection fails.

## Ledger diagnostics

```powershell
agent-reach ledger validate --input .agent-reach/evidence.jsonl --json
agent-reach ledger validate --input .agent-reach/evidence.jsonl --require-metadata --json
agent-reach ledger summarize --input .agent-reach/evidence.jsonl --json
agent-reach ledger query --input .agent-reach/evidence.jsonl --filter "channel == github" --json
agent-reach ledger append --input live-results/twitter-openai.json --output .agent-reach/evidence.jsonl --run-id external-run --json
```

Use `ledger validate` when a CI job needs to prove that saved evidence is parseable. Add `--require-metadata` only when missing `intent`, `query_id`, or `source_role` should fail automation. Use `ledger summarize` for neutral artifact health counts, `ledger query` for lightweight filtering and projection over saved evidence, and `ledger append` when a conditional live collect was first captured to a JSON file and should be added to the evidence ledger afterward.
