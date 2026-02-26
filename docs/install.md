# Agent Reach — Installation Guide

## For Humans

Copy this to your AI Agent:

```
帮我安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

> 🛡️ **Security-conscious?** Use safe mode — it won't auto-install system packages:
> ```
> 帮我安装 Agent Reach（安全模式）：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> 安装时使用 --safe 参数
> ```

---

## For AI Agents

### Goal

Install Agent Reach and all upstream tools so your user's agent has full internet access. After installation, you'll use the upstream tools directly (bird CLI, yt-dlp, mcporter, gh CLI, etc.) — Agent Reach is just the installer and health checker.

### ⚠️ Boundaries

When fixing issues, stay within these limits:

- **DO NOT** run commands with `sudo` unless the user explicitly approved
- **DO NOT** modify system files outside `~/.agent-reach/`
- **DO NOT** install packages not listed in this guide
- **DO NOT** disable firewalls, security settings, or system protections
- If something requires elevated permissions, **tell the user** what's needed and let them decide

### Step 1: Install

**Default (fully automatic):**

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

This auto-installs system dependencies (gh CLI, Node.js, mcporter, bird), configures Exa search, detects environment, and tests all channels.

**Safe mode (no automatic system changes):**

If the user asked for safe mode, or you're on a production machine:

```bash
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto --safe
```

Safe mode checks what's installed and tells you what's missing, but doesn't auto-install system packages. You can then install each dependency manually.

**Dry run (preview only):**

```bash
agent-reach install --env=auto --dry-run
```

Shows what would be done without making any changes.

**Read the output carefully**, then run:

```bash
agent-reach doctor
```

### Step 2: Fix what's broken

`agent-reach doctor` shows you which channels are active and which aren't.

Try to get as many channels to ✅ as possible. If something failed during install or shows as ❌/⚠️ in doctor, diagnose the problem and try to fix it — but stay within the boundaries above. If a fix requires elevated permissions or system changes, ask the user first.

Only ask the user when you genuinely need their input (credentials, permissions, etc.).

### Step 3: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing:

> 🔒 **Security tip:** For platforms that need cookies (Twitter, XiaoHongShu), we recommend using a **dedicated/secondary account** rather than your main account. Cookie-based auth grants full account access — using a separate account limits the blast radius if credentials are ever compromised.

**Twitter search & posting (server users):**
> "To unlock Twitter search, I need your Twitter cookies. Install the Cookie-Editor Chrome extension, go to x.com/twitter.com, click the extension → Export → Header String, and paste it to me."
> Extension: https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm

```bash
agent-reach configure twitter-cookies "PASTED_STRING"
```

> **代理说明（中国大陆等需要翻墙的网络环境）：**
>
> bird CLI 使用 Node.js 原生 `fetch()`，默认不走系统代理（`HTTP_PROXY`/`HTTPS_PROXY`）。
> Agent Reach 已内置解决方案：安装时会自动安装 `undici`（`npm install -g undici`），
> 运行 bird 时自动注入 `EnvHttpProxyAgent`，让 fetch 走用户配置的代理。
>
> **你（Agent）需要做的：**
> 1. 确认 `undici` 已全局安装：`npm list -g undici`，没有就装：`npm install -g undici`
> 2. 确认用户配了代理：`agent-reach configure proxy http://user:pass@ip:port`
> 3. Agent Reach 会自动处理剩下的，不需要用户做额外操作
>
> 如果用户报告 "fetch failed"，参考 [troubleshooting.md](troubleshooting.md)

**Reddit & Bilibili full access (server users):**
> "Reddit and Bilibili block server IPs. To unlock full access, I need a residential proxy. You can get one at https://webshare.io ($1/month). Send me the proxy address."

```bash
agent-reach configure proxy http://user:pass@ip:port
```

**XiaoHongShu / 小红书 (需要 Docker):**
> "小红书需要一个 MCP 服务。需要你的机器上有 Docker。安装好 Docker 后我来搞定剩下的。"

```bash
docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp
mcporter config add xiaohongshu http://localhost:18060/mcp
```

> 如果在服务器上，建议加代理避免 IP 风控：
> `docker run -d --name xiaohongshu-mcp -p 18060:18060 -e XHS_PROXY=http://user:pass@ip:port xpzouying/xiaohongshu-mcp`
>
> **登录方式：**
> - **本地电脑（有浏览器）：** 打开 http://localhost:18060 扫码登录即可。
> - **服务器（无 UI 界面）：** 服务器上通常没有浏览器，无法直接扫码。最方便的方式是在自己的电脑上用浏览器登录小红书，然后用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 插件导出 Cookie（Header String 格式），发给 Agent 即可完成配置。详见 [Cookie 导出指南](cookie-export.md)。

**LinkedIn (可选 — linkedin-scraper-mcp):**
> "LinkedIn 基本内容可通过 Jina Reader 读取。完整功能（Profile 详情、职位搜索）需要 linkedin-scraper-mcp。"

```bash
pip install linkedin-scraper-mcp
```

> **登录方式（需要浏览器界面）：**
>
> linkedin-scraper-mcp 使用 Chromium 浏览器登录，需要你能看到浏览器窗口。
>
> - **本地电脑（有桌面）：** 直接运行：
>   ```bash
>   linkedin-scraper-mcp --login --no-headless
>   ```
>   浏览器会弹出来，手动登录 LinkedIn 即可。
>
> - **服务器（无 UI）：** 需要通过 VNC 远程桌面操作：
>   ```bash
>   # 1. 服务器上安装并启动 VNC（如已有可跳过）
>   apt install -y tigervnc-standalone-server
>   vncserver :1 -geometry 1280x720
>   
>   # 2. 用 VNC 客户端连接 服务器IP:5901
>   
>   # 3. 在 VNC 桌面的终端里运行：
>   export DISPLAY=:1
>   linkedin-scraper-mcp --login --no-headless
>   ```
>   在 VNC 里看到浏览器后手动登录。登录成功后 session 会保存到 `~/.linkedin-mcp/profile/`。
>
> **登录后启动 MCP 服务：**
> ```bash
> linkedin-scraper-mcp --transport streamable-http --port 8001
> mcporter config add linkedin http://localhost:8001/mcp
> ```
>
> 详见 https://github.com/stickerdaniel/linkedin-mcp-server

**Boss直聘 (可选 — mcp-bosszp):**
> "Boss直聘职位页面可直接读取。完整搜索和打招呼功能需要 mcp-bosszp。"

```bash
git clone https://github.com/mucsbr/mcp-bosszp.git && cd mcp-bosszp
pip install -r requirements.txt && playwright install chromium
```

> **登录方式（手机 App 扫码）：**
>
> mcp-bosszp 使用二维码登录，需要 Boss直聘 App 扫码。
>
> ```bash
> # 1. 启动 MCP 服务
> python boss_zhipin_fastmcp_v2.py
> 
> # 2. 通过 MCP 触发登录（会生成二维码图片）
> mcporter call 'bosszhipin.start_login()'
> 
> # 3. 浏览器打开二维码图片（服务器上用 http://服务器IP:8000/static/qrcode_xxx.png）
> # 4. 用 Boss直聘 App 扫码确认
> ```
>
> 扫码成功后 session 自动保存，之后可以搜索职位和自动打招呼。
>
> 或用 Docker：`docker-compose up -d`
>
> 详见 https://github.com/mucsbr/mcp-bosszp

### Step 4: Final check

Run `agent-reach doctor` one final time and report the results to your user.

### Step 5: Set up daily monitoring (OpenClaw only)

If you are running inside **OpenClaw**, ask your user:

> "Agent Reach 安装好了。要不要我设一个每天自动检查的任务？它会帮你盯着这些渠道是否正常、有没有新版本。有问题才会通知你，没问题不打扰。"

If the user agrees, create a **cron job** (daily, `sessionTarget: "isolated"`, `delivery: "announce"`) with this task:

```
运行 agent-reach watch 命令。
如果输出包含"全部正常"，不需要通知用户，静默结束。
如果输出包含问题（❌ ⚠️）或新版本（🆕），把完整报告发给用户，并建议修复方案。
如果有新版本可用，问用户是否要升级（升级命令：pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip）。
```

If the user wants a different agent to handle it, let them choose.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `agent-reach install --env=auto` | Full auto-setup (installs deps + configures) |
| `agent-reach install --env=auto --safe` | Safe setup (no auto system changes) |
| `agent-reach install --env=auto --dry-run` | Preview what would be done |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Quick health + update check (for scheduled tasks) |
| `agent-reach check-update` | Check for new versions |
| `agent-reach configure twitter-cookies "..."` | Unlock Twitter search + posting |
| `agent-reach configure proxy URL` | Unlock Reddit + Bilibili on servers |

After installation, use upstream tools directly. See SKILL.md for the full command reference:

| Platform | Upstream Tool | Example |
|----------|--------------|---------|
| Twitter/X | `bird` | `bird search "query" --json` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `yt-dlp` | `yt-dlp --dump-json URL` |
| Reddit | `curl` | `curl -s "https://reddit.com/r/xxx.json"` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call 'exa.web_search_exa(...)'` |
| 小红书 | `mcporter` | `mcporter call 'xiaohongshu.search_feeds(...)'` |
| LinkedIn | `mcporter` | `mcporter call 'linkedin.get_person_profile(...)'` |
| Boss直聘 | `mcporter` | `mcporter call 'bosszhipin.search_jobs_tool(...)'` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |
