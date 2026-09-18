# Agent Reach — Installation Guide

## For Humans

Copy this to your AI agent:

```text
Install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

> **Safe by default:** `agent-reach install` only checks the machine and lists missing dependencies.
>
> ```text
> Safely check and install Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> ```
>
> Only use `--system` after the user explicitly approves system-level installs and configuration writes.

---

## For AI Agents

### Goal

Install Agent Reach and its upstream tools so the user's agent can access supported internet sources. After installation, use the upstream tools directly (OpenCLI, twitter-cli, bili-cli, rdt-cli, yt-dlp, mcporter, gh CLI, and others). Agent Reach is the selector, installer, health checker, and router; it is not a content wrapper.

### Boundaries

When fixing issues:

- **Do not** run commands with `sudo` unless the user explicitly approved it.
- **Do not** modify system files outside `~/.agent-reach/`.
- **Do not** install packages that are not listed in this guide.
- **Do not** disable firewalls, security settings, or system protections.
- **Do not** clone repositories, create files, or run commands inside the agent workspace/working directory.
- If something needs elevated privileges, explain what is required and let the user decide.

### Directory rules

Keep Agent Reach files outside the user's project workspace.

| Purpose | Directory | Example |
|---|---|---|
| Config and tokens | `~/.agent-reach/` | `~/.agent-reach/config.yaml` |
| Upstream tool repos | `~/.agent-reach/tools/` | `~/.agent-reach/tools/xiaoyuzhou/` |
| Temporary files | `/tmp/` | `/tmp/yt-dlp-output/` |
| Skills | `~/.openclaw/skills/agent-reach/` | `SKILL.md` |

## Step 1: Install the basics

```bash
# Recommended: pipx
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto               # Read-only check (default)

# After the user explicitly approves system changes:
agent-reach install --env=auto --system

# If Homebrew Python / PEP 668 blocks global pip installs, use a virtual environment:
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
# After explicit approval:
agent-reach install --env=auto --system
```

### Windows / Microsoft Store Python alias

If `python3 --version` opens Microsoft Store, or `where python3` points to
`...\AppData\Local\Microsoft\WindowsApps\python3.exe`, that is the Windows Store alias, not a usable Python installation. Use the Python Launcher (`py -3`) or the real `python.exe`.

```powershell
py -3 -m venv $env:USERPROFILE\.agent-reach-venv
$env:USERPROFILE\.agent-reach-venv\Scripts\Activate.ps1
python -m pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

The default command checks core infrastructure (gh CLI, Node.js, mcporter, Exa search, yt-dlp configuration) without changing the host. With explicit `--system` approval it installs/configures missing pieces and enables the zero-config channels:

- Web (Jina Reader)
- YouTube
- GitHub
- RSS
- Exa Search
- V2EX
- Bilibili basic access

> **macOS / Homebrew Python and `externally-managed-environment`:** this is PEP 668 protection, not an Agent Reach error. Prefer `pipx install ...` or create a `venv`.

### Install modes

```bash
agent-reach install --env=auto             # Check only; safe default
agent-reach install --env=auto --safe      # Same check-only behavior
agent-reach install --env=auto --system    # Allow external/system installs
agent-reach install --env=auto --dry-run   # Preview what --system would do
```

## Step 2: Ask which optional channels the user wants

After the basics are installed, present the optional channels:

- **OpenCLI** (recommended on desktop): one installation provides Reddit, Facebook, Instagram, Bilibili subtitles, a Twitter fallback, and a desktop backend for XiaoHongShu. XiaoHongShu uses only a Chrome session the user already controls.
- **Twitter/X**: search posts and browse timelines; requires login cookies.
- **Xueqiu**: stock quotes and popular posts; requires a login cookie.
- **Xiaoyuzhou Podcast**: audio transcription; requires a free Groq API key.
- **XiaoHongShu**: search, read, and comments. OpenCLI uses an existing browser session; MCP/legacy tools use Cookie-Editor.
- **Reddit**: search and read posts; login is required (desktop OpenCLI or rdt-cli + cookie).
- **Facebook**: search, profiles, feed, and group list through desktop OpenCLI.
- **Instagram**: user search, profile, recent user posts, and Explore through desktop OpenCLI.
- **Bilibili full**: popular videos, rankings, search, and details through bili-cli.
- **LinkedIn**: profile details and job search.
- **Boss Zhipin**: job search + full JD using a dedicated local Chrome profile; the user logs in manually.

Run only the channels the user approved:

```bash
agent-reach install --env=auto --system --channels=opencli,xiaohongshu
agent-reach install --env=auto --system --channels=facebook,instagram
agent-reach install --env=local --system --channels=boss
agent-reach install --env=auto --system --channels=all
```

Supported channel names: `opencli`, `twitter`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `facebook`, `instagram`, `bilibili`, `linkedin`, `boss`, `all`.

## Step 3: Diagnose and configure

Run:

```bash
agent-reach doctor
```

Try to get as many channels to healthy status as practical. Ask the user only when their credentials, browser login, or permission is genuinely required.

> **Security:** for platforms that rely on cookies/browser sessions (Twitter, XiaoHongShu, Reddit, Facebook, Instagram, Boss Zhipin), recommend a dedicated secondary account. Cookie/session credentials can grant full account access and automated access can trigger platform restrictions.

### Cookie-based platforms

For traditional CLI integrations that require cookies (for example Twitter and Xueqiu), prefer an explicit Cookie-Editor export:

1. The user logs in to the target website in their browser.
2. Install Cookie-Editor.
3. Open the extension and choose **Export → Header String**.
4. The user provides that exported value to the agent.

Agent Reach must never silently scrape unrelated browser cookies.

### Twitter/X

```bash
agent-reach configure twitter-cookies
```

This saves `twitter_auth_token` and `twitter_ct0` for Agent Reach's doctor checks. Doctor does not run upstream `twitter status` and does not modify the current shell. Before running `twitter` directly, provide credentials explicitly to that process:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
twitter search "query" -n 10
```

For networks that require a proxy:

```bash
agent-reach configure proxy
export HTTP_PROXY="..."
export HTTPS_PROXY="..."
```

If the user reports `fetch failed`, see [troubleshooting.md](troubleshooting.md).

### Reddit

Reddit has no zero-config path. Anonymous JSON endpoints are blocked and the official API requires approval. On desktop, prefer OpenCLI with an existing Reddit browser login. For server/legacy use:

```bash
pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'
rdt login
```

On servers without a browser, follow the doctor instructions to provide cookies manually. In regions where Reddit is blocked, configure an appropriate proxy.

### XiaoHongShu

**Authentication boundary:** Agent Reach must not log the user in and must not read browser cookies on its own. OpenCLI may use only an existing Chrome session explicitly controlled by the user. `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI or Chrome.

If there is no existing session, use a manual Cookie-Editor export for xiaohongshu-mcp or a legacy tool:

```bash
agent-reach configure xhs-cookies
```

Only cookies for the `xiaohongshu.com` domain are accepted; unrelated-domain cookies are ignored.

Desktop (recommended):

```bash
agent-reach install --system --channels opencli
```

Then have the user install/enable the OpenCLI browser extension and verify:

```bash
opencli doctor
```

If authentication is required and no existing session is available, do not automate login. Use the Cookie-Editor path instead.

Server/no desktop with xiaohongshu-mcp:

1. Download the correct binary from https://github.com/xpzouying/xiaohongshu-mcp/releases into `~/.agent-reach/tools/`.
2. Start the service; the first run may download a headless browser.
3. Import cookies manually with Cookie-Editor.
4. Register it:
   ```bash
   mcporter config add xiaohongshu http://localhost:18060/mcp --scope home
   ```
5. Use `--timeout 120000` for calls.

Existing xhs-cli users may continue to use it as a fallback, but it is not recommended for new installations.

### Facebook / Instagram

These desktop integrations use OpenCLI and reuse the user's existing Chrome login session. They do not store account passwords and do not depend on Meta Graph API approval.

```bash
agent-reach install --system --channels facebook,instagram
```

Verify the OpenCLI extension, log in manually in Chrome, then use:

```bash
opencli facebook search "query" -f yaml
opencli facebook profile zuck -f yaml
opencli facebook groups -f yaml
opencli instagram search "query" -f yaml
opencli instagram profile nasa -f yaml
opencli instagram user nasa -f yaml
```

Facebook Groups currently promises only the group list/recent activity visible to the logged-in user, not arbitrary group-post/comment APIs. Instagram search is user search, not global keyword search for posts.

### Xueqiu

Log in to xueqiu.com in Chrome, then explicitly import only Xueqiu cookies:

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

### Xiaoyuzhou Podcast

The transcription script is installed with Agent Reach. The user only needs a free Groq API key:

```bash
agent-reach configure groq-key
```

Get a key from https://console.groq.com and run:

```bash
bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh https://www.xiaoyuzhoufm.com/episode/xxxxx
```

The script downloads audio, transcodes/chunks it, sends chunks to Groq Whisper, and writes the transcript.

### LinkedIn

Basic public pages can be read with Jina Reader. Full profile/job capabilities use `mcp-server-linkedin`.

Install `uv`/`uvx` following https://docs.astral.sh/uv/getting-started/installation/, then:

```bash
mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home
uvx mcp-server-linkedin@latest --login
```

The browser login is manual. The saved profile lives under `~/.linkedin-mcp/profile/`.

### Boss Zhipin

Boss Zhipin uses boss-agent-cli with a dedicated real Chrome instance over CDP. Headless mode is intentionally avoided.

1. Explain that Agent Reach will install the pinned upstream CLI and start a dedicated Chrome profile. Ask for system-install approval.
2. After approval:
   ```bash
   agent-reach install --env=local --system --channels=boss
   ```
3. Start Chrome bound only to loopback:

   macOS:
   ```bash
   open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Linux:
   ```bash
   google-chrome --remote-debugging-address=127.0.0.1 \
     --remote-debugging-port=9222 --user-data-dir="$HOME/.boss-chrome-profile" \
     "https://www.zhipin.com/web/geek/job"
   ```

   Windows PowerShell:
   ```powershell
   Start-Process chrome.exe -ArgumentList '--remote-debugging-address=127.0.0.1','--remote-debugging-port=9222',"--user-data-dir=$env:USERPROFILE\.boss-chrome-profile",'https://www.zhipin.com/web/geek/job'
   ```
4. Pause and have the user visually confirm that Chrome is logged in. If not, the user logs in manually and handles any QR/sliding challenge. Do not request account passwords and do not treat `boss status` as proof that this browser is logged in; it checks local `session.enc`, not the Chrome cookie state.
5. After the user confirms:
   ```bash
   boss --cdp-url http://localhost:9222 login --cdp
   agent-reach doctor
   ```

Security boundary: any local process that can reach port 9222 can control this Chrome session. Always bind to `127.0.0.1`, never expose the debugging port to LAN/public networks, and use a dedicated persistent profile. Search commands must use `--browser-source existing-browser --cdp-url http://localhost:9222`.

The installer pins upstream commit `4c991b77086a203173bf08a4cb64a23af6514fe6`, which includes strict existing-browser CDP support, `JobItem.lid`, and `job_card_browser()`.

## Step 4: Final check

Run `agent-reach doctor` again and report the channel status.

## Step 5: Optional daily monitoring for OpenClaw

If running inside OpenClaw, ask whether the user wants a daily health/update check. If approved, schedule `agent-reach watch`; notify only when a channel has a problem or an update is available.

A suitable task instruction is:

```text
Run agent-reach watch.
If everything is healthy, finish silently.
If there are errors/warnings or a new version, send the complete report and recommended fix.
If a new version is available, ask whether to update and provide:
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

---

## Quick Reference

| Command | What it does |
|---|---|
| `agent-reach install --env=auto` | Read-only dependency/channel check |
| `agent-reach install --env=auto --system` | Install/configure approved external tools |
| `agent-reach install --env=auto --system --channels=twitter,xiaohongshu` | Install selected optional channels |
| `agent-reach install --env=local --system --channels=boss` | Install Boss Zhipin strict-CDP backend |
| `agent-reach install --env=auto --system --channels=all` | Install all optional channels after approval |
| `agent-reach install --env=auto --safe` | Compatibility alias for safe default |
| `agent-reach install --env=auto --dry-run` | Preview system changes |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Health + update check |
| `agent-reach check-update` | Check for a new version |
| `agent-reach configure twitter-cookies` | Save Twitter cookies via hidden input |
| `agent-reach configure proxy` | Save a proxy URL via hidden input |
| `agent-reach configure groq-key` | Configure Groq key for Xiaoyuzhou transcription |

After installation, use upstream tools directly.

| Platform | Upstream tool | Example |
|---|---|---|
| Twitter/X | `twitter` (fallback: `opencli`) | `twitter search "query" -n 10` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `bili` (subtitles: `opencli`) | `bili search "query" --type video` |
| Reddit | `opencli` (fallback: `rdt`) | `opencli reddit search "query" -f yaml` |
| Facebook | `opencli` | `opencli facebook search "query" -f yaml` |
| Instagram | `opencli` | `opencli instagram user nasa -f yaml` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call exa.web_search_exa query="..." numResults=5` |
| XiaoHongShu | `opencli` (server: `mcporter`) | `opencli xiaohongshu search "query" -f yaml` |
| Xiaoyuzhou Podcast | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |
| LinkedIn | `mcporter` | `mcporter call linkedin.get_person_profile linkedin_username="..."` |
| Boss Zhipin | `boss` / public Python API | See `agent_reach/skill/references/career.md` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |

For multi-backend platforms, use the `active_backend` value from `agent-reach doctor --json`.
