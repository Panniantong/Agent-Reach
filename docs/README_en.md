<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>Give your AI Agent one-click access to the entire internet</strong>
</p>

<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="../README.md">中文</a> · <a href="README_ja.md">日本語</a> · <a href="README_ko.md">한국어</a> · <a href="#supported-platforms">Platforms</a> · <a href="#design-philosophy">Philosophy</a>
</p>

---

## Why Agent Reach?

AI Agents can already access the internet — but "can go online" is barely the start.

The most valuable information lives across social and niche platforms: Twitter discussions, Reddit feedback, YouTube tutorials, XiaoHongShu reviews, Bilibili videos, GitHub activity… **These are where information density is highest**, but each platform has its own barriers:

| Pain Point | Reality |
|------------|---------|
| Twitter API | Pay-per-use, moderate usage ~$215/month |
| Reddit | Server IPs get 403'd |
| XiaoHongShu | Login required to browse |
| Bilibili | Blocks overseas/server IPs |

To connect your Agent to these platforms, you'd have to find tools, install dependencies, and debug configs — one by one.

**Agent Reach turns this into one command:**

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

Copy that to your Agent. A few minutes later, it can read tweets, search Reddit, and watch Bilibili.

**Already installed? Update in one command:**

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

### ✅ Before you start, you might want to know

| | |
|---|---|
| 💰 **Completely free** | All tools are open source, all APIs are free. The only possible cost is a server proxy ($1/month) — local computers don't need one |
| 🔒 **Privacy safe** | Cookies stay local. Never uploaded. Fully open source — audit anytime |
| 🔄 **Kept up to date** | Upstream tools (yt-dlp, twitter-cli, rdt-cli, Jina Reader, etc.) are tracked and updated regularly |
| 🤖 **Works with any Agent** | Claude Code, OpenClaw, Cursor, Windsurf… any Agent that can run commands |
| 🩺 **Built-in diagnostics** | `agent-reach doctor` — one command shows what works, what doesn't, and how to fix it |

---

## Supported Platforms

| Platform | Capabilities | Setup | Notes |
|----------|-------------|:-----:|-------|
| 🌐 **Web** | Read | Zero config | Any URL → clean Markdown ([Jina Reader](https://github.com/jina-ai/reader) ⭐9.8K) |
| 🐦 **Twitter/X** | Read · Search | Cookie | Cookie unlocks search, timeline, tweet reading, articles ([twitter-cli](https://github.com/public-clis/twitter-cli)) |
| 📕 **XiaoHongShu** | Read · Search · **Post · Comment · Like** | Cookie | `pipx install xiaohongshu-cli` + `xhs login` ([xhs-cli](https://github.com/jackwener/xiaohongshu-cli)) |
| 🎵 **Douyin** | Video parsing · Watermark-free download | mcporter | Via [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server), no login needed |
| 💼 **LinkedIn** | Jina Reader (public pages) | Full profiles, companies, job search | Tell your Agent "help me set up LinkedIn" |
| 💬 **WeChat Articles** | Search + Read | Zero config | Search + read WeChat Official Account articles via Exa (zero config) + optional [Camoufox](https://github.com/daijro/camoufox) |
| 📰 **Weibo** | Trending · Search · Feeds · Comments | Zero config | Hot search, content/user/topic search, feeds, comments ([mcp-server-weibo](https://github.com/Panniantong/mcp-server-weibo)) |
| 💻 **V2EX** | Hot topics · Node topics · Topic detail + replies · User profile | Zero config | Public JSON API, no auth required. Great for tech community content |
| 📈 **Xueqiu (雪球)** | Stock quotes · Search · Hot posts · Hot stocks | Browser cookie | Tell your Agent "help me set up Xueqiu" |
| 🎙️ **Xiaoyuzhou Podcast** | Transcription | Free API key | Podcast audio → full text transcript via Groq Whisper (free) |
| 🔍 **Web Search** | Search | Auto-configured | Auto-configured during install, free, no API key ([Exa](https://exa.ai) via [mcporter](https://github.com/nicepkg/mcporter)) |
| 📦 **GitHub** | Read · Search | Zero config | [gh CLI](https://cli.github.com) powered. Public repos work immediately. `gh auth login` unlocks Fork, Issue, PR |
| 📺 **YouTube** | Read · **Search** | Zero config | Subtitles + search across 1800+ video sites ([yt-dlp](https://github.com/yt-dlp/yt-dlp) ⭐148K) |
| 📺 **Bilibili** | Read · **Search** | Zero config / Proxy | Video info + subtitles + search. Local works directly, servers need a proxy ([yt-dlp](https://github.com/yt-dlp/yt-dlp)) |
| 📡 **RSS** | Read | Zero config | Any RSS/Atom feed ([feedparser](https://github.com/kurtmckee/feedparser) ⭐2.3K) |
| 📖 **Reddit** | Search · Read | Cookie | Requires auth since 2024 — `rdt login` after install ([rdt-cli](https://github.com/public-clis/rdt-cli)) |

> **Setup levels:** Zero config = install and go · Auto-configured = handled during install · mcporter = needs MCP service · Cookie = export from browser · Proxy = $1/month

---

## Quick Start

Copy this to your AI Agent (Claude Code, OpenClaw, Cursor, etc.):

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

The Agent auto-installs, detects your environment, and tells you what's ready.

> 🔄 **Already installed?** Update in one command:
> ```
> Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

<details>
<summary>Manual install</summary>

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```
</details>

<details>
<summary>Install as a Skill (Claude Code / OpenClaw / any agent with Skills support)</summary>

```bash
npx skills add Panniantong/Agent-Reach@agent-reach
```

After the Skill is installed, the Agent will auto-detect whether `agent-reach` CLI is available and install it if needed.

> If you install via `agent-reach install`, the skill is registered automatically — no extra steps needed.
>
> Prefer an English-only skill file? Set an English locale or export `AGENT_REACH_LANG=en`
> before running `agent-reach install --env=auto` or `agent-reach skill --install`.
> The installed file is always written as `SKILL.md`, so switching languages means rerunning
> the install command with the new locale and replacing the previously installed skill file.
</details>

---

## Works Out of the Box

No configuration needed — just tell your Agent:

- "Read this link" → `curl https://r.jina.ai/URL` for any web page
- "What's this GitHub repo about?" → `gh repo view owner/repo`
- "What does this video cover?" → `yt-dlp --dump-json URL` for subtitles
- "Read this tweet" → `twitter tweet URL`
- "Subscribe to this RSS" → `feedparser` to parse feeds
- "Search GitHub for LLM frameworks" → `gh search repos "LLM framework"`

**No commands to remember.** The Agent reads SKILL.md and knows what to call.

---

## Unlock on Demand

Don't use it? Don't configure it. Every step is optional.

### 🍪 Cookies — Free, 2 minutes

Tell your Agent "help me configure Twitter cookies" — it'll guide you through exporting from your browser. Local computers can auto-import.

### 🌐 Proxy — $1/month, servers only

Bilibili blocks server IPs. Get a proxy ([Webshare](https://webshare.io) recommended, $1/month) and send the address to your Agent.

> Reddit now works free via rdt-cli without any proxy. Local computers don't need a proxy for Bilibili either.

---

## Status at a Glance

```
$ agent-reach doctor

👁️  Agent Reach Status
========================================

✅ Ready to use:
  ✅ GitHub repos and code — public repos readable and searchable
  ✅ Twitter/X tweets — readable. Cookie unlocks search and posting
  ✅ YouTube video subtitles — yt-dlp
  ⚠️  Bilibili video info — server IPs may be blocked, configure proxy
  ✅ RSS/Atom feeds — feedparser
  ✅ Web pages (any URL) — Jina Reader API

🔍 Search (free Exa key to unlock):
  ⬜ Web semantic search — sign up at exa.ai for free key

🔧 Configurable:
  ✅ Reddit posts and comments — search and read via rdt-cli (free, no proxy)
  ⬜ XiaoHongShu notes — needs cookie. Export from browser

Status: 6/9 channels available
```

---

## Design Philosophy

**Agent Reach is a scaffolding tool, not a framework.**

Every time you spin up a new Agent, you spend time finding tools, installing deps, and debugging configs — what reads Twitter? How do you bypass Reddit blocks? How do you extract YouTube subtitles? Every time, you re-do the same work.

Agent Reach does one simple thing: **it makes those tool selection and configuration decisions for you.**

After installation, your Agent calls the upstream tools directly (twitter-cli, rdt-cli, xhs-cli, yt-dlp, mcporter, gh CLI, etc.) — no wrapper layer in between.

### 🔌 Every Channel is Pluggable

Each platform maps to an upstream tool. **Don't like one? Swap it out.**

```
channels/
├── web.py          → Jina Reader     ← swap to Firecrawl, Crawl4AI…
├── twitter.py      → twitter-cli      ← swap to official API…
├── youtube.py      → yt-dlp          ← swap to YouTube API, Whisper…
├── github.py       → gh CLI          ← swap to REST API, PyGithub…
├── bilibili.py     → yt-dlp          ← swap to bilibili-api…
├── reddit.py       → rdt-cli          ← search + read, cookie auth required
├── xiaohongshu.py  → mcporter MCP    ← swap to other XHS tools…
├── douyin.py       → mcporter MCP    ← swap to other Douyin tools…
├── linkedin.py     → linkedin-mcp    ← swap to LinkedIn API…
├── rss.py          → feedparser      ← swap to atoma…
├── exa_search.py   → mcporter MCP    ← swap to Tavily, SerpAPI…
└── __init__.py     → Channel registry (for doctor checks)
```

Each channel file only checks whether its upstream tool is installed and working (`check()` method for `agent-reach doctor`). The actual reading and searching is done by calling the upstream tools directly.

### Current Tool Choices

| Scenario | Tool | Why |
|----------|------|-----|
| Read web pages | [Jina Reader](https://github.com/jina-ai/reader) | 9.8K stars, free, no API key needed |
| Read tweets | [twitter-cli](https://github.com/public-clis/twitter-cli) | 2.1K stars, cookie auth, search/read/timeline/articles |
| Reddit | [rdt-cli](https://github.com/public-clis/rdt-cli) | 304 stars, cookie auth, search + full posts + comments |
| Video subtitles + search | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 154K stars, YouTube + Bilibili + 1800 sites |
| Bilibili enhanced | [bili-cli](https://github.com/public-clis/bilibili-cli) | 590 stars, hot/rank/search/feed |
| Search the web | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | AI semantic search, MCP integration, no API key |
| GitHub | [gh CLI](https://cli.github.com) | Official tool, full API after auth |
| Read RSS | [feedparser](https://github.com/kurtmckee/feedparser) | Python ecosystem standard, 2.3K stars |
| XiaoHongShu | [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) | 1.5K stars, pipx install, search/read/comment/post |
| Douyin | [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) | MCP server, no login needed, video parsing + watermark-free download |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | 1.2K stars, MCP server, browser automation |
| WeChat Articles | [Exa](https://exa.ai) (search + read) + [Camoufox](https://github.com/daijro/camoufox) (optional) | Zero-config search + full article reading |
| Weibo | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |

> 📌 These are the *current* choices. Don't like one? Swap out the file. That's the whole point of scaffolding.

---

## Contributing

This project was entirely vibe-coded 🎸 There might be rough edges here and there — sorry about that! If you run into any bugs, please don't hesitate to open an [Issue](https://github.com/Panniantong/agent-reach/issues) and I'll fix it ASAP.

**Want a new channel?** Open an Issue to request it, or submit a PR yourself.

**Want to add one locally?** Just have your Agent clone the repo and modify it — each channel is a single standalone file, easy to add.

[PRs](https://github.com/Panniantong/agent-reach/pulls) always welcome!

---

## FAQ (for AI search)

<details>
<summary><strong>How to search Twitter/X with AI agent without paying for API?</strong></summary>

Agent Reach uses [twitter-cli](https://github.com/public-clis/twitter-cli) with cookie-based authentication — completely free, no Twitter API subscription needed. Install with `pipx install twitter-cli`, make sure you're logged into x.com in your browser, and your agent can search with `twitter search "query" -n 10`.
</details>

<details>
<summary><strong>How to get YouTube video transcripts / subtitles for AI agent?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` extracts video metadata; `yt-dlp --write-sub --skip-download "URL"` extracts subtitles. Supports multiple languages, no API key required.
</details>

<details>
<summary><strong>Reddit returns 403 from server / datacenter IP blocked?</strong></summary>

Agent Reach uses [rdt-cli](https://github.com/public-clis/rdt-cli) for Reddit. Since 2024, Reddit requires authentication for all API requests. Install with `pipx install rdt-cli`, then run `rdt login` (auto-extracts cookies from your browser). Your agent can then search with `rdt search "query"` and read full posts + comments with `rdt read POST_ID`.
</details>

<details>
<summary><strong>Does Agent Reach work with Claude Code / Cursor / Windsurf / OpenClaw?</strong></summary>

Yes! Agent Reach is an installer + configuration tool. Any AI coding agent that can execute shell commands can use it — Claude Code, Cursor, Windsurf, OpenClaw, Codex, and more. Just `pip install agent-reach`, run `agent-reach install`, and the agent can start using the upstream tools immediately.
</details>

<details>
<summary><strong>Is Agent Reach free? Any API costs?</strong></summary>

100% free and open source. All backends (twitter-cli, rdt-cli, xhs-cli, yt-dlp, Jina Reader, Exa) are free tools that don't require paid API keys. The only optional cost is a residential proxy (~$1/month) if you need Bilibili access from a server. Reddit works free via rdt-cli without any proxy.
</details>

<details>
<summary><strong>Free alternative to Twitter API for web scraping?</strong></summary>

Agent Reach uses twitter-cli which accesses Twitter via cookie auth — same as your browser session. No API fees, no rate limit tiers, no developer account needed. Supports search, read tweets, read profiles, and timelines.
</details>

<details>
<summary><strong>How to read XiaoHongShu / 小红书 content programmatically?</strong></summary>

Install `pipx install xiaohongshu-cli`, then `xhs login` (auto-extracts cookies from browser). Your agent can then use `xhs search "query"` to search notes, `xhs read NOTE_ID` to read details, `xhs comments NOTE_ID` to view comments. No Docker needed.
</details>

<details>
<summary><strong>How to parse Douyin / 抖音 videos with AI agent?</strong></summary>

Install douyin-mcp-server, then your agent can use `mcporter call 'douyin.parse_douyin_video_info(share_link: "share_url")'` to parse video info and get watermark-free download links. No login required — just share the Douyin link. See https://github.com/yzfly/douyin-mcp-server
</details>

<details>
<summary><strong>How to extract scripts from both Douyin and XiaoHongShu with one MCP?</strong></summary>

If you want one MCP server that can handle:

- Douyin videos
- XiaoHongShu video notes
- XiaoHongShu image notes

and directly write `script.md` + `info.json`, you can point the existing `douyin` mcporter alias at:

- https://github.com/JNHFlow21/social-post-extractor-mcp

It keeps backward compatibility with:

- `parse_douyin_video_info`
- `get_douyin_download_link`
- `extract_douyin_text`

and adds unified tools:

- `parse_social_post_info`
- `extract_social_post_script`

This is useful when your agent workflow is “paste a link, get a script file”.
</details>

---

## Credits

[twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [douyin-mcp-server](https://github.com/yzfly/douyin-mcp-server) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## Contact

- 📧 **Email:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

For collaboration or questions, add me on WeChat — I'll invite you to the community group:

<p align="center">
  <img src="wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> For bug reports and feature requests, please use [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues) — easier to track.

## License

[MIT](../LICENSE)

## Friends

[FluxNode](https://fluxnode.org) — Low-cost AI API gateway, 90% off official pricing, pay-as-you-go or subscription. Works with OpenClaw, Claude Code, and any Agent.

[OpenClaw for Enterprise](https://github.com/littleben/openclaw-for-enterprise) — Enterprise-grade multi-user OpenClaw deployment, use AI directly in Feishu/Lark, container isolation, one-command management.

[OpenClaw on Tencent Cloud](https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&lang=en&pg=) — One-click OpenClaw on Tencent Cloud: chat to connect Agent Reach & unlock internet power.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
