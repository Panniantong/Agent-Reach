# Agent Reach — Installation Guide

## For Humans

Copy this to your AI Agent:

```
Help me install Agent Reach:https://raw.githubusercontent.com/jermiah/Agent-Reach/main/docs/install.md
```

> 🛡️ **Safe by default:** `agent-reach install` only checks the machine and lists missing dependencies:
> ```
> Help me with security checks and install Agent Reach: https://raw.githubusercontent.com/jermiah/Agent-Reach/main/docs/install.md
> ```
> Only use `--system` after the user explicitly approves system-level installs and configuration writes.

---

## For AI Agents

### Goal

Install Agent Reach and all upstream tools so your user's agent has full internet access. After installation, you'll use the upstream tools directly (OpenCLI, twitter-cli, bili-cli, rdt-cli, yt-dlp, mcporter, gh CLI, etc.) — Agent Reach is the selector, installer, health checker and router, never a wrapper.

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
| Upstream tool repos | `~/.agent-reach/tools/` | `~/.agent-reach/tools/xiaoyuzhou/` |
| Temporary files | `/tmp/` | `/tmp/yt-dlp-output/` |
| Skills | `~/.openclaw/skills/agent-reach/` | SKILL.md |

**Why?** If you clone repos or create files in the workspace, it pollutes the user's project directory and can break their agent over time. Keep the workspace clean.

### Step 1: Install the basics

```bash
# recommend:pipx (The most worry-free)
pipx install https://github.com/jermiah/Agent-Reach/archive/main.zip
agent-reach install --env=auto               # Read-only check (default)
# After the user explicitly approves system changes:
agent-reach install --env=auto --system

# if your Python from Homebrew / meet PEP 668 (externally-managed-environment)
# Install using virtual environment:
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/jermiah/Agent-Reach/archive/main.zip
agent-reach install --env=auto               # Read-only check (default)
# After the user explicitly approves system changes:
agent-reach install --env=auto --system
```

> 💡 **Windows / Microsoft Store Python alias?**
> If `python3 --version` opens the Microsoft Store, or `where python3` points to
> `...\AppData\Local\Microsoft\WindowsApps\python3.exe`, indicating that `python3` is Windows
> The Store alias is not available for Python installations. Please use Python Launcher `py -3` instead, or `python.exe` in the actual installation directory.
>
> PowerShell example:
> ```powershell
> py -3 -m venv $env:USERPROFILE\.agent-reach-venv
> $env:USERPROFILE\.agent-reach-venv\Scripts\Activate.ps1
> python -m pip install https://github.com/jermiah/Agent-Reach/archive/main.zip
> agent-reach install --env=auto
> ```

The default command checks core infrastructure (gh CLI, Node.js, mcporter, Exa search, yt-dlp config) without changing the host. With explicit `--system` approval it installs/configures the missing pieces and activates these zero-config channels:

- Web (Jina Reader), YouTube, GitHub, RSS, Exa Search, V2EX, Bilibili (basic)

> 💡 **macOS/Homebrew Python prompt `externally-managed-environment`?**
> This is a PEP 668 protection, not an issue with Agent Reach itself. Use `pipx install ...` first, or create `venv` first and then install it.

**Install modes:**

```bash
agent-reach install --env=auto             # Check only; safe default
agent-reach install --env=auto --safe      # Same check-only behavior (compatibility)
agent-reach install --env=auto --system    # Explicitly allow external/system installs
agent-reach install --env=auto --dry-run   # Preview what --system would do
```

### Step 2: Ask the user which optional channels they want

After installing the basics, **ask the user** which additional channels they need. Present this list:

> The basic channels are installed! You can now let me search the web, watch YouTube, read GitHub, etc.
>
> Among these alternative channels, which ones do you need?
>
> - 🌟 **OpenCLI** (Desktop recommendation) - One installation can provide Reddit/Facebook/Instagram/Bilibili subtitles/Twitter alternatives and serve as XiaoHongShu desktop backend; XiaoHongShu only uses Chrome sessions that the user already has and explicitly controls
> - 🐦 **Twitter/X** — Search tweets and view timeline (requires cookie login)
> - 📈 **Xueqiu** — Stock quotes, popular posts (requires login cookie)
> - 🎙️ **Xiaoyuzhou Podcast** — audio to text (requires free Groq Key)
> - 📕 **XiaoHongShu** — search, read, comment (OpenCLI uses existing session; MCP/legacy tool uses Cookie-Editor)
> - 📖 **Reddit** — Search and read posts (requires login: desktop OpenCLI or rdt-cli + Cookie)
> - 📘 **Facebook** — search, homepage, feed, group list (OpenCLI on desktop, reuse Chrome login state)
> - 📷 **Instagram** — User search, Profile, user’s recent posts, Explore (OpenCLI on desktop, reuse Chrome login state)
> - 📺 **Bilibili full version** — popular, ranking, search, video details (bili-cli, no login required)
> - 💼 **LinkedIn** — Profile, job search
> - 🎯 **Boss Zhipin** — Search positions + JD full text (local Chrome only; users log in manually)
>
> Tell me what you want, such as "Help me install XiaoHongShu and Twitter", "Help me install Facebook and Instagram". In other words, "install them all".

Based on the user's choice, run:

```bash
agent-reach install --env=auto --system --channels=opencli,xiaohongshu   # Desktop user chose XHS
agent-reach install --env=auto --system --channels=facebook,instagram    # Desktop Meta channels
agent-reach install --env=local --system --channels=boss                # Desktop Boss Zhipin
agent-reach install --env=auto --system --channels=all                   # User approved everything
```

Supported channel names: `opencli`, `twitter`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `facebook`, `instagram`, `bilibili`, `linkedin`, `boss`, `all`

### Step 3: Fix what's broken

Run `agent-reach doctor` and check the output.

Try to get as many channels to ✅ as possible. If something failed during install or shows as ❌/⚠️ in doctor, diagnose the problem and try to fix it — but stay within the boundaries above. If a fix requires elevated permissions or system changes, ask the user first.

Only ask the user when you genuinely need their input (credentials, permissions, etc.).

### Step 3: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing:

> 🔒 **Security tip:** For platforms that need cookies or browser sessions (Twitter, XiaoHongShu, Reddit, Facebook, Instagram, Boss Zhipin), we recommend using a **dedicated/secondary account** rather than your main account. Cookie/browser-session auth carries two risks:
> 1. **Account ban** — platforms may detect non-browser API calls and restrict or ban the account
> 2. **Credential exposure** — cookies grant full account access; using a secondary account limits the blast radius if credentials are ever compromised

> 🍪 **Cookie / Login status: **
>
> For platforms where traditional CLI requires cookies (Twitter, Xueqiu, etc.), **import using Cookie-Editor** is preferred. This is the simplest and most reliable way:
> 1. Users log in to the corresponding platform on their own browser
> 2. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
> 3. Click Plug-in → Export → Header String
> 4. Send the exported string to Agent
>
> Twitter only accepts content explicitly exported by the user via Cookie-Editor. Agent Reach does not perform XiaoHongShu login for the user, nor does it read XiaoHongShu browser cookies; XiaoHongShu OpenCLI only uses Chrome sessions that the user already has and explicitly controls. When there is no existing session, use Cookie-Editor to export and configure xiaohongshu-mcp / legacy tool instead. Xueqiu and Bilibili can be imported explicitly by platform, such as `agent-reach configure --from-browser chrome --platform xueqiu`; the command will not scan or save other platforms.

**Twitter search & posting:**
> "To unlock Twitter search, I need your Twitter cookies. Install the Cookie-Editor Chrome extension, go to x.com/twitter.com, click the extension → Export → Header String, and paste it to me."

```bash
agent-reach configure twitter-cookies
```

This will save `twitter_auth_token` and `twitter_ct0` to Agent Reach's own
`doctor` configuration check. `doctor` will not execute the upstream `twitter status` in real time, nor will it modify
Current Shell. Before running `twitter search/read/...` directly, it must be explicitly set in the process environment:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
twitter search "query" -n 10
```

> **Agent instructions (mainland China and other network environments that require circumvention): **
>
> twitter-cli and rdt-cli use Python, and the proxy can be configured through environment variables in network environments that require a proxy.
>
> **What you (Agent) need to do:**
> 1. Confirm that the user is assigned a proxy: `agent-reach configure proxy` (hidden input)
> 2. Set environment variable: `export HTTP_PROXY="..." HTTPS_PROXY="..."`
> 3. Agent Reach will automatically handle the rest without requiring additional operations from the user.
>
> If users report "fetch failed", refer to [troubleshooting.md](troubleshooting.md)

**Reddit (login is mandatory — no zero-config path):**
> Reddit's anonymous interface has been blocked, and the official API requires manual approval. Desktop users prefer OpenCLI (available after logging into reddit.com in the browser); server/existing users use rdt-cli:

```bash
# PyPI behind, from GitHub Pack (with code _RDT_GIT_SOURCE same pinned version)
pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'
rdt login   # Automatic extraction of browsers Cookie;Press when the server does not have a browser doctor Prompt to write manually Cookie
```

> Mainland China needs a proxy to access Reddit; when the server IP is risk-controlled, a residential proxy can be configured (such as https://webshare.io, about $1/month):
> ```bash
> agent-reach configure proxy
> ```

**XiaoHongShu / XiaoHongShu (multiple backends, choose according to the environment):**

> **Authentication Boundary:** Agent Reach does not perform XiaoHongShu login for the user, nor does it read the browser
> Cookies. OpenCLI only uses an existing and explicitly controlled Chrome session;
> `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI or Chrome.
> If there is no existing session, do not log in automatically; instead use Cookie-Editor to manually export and configure
> xiaohongshu-mcp or legacy tool:
>
> ```bash
> agent-reach configure xhs-cookies
> ```
>
> This explicit command will save/import the xiaohongshu.com same-domain cookie set provided by the user; please confirm first
> Cookie name and scope. Non-xiaohongshu.com domain cookies will be ignored.
>
> **Desktop (OpenCLI recommended):**

```bash
agent-reach install --system --channels opencli
```

> After installation, guide the user to do the only manual operation (Chrome security restrictions cannot do it for you):
> 1. Open https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
> 2. Click "Add to Chrome"
> 3. Run `opencli doctor` verification (it will be successful if Extension: connected is displayed)
>
> When AUTH_REQUIRED and the user does not have an existing session, do not automatically log in for the user; instead use the following
> xiaohongshu-mcp / Legacy tool Cookie-Editor route.
>
> **Server/no desktop environment (xiaohongshu-mcp):**
> 1. Download the corresponding platform binary from https://github.com/xpzouying/xiaohongshu-mcp/releases to `~/.agent-reach/tools/`
> 2. Start the service (the first run will automatically download about 150MB of headless browser, wait patiently for completion)
> 3. Follow the above Cookie-Editor process to manually import cookies
> 4. Access: `mcporter config add xiaohongshu http://localhost:18060/mcp --scope home`
> 5. Be sure to bring `--timeout 120000` when calling
>
> **Existing users (xhs-cli):** The installed xhs-cli continues to work as an alternative backend
> (upstream maintenance stopped in March 2026, new installation is not recommended); authentication still uses the above Cookie-Editor
> Manual export process.

**Facebook / Instagram (Desktop OpenCLI):**
> These two platforms use OpenCLI: reuse the user's own Chrome login status, do not save the account password, and do not go through the Meta Graph API approval flow. Support is not recommended for server/desktop-less environments.

```bash
agent-reach install --system --channels facebook,instagram
```

> After installation:
> 1. Confirm that Chrome has installed the OpenCLI extension and passed `opencli doctor`
> 2. Log in to facebook.com / instagram.com in Chrome
> 3. Agent calls directly:
>    ```bash
>    opencli facebook search "query" -f yaml
>    opencli facebook profile zuck -f yaml
>    opencli facebook groups -f yaml
> opencli instagram search "query" -f yaml # User search
>    opencli instagram profile nasa -f yaml
> opencli instagram user nasa -f yaml # Specify the latest posts of the user
>    ```
>
> Facebook Groups currently only commits to reading the group list/recent updates visible after the user logs in, and does not commit to any group posts and comments API. Instagram's search is a user search, not a site-wide post keyword search; if a 429/login error is prompted, first ask the user to log in again in Chrome and reduce the frequency.

**Xueqiu/Xueqiu (Stock Quotes + Popular Posts):**
> "Xueqiu requires login cookies. Please log in to xueqiu.com in Chrome first, and then run:"

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

> Only the minimum cookies required by Xueqiu will be read and saved; other platforms will not be read incidentally.

**Xiaoyuzhou Podcast / Xiaoyuzhou Podcast (Groq Whisper):**
> "Xiaoyuzhou Podcast to Text is installed by default and only requires a free Groq API Key."

The script is automatically installed with Agent Reach, the user only needs to provide the Key:

```bash
agent-reach configure groq-key
```

> **Get Groq API Key (free, no credit card required, 30 seconds): **
> 1. Open https://console.groq.com
> 2. Log in (or register) with your Google/GitHub account
> 3. Left menu → API Keys → Create API Key
> 4. Copy the Key (starting with `gsk_`) and send it to the Agent
>
> **How ​​to use:**
> The user sends a Xiaoyuzhou link to the Agent, and the Agent automatically calls:
> ```bash
> bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh https://www.xiaoyuzhoufm.com/episode/xxxxx
> ```
>
> Automatically download audio → Transcode and slice → Groq Whisper transcription → Output complete Chinese transcript.
>
> **Free Quota and Limitations:**
> - About 2 hours of audio (7200 seconds) per hour, automatically resume after 15 minutes
> - Listening to a few podcasts every day is enough
> - High transcription quality (Whisper large-v3), but does not differentiate between speakers
> - Podcasts longer than 2 hours are recommended to be processed in batches

**LinkedIn (optional — mcp-server-linkedin):**
> "Basic LinkedIn content can be read with Jina Reader. Full functionality (Profile details, talent and job search) requires mcp-server-linkedin."

> **Configuration method (stdio recommended):**
> First install `uv` according to the official instructions (`uvx` will be provided at the same time):
> https://docs.astral.sh/uv/getting-started/installation/
>
> ```bash
> mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home
> ```
>
> `uvx` will obtain and start the latest version of the service on demand, without the need to install additional Python packages or resident HTTP services.
>
> **First time login (requires browser interface):**
> ```bash
> uvx mcp-server-linkedin@latest --login
> ```
> Manually log in to LinkedIn after the browser pops up; the login status will be saved to `~/.linkedin-mcp/profile/`. Servers without desktops need to run the same login command in a visible desktop such as VNC.
>
> See https://github.com/stickerdaniel/linkedin-mcp-server for details

**Boss Zhipin (desktop only — boss-agent-cli + CDP):**

When the user says "help me configure Boss Zhipin", the Agent completes the part that can be completed automatically, leaving only the website login to the user:

1. First explain that you will install an upstream CLI, launch the independent Chrome configuration directory, and request system installation authorization.
2. Run after user agrees:
   ```bash
   agent-reach install --env=local --system --channels=boss
   ```
3. Start the dedicated Chrome that only binds the local loopback address according to the operating system:
   ```bash
   # macOS
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"

   # Linux
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```
   Windows PowerShell:
   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```
4. Pause and ask the user to log in manually if needed, then visually confirm the
   logged-in state (avatar in the top-right). Let the user handle QR codes or sliders.
   Agent Reach must not request passwords or log in on the user's behalf. Do not
   substitute `boss status` for this check: it only verifies local `session.enc`,
   not the dedicated Chrome session.
5. Run after the user confirms the login is complete:
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   agent-reach doctor    # look boss OK message browser in wt2 cookie Detection results
   ```

> Security Boundary: Any native process with access to debug port 9222 has full control over this Chrome.
> `--remote-debugging-address=127.0.0.1` must be used and must not be exposed to the LAN or public network; use
> Make an independent profile and reuse it for a long time. Do not delete or create a new one every time, and do not switch to daily main Chrome by default;
> Close Private Chrome when not in use. Boss does not support server/desktopless environments. The search command must include
> `--browser-source existing-browser --cdp-url http://localhost:9222`.
>
> Dependency: boss-agent-cli subsequent split PR #403–#407 has been merged into the upstream master, and the installer locks the upstream
> Fixed commit
> `4c991b77086a203173bf08a4cb64a23af6514fe6`, does not follow the branch that will move. This commit contains
> `browser_source="existing-browser"` (strict CDP), `JobItem.lid` and `job_card_browser()`. After the upstream releases the official version,
> Agent Reach should use version constraints instead.

### Step 4: Final check

Run `agent-reach doctor` one final time and report the results to your user.

### Step 5: Set up daily monitoring (OpenClaw only)

If you are running inside **OpenClaw**, ask your user:

> "Agent Reach is installed. Do you want me to set up a task to automatically check every day? It will help you keep an eye on whether these channels are normal and whether there are new versions. It will notify you only if there is a problem. If there is no problem, I will not disturb you."

If the user agrees, create a **cron job** (daily, `sessionTarget: "isolated"`, `delivery: "announce"`) with this task:

```
run agent-reach watch Order.
If the output contains"All normal", No need to notify users, End of silence.
If the output contains questions (❌ ⚠️)or new version (🆕), Send full report to user, and suggest fixes.
If a new version is available, Ask the user if they want to upgrade (Send this sentence to the user Agent can be fully updated:Help me update Agent Reach:https://raw.githubusercontent.com/jermiah/Agent-Reach/main/docs/update.md).
```

If the user wants a different agent to handle it, let them choose.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `agent-reach install --env=auto` | Read-only dependency and channel check (default) |
| `agent-reach install --env=auto --system` | Explicitly install/configure core external tools |
| `agent-reach install --env=auto --system --channels=twitter,xiaohongshu` | Install approved optional channels |
| `agent-reach install --env=local --system --channels=boss` | Install the desktop Boss strict-CDP backend |
| `agent-reach install --env=auto --system --channels=all` | Install everything after explicit approval |
| `agent-reach install --env=auto --safe` | Compatibility alias for the safe default |
| `agent-reach install --env=auto --dry-run` | Preview what would be done |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Quick health + update check (for scheduled tasks) |
| `agent-reach check-update` | Check for new versions |
| `agent-reach configure twitter-cookies` | Save Twitter cookies through a hidden prompt; direct commands still require environment variables |
| `agent-reach configure proxy` | Save proxy address via hidden input; not auto-unlock switch |
| `agent-reach configure groq-key` | Set the Xiaoyuzhou transcription API key through a hidden prompt |

After installation, use upstream tools directly. See SKILL.md for the full command reference:

| Platform | Upstream Tool | Example |
|----------|--------------|---------|
| Twitter/X | `twitter` (alternative to `opencli`) | Run `twitter search "query" -n 10` after setting up `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `bili` (subtitles go to `opencli`) | `bili search "query" --type video` / `opencli bilibili subtitle BVxxx` |
| Reddit | `opencli` (alternative `rdt`) | `opencli reddit search "query" -f yaml` / `rdt read POST_ID` |
| Facebook | `opencli` | `opencli facebook search "query" -f yaml` |
| Instagram | `opencli` | `opencli instagram user nasa -f yaml` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call exa.web_search_exa query="..." numResults=5` |
| XiaoHongShu | `opencli` (server `mcporter`) | `opencli xiaohongshu search "query" -f yaml` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |
| LinkedIn | `mcporter` | `mcporter call linkedin.get_person_profile linkedin_username="..."` |
| Boss Zhipin | `boss` / Python public API | `agent-reach doctor` (browser wt2 detection; `boss status` only reflects local session.enc); search and JD see `references/career.md` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |

> Multi-backend platforms are subject to `active_backend` of `agent-reach doctor --json`.
