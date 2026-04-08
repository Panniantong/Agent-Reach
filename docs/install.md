# Agent Reach Install Guide

This fork targets native Windows installs for Codex and similar agents.

## Local install from source

```powershell
uv tool install .
agent-reach install --env=auto
```

## Safe mode

Use safe mode when you want to see the exact Windows commands first.

```powershell
agent-reach install --env=auto --safe
```

The installer only automates these Windows-friendly steps:

- `winget install --id GitHub.cli -e`
- `winget install --id yt-dlp.yt-dlp -e`
- `winget install --id OpenJS.NodeJS.LTS -e` when Node.js is missing
- `npm install -g mcporter`
- `mcporter --config "$HOME\\.mcporter\\mcporter.json" config add exa https://mcp.exa.ai/mcp`
- `uv tool install twitter-cli` for the optional Twitter channel

## Optional Twitter/X support

```powershell
agent-reach install --env=auto --channels=twitter
```

Then configure cookies explicitly:

```powershell
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
```

Or import them from a local browser:

```powershell
agent-reach configure --from-browser chrome
```

GitHub can be authenticated either with the native CLI flow or by storing a token:

```powershell
gh auth login
agent-reach configure github-token YOUR_TOKEN
```

## Final verification

```powershell
agent-reach doctor
```

Core channels should report ready or give a specific Windows command to fix the remaining gap.
