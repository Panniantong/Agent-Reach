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
> - 🐦 **Twitter/X** — 搜推文、看时间线（需要登录 Cookie）
> - 📰 **微博** — 热搜、搜索、用户动态
> - 💬 **微信公众号** — 搜索和阅读公众号文章
> - 📈 **雪球** — 股票行情、热门帖子（需要登录 Cookie）
> - 🎙️ **小宇宙播客** — 音频转文字（需要免费 Groq Key）
> - 📕 **小红书** — 阅读、搜索、发帖（需要登录）
> - 📖 **Reddit** — 搜索和阅读帖子
> - 📺 **B站完整版** — 热门、排行、搜索
> - 🎵 **抖音** — 视频解析
> - 💼 **LinkedIn** — Profile、职位搜索
>
> 告诉我你要哪些，比如"帮我装微博和 Twitter"。或者说"全部装"。

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

> 🍪 **Cookie 导入（所有需要登录的平台通用）：**
>
> 所有需要 Cookie 的平台（Twitter、小红书、雪球等），**优先使用 Cookie-Editor 导入**，这是最简单最可靠的方式：
> 1. 用户在自己的浏览器上登录对应平台
> 2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome 插件
> 3. 点击插件 → Export → Header String
> 4. 把导出的字符串发给 Agent
>
> **本地电脑用户**也可以用 `agent-reach configure --from-browser chrome` 一键自动提取（支持 Twitter + 小红书 + 雪球）。

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

**Reddit & Bilibili full access (server users):**
> "Reddit and Bilibili block server IPs. To unlock full access, I need a residential proxy. You can get one at https://webshare.io ($1/month). Send me the proxy address."

```bash
agent-reach configure proxy http://user:pass@ip:port
```

**XiaoHongShu / 小红书 (xhs-cli):**
> "小红书通过 xhs-cli 访问，pipx 一行安装，不需要 Docker。"

```bash
pipx install xiaohongshu-cli
xhs login
```

> `xhs login` 会自动从浏览器提取 Cookie。如果自动提取失败，可以手动导入：
>
> **手动导入 Cookie（Cookie-Editor 方式）：**
> 1. 用户在自己的浏览器登录小红书 (xiaohongshu.com)
> 2. 用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 插件导出 Cookie（JSON 或 Header String 格式均可）
> 3. 把 Cookie 字符串发给 Agent
> 4. Agent 运行命令完成登录：
>
> ```bash
> # JSON 格式（Cookie-Editor → Export → JSON）
> agent-reach configure xhs-cookies '[{"name":"web_session","value":"xxx","domain":".xiaohongshu.com",...}]'
>
> # 或 Header String 格式（Cookie-Editor → Export → Header String）
> agent-reach configure xhs-cookies "key1=val1; key2=val2; ..."
> ```
>
> **注意：** 推荐使用 Cookie-Editor 导出方式，不要依赖 QR 扫码登录。
>
> **备选方案：Docker MCP**
> 如果你已经在使用 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker 方案，它也能正常工作：
> ```bash
> docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp
> mcporter config add xiaohongshu http://localhost:18060/mcp
> ```

**微博 / Weibo (mcp-server-weibo):**
> "微博已默认安装，装好即用。可搜索微博内容、查看热搜、获取用户动态和评论。"

如果自动安装失败，手动安装：

```bash
pip install git+https://github.com/Panniantong/mcp-server-weibo.git
mcporter config add weibo --command 'mcp-server-weibo'
```

> 无需登录、无需 Cookie、无需代理。海外服务器也可以直接访问。

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

**抖音 / Douyin (douyin-mcp-server):**
> "抖音视频解析需要一个 MCP 服务。安装 douyin-mcp-server 后即可解析视频、获取无水印下载链接。"

```bash
# 1. 安装
pip install douyin-mcp-server

# 2. 启动 HTTP 服务（端口 18070）
# 方式一：用 uv（推荐）
mkdir -p ~/.agent-reach/tools && cd ~/.agent-reach/tools
git clone https://github.com/yzfly/douyin-mcp-server.git && cd douyin-mcp-server
uv sync && uv run python run_http.py

# 方式二：直接用 Python 启动
python -c "
from douyin_mcp_server.server import mcp
mcp.settings.host = '127.0.0.1'
mcp.settings.port = 18070
mcp.run(transport='streamable-http')
"

# 3. 注册到 mcporter
mcporter config add douyin http://localhost:18070/mcp
```

> 无需认证即可解析视频信息和获取下载链接。
> 如需 AI 语音识别提取文案功能，需要配置硅基流动 API Key（`export API_KEY="sk-xxx"`）。
>
> 详见 https://github.com/yzfly/douyin-mcp-server

**可选实现：Douyin + XiaoHongShu unified extractor**
> "如果你想把抖音和小红书统一成一个 MCP，并直接输出 `script.md` 和 `info.json`，可以改用 social-post-extractor-mcp。"

适用场景：

- 抖音视频转文字稿
- 小红书视频笔记转文字稿
- 小红书图文笔记正文 + 图片文字提取

兼容性：

- 仍然可以注册成 `douyin` 这个 mcporter server 名称
- 兼容旧工具名 `parse_douyin_video_info` / `get_douyin_download_link` / `extract_douyin_text`
- 同时新增 `parse_social_post_info` / `extract_social_post_script`

示例配置：

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

> 这个实现更适合“把链接直接交给 Agent，然后拿到脚本文件”的工作流。
>
> 详见 https://github.com/JNHFlow21/social-post-extractor-mcp

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
如果有新版本可用，问用户是否要升级（升级命令：pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip）。
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
| 小红书 | `mcporter` | `mcporter call 'xiaohongshu.search_feeds(...)'` |
| 微博 | `mcporter` | `mcporter call 'weibo.get_trendings(limit: 10)'` |
| 小宇宙播客 | `transcribe.sh` | `bash ~/.agent-reach/tools/xiaoyuzhou/transcribe.sh <URL>` |
| 抖音 | `mcporter` | `mcporter call 'douyin.parse_douyin_video_info(...)'` |
| LinkedIn | `mcporter` | `mcporter call 'linkedin.get_person_profile(...)'` |
| RSS | `feedparser` | `python3 -c "import feedparser; ..."` |
