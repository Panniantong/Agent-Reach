---
name: agent-reach
description: "Give your AI Agent eyes to see the entire internet — search & read 13+ platforms (Twitter, Reddit, YouTube, GitHub, Bilibili, XiaoHongShu, LinkedIn, RSS, Web, V2EX, Xueqiu, Xiaoyuzhou). Multi-backend routing with auto-fallback."
version: 1.5.0
author: Neo Reid
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [web, research, search, social-media, github, youtube, rss, scraping, agent-reach]
    related_skills: [web-search, youtube-content, github-code-review, arxiv]
    homepage: https://github.com/Panniantong/Agent-Reach
triggers:
  - research: 调研/全网调研/帮我调研/研究一下/research/深入了解
  - search: 搜/查/找/search/搜索/查一下/帮我搜/看看大家怎么说
  - social:
    - 小红书: xiaohongshu/xhs/小红书/红书
    - Twitter: twitter/推特/x.com/推文
    - B站: bilibili/b站/哔哩哔哩
    - V2EX: v2ex
    - Reddit: reddit
  - career: 招聘/职位/求职/linkedin/领英/找工作
  - dev: github/代码/仓库/gh/issue/pr/分支/commit
  - web: 网页/链接/文章/rss/读一下/打开这个
  - video: youtube/视频/播客/字幕/小宇宙/转录/yt
  - finance: 雪球/股票/stock/xueqiu/行情/基金
---

# Agent Reach — Internet Access Router

Gives Hermes read/search access to **13+ platforms** through a unified capability layer. Agent Reach handles install, config, health checks, and multi-backend routing — after install, agents call upstream tools directly.

## Golden Rule: Verify Once Per Session

At the **start** of a research task, run:

```bash
agent-reach doctor --json
```

Cache the result for the duration of this task. **Re-check** only when a platform command returns output that signals failure — an empty body, HTTP error page, or a non-zero exit code. Exit code alone is insufficient (e.g. `curl` returns 0 on HTTP 404 without `-f`).

This trades per-command freshness for speed — acceptably safe because backends don't change mid-session, but if a platform silently degrades mid-task the cached result will be stale until the next task start.

Check the `active_backend` and `status` fields for each platform:
- `"status": "ok"` → Use the static commands below
- `"status": "error"` or `"status": "missing"` → **Do not keep retrying.** Switch to an alternative approach: web search, browser automation, or ask the user.
- Backends change over time — re-run doctor only when a command fails.

## Platform Routing Table

| Intent | Category | Primary Command |
|--------|----------|-----------------|
| **Web page** | web | `curl -s "https://r.jina.ai/URL"` |
| **Web search** | search | `mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'` |
| **Twitter/X** | social | `twitter tweet <url>` / `twitter search "query"` |
| **Reddit** | social | `opencli reddit search "query"` or `rdt search "query"` |
| **Bilibili** | social | `bili search "query"` / `bili detail <avid>` |
| **XiaoHongShu** | social | `opencli xiaohongshu search "query"` |
| **V2EX** | social | `curl -s "https://www.v2ex.com/api/v2/topics/hot"` |
| **GitHub** | dev | `gh search repos "query" --sort stars --limit 10` |
| **YouTube** | video | `yt-dlp --write-sub --skip-download --sub-lang en "URL"` |
| **RSS** | web | `python3 -c "import feedparser; ..."` |
| **LinkedIn** | career | linkedin-mcp or Jina Reader |
| **Xueqiu** | finance | Stock search via configured CLI |
| **Xiaoyuzhou** | video | `agent-reach transcribe <url>` |

> **When a command fails:** Run `agent-reach doctor --json` to check the current active backend. If the backend is dead, do NOT keep retrying — use an alternative method (native web tools, browser fallback, or tell the user).

## Installation

```bash
pip install agent-reach
agent-reach install --env=auto
agent-reach skill --install   # Hermes skill
```

## Update Check

After multi-platform research, run:

```bash
agent-reach check-update
```
