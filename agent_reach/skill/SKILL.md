---
name: agent-reach
description: >
  Give your AI agent eyes to see the entire internet.
  17 platforms via CLI, MCP, curl, and Python scripts.
  Zero config for 8 channels.

  [Routing] SKILL.md contains the routing table and common commands; for complex scenarios, read the matching category file under references/*.md as needed.
  Categories: search / social (XiaoHongShu/Douyin/Weibo/Twitter/Bilibili/V2EX/Reddit) / career(LinkedIn) / dev(github) / web(Web/articles/WeChat Official Account/RSS) / video(YouTube/Bilibili/podcasts).

  Use when user asks to search, read, or interact on any supported platform,
  shares a URL, or asks to search the web.
triggers:
  - search: search/find/look up/search/search for/look this up/search for me
  - social:
    - XiaoHongShu: xiaohongshu/xhs/XiaoHongShu/RED
    - Douyin: douyin/Douyin
    - Twitter: twitter/Twitter/x.com/tweet
    - Weibo: weibo/Weibo
    - Bilibili: bilibili/bilibili/Bilibili
    - V2EX: v2ex
    - Reddit: reddit
  - career: hiring/job posting/job search/linkedin/LinkedIn/find a job
  - dev: github/code/repo/gh/issue/pr/branch/commit
  - web: web page/link/article/WeChat Official Account/WeChat article/rss/read this/open this
  - video: youtube/video/podcast/subtitles/Xiaoyuzhou/transcribe/yt
  - finance: Xueqiu/stock/stock/xueqiu/quotes/funds
metadata:
  openclaw:
    homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — Router

A collection of tools for 17 platforms. Pick the matching category based on user intent.

## Routing Table

| User Intent | Category | Detailed Docs |
|---------|------|---------|
| Web search/code search | search | [references/search.md](references/search.md) |
| XiaoHongShu/Douyin/Weibo/Twitter/Bilibili/V2EX/Reddit | social | [references/social.md](references/social.md) |
| Hiring/job postings/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub/code | dev | [references/dev.md](references/dev.md) |
| Web/articles/WeChat Official Account/RSS | web | [references/web.md](references/web.md) |
| YouTube/Bilibili/podcast subtitles | video | [references/video.md](references/video.md) |

## Zero-Config Quick Commands

```bash
# Exa web search
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'

# Generic web reading
curl -s "https://r.jina.ai/URL"

# GitHub search
gh search repos "query" --sort stars --limit 10

# Twitter search
twitter search "query" --limit 10

# YouTube/Bilibili subtitles
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"

# Reddit search
rdt search "query" --limit 10

# Reddit read post + comments
rdt read POST_ID

# V2EX hot topics
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"
```

## Environment Check

```bash
# Check available channels
agent-reach doctor

# View all MCP services
mcporter_list_servers()
```

## Workspace Rules

**Do not create files in the agent workspace.** Use `/tmp/` for temporary output and `~/.agent-reach/` for persistent data.

## Detailed Docs

Read the matching detailed doc based on the user's needs:

- [Search tools](references/search.md) — Exa AI search
- [Social media](references/social.md) — XiaoHongShu, Douyin, Twitter, Bilibili, V2EX, Reddit
- [Career & hiring](references/career.md) — LinkedIn
- [Dev tools](references/dev.md) — GitHub CLI
- [Web reading](references/web.md) — Jina Reader, WeChat Official Account, RSS
- [Video & podcasts](references/video.md) — YouTube, Bilibili, Xiaoyuzhou

## Configuring Channels

If a channel needs configuration, get the install guide:
https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md

The user only needs to provide cookies; the agent handles the rest of the configuration.
