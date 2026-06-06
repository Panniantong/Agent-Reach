# Agent Reach — Installation Guide (English)

> 🌐 **English is active when `AGENT_REACH_LANG=en` is set.**
> The install commands below use `AGENT_REACH_LANG=en` so you get English
> output, doctor reports, and skill files automatically. Omit it if you
> prefer Chinese.

## For Humans

Copy this to your AI Agent:

```
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install_en.md
```

> 🛡️ **Security-conscious?** Use safe mode:
> ```
> Install Agent Reach (safe mode): https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> Use --safe flag when installing
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
# Preferred: pipx (most convenient)
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto

# If your Python is from Homebrew / gets PEP 668 (externally-managed-environment)
# use a virtual environment:
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

**Safe mode / Dry run:**

```bash
agent-reach install --env=auto --safe      # Check only, no auto-install
agent-reach install --env=auto --dry-run   # Preview what would be done
```

### Step 2: Ask the user which optional channels they want

After installing the basics, **ask the user** which additional channels they need. Present this list:

> Basic channels are installed! I can now search the web, watch YouTube, read GitHub, and more.
>
> These optional channels are also available. Which ones do you need?
>
> - 🐦 **Twitter/X** — Search tweets, view timeline (needs login cookie)
> - 📰 **Weibo** — Trending, search, user feeds
> - 💬 **WeChat Articles** — Search and read Official Account articles
> - 📈 **Xueqiu** — Stock quotes, trending posts (needs login cookie)
> - 🎙️ **Xiaoyuzhou Podcast** — Audio transcription (needs free Groq Key)
> - 📕 **XiaoHongShu** — Read, search, post (needs login)
> - 📖 **Reddit** — Search and read posts
> - 📺 **Bilibili (full)** — Hot, rankings, search
> - 🎵 **Douyin** — Video parsing
> - 💼 **LinkedIn** — Profiles, job search
>
> Tell me which ones, e.g. "install Twitter and Weibo." Or say "install all."

Based on the user's choice, run:

```bash
agent-reach install --env=auto --channels=twitter,weibo   # Example
agent-reach install --env=auto --channels=all              # Everything
```

Supported channel names: `twitter`, `weibo`, `wechat`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `bilibili`, `douyin`, `linkedin`, `all`

### Step 3: Fix what's broken

Run `agent-reach doctor` and check the output.

Try to get as many channels to ✅ as possible. If something requires elevated permissions or system changes, ask the user first.

### Step 4: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing.

> 🍪 **Cookie import (for all platforms that need login):**
>
> 1. User logs into the platform in their browser
> 2. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
> 3. Click extension → Export → Header String
> 4. Paste the exported string to the agent
>
> **Local computer users** can also use `agent-reach configure --from-browser chrome` for one-click auto-extraction (supports Twitter + XiaoHongShu + Xueqiu).

## Quick Reference

| Command | What it does |
|---------|-------------|
| `agent-reach install --env=auto` | Install core channels (lightweight, zero-config) |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Quick health + update check (for scheduled tasks) |
| `agent-reach check-update` | Check for new versions |
| `agent-reach configure twitter-cookies "..."` | Unlock Twitter search + posting |
| `agent-reach configure proxy URL` | Unlock Reddit + Bilibili on servers |
| `agent-reach configure groq-key gsk_xxx` | Unlock Xiaoyuzhou podcast transcription |