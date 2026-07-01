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
# 推荐：pipx（最省心）
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto

# 如果你的 Python 来自 Homebrew / 遇到 PEP 668（externally-managed-environment）
# 用虚拟环境安装：
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=auto
```

> 💡 **Windows / Microsoft Store Python alias?**
> 如果 `python3 --version` 打开 Microsoft Store，或 `where python3` 指向
> `...\AppData\Local\Microsoft\WindowsApps\python3.exe`，说明 `python3` 是 Windows
> 的 Store alias，不是可用的 Python 安装。请改用 Python Launcher `py -3`，或实际安装目录里的 `python.exe`。
>
> PowerShell 示例：
> ```powershell
> py -3 -m venv $env:USERPROFILE\.agent-reach-venv
> $env:USERPROFILE\.agent-reach-venv\Scripts\Activate.ps1
> python -m pip install https://github.com/Panniantong/agent-reach/archive/main.zip
> agent-reach install --env=auto
> ```

This installs core infrastructure (gh CLI, Node.js, mcporter, Exa search, yt-dlp config) and activates these zero-config channels:

- Web (Jina Reader), YouTube, GitHub, RSS, Exa Search, V2EX, Bilibili (basic)

> 💡 **macOS / Homebrew Python 提示 `externally-managed-environment`？**
> 这是 PEP 668 保护，不是 Agent Reach 本身的问题。优先用 `pipx install ...`，或先创建 `venv` 再安装。

**Safe mode / Dry run:**

```bash
agent-reach install --env=auto --safe      # Check only, no auto-install
agent-reach install --env=auto --dry-run   # Preview what would be done
```

### Step 2: Ask the user which optional channels they want

After installing the basics, **ask the user** which additional channels they need. Present this list:

> 基础渠道装好了！你现在可以让我搜网页、看 YouTube、读 GitHub 等。
>
> 还有这些可选渠道，你需要哪些？
>
> - 🌟 **OpenCLI**（桌面推荐）— 一次安装，小红书/Reddit/Facebook/Instagram/B站字幕/Twitter 备选全解锁（复用浏览器登录态，零配置；只需在 Chrome 商店点一次"添加扩展"）
> - 🐦 **Twitter/X** — 搜推文、看时间线（需要登录 Cookie）
> - 📈 **雪球** — 股票行情、热门帖子（需要登录 Cookie）
> - 🎙️ **小宇宙播客** — 音频转文字（需要免费 Groq Key）
> - 📕 **小红书** — 搜索、阅读、评论（桌面走 OpenCLI；服务器用 xiaohongshu-mcp 扫码）
> - 📖 **Reddit** — 搜索和阅读帖子（必须登录态：桌面 OpenCLI 或 rdt-cli + Cookie）
> - 📘 **Facebook** — 搜索、主页、Feed、群组列表（桌面走 OpenCLI，复用 Chrome 登录态）
> - 📷 **Instagram** — 用户搜索、Profile、用户最近帖子、Explore（桌面走 OpenCLI，复用 Chrome 登录态）
> - 📺 **B站完整版** — 热门、排行、搜索、视频详情（bili-cli，无需登录）
> - 💼 **LinkedIn** — Profile、职位搜索
>
> 告诉我你要哪些，比如"帮我装小红书和 Twitter"、"帮我装 Facebook 和 Instagram"。或者说"全部装"。

Based on the user's choice, run:

```bash
agent-reach install --env=auto --channels=opencli,xiaohongshu   # Example: desktop user chose XHS (OpenCLI-backed)
agent-reach install --env=auto --channels=facebook,instagram    # Example: desktop user chose Meta social channels
agent-reach install --env=auto --channels=all              # User wants everything
```

Supported channel names: `opencli`, `twitter`, `xiaoyuzhou`, `xueqiu`, `xiaohongshu`, `reddit`, `facebook`, `instagram`, `bilibili`, `linkedin`, `all`

### Step 3: Fix what's broken

Run `agent-reach doctor` and check the output.

Try to get as many channels to ✅ as possible. If something failed during install or shows as ❌/⚠️ in doctor, diagnose the problem and try to fix it — but stay within the boundaries above. If a fix requires elevated permissions or system changes, ask the user first.

Only ask the user when you genuinely need their input (credentials, permissions, etc.).

### Step 3: Configure things that need user input

Some channels need credentials only the user can provide. Based on the doctor output, ask for what's missing:

> 🔒 **Security tip:** For platforms that need cookies or browser sessions (Twitter, XiaoHongShu, Reddit, Facebook, Instagram), we recommend using a **dedicated/secondary account** rather than your main account. Cookie/browser-session auth carries two risks:
> 1. **Account ban** — platforms may detect non-browser API calls and restrict or ban the account
> 2. **Credential exposure** — cookies grant full account access; using a secondary account limits the blast radius if credentials are ever compromised

> 🍪 **Cookie / 登录态：**
>
> 传统 CLI 需要 Cookie 的平台（Twitter、雪球等），**优先使用 Cookie-Editor 导入**，这是最简单最可靠的方式：
> 1. 用户在自己的浏览器上登录对应平台
> 2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome 插件
> 3. 点击插件 → Export → Header String
> 4. 把导出的字符串发给 Agent
>
> **本地电脑用户**也可以用 `agent-reach configure --from-browser chrome` 一键自动提取（支持 Twitter + 小红书 + 雪球）。OpenCLI 平台（Reddit、小红书桌面后端、Facebook、Instagram）优先复用 Chrome 登录态，不需要把 Cookie 发给 Agent。

**Twitter search & posting:**
> "To unlock Twitter search, I need your Twitter cookies. Install the Cookie-Editor Chrome extension, go to x.com/twitter.com, click the extension → Export → Header String, and paste it to me."

```bash
agent-reach configure twitter-cookies "PASTED_STRING"
```

> **代理说明（中国大陆等需要翻墙的网络环境）：**
>
> twitter-cli 和 rdt-cli 使用 Python，在需要代理的网络环境下可通过环境变量配置代理。
>
> **你（Agent）需要做的：**
> 1. 确认用户配了代理：`agent-reach configure proxy http://user:pass@ip:port`
> 2. 设置环境变量：`export HTTP_PROXY="..." HTTPS_PROXY="..."`
> 3. Agent Reach 会自动处理剩下的，不需要用户做额外操作
>
> 如果用户报告 "fetch failed"，参考 [troubleshooting.md](troubleshooting.md)

**Reddit (login is mandatory — no zero-config path):**
> Reddit 的匿名接口已被封、官方 API 需人工审批。桌面用户首选 OpenCLI（浏览器里登录过 reddit.com 即可用）；服务器/存量用户用 rdt-cli：

```bash
# PyPI 落后，从 GitHub 装（与代码内 _RDT_GIT_SOURCE 同一钉定版本）
pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'
rdt login   # 自动提取浏览器 Cookie；服务器无浏览器时按 doctor 提示手动写 Cookie
```

> 中国大陆访问 Reddit 需要代理；服务器 IP 被风控时可配住宅代理（如 https://webshare.io，约 $1/月）：
> ```bash
> agent-reach configure proxy http://user:pass@ip:port
> ```

**XiaoHongShu / 小红书（多后端，按环境选）:**

> **桌面电脑（推荐 OpenCLI）：**
> "小红书走 OpenCLI——复用你浏览器里的登录态，平时刷过小红书就直接能用，零配置。"

```bash
agent-reach install --channels opencli
```

> 装完后引导用户做唯一一步手动操作（Chrome 安全限制，无法代劳）：
> 1. 打开 https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
> 2. 点「添加至 Chrome」
> 3. 运行 `opencli doctor` 验证（显示 Extension: connected 即成功）
>
> **服务器 / 无桌面环境（xiaohongshu-mcp）：**
> 1. 从 https://github.com/xpzouying/xiaohongshu-mcp/releases 下载对应平台 binary 到 `~/.agent-reach/tools/`
> 2. 启动服务（首次运行会自动下载约 150MB 无头浏览器，耐心等完成）
> 3. 让用户扫码登录（agent 调 `get_login_qrcode` 工具取二维码）
> 4. 接入：`mcporter config add xiaohongshu http://localhost:18060/mcp`
> 5. 调用时务必带 `--timeout 120000`
>
> **存量用户（xhs-cli）：** 已装好的 xhs-cli 继续作为备选后端工作（上游 2026-03 起停更，不推荐新装）。`xhs login` 自动提取浏览器 Cookie；失败时用 Cookie-Editor 导出后：
> ```bash
> agent-reach configure xhs-cookies "key1=val1; key2=val2; ..."
> ```

**Facebook / Instagram（桌面 OpenCLI）:**
> 这两个平台走 OpenCLI：复用用户自己的 Chrome 登录态，不保存账号密码，不走 Meta Graph API 审批流。服务器/无桌面环境不推荐支持。

```bash
agent-reach install --channels facebook,instagram
```

> 装完后：
> 1. 确认 Chrome 已安装 OpenCLI 扩展并通过 `opencli doctor`
> 2. 在 Chrome 里登录 facebook.com / instagram.com
> 3. Agent 直接调用：
>    ```bash
>    opencli facebook search "query" -f yaml
>    opencli facebook profile zuck -f yaml
>    opencli facebook groups -f yaml
>    opencli instagram search "query" -f yaml     # 用户搜索
>    opencli instagram profile nasa -f yaml
>    opencli instagram user nasa -f yaml          # 指定用户最近帖子
>    ```
>
> Facebook Groups 当前只承诺读取用户登录后可见的群组列表/最近动态，不承诺任意群帖子和评论 API。Instagram 的 search 是用户搜索，不是全站帖子关键词搜索；若提示 429/登录错误，先让用户在 Chrome 里重新登录并降低频率。

**雪球 / Xueqiu (股票行情 + 热门帖子):**
> "雪球需要登录后的 Cookie。请先在 Chrome 里登录 xueqiu.com，然后运行："

```bash
agent-reach configure --from-browser chrome
```

> Cookie 会随其他平台一起自动提取。

**小宇宙播客 / Xiaoyuzhou Podcast (Groq Whisper):**
> "小宇宙播客转文字已默认安装，只需要一个免费的 Groq API Key。"

脚本已随 Agent Reach 自动安装，用户只需提供 Key：

```bash
agent-reach configure groq-key gsk_xxxxx
```

> **获取 Groq API Key（免费、无需信用卡、30 秒搞定）：**
> 1. 打开 https://console.groq.com
> 2. 用 Google/GitHub 账号登录（或注册）
> 3. 左侧菜单 → API Keys → Create API Key
> 4. 复制 Key（以 `gsk_` 开头），发给 Agent 即可
>
> **使用方式：**
> 用户发一个小宇宙链接给 Agent，Agent 自动调用：
> ```bash
> bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh https://www.xiaoyuzhoufm.com/episode/xxxxx
> ```
>
> 自动下载音频 → 转码切片 → Groq Whisper 转录 → 输出完整中文文字稿。
>
> **免费额度和限制：**
> - 每小时约 2 小时音频（7200 秒），超出后等 15 分钟自动恢复
> - 日常听几期播客完全够用
> - 转录质量高（Whisper large-v3），但不区分说话人
> - 2 小时以上的播客建议分批处理

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
如果有新版本可用，问用户是否要升级（把这句话发给用户的 Agent 即可完整更新：帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md）。
```

If the user wants a different agent to handle it, let them choose.

---

## Quick Reference

| Command | What it does |
|---------|-------------|
| `agent-reach install --env=auto` | Install core channels (lightweight, zero-config) |
| `agent-reach install --env=auto --channels=twitter,xiaohongshu` | Install core + optional channels |
| `agent-reach install --env=auto --channels=all` | Install everything |
| `agent-reach install --env=auto --safe` | Safe setup (no auto system changes) |
| `agent-reach install --env=auto --dry-run` | Preview what would be done |
| `agent-reach doctor` | Show channel status |
| `agent-reach watch` | Quick health + update check (for scheduled tasks) |
| `agent-reach check-update` | Check for new versions |
| `agent-reach configure twitter-cookies "..."` | Unlock Twitter search + posting |
| `agent-reach configure proxy URL` | 保存代理地址（Agent 访问 Reddit/Twitter 等受限网络时读取它设置 HTTP_PROXY/HTTPS_PROXY，不是自动解锁开关） |
| `agent-reach configure groq-key gsk_xxx` | Unlock Xiaoyuzhou podcast transcription |

After installation, use upstream tools directly. See SKILL.md for the full command reference:

| Platform | Upstream Tool | Example |
|----------|--------------|---------|
| Twitter/X | `twitter`（备选 `opencli`） | `twitter search "query" -n 10` |
| YouTube | `yt-dlp` | `yt-dlp --dump-json URL` |
| Bilibili | `bili`（字幕走 `opencli`） | `bili search "query" --type video` / `opencli bilibili subtitle BVxxx` |
| Reddit | `opencli`（备选 `rdt`） | `opencli reddit search "query" -f yaml` / `rdt read POST_ID` |
| Facebook | `opencli` | `opencli facebook search "query" -f yaml` |
| Instagram | `opencli` | `opencli instagram user nasa -f yaml` |
| GitHub | `gh` | `gh search repos "query"` |
| Web | `curl` + Jina | `curl -s "https://r.jina.ai/URL"` |
| Exa Search | `mcporter` | `mcporter call 'exa.web_search_exa(...)'` |
| 小红书 | `opencli`（服务器 `mcporter`） | `opencli xiaohongshu search "query" -f yaml` |
| 小宇宙播客 | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |
| LinkedIn | `mcporter` | `mcporter call 'linkedin.get_person_profile(...)'` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |

> 多后端平台以 `agent-reach doctor --json` 的 `active_backend` 为准。
