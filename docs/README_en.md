# Agent Reach for Windows and Codex

This fork keeps Agent Reach intentionally small and predictable.

Supported channels:

- `web` through Jina Reader
- `exa_search` through `mcporter`
- `github` through `gh`
- `youtube` through `yt-dlp`
- `rss` through `feedparser`
- optional `twitter` through `twitter-cli`

## Install

```powershell
uv tool install .
agent-reach install --env=auto
```

Optional Twitter/X support:

```powershell
agent-reach install --env=auto --channels=twitter
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
```

Browser import is also available:

```powershell
agent-reach configure --from-browser chrome
```

## Verification

```powershell
agent-reach doctor
gh auth login
twitter status
```

`doctor` should only report the supported Windows/Codex channels listed above.
