<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>Give your AI Agent one-click access to the internet.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/Agent-Reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/Agent-Reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <em>English version. 中文版见 <a href="./README.md">README.md</a>.</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#supported-platforms">Platforms</a> ·
  <a href="#design-philosophy">Philosophy</a> ·
  <a href="#faq">FAQ</a>
</p>

---

## Why Agent Reach?

AI Agents can write code, edit docs, and manage projects — but the moment you ask one to "look something up online," it goes blind:

- 📺 "Summarize this YouTube tutorial" → **Can't.** No subtitles.
- 🐦 "What are people saying about this product on Twitter?" → **Can't.** Twitter API is paid.
- 📖 "Has anyone hit this same bug on Reddit?" → **403.** Server IP is blocked.
- 📕 "Check Xiaohongshu reviews for this product" → **Can't open.** Login wall.
- 📺 "There's a Bilibili tech video, summarize it" → **Connection refused.** Region-blocked.
- 🔍 "Search the web for the latest LLM framework comparisons" → **Either pay or get junk results.**
- 🌐 "Read this webpage for me" → **Returns raw HTML soup.** Unreadable.
- 📦 "What does this GitHub repo do? What's in the issues?" → Works, but auth is a pain.
- 📡 "Subscribe to these RSS feeds and notify me on updates" → Need to write your own glue.

**None of this is hard — but each platform has its own toll booth.**

Paid APIs, IP blocks, login walls, dirty HTML. You burn an afternoon getting your agent to read a single tweet.

**Agent Reach turns the whole thing into one line:**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/Agent-Reach/main/docs/install.md
```

Paste that to your agent. Minutes later it can read Twitter, search Reddit, watch YouTube, and browse Xiaohongshu.

**Already installed? Updates are one line too:**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/Agent-Reach/main/docs/update.md
```

> ⭐ **Star the project** — we track platform changes and add new channels so you don't have to. Platform breaks something? We patch it. New channel? We add it.

### ✅ Before you start

| | |
|---|---|
| 💰 **Free** | All tools are open source. All APIs are free. The only possible cost is a server proxy (~$1/month). Local machines don't need one. |
| 🔒 **Privacy-safe** | Cookies are stored only on your machine. Never uploaded. Fully open source — audit anytime. |
| 🔄 **Maintained** | Upstream tools (yt-dlp, twitter-cli, rdt-cli, Jina Reader, etc.) are tracked and updated. You don't have to watch them. |
| 🤖 **Works with any agent** | Claude Code, OpenClaw, Cursor, Windsurf — anything that can run shell commands. |
| 🩺 **Self-diagnostic** | `agent-reach doctor` — one command tells you what works, what's broken, and how to fix it. |

---

## Supported Platforms

| Platform | Works out of the box | Unlocked with config | How to configure |
|------|---------|-----------|-------|
| 🌐 **Web** | Read any webpage | — | None |
| 📺 **YouTube** | Subtitle extraction + video search | — | None |
| 📡 **RSS** | Read any RSS/Atom feed | — | None |
| 🔍 **Web search** | — | Semantic search across the web | Auto-configured (MCP, free, no API key) |
| 📦 **GitHub** | Read public repos + search | Private repos, file Issue/PR, Fork | Tell your agent "log me into GitHub" |
| 🐦 **Twitter/X** | Read a single tweet | Search, timeline, post tweets | Tell your agent "configure Twitter for me" |
| 📺 **Bilibili** | Local: subtitles + search | Works on servers too | Tell your agent "configure a proxy" |
| 📖 **Reddit** | Search + read posts and comments (via rdt-cli) | Cookie | Login required (`rdt login`) — see [rdt-cli](https://github.com/public-clis/rdt-cli) |
| 📕 **Xiaohongshu** | — | Read, search, post, comment, like | Tell your agent "configure Xiaohongshu" |
| 🎵 **Douyin** | — | Video parsing, watermark-free download | Tell your agent "configure Douyin" |
| 💼 **LinkedIn** | Public pages via Jina Reader | Profile details, company pages, job search | Tell your agent "configure LinkedIn" |
| 💬 **WeChat Official Accounts** | Search + read articles (full Markdown) | — | None |
| 📰 **Weibo** | Trending, search content/users/topics, user feeds, comments | — | None |
| 💻 **V2EX** | Hot topics, node topics, topic detail + replies, user info | — | None |
| 📈 **Xueqiu (雪球)** | Stock quotes, stock search, hot posts, hot-stock ranking | — | Tell your agent "configure Xueqiu" |
| 🎙️ **Xiaoyuzhou (小宇宙) podcasts** | — | Podcast audio → text (Whisper transcription, free key) | Tell your agent "configure Xiaoyuzhou" |

> **Don't know how to set something up? Don't read the docs.** Just tell your agent "configure X for me" — it already knows what's needed and will walk you through it.
>
> 🍪 For cookie-based platforms (Twitter, Xiaohongshu, etc.), use the Chrome extension [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) to export your cookie and send it to your agent. The flow is uniform: log in via browser → export with Cookie-Editor → send to agent. Easier and more reliable than QR-code scanning.
>
> 🔒 Cookies are stored only on your machine. Never uploaded. Code is fully open — audit any time.
> 💻 Local machines don't need a proxy. Proxies are only needed when deployed to a server (~$1/month).

---

## Quick Start

> ⚠️ **OpenClaw users: enable `exec` first**
>
> Agent Reach relies on your agent being able to run shell commands (`pip install`, `mcporter`, `twitter`, etc.). If your OpenClaw is using the default `messaging` tool profile, the agent cannot run commands. **Switch the profile to `coding` before installing:**
>
> ```bash
> openclaw config set tools.profile "coding"
> ```
> Or set `"tools": { "profile": "coding" }` in `~/.openclaw/openclaw.json`. Restart the Gateway (`openclaw gateway restart`) and open a new conversation. Other clients (Claude Code, Cursor, Windsurf, etc.) are not affected.

Paste this to your AI agent (Claude Code, OpenClaw, Cursor, etc.):

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/Agent-Reach/main/docs/install.md
```

That's it. The agent handles everything else.

> 🔄 **Already installed?** Update with one line:
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/Agent-Reach/main/docs/update.md
> ```

> 🛡️ **Worried about safety?** Use safe mode — won't auto-install system packages, just tells you what's needed:
> ```
> Install Agent Reach (safe mode): https://raw.githubusercontent.com/Panniantong/Agent-Reach/main/docs/install.md
> Use the --safe flag during install.
> ```

<details>
<summary>What does it actually do? (click to expand)</summary>

1. **Install the CLI** — `pip install` puts the `agent-reach` command on your path.
2. **Install system dependencies** — auto-detects and installs Node.js, gh CLI, mcporter, twitter-cli, rdt-cli, etc.
3. **Configure search** — wires up Exa via MCP (free, no API key).
4. **Detect environment** — figures out whether you're on a local machine or a server, suggests the right configuration.
5. **Register SKILL.md** — installs a usage guide into your agent's skills directory. Next time the agent sees "search Twitter" or "summarize this video," it already knows which upstream tool to call.

After install, `agent-reach doctor` shows the status of every channel.
</details>

---

## Works Right Away

No configuration needed. Just tell the agent:

- "Open this link for me" → `curl https://r.jina.ai/URL` reads any webpage.
- "What is this GitHub repo?" → `gh repo view owner/repo`
- "What's in this video?" → `yt-dlp --dump-json URL` extracts subtitles.
- "Show me this tweet" → `twitter tweet URL`
- "Subscribe to this RSS" → `feedparser`
- "Search GitHub for LLM frameworks" → `gh search repos "LLM framework"`

**You don't memorize commands.** Once the agent reads SKILL.md, it picks the right tool on its own.

---

## Design Philosophy

**Agent Reach is scaffolding, not a framework.**

Every time you give a new agent a fresh environment, you spend hours picking tools, installing dependencies, debugging configs — what reads Twitter? How do you get past Reddit's 403? How do you extract YouTube subtitles? You re-step on the same rakes every time.

Agent Reach does one simple thing: **it does that picking and configuring work for you, once.**

After install, the agent calls upstream tools (`twitter-cli`, `rdt-cli`, `xhs-cli`, `yt-dlp`, `mcporter`, `gh CLI`, etc.) **directly**. There is no wrapper layer in between.

### 🔌 Every channel is pluggable

Each platform is backed by an independent upstream tool. **Don't like one? Swap it.**

```
channels/
├── web.py          → Jina Reader     ← swap for Firecrawl, Crawl4AI, ...
├── twitter.py      → twitter-cli     ← swap for the official API, ...
├── youtube.py      → yt-dlp          ← swap for YouTube API, Whisper, ...
├── github.py       → gh CLI          ← swap for REST API, PyGithub, ...
├── bilibili.py     → yt-dlp          ← swap for bilibili-api, ...
├── reddit.py       → rdt-cli         ← search + read, needs cookie
├── xiaohongshu.py  → mcporter MCP    ← swap for another XHS tool, ...
├── douyin.py       → mcporter MCP    ← swap for another Douyin tool, ...
├── linkedin.py     → linkedin-mcp    ← swap for the LinkedIn API, ...
├── wechat.py       → Exa (+ Camoufox) ← search + read WeChat articles
├── rss.py          → feedparser      ← swap for atoma, ...
├── exa_search.py   → mcporter MCP    ← swap for Tavily, SerpAPI, ...
└── __init__.py     → channel registry (doctor uses this)
```

Each channel file only checks whether the corresponding upstream tool is available (a `check()` method) and reports back to `agent-reach doctor`. The actual fetch and search calls are made by the agent directly.

### Current selections

| Use case | Tool | Why |
|------|------|-----------|
| Read webpage | [Jina Reader](https://github.com/jina-ai/reader) | 9.8K stars, free, no API key |
| Read Twitter | [twitter-cli](https://github.com/public-clis/twitter-cli) | 2.1K stars, cookie login, search/read/timeline/articles |
| Reddit | [rdt-cli](https://github.com/public-clis/rdt-cli) | 304 stars, cookie auth, search + full text + comments |
| Video subtitles + search | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 154K stars, works on YouTube + Bilibili + 1,800 sites |
| Bilibili enhanced | [bili-cli](https://github.com/public-clis/bilibili-cli) | 590 stars, hot/ranking/search/feed |
| Web search | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | AI semantic search, MCP-native, no key |
| GitHub | [gh CLI](https://cli.github.com) | Official tool, full API after auth |
| RSS | [feedparser](https://github.com/kurtmckee/feedparser) | Python ecosystem standard, 2.3K stars |
| Xiaohongshu | [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) | 1.5K stars, one-line pipx install, search/read/comment/post |
| Douyin | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | MCP server, no login, video parsing + watermark-free download |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | ⭐1.2K, MCP server, browser automation |
| WeChat Official Accounts | [Exa](https://exa.ai) (search + read) + [Camoufox](https://github.com/daijro/camoufox) (optional) | Zero-config search + full read, Camoufox optional |

> 📌 These are *current* selections. Don't like one? Swap the file. That's the point of scaffolding.

### Optional alternative for Douyin / Xiaohongshu script extraction

If you don't just want "Douyin video info parsing" but also need a unified pipeline for:

- Douyin video script extraction
- Xiaohongshu video-note script extraction
- Xiaohongshu image-note body + image OCR
- Standardized `script.md` and `info.json` output

You can point the `douyin` mcporter alias to a compatible alternative implementation:

- [social-post-extractor-mcp](https://github.com/JNHFlow21/social-post-extractor-mcp)

It preserves backward-compatible tool names:

- `parse_douyin_video_info`
- `get_douyin_download_link`
- `extract_douyin_text`

And adds unified tools:

- `parse_social_post_info`
- `extract_social_post_script`

From Agent Reach's perspective it's still a `mcporter` server called `douyin` — just with broader capability.

---

## Security

Agent Reach takes security seriously by design:

| Measure | Description |
|------|-------------|
| 🔒 **Credentials stay local** | Cookies and tokens live in `~/.agent-reach/config.yaml` with file mode 600 (owner read/write only). Never uploaded. |
| 🛡️ **Safe mode** | `agent-reach install --safe` won't auto-modify the system. It tells you what's needed and lets you decide. |
| 👀 **Fully open source** | Code is transparent and auditable. Every dependency is open source too. |
| 🔍 **Dry run** | `agent-reach install --dry-run` previews everything without making any changes. |
| 🧩 **Pluggable** | Don't trust a component? Swap the channel file. Doesn't affect anything else. |

### 🍪 Cookie safety

> ⚠️ **Account-ban warning:** Platforms that use cookie login (Twitter, Xiaohongshu, etc.) can detect non-browser API calls and **may ban or restrict your account**. Use a **dedicated burner account**, never your main account.

For cookie-based platforms (Twitter, Xiaohongshu), use a **dedicated alt account**, not your main, for two reasons:
1. **Ban risk** — platforms may detect non-browser API behavior and restrict or ban the account.
2. **Blast radius** — a cookie is equivalent to a full session. Using an alt limits damage if leaked.

### 📦 Install modes

| Mode | Command | When |
|------|---------|------|
| One-shot full install (default) | `agent-reach install --env=auto` | Personal machine, dev environment |
| Safe mode | `agent-reach install --env=auto --safe` | Production server, shared machine |
| Preview only | `agent-reach install --env=auto --dry-run` | When you want to see what would happen first |

### 🗑️ Uninstall

```bash
agent-reach uninstall
```

Removes: `~/.agent-reach/` (incl. all tokens / cookies), each agent's skill file, mcporter MCP configuration.

```bash
# Preview only, no actual delete
agent-reach uninstall --dry-run

# Only remove skill files, keep token config (useful when reinstalling)
agent-reach uninstall --keep-config
```

To uninstall the Python package itself: `pip uninstall agent-reach`

---

## Contributing

This project was made in pure vibe coding 🎸 — there may be rough edges. If you hit an issue please be patient. Open a [GitHub Issue](https://github.com/Panniantong/Agent-Reach/issues) for any bug and we'll get to it.

**Want a new channel?** Open an Issue or send a PR.

**Want to add one locally?** Have your agent clone the repo and add a new file under `channels/`. Each channel is one independent file — pretty easy to add.

[PRs](https://github.com/Panniantong/Agent-Reach/pulls) are always welcome.

For broader discussion and questions in Chinese, see the original [README.md](./README.md) and the maintainer's contact info there.

---

## ⭐ Why star this

I (the maintainer) use this every day, so it gets maintained.

- New channels people ask for get added over time.
- Each channel aims to be **working, useful, and free**.
- When platforms change their anti-scraping logic or APIs, I fix it.

A small contribution to the Web 4.0 toolchain.

Star it so you can find it when you need it. ⭐

---

## FAQ

<details>
<summary><strong>How does my AI agent search Twitter / X without paying for the API?</strong></summary>

Agent Reach uses [twitter-cli](https://github.com/public-clis/twitter-cli) with cookie auth — zero API cost. Install: `pipx install twitter-cli`. Make sure you're logged into x.com in your browser. Then the agent can run `twitter search "query"` to search and `twitter tweet URL` to read a tweet.
</details>

<details>
<summary><strong>Reddit returns 403 — how to fix?</strong></summary>

Agent Reach uses [rdt-cli](https://github.com/public-clis/rdt-cli) for Reddit. Since 2024 Reddit requires auth; after install you need to run `rdt login`. Install: `pipx install rdt-cli`, then `rdt login` (it pulls the cookie from your browser automatically). After that the agent can use `rdt search "query"` to search and `rdt read POST_ID` to read full posts and comments.
</details>

<details>
<summary><strong>How do I get YouTube video transcripts for my agent?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` extracts video metadata; `yt-dlp --write-sub --skip-download "URL"` extracts subtitles. Powered by yt-dlp, supports many languages. No API key needed.
</details>

<details>
<summary><strong>How do I let my agent read Xiaohongshu?</strong></summary>

Install with `pipx install xiaohongshu-cli`, then `xhs login` (pulls cookie from your browser). After that the agent can use `xhs search "query"` to search notes, `xhs read NOTE_ID` for note detail, and `xhs comments NOTE_ID` for the comment thread. No Docker needed.
</details>

<details>
<summary><strong>How do I parse Douyin videos with my agent?</strong></summary>

Install the douyin-mcp-server. Then the agent can run `mcporter call 'douyin.parse_douyin_video_info(share_link: "share-link")'` to parse video info and get a watermark-free download URL. No login needed — just send your agent the Douyin share link. See https://github.com/yzfly/douyin-mcp-server
</details>

<details>
<summary><strong>Compatible with Claude Code / Cursor / OpenClaw / Windsurf?</strong></summary>

Yes. Agent Reach is an installer + configurator — any AI coding agent that can execute shell commands can use it. Works with Claude Code, Cursor, OpenClaw, Windsurf, Codex, and more. Just `pip install agent-reach`, run `agent-reach install`, and the agent can start using the upstream tools immediately.

**OpenClaw note:** if your OpenClaw is using the default `messaging` tool profile, the agent can't run shell commands. Enable exec first: `openclaw config set tools.profile "coding"` (or set `"tools": { "profile": "coding" }` in `~/.openclaw/openclaw.json`), then restart the Gateway and start a new conversation.
</details>

<details>
<summary><strong>Is this really free? Any API costs?</strong></summary>

100% free. All backends are open-source tools (twitter-cli, rdt-cli, xhs-cli, yt-dlp, Jina Reader, Exa, etc.) that don't require paid API keys. The only optional cost is a residential proxy (~$1/month) if you need Bilibili access from an overseas server.
</details>

---

## Acknowledgements

[twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## Contact

- 📧 **Email:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

For bug reports and feature requests, please use [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues) — easier to track.

## License

[MIT](LICENSE)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
