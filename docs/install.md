# Agent Reach — Installation Guide

## For Humans

Copy this to your AI Agent:

```
Help me install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

> 🛡️ **Security-conscious?** Use safe mode — it won't auto-install system packages:
> ```
> Help me install Agent Reach (safe mode): https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> Use the --safe flag during installation
> ```

---

## For AI Agents

### Goal

Install Agent Reach and all upstream tools so your user's agent has full internet access. After installation, you'll use the upstream tools directly (twitter-cli, rdt-cli, xhs-cli, yt-dlp, mcporter, gh CLI, etc.) — Agent Reach is just the installer and health checker.

### ⚠️ Boundaries

When fixing issues, stay within these limits:

- **DO NOT** run commands with `sudo` unless the user explicitly approved
- **DO NOT** modify system files outside `~/.agent-reach/`
- **DO NOT** install packages not listed in this guide
- **DO NOT** disable firewalls, security settings, or system protections
- **DO NOT** clone repos, create files, or run commands inside the agent workspace / working directory
- If something requires elevated permissions, **tell the user** what's needed and let them decide

### 📁 Directory Rules

All Agent Reach files go in dedicated directories — **never in the agent workspace**:

| Purpose | Directory | Example |
|---------|-----------|---------|
| Config & tokens | `~/.agent-reach/` | `~/.agent-reach/config.json` |
| Upstream tool repos | `~/.agent-reach/tools/` | `~/.agent-reach/tools/douyin-mcp-server/` |
| Temporary files | `/tmp/` | `/tmp/yt-dlp-output/` |
| Skills | `~/.openclaw/skills/agent-reach/` | SKILL.md |

**Why?** If you clone repos or create files in the workspace, it pollutes the user's project directory and can break their agent over time. Keep the workspace clean.

### Step 1: Install the basics

```bash
# Recommended: pipx (the easiest option)
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto

# If your Python comes from Homebrew / you hit PEP 668 (externally-managed-environment)
# install inside a virtual environment:
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

This installs core infrastructure (gh CLI, Node.js, mcporter, Exa search, yt-dlp config) and activates these zero-config channels:

- Web (Jina Reader), YouTube, GitHub, RSS, Exa Search, V2EX, Bilibili (basic)

> 💡 **macOS / Homebrew Python reporting `externally-managed-environment`?**
> This is PEP 668 protection, not a problem with Agent Reach itself. Prefer `pipx install ...`, or create a `venv` first and then install.

**Safe mode / Dry run:**

```bash
agent-reach install --env=auto --safe      # Check only, no auto-install
agent-reach install --env=auto --dry-run   # Preview what would be done
```

### Step 2: Ask the user which optional channels they want

After installing the basics, **ask the user** which additional channels they need. Present this list:

> The core channels are installed! You can now ask me to search the web, watch YouTube, read GitHub, and more.
>
> There are also these optional channels — which ones do you need?
>
> - 🐦 **Twitter/X** — Search tweets, view timelines (login cookie required)
> - 📰 **Weibo** — Trending, search, user feeds
> - 💬 **WeChat Official Account** — Search and read official-account articles
> - 📈 **Xueqiu** — Stock quotes, hot posts (login cookie required)
> - 🎙️ **Xiaoyuzhou Podcast** — Audio-to-text (free Groq key required)
> - 📕 **XiaoHongShu** — Read, search, post (login required)
> - 📖 **Reddit** — Search and read posts
> - 📺 **Bilibili (full version)** — Trending, rankings, search
> - 🎵 **Douyin** — Video parsing
> - 💼 **LinkedIn** — Profiles, job search
>
> Tell me which ones you want, for example "install Weibo and Twitter for me". Or say "install everything".

Based on the user's choice, run:

```bash
agent-reach install --env=auto --channels=twitter,weibo   # Example: user chose Twitter + Weibo
agent-reach install --env=auto --channels=all              # User wants everything
```

Supported channel names: `twitter`, `weibo`, `wechat`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `bilibili`, `douyin`, `linkedin`, `all`

### Step 3: Fix what's broken

Run `agent-reach doctor` and check the output.

Try to get as many channels to ✅ as possible. If something failed during install or shows as ❌/⚠️ in doctor, diagnose the problem and try to fix it — but stay within the boundaries above. If a fix requires elevated permissions or system changes, ask the user first.

Only ask the user when you genuinely need their input (credentials, permissions, etc.).

### Step 3: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing:

> 🔒 **Security tip:** For platforms that need cookies (Twitter, XiaoHongShu), we recommend using a **dedicated/secondary account** rather than your main account. Cookie-based auth carries two risks:
> 1. **Account ban** — platforms may detect non-browser API calls and restrict or ban the account
> 2. **Credential exposure** — cookies grant full account access; using a secondary account limits the blast radius if credentials are ever compromised

> 🍪 **Cookie import (common to all platforms that require login):**
>
> For all platforms that need a cookie (Twitter, XiaoHongShu, Xueqiu, etc.), **prefer importing via Cookie-Editor** — it's the simplest and most reliable method:
> 1. The user logs in to the platform in their own browser
> 2. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
> 3. Click the extension → Export → Header String
> 4. Send the exported string to the Agent
>
> **Local-computer users** can also use `agent-reach configure --from-browser chrome` to auto-extract everything in one step (supports Twitter + XiaoHongShu + Xueqiu).

**Twitter search & posting:**
> "To unlock Twitter search, I need your Twitter cookies. Install the Cookie-Editor Chrome extension, go to x.com/twitter.com, click the extension → Export → Header String, and paste it to me."

```bash
agent-reach configure twitter-cookies "PASTED_STRING"
```

> **Proxy notes (for networks that require circumventing restrictions, e.g. mainland China):**
>
> twitter-cli and rdt-cli are Python-based; in networks that require a proxy, you can configure one via environment variables.
>
> **What you (the Agent) need to do:**
> 1. Confirm the user has configured a proxy: `agent-reach configure proxy http://user:pass@ip:port`
> 2. Set the environment variables: `export HTTP_PROXY="..." HTTPS_PROXY="..."`
> 3. Agent Reach handles the rest automatically — no extra steps required from the user
>
> If the user reports "fetch failed", see [troubleshooting.md](troubleshooting.md)

**Reddit & Bilibili full access (server users):**
> "Reddit and Bilibili block server IPs. To unlock full access, I need a residential proxy. You can get one at https://webshare.io ($1/month). Send me the proxy address."

```bash
agent-reach configure proxy http://user:pass@ip:port
```

**XiaoHongShu (xhs-cli):**
> "XiaoHongShu is accessed via xhs-cli — a one-line pipx install, no Docker required."

```bash
pipx install xiaohongshu-cli
xhs login
```

> `xhs login` automatically extracts the cookie from the browser. If auto-extraction fails, you can import it manually:
>
> **Manual cookie import (Cookie-Editor method):**
> 1. The user logs in to XiaoHongShu (xiaohongshu.com) in their own browser
> 2. Use the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension to export the cookie (either JSON or Header String format works)
> 3. Send the cookie string to the Agent
> 4. The Agent runs a command to complete login:
>
> ```bash
> # JSON format (Cookie-Editor → Export → JSON)
> agent-reach configure xhs-cookies '[{"name":"web_session","value":"xxx","domain":".xiaohongshu.com",...}]'
>
> # Or Header String format (Cookie-Editor → Export → Header String)
> agent-reach configure xhs-cookies "key1=val1; key2=val2; ..."
> ```
>
> **Note:** We recommend the Cookie-Editor export method — do not rely on QR-code login.
>
> **Alternative: Docker MCP**
> If you're already using the [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker approach, it also works:
> ```bash
> docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp
> mcporter config add xiaohongshu http://localhost:18060/mcp
> ```

**Weibo (mcp-server-weibo):**
> "Weibo is installed by default and works out of the box. You can search Weibo content, view trending topics, and fetch user feeds and comments."

If auto-install fails, install manually:

```bash
pip install git+https://github.com/Panniantong/mcp-server-weibo.git
mcporter config add weibo --command 'mcp-server-weibo'
```

> No login, no cookie, no proxy required. Overseas servers can access it directly.

**Xueqiu (stock quotes + hot posts):**
> "Xueqiu requires a cookie after login. Log in to xueqiu.com in Chrome first, then run:"

```bash
agent-reach configure --from-browser chrome
```

> The cookie is auto-extracted along with the other platforms.

**Xiaoyuzhou Podcast (Groq Whisper):**
> "Xiaoyuzhou podcast transcription is installed by default — all it needs is a free Groq API key."

The script is installed automatically with Agent Reach; the user only needs to provide a key:

```bash
agent-reach configure groq-key gsk_xxxxx
```

> **Get a Groq API key (free, no credit card, takes 30 seconds):**
> 1. Open https://console.groq.com
> 2. Sign in with a Google/GitHub account (or sign up)
> 3. Left-hand menu → API Keys → Create API Key
> 4. Copy the key (starts with `gsk_`) and send it to the Agent
>
> **How to use it:**
> The user sends a Xiaoyuzhou link to the Agent, and the Agent calls automatically:
> ```bash
> bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh https://www.xiaoyuzhoufm.com/episode/xxxxx
> ```
>
> It automatically downloads the audio → transcodes and segments it → transcribes via Groq Whisper → outputs a full text transcript.
>
> **Free quota and limits:**
> - About 2 hours of audio per hour (7,200 seconds); once exceeded, it auto-recovers after 15 minutes
> - More than enough for listening to a few episodes a day
> - High transcription quality (Whisper large-v3), but no speaker diarization
> - For podcasts longer than 2 hours, process them in batches

**Douyin (douyin-mcp-server):**
> "Douyin video parsing requires an MCP service. After installing douyin-mcp-server, you can parse videos and get watermark-free download links."

```bash
# 1. Install
pip install douyin-mcp-server

# 2. Start the HTTP service (port 18070)
# Option A: use uv (recommended)
mkdir -p ~/.agent-reach/tools && cd ~/.agent-reach/tools
git clone https://github.com/yzfly/douyin-mcp-server.git && cd douyin-mcp-server
uv sync && uv run python run_http.py

# Option B: start directly with Python
python -c "
from douyin_mcp_server.server import mcp
mcp.settings.host = '127.0.0.1'
mcp.settings.port = 18070
mcp.run(transport='streamable-http')
"

# 3. Register with mcporter
mcporter config add douyin http://localhost:18070/mcp
```

> No authentication is needed to parse video info and get download links.
> If you want the AI speech-recognition transcript-extraction feature, you need to configure a SiliconFlow API key (`export API_KEY="sk-xxx"`).
>
> See https://github.com/yzfly/douyin-mcp-server

**Optional implementation: Douyin + XiaoHongShu unified extractor**
> "If you want to unify Douyin and XiaoHongShu into a single MCP that directly outputs `script.md` and `info.json`, you can switch to social-post-extractor-mcp."

Use cases:

- Transcribe Douyin videos to text
- Transcribe XiaoHongShu video notes to text
- Extract the body text + image text of XiaoHongShu image notes

Compatibility:

- Can still be registered under the `douyin` mcporter server name
- Compatible with the old tool names `parse_douyin_video_info` / `get_douyin_download_link` / `extract_douyin_text`
- Also adds `parse_social_post_info` / `extract_social_post_script`

Example configuration:

```bash
git clone https://github.com/JNHFlow21/social-post-extractor-mcp.git
cd social-post-extractor-mcp
uv sync

mcporter config add douyin \
  --command /bin/zsh \
  --arg -lc \
  --arg "cd '$PWD' && exec '.venv/bin/python' -m social_post_extractor_mcp" \
  --env ASR_PROVIDER=bailian \
  --env ASR_MODEL=paraformer-v2 \
  --env VISION_PROVIDER=bailian \
  --env VISION_MODEL=qwen3-vl-flash \
  --env CLEAN_PROVIDER=bailian \
  --env CLEAN_MODEL=qwen-flash \
  --env BAILIAN_API_KEY=YOUR_BAILIAN_API_KEY
```

> This implementation is better suited to a "hand the link straight to the Agent and get a script file back" workflow.
>
> See https://github.com/JNHFlow21/social-post-extractor-mcp

**LinkedIn (optional — linkedin-scraper-mcp):**
> "Basic LinkedIn content can be read via Jina Reader. Full features (profile details, job search) require linkedin-scraper-mcp."

```bash
pip install linkedin-scraper-mcp
```

> **Login method (requires a browser UI):**
>
> linkedin-scraper-mcp logs in using a Chromium browser, so you need to be able to see the browser window.
>
> - **Local computer (has a desktop):** run directly:
>   ```bash
>   linkedin-scraper-mcp --login --no-headless
>   ```
>   The browser will pop up; just log in to LinkedIn manually.
>
> - **Server (no UI):** you need to operate it through a VNC remote desktop:
>   ```bash
>   # 1. Install and start VNC on the server (skip if you already have it)
>   apt install -y tigervnc-standalone-server
>   vncserver :1 -geometry 1280x720
>   
>   # 2. Connect to SERVER_IP:5901 with a VNC client
>   
>   # 3. In a terminal on the VNC desktop, run:
>   export DISPLAY=:1
>   linkedin-scraper-mcp --login --no-headless
>   ```
>   Once you see the browser in VNC, log in manually. After a successful login, the session is saved to `~/.linkedin-mcp/profile/`.
>
> **After login, start the MCP service:**
> ```bash
> linkedin-scraper-mcp --transport streamable-http --port 8001
> mcporter config add linkedin http://localhost:8001/mcp
> ```
>
> See https://github.com/stickerdaniel/linkedin-mcp-server

### Step 4: Final check

Run `agent-reach doctor` one final time and report the results to your user.

### Step 5: Set up daily monitoring (OpenClaw only)

If you are running inside **OpenClaw**, ask your user:

> "Agent Reach is installed. Want me to set up a task that checks it automatically every day? It will keep an eye on whether these channels are working and whether there are new versions. It only notifies you when there's a problem — otherwise it stays quiet."

If the user agrees, create a **cron job** (daily, `sessionTarget: "isolated"`, `delivery: "announce"`) with this task:

```
Run the agent-reach watch command.
If the output contains "all good", do not notify the user — exit silently.
If the output contains problems (❌ ⚠️) or a new version (🆕), send the full report to the user and suggest a fix.
If a new version is available, ask the user whether to upgrade (upgrade command: pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip).
```

If the user wants a different agent to handle it, let them choose.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `agent-reach install --env=auto` | Install core channels (lightweight, zero-config) |
| `agent-reach install --env=auto --channels=twitter,weibo` | Install core + optional channels |
| `agent-reach install --env=auto --channels=all` | Install everything |
| `agent-reach install --env=auto --safe` | Safe setup (no auto system changes) |
| `agent-reach install --env=auto --dry-run` | Preview what would be done |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Quick health + update check (for scheduled tasks) |
| `agent-reach check-update` | Check for new versions |
| `agent-reach configure twitter-cookies "..."` | Unlock Twitter search + posting |
| `agent-reach configure proxy URL` | Unlock Reddit + Bilibili on servers |
| `agent-reach configure groq-key gsk_xxx` | Unlock Xiaoyuzhou podcast transcription |

After installation, use upstream tools directly. See SKILL.md for the full command reference:

| Platform | Upstream Tool | Example |
|----------|--------------|---------|
| Twitter/X | `twitter` | `twitter search "query" -n 10` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `yt-dlp` + `bili` | `bili hot` / `bili search "query" --type video` |
| Reddit | `rdt` | `rdt search "query"` / `rdt read POST_ID` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call 'exa.web_search_exa(...)'` |
| XiaoHongShu | `mcporter` | `mcporter call 'xiaohongshu.search_feeds(...)'` |
| Weibo | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |
| Douyin | `mcporter` | `mcporter call 'douyin.parse_douyin_video_info(...)'` |
| LinkedIn | `mcporter` | `mcporter call 'linkedin.get_person_profile(...)'` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |
