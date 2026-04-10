# Agent Reach Install Guide

This fork targets native Windows installs for Codex, GitHub Actions, and other downstream tooling that needs a predictable read-only collection surface.

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

For the evidence ledger and candidate planner release, `agent-reach version` should report `Agent Reach v1.6.0` or newer.

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

## Integration discovery

```powershell
agent-reach channels --json
agent-reach doctor --json
agent-reach doctor --json --probe
agent-reach export-integration --client codex --format json
```

## Read-only collection smoke commands

```powershell
agent-reach collect --channel web --operation read --input "https://example.com" --json
agent-reach collect --channel github --operation read --input "openai/openai-python" --json
agent-reach collect --channel rss --operation read --input "https://hnrss.org/frontpage" --limit 1 --json
```

These commands are the supported integration surface for downstream tools. They are non-interactive by default and keep errors in JSON when collection fails.
