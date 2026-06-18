<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>给你的 AI Agent 一键装上互联网能力</strong>
</p>

<p align="center">
  当下最稳的接入方式，替你选好、装好、体检好——接入方式会换代，你不用操心
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
  <a href="https://trendshift.io/repositories/24387"><img src="https://trendshift.io/api/badge/repositories/24387" alt="Trendshift GitHub Trending #1 Repository of the Day"></a>
</p>

<p align="center">
  <a href="#快速上手">快速开始</a> · <a href="docs/README_en.md">English</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_ko.md">한국어</a> · <a href="#支持的平台">支持平台</a> · <a href="#设计理念">设计理念</a>
</p>

---

## 为什么需要 Agent Reach？

AI Agent 已经能帮你写代码、改文档、管项目——但你让它去网上找点东西，它就抓瞎了：

- 📺 "帮我看看这个 YouTube 教程讲了什么" → **看不了**，拿不到字幕
- 🐦 "帮我搜一下推特上大家怎么评价这个产品" → **搜不了**，Twitter API 要付费
- 📖 "去 Reddit 上看看有没有人遇到过同样的 bug" → **403 被封**，服务器 IP 被拒
- 📕 "帮我看看小红书上这个品的口碑" → **打不开**，必须登录才能看
- 📺 "B站上有个技术视频，帮我总结一下" → **拿不到**，通用下载工具被 B站风控全面拦截
- 🔍 "帮我在网上搜一下最新的 LLM 框架对比" → **没有好用的搜索**，要么付费要么质量差
- 🌐 "帮我看看这个网页写了啥" → **抓回来一堆 HTML 标签**，根本没法读
- 📦 "这个 GitHub 仓库是干嘛的？Issue 里说了什么？" → 能用，但认证配置很麻烦
- 📡 "帮我订阅这几个 RSS 源，有更新告诉我" → 要自己装库写代码

**这些不难实现，但是需要自己折腾配置**

每个平台都有自己的门槛——要付费的 API、要绕过的封锁、要登录的账号、要清洗的数据。你要一个一个去踩坑、装工具、调配置，光是让 Agent 能读个推特就得折腾半天。

**Agent Reach 把这件事变成一句话：**

```
帮我安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

复制给你的 Agent，几分钟后它就能读推特、搜 Reddit、看 YouTube、刷小红书了。

**已经装过了？更新也是一句话：**

```
帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

> ⭐ **Star 这个项目**，我们会持续追踪各平台的变化、接入新的渠道。你不用自己盯——平台封了我们修，有新渠道我们加。

### ✅ 在你用之前，你可能想知道

| | |
|---|---|
| 💰 **完全免费** | 所有工具开源、所有 API 免费。唯一可能花钱的是服务器代理（$1/月），本地电脑不需要 |
| 🔒 **隐私安全** | Cookie 只存在你本地，不上传不外传。代码完全开源，随时可审查 |
| 🔄 **持续换代** | 每个平台都是「首选 + 备选」多后端路由。某个接入方式失效了，我们换下一个，你无感（2026-06 实例：yt-dlp 被 B站风控封死 → 已切换 bili-cli，用户零操作） |
| 🤖 **兼容所有 Agent** | Claude Code、OpenClaw、Cursor、Windsurf……任何能跑命令行的 Agent 都能用 |
| 🩺 **自带诊断** | `agent-reach doctor` 一条命令告诉你哪个通、哪个不通、怎么修 |

---

## 支持的平台

| 平台 | 装好即用 | 配置后解锁 | 怎么配 |
|------|---------|-----------|-------|
| 🌐 **网页** | 阅读任意网页 | — | 无需配置 |
| 📺 **YouTube** | 字幕提取 + 视频搜索 | — | 无需配置 |
| 📡 **RSS** | 阅读任意 RSS/Atom 源 | — | 无需配置 |
| 🔍 **全网搜索** | — | 全网语义搜索 | 自动配置（MCP 接入，免费无需 Key） |
| 📦 **GitHub** | 读公开仓库 + 搜索 | 私有仓库、提 Issue/PR、Fork | 告诉 Agent「帮我登录 GitHub」 |
| 🐦 **Twitter/X** | 读单条推文 | 搜索推文、浏览时间线、读长文 | 告诉 Agent「帮我配 Twitter」 |
| 📺 **B站** | 搜索 + 视频详情（bili-cli，无需登录） | 字幕（OpenCLI） | 告诉 Agent「帮我配 B站」 |
| 📖 **Reddit** | —（没有零配置路径：匿名接口已被封） | 搜索 + 读帖子和评论 | 桌面装 OpenCLI 用浏览器登录态；或 rdt-cli + Cookie |
| 📕 **小红书** | — | 搜索、阅读、评论 | 桌面装 OpenCLI（刷过小红书即可用）；服务器用 xiaohongshu-mcp 扫码 |
| 💼 **LinkedIn** | Jina Reader 读公开页面 | Profile 详情、公司页面、职位搜索 | 告诉 Agent「帮我配 LinkedIn」 |
| 💻 **V2EX** | 热门帖子、节点帖子、帖子详情+回复、用户信息 | — | 无需配置 |
| 📈 **雪球** | 股票行情、搜索股票、热门帖子、热门股票排行 | — | 告诉 Agent「帮我配雪球」 |
| 🎙️ **小宇宙播客** | — | 播客音频转文字（Whisper 转录，免费 Key） | 告诉 Agent「帮我配小宇宙播客」 |

> **不知道怎么配？不用查文档。** 直接告诉 Agent「帮我配 XXX」，它知道需要什么、会一步一步引导你。
>
> 🍪 需要 Cookie 的平台（Twitter、小红书等），**优先使用** Chrome 插件 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 导出 Cookie，发给 Agent 即可配置。流程统一：浏览器登录 → Cookie-Editor 导出 → 发给 Agent。比扫码更简单可靠。
>
> 🔒 Cookie 只存在你本地，不上传不外传。代码完全开源，随时可审查。
> 💻 本地电脑不需要代理。代理只有部署在服务器上才需要（~$1/月）。

---

## 快速上手

> ⚠️ **OpenClaw 用户请先确认 exec 权限已开启**
>
> Agent Reach 依赖 Agent 执行 shell 命令（`pip install`、`mcporter`、`twitter` 等）。如果你的 OpenClaw 使用了默认的 `messaging` 工具配置，Agent 将无法执行命令。**安装前请先开启 exec 权限**：
>
> ```bash
> openclaw config set tools.profile "coding"
> ```
> 或在 `~/.openclaw/openclaw.json` 中设置 `"tools": { "profile": "coding" }`。
> 设置后重启 Gateway（`openclaw gateway restart`）并开启新对话即可。其他平台（Claude Code、Cursor、Windsurf 等）不受此限制。

复制这句话给你的 AI Agent（Claude Code、OpenClaw、Cursor 等）：

```
帮我安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

就这一步。Agent 会自己完成剩下的所有事情。

> 🔄 **已安装过？** 更新也是一句话：
> ```
> 帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
> ```

> 🛡️ **担心安全？** 可以用安全模式——不会自动装系统包，只告诉你需要什么：
> ```
> 帮我安装 Agent Reach（安全模式）：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> 安装时使用 --safe 参数
> ```

<details>
<summary>手动安装（点击展开）</summary>

```bash
# 方式 A：pipx（推荐）
pipx install https://github.com/Panniantong/agent-reach/archive/main.zip

# 方式 B：uv tool（更快的 pipx 替代）
uv tool install https://github.com/Panniantong/agent-reach/archive/main.zip

# 方式 C：pip（遇到 PEP 668 请先建 venv）
pip install https://github.com/Panniantong/agent-reach/archive/main.zip

# 然后运行：
agent-reach install --env=auto
```
</details>

<details>
<summary>它会做什么？（点击展开）</summary>

1. **安装 CLI 工具** — `pip install` 装好 `agent-reach` 命令行（自带 yt-dlp、feedparser）
2. **安装系统基建** — 自动检测并安装 Node.js、gh CLI、mcporter
3. **配置搜索引擎** — 通过 MCP 接入 Exa（免费，无需 API Key）
4. **检测环境** — 判断是本地电脑还是服务器，给出对应的配置建议
5. **注册 SKILL.md** — 在 Agent 的 skills 目录安装使用指南，以后 Agent 遇到"全网调研"、"搜推特"、"看视频"这类需求，会自动知道该调哪个上游工具
6. **问你要不要更多** — 默认只激活 6 个零配置渠道；小红书、Twitter、Reddit 这些需要登录的，Agent 会列菜单问你要哪些，点名才装

安装完之后，`agent-reach doctor` 一条命令告诉你每个渠道的状态、当前走哪条路。
</details>

---

## 装好就能用

不需要任何配置，告诉 Agent 就行：

- "帮我看看这个链接" → `curl https://r.jina.ai/URL` 读任意网页
- "这个 GitHub 仓库是做什么的" → `gh repo view owner/repo`
- "这个 YouTube 视频讲了什么" → `yt-dlp` 提取字幕
- "B站搜一下 AI 教程" → `bili search`（无需登录）
- "全网搜一下 LLM 框架对比" → Exa 语义搜索
- "订阅这个 RSS" → `feedparser` 解析

**不需要记命令。** Agent 读了 SKILL.md 之后自己知道该调什么。需要登录的平台（小红书、Twitter、Reddit），告诉 Agent「帮我配 XXX」即可解锁。

---

## 能力边界：读内容 vs 操作网页

有些任务超出"读"的范围：登录后的网页操作、表单提交、多账号隔离、并行浏览器会话、自动化流程中的登录、验证、风控提示等高摩擦环节的人工接手。这类"动手"场景，可以配合 [BrowserAct](https://www.browseract.ai/Agent) 这类浏览器自动化工具——30+ 预制平台技能，支持 Claude Code / OpenClaw / Cursor 等主流 Agent。

---

## 设计理念

**Agent Reach 是一个能力层（capability layer），不是又一个工具。**

它比任何具体实现高一层——负责**选型、安装、体检、路由**，不负责底层读取本身。读取由 Agent 直接调用上游工具完成，没有包装层。

你给一个新 Agent 装环境的时候，总要花时间去找工具、装依赖、调配置——Twitter 用什么读？Reddit 怎么登录？小红书的 CLI 停更了换什么？每次都要重新踩一遍。Agent Reach 做的事情很简单：**当下最稳的接入方式，我们替你选好、装好、体检好。接入方式会换代（2026 年 3 月一批单平台 CLI 集体停更，我们换了路由），你不用操心。**

### 🔌 每个平台 = 首选 + 备选的有序后端列表

换接入方式 = 调整列表顺序，不是重写代码。`agent-reach doctor` 会告诉你每个平台**当前在用哪个后端**。

```
channels/
├── web.py          → Jina Reader
├── twitter.py      → twitter-cli ▸ OpenCLI ▸ bird
├── youtube.py      → yt-dlp
├── github.py       → gh CLI
├── bilibili.py     → bili-cli ▸ OpenCLI ▸ 搜索 API（yt-dlp 已被 B站风控封死，退役）
├── reddit.py       → OpenCLI ▸ rdt-cli（无零配置路径，必须登录态）
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── linkedin.py     → linkedin-mcp ▸ Jina Reader
├── rss.py          → feedparser
├── exa_search.py   → Exa via mcporter
└── __init__.py     → 渠道注册（doctor 检测用）
```

每个渠道文件按序**真实探测**各候选后端（不只是看命令存不存在），第一个完整可用的当选；坏掉的会给出修复处方。实际的读取和搜索由 Agent 直接调用上游工具完成。

### 当前选型

| 场景 | 首选 | 备选 | 为什么这么选 |
|------|------|------|-----------|
| 读网页 | [Jina Reader](https://github.com/jina-ai/reader) | — | 免费，不需要 API Key |
| 读推特 | [twitter-cli](https://github.com/public-clis/twitter-cli) | [OpenCLI](https://github.com/jackwener/opencli) | 实测搜索稳定；OpenCLI 走浏览器登录态兜底 |
| Reddit | [OpenCLI](https://github.com/jackwener/opencli)（桌面） | [rdt-cli](https://github.com/public-clis/rdt-cli) | 匿名接口已被封、官方 API 审批制——只剩登录态路线 |
| YouTube 字幕 + 搜索 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | — | 154K Star，YouTube 仍是最佳（注意：不再用于 B站） |
| B站 | [bili-cli](https://github.com/public-clis/bilibili-cli) | OpenCLI ▸ 搜索 API | yt-dlp 被 B站风控 412 封死（2026-06 实测），bili-cli 无登录可搜可读 |
| 搜全网 | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | — | AI 语义搜索，MCP 接入免 Key |
| GitHub | [gh CLI](https://cli.github.com) | — | 官方工具，认证后完整 API 能力 |
| 读 RSS | [feedparser](https://github.com/kurtmckee/feedparser) | — | Python 生态标准选择 |
| 小红书 | [OpenCLI](https://github.com/jackwener/opencli)（桌面） | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（服务器）▸ xhs-cli | xhs-cli 作者已转投 OpenCLI（24K Star）；浏览器登录态零摩擦 |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | Jina Reader | MCP 服务，浏览器自动化 |

> 📌 这些都是「当前选型」，基于真机实测定期复核。某条路失效了我们换下一条——`agent-reach doctor` 永远告诉你现在走的是哪条。

---

## 安全性

Agent Reach 在设计上重视安全：

| 措施 | 说明 |
|------|------|
| 🔒 **凭据本地存储** | Cookie、Token 只存在你本机 `~/.agent-reach/config.yaml`，文件权限 600（仅所有者可读写），不上传不外传 |
| 🛡️ **安全模式** | `agent-reach install --safe` 不会自动修改系统，只列出需要什么，由你决定装不装 |
| 👀 **完全开源** | 代码透明，随时可审查。所有依赖工具也是开源项目 |
| 🔍 **Dry Run** | `agent-reach install --dry-run` 预览所有操作，不做任何改动 |
| 🧩 **可插拔架构** | 不信任某个组件？换掉对应的 channel 文件即可，不影响其他 |

### 🍪 Cookie 安全建议

> ⚠️ **封号风险提醒：** 使用 Cookie 登录的平台（Twitter、小红书等），通过脚本/API 调用**存在被平台检测并封号的风险**。请务必使用**专用小号**，不要用你的主账号。

需要 Cookie 的平台（Twitter、小红书）建议使用**专用小号**，不要用主账号。原因有二：
1. **封号风险** — 平台可能检测到非正常浏览器的 API 调用行为，导致账号被限制或封禁
2. **安全风险** — Cookie 等同于完整登录权限，用小号可以在凭据泄露时限制影响范围

### 📦 安装方式

| 方式 | 命令 | 适合场景 |
|------|------|---------|
| 一键全自动（默认） | `agent-reach install --env=auto` | 个人电脑、开发环境 |
| 安全模式 | `agent-reach install --env=auto --safe` | 生产服务器、多人共用机器 |
| 仅预览 | `agent-reach install --env=auto --dry-run` | 先看看会做什么 |

### 🗑️ 卸载

```bash
agent-reach uninstall
```

会清除：`~/.agent-reach/`（含所有 token/cookie）、各 Agent 的 skill 文件、mcporter 中的 MCP 配置。

```bash
# 只预览，不实际删除
agent-reach uninstall --dry-run

# 只删 skill 文件，保留 token 配置（重装时用）
agent-reach uninstall --keep-config
```

卸载 Python 包本身：`pip uninstall agent-reach`

---

## 贡献

这个项目是纯 vibe coding 出来的 🎸 可能会有一些不完美的地方，如果遇到问题请多多包涵。有 bug 尽管提 [Issue](https://github.com/Panniantong/agent-reach/issues)，我都会尽快修复。

**想要新渠道？** 直接提 Issue 告诉我们，或者自己提 PR。

**想在本地加？** 让你的 Agent clone 下来改就行，每个渠道就是一个独立文件，加起来很简单。

[PR](https://github.com/Panniantong/agent-reach/pulls) 也随时欢迎！

---

## ⭐ 为什么值得 Star

这个项目我自己每天在用，所以我会一直维护它。

- 有新需求或者大家提了想要的渠道，我会陆续加上
- 每个渠道我会尽量保证**能用、好用、免费**
- 平台改了反爬或者 API 变了，我会想办法解决

为 Web 4.0 基建贡献一份自己的力量。

Star 一下，下次需要的时候能找到。⭐

---

## 常见问题 / FAQ

<details>
<summary><strong>AI Agent 怎么搜索 Twitter / X？不想付 API 费用</strong></summary>

Agent Reach 使用 [twitter-cli](https://github.com/public-clis/twitter-cli) 通过 Cookie 认证访问 Twitter，完全免费。安装：`pipx install twitter-cli`，确保浏览器已登录 x.com，Agent 就可以用 `twitter search "关键词"` 搜索、`twitter tweet URL` 读推文了。
</details>

<details>
<summary><strong>How to search Twitter/X with AI agent for free (no API)?</strong></summary>

Agent Reach uses twitter-cli with cookie auth — zero API fees. Install with `pipx install twitter-cli`, make sure you're logged into x.com in your browser, then your agent can search with `twitter search "query"` and read tweets with `twitter tweet URL`.
</details>

<details>
<summary><strong>Reddit 返回 403 怎么办？</strong></summary>

Reddit 所有访问都需要登录态（匿名接口已被全面封锁，官方 API 需人工审批）。桌面首选 **OpenCLI**：浏览器里登录过 reddit.com 即可直接 `opencli reddit search "关键词"`。备选 [rdt-cli](https://github.com/public-clis/rdt-cli)：`pipx install 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66'`（与代码同一钉定版本，PyPI 落后），然后 `rdt login`。中国大陆网络访问 Reddit 需要代理。
</details>

<details>
<summary><strong>How to get YouTube video transcripts for AI?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` extracts video metadata; `yt-dlp --write-sub --skip-download "URL"` extracts subtitles. Uses yt-dlp under the hood, supports multiple languages. No API key needed.
</details>

<details>
<summary><strong>怎么让 AI Agent 读小红书？</strong></summary>

桌面电脑首选 **OpenCLI**（`agent-reach install --channels opencli`）——它复用你浏览器里的登录态，平时刷过小红书就直接能用，零配置；装完在 Chrome 商店点一次「添加扩展」即可。之后 Agent 用 `opencli xiaohongshu search "关键词"` 搜索、`opencli xiaohongshu note URL` 读笔记。服务器上用 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（自带无头浏览器，扫码登录）。已装过 xhs-cli 的老用户不受影响，它仍是备选后端（上游 2026-03 起停更，不推荐新装）。
</details>

<details>
<summary><strong>Compatible with Claude Code / Cursor / OpenClaw / Windsurf?</strong></summary>

Yes! Agent Reach is an installer + configuration tool — any AI coding agent that can run shell commands can use it. Works with Claude Code, Cursor, OpenClaw, Windsurf, Codex, and more. Just `pip install agent-reach`, run `agent-reach install`, and the agent can start using the upstream tools immediately.

**OpenClaw note:** If your OpenClaw is using the default `messaging` tool profile, the agent won't be able to run shell commands. Enable exec first: `openclaw config set tools.profile "coding"` (or set `"tools": { "profile": "coding" }` in `~/.openclaw/openclaw.json`), then restart the Gateway and start a new conversation before installing.
</details>

<details>
<summary><strong>Is this free? Any API costs?</strong></summary>

100% free. All backends are open-source tools (OpenCLI, twitter-cli, bili-cli, rdt-cli, yt-dlp, Jina Reader, Exa, xiaohongshu-mcp, etc.) that don't require paid API keys. The only optional cost is a residential proxy (~$1/month) if your network blocks Reddit/Twitter (e.g. mainland China).
</details>

---

## 致谢

[OpenCLI](https://github.com/jackwener/opencli) · [twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)

## 联系

- 📧 **Email:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

交流或合作可加微信，拉你进交流群：

<p align="center">
  <img src="docs/wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> Bug 反馈和功能请求请用 [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues)，更容易跟踪。

## License

[MIT](LICENSE)

## 友情链接

[腾讯云 OpenClaw](https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&lang=zh&pg=) — 在腾讯云Lighthouse秒级部署OpenClaw全能助手，可通过对话丝滑接入Agent Reach，给你的OpenClaw一键装上互联网能力。

[AtomGit 镜像](https://atomgit.com/qq_51337814/Agent-Reach) — Agent Reach 的 AtomGit 同步镜像，便于国内访问与克隆。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
