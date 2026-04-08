# Agent Reach

Windows-first research tooling for Codex and similar CLI agents.

This fork narrows the original project on purpose. It focuses on a small set of channels that are practical on a native Windows machine:

- Web pages via Jina Reader
- Cross-web search via Exa MCP
- GitHub via `gh`
- YouTube via `yt-dlp`
- RSS and Atom feeds via `feedparser`
- Optional Twitter/X via `twitter-cli`

Platforms that need extra regional tooling or are outside this fork's scope are not surfaced in the installer, doctor output, or skill routing.

## Why this fork exists

The upstream project is broad and platform-rich. This fork optimizes for:

- Native Windows setup without `apt`, `brew`, `bash`, or WSL
- Codex skill installation under `CODEX_HOME/skills` or `~/.codex/skills`
- A smaller, predictable public surface for research-heavy workflows

## Install

From a local checkout:

```powershell
uv tool install .
agent-reach install --env=auto
```

Safe mode:

```powershell
agent-reach install --env=auto --safe
```

Optional Twitter/X support:

```powershell
agent-reach install --env=auto --channels=twitter
agent-reach configure twitter-cookies "auth_token=...; ct0=..."
```

Browser import for Twitter/X:

```powershell
agent-reach configure --from-browser chrome
```

## What `install` does on Windows

- Installs `gh` with `winget`
- Installs `yt-dlp` with `winget`
- Uses the existing `node`/`npm` install, or installs Node.js LTS with `winget`
- Installs `mcporter` with `npm install -g mcporter`
- Registers Exa in the user config with `mcporter --config "$HOME\\.mcporter\\mcporter.json" config add exa https://mcp.exa.ai/mcp`
- Writes the `yt-dlp` JS runtime config for Node.js
- Installs the bundled skill into Codex and other known agent skill roots

## Health Check

```powershell
agent-reach doctor
```

Typical commands after install:

```powershell
mcporter --config "$HOME\.mcporter\mcporter.json" call "exa.web_search_exa(query: \"latest agent frameworks\", numResults: 5)"
curl.exe -L "https://r.jina.ai/http://example.com"
gh search repos "agent reach" --limit 10
yt-dlp --dump-single-json "https://www.youtube.com/watch?v=VIDEO_ID"
twitter search "gpt-5.4" --limit 10
```

GitHub authentication can also be stored explicitly:

```powershell
agent-reach configure github-token YOUR_TOKEN
```

## Publishing your fork

This local implementation keeps the package name `agent-reach` for compatibility, but does not assume a published GitHub namespace yet. After you publish your fork, update the repository URLs and install snippets if you want remote installs from ZIP or Git.
