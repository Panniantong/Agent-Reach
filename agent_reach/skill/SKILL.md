---
name: agent-reach
description: Windows-first research tooling for Codex. Use when the user asks to search the web, inspect a GitHub repository, summarize a YouTube video, read an article or RSS feed, or check Twitter/X reactions. Route note, Qiita, Zenn, docs sites, and other general web sources through Exa search plus Jina Reader instead of bespoke platform adapters.
---

# Agent Reach

Use the bundled tools directly. This fork is intentionally narrow:

- `web`: generic page reading through Jina Reader
- `exa_search`: wide web search through `mcporter`
- `github`: repository and code search through `gh`
- `youtube`: metadata and subtitle extraction through `yt-dlp`
- `rss`: RSS and Atom feeds through `feedparser`
- `twitter`: optional Twitter/X search through `twitter-cli`

## Workflow

1. Run `agent-reach doctor` if availability is unclear.
2. Pick the narrowest tool that matches the user request.
3. Prefer `exa_search` plus `web` for note, Qiita, Zenn, blogs, and docs sites.
4. Treat Twitter/X as opt-in and expect cookie-based auth.
5. Avoid creating files in the user workspace unless the task explicitly needs artifacts.

## Command Routing

- General search: read [references/search.md](references/search.md)
- GitHub work: read [references/dev.md](references/dev.md)
- Web pages and RSS: read [references/web.md](references/web.md)
- YouTube: read [references/video.md](references/video.md)
- Twitter/X: read [references/social.md](references/social.md)

## Quick Checks

```powershell
agent-reach doctor
mcporter --config "$HOME\.mcporter\mcporter.json" config list
gh auth status
twitter status
```
