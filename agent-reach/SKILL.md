---
name: agent-reach
description: >
  Give your AI agent eyes to see the entire internet. Read and search across
  Twitter/X, Reddit, YouTube, GitHub, Bilibili, XiaoHongShu, RSS, and any web page
  — all from a single CLI. Use when: (1) reading content from URLs (tweets, Reddit posts,
  articles, videos), (2) searching across platforms (web, Twitter, Reddit, GitHub, YouTube,
  Bilibili, XiaoHongShu), (3) checking channel health or updating Agent Reach.
  Triggers: "search Twitter/Reddit/YouTube", "read this URL", "find posts about",
  "搜索", "读取", "查一下", "看看这个链接".
---

# Agent Reach

Read and search the internet across 9+ platforms via unified CLI.

## Commands

### Read any URL
```bash
agent-reach read <url>
agent-reach read <url> --json    # structured output
```
Handles: tweets, Reddit posts, articles, YouTube (transcripts), GitHub repos, etc.

### Search

```bash
agent-reach search "query"             # web search (Exa)
agent-reach search-twitter "query"     # Twitter/X
agent-reach search-reddit "query"      # Reddit (--sub <subreddit>)
agent-reach search-github "query"      # GitHub (--lang <language>)
agent-reach search-youtube "query"     # YouTube
agent-reach search-bilibili "query"    # Bilibili (B站)
agent-reach search-xhs "query"        # XiaoHongShu (小红书)
```

All search commands support `-n <count>` for number of results.

### Management

```bash
agent-reach doctor        # channel status overview
agent-reach watch         # quick health + update check (for scheduled tasks)
agent-reach check-update  # check for new versions
```

### Configure channels

```bash
agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy"
agent-reach configure proxy http://user:pass@ip:port
agent-reach configure --from-browser chrome    # auto-extract cookies
```

## Channel Status Tiers

- **Tier 0 (zero config):** Web, YouTube, RSS, Twitter (read-only via Jina)
- **Tier 1 (free setup):** Exa web search (mcporter required)
- **Tier 2 (user config):** Twitter search (cookie), Reddit full (proxy), GitHub (token), Bilibili (proxy), XiaoHongShu (MCP)

Run `agent-reach doctor` to see which channels are active.

## Tips

- Always try `agent-reach read <url>` first for any URL — it auto-detects the platform
- For Twitter cookies, recommend the user install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
- Reddit and Bilibili block server IPs — suggest a residential proxy (~$1/month) if on a server
- If a channel breaks, run `agent-reach doctor` to diagnose
