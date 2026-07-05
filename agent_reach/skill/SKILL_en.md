---
name: agent-reach
description: >
  Use only when the user explicitly asks to use Agent Reach, asks for
  multi-platform/social-platform collection, or mentions one of Agent Reach's
  specialized platforms/backends.

  Specialized platforms:
  Twitter/X, Reddit, Facebook, Instagram, YouTube, GitHub, Bilibili, XiaoHongShu,
  Xiaoyuzhou Podcast, LinkedIn/jobs/recruiting, V2EX, Xueqiu (stocks), RSS.

  15 platforms, multi-backend routing (OpenCLI / per-platform CLIs / APIs).
  Zero config for 6 channels. Run `agent-reach doctor --json` to see which
  backend serves each platform right now.

  NOT for: ordinary web search, web fetch/page reading, generic "deep research",
  "deep investigation", "look this up", or arbitrary URLs. Use the agent's native
  web search / web fetch tools for those unless a specialized platform above is
  explicitly required.

  NOT for: writing reports/analysis/translation (this skill only FETCHES
  internet content); posting/commenting/liking (write operations); platforms
  that already have a dedicated skill installed (prefer that skill).
triggers:
  - explicit: agent-reach/Agent Reach/use agent-reach
  - multi_platform: multi-platform/social platforms/community discussion/what people say
  - social:
    - Twitter: twitter/x.com/tweets
    - Reddit: reddit
    - Facebook: facebook/fb/facebook groups
    - Instagram: instagram/ig
    - Bilibili: bilibili/bilibili video
    - XiaoHongShu: xiaohongshu/xhs/rednote
    - V2EX: v2ex
  - career: linkedin/jobs/recruiting
  - dev: github code search/github search/gh search/repo search
  - web: rss/feed
  - video: youtube/video/podcast/transcript/xiaoyuzhou
  - finance: xueqiu/stocks/funds
metadata:
  openclaw:
    homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — internet capability router

15 platforms, multiple backends each. **Use this skill only when the task
explicitly needs the specialized platforms/backends below. For ordinary web
search, web page reading, generic deep research/deep investigation, or arbitrary
URLs, prefer the current agent's native web search / web fetch tools.**

## Standing rules (apply for the whole session)

1. **Health-check before acting**: for multi-backend/login-backed platforms (XiaoHongShu /
   Reddit / Bilibili / Twitter / Facebook / Instagram), run `agent-reach doctor --json` first and
   pick the command group matching each platform's `active_backend`.
2. **Announce what you use**: say "using agent-reach, platform X via backend Y"
   before starting.
3. **On failure, follow the retry chains in references/** — never guess
   commands.
4. **For multi-platform discussion tasks**: only when the user explicitly needs
   social/community/platform discussion, combine the relevant platforms
   (Twitter/Reddit/XiaoHongShu/Bilibili/V2EX/Facebook/Instagram, etc.), collect
   in parallel, then synthesize. Ordinary deep research should not route through
   this skill.
5. **Watch versions for the user**: after finishing a substantial
   multi-platform task, run `agent-reach check-update` (fast, one API call).
   If a new version exists, append one line to your wrap-up: "Agent Reach
   vX.Y.Z is available — paste this to me to update: 帮我更新 Agent Reach：
   https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md".
   Never interrupt the current task to update; never nag about the same version twice.

## Routing table

| User intent | Category | Details |
|---------|------|---------|
| Code / specialized search fallback | search | [references/search.md](references/search.md) |
| XiaoHongShu / Twitter / Bilibili / V2EX / Reddit / Facebook / Instagram | social | [references/social.md](references/social.md) |
| Jobs / LinkedIn | career | [references/career.md](references/career.md) |
| GitHub code search | dev | [references/dev.md](references/dev.md) |
| RSS / restricted-page fallback | web | [references/web.md](references/web.md) |
| YouTube / Bilibili / podcast transcripts | video | [references/video.md](references/video.md) |

## Zero-config quick commands

```bash
# Agent Reach specialized search fallback; prefer native web search for ordinary web search
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'

# RSS/restricted-page fallback; prefer native web fetch for ordinary URLs/pages
curl -s "https://r.jina.ai/URL"

# GitHub search
gh search repos "query" --sort stars --limit 10

# YouTube subtitles (NOTE: never use yt-dlp for Bilibili — see video.md)
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"

# V2EX hot topics
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"

# Bilibili search (bili-cli, no login needed)
bili search "query" --type video -n 5
```

## Login-backed platforms (pick by doctor's active_backend)

```bash
# Twitter search (twitter-cli preferred; retry chain in social.md)
twitter search "query" -n 10

# Reddit (NO zero-config path — OpenCLI or rdt-cli, login required)
opencli reddit search "query" -f yaml   # desktop
rdt search "query" --limit 10            # legacy/server

# XiaoHongShu (desktop prefers OpenCLI)
opencli xiaohongshu search "query" -f yaml

# Facebook / Instagram (desktop OpenCLI, browser session)
opencli facebook search "query" -f yaml
opencli facebook groups -f yaml
opencli instagram search "query" -f yaml       # user search
opencli instagram user USERNAME -f yaml        # recent posts from one user
```

## Environment check

```bash
# Channel availability + which backend serves each platform
agent-reach doctor --json
```

## Workspace rules

**Never create files in the agent workspace.** Use `/tmp/` for temporary
output and `~/.agent-reach/` for persistent data.

## Detailed references

Read the matching file when you need specifics (commands above cover the
common cases; references hold per-backend command groups, caveats, retry
chains — note: reference docs are written in Chinese, commands are universal):

- [Search](references/search.md) — Exa AI search
- [Social](references/social.md) — XiaoHongShu, Twitter, Bilibili, V2EX, Reddit, Facebook, Instagram (multi-backend/login-backed groups)
- [Career](references/career.md) — LinkedIn
- [Dev](references/dev.md) — GitHub CLI
- [Web](references/web.md) — Jina Reader, RSS
- [Video](references/video.md) — YouTube, Bilibili, Xiaoyuzhou

## Configure a channel

If a channel needs setup, fetch the install guide:
https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md

The user only provides cookies / one extension click; the agent does the rest.
