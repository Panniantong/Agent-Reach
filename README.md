<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>给你的 AI Agent 一键装上互联网能力</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#快速上手">快速开始</a> · <a href="docs/README_en.md">English</a> · <a href="#支持的平台">支持平台</a> · <a href="#设计理念">设计理念</a>
</p>

---

## 为什么需要 Agent Reach？

AI Agent 已经能帮你写代码、改文档、管项目——但你让它去网上找点东西，它就抓瞎了：

- 📺 "帮我看看这个 YouTube 教程讲了什么" → **看不了**，拿不到字幕
- 🐦 "帮我搜一下推特上大家怎么评价这个产品" → **搜不了**，Twitter API 要付费
- 📖 "去 Reddit 上看看有没有人遇到过同样的 bug" → **403 被封**，服务器 IP 被拒
- 📕 "帮我看看小红书上这个品的口碑" → **打不开**，必须登录才能看
- 📺 "B站上有个技术视频，帮我总结一下" → **连不上**，海外/服务器 IP 被屏蔽
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

> ⭐ **Star 这个项目**，我们会持续追踪各平台的变化、接入新的渠道。你不用自己盯——平台封了我们修，有新渠道我们加。

### ✅ 在你用之前，你可能想知道

| | |
|---|---|
| 💰 **完全免费** | 所有工具开源、所有 API 免费。唯一可能花钱的是服务器代理（$1/月），本地电脑不需要 |
| 🔒 **隐私安全** | Cookie 只存在你本地，不上传不外传。代码完全开源，随时可审查 |
| 🔄 **持续更新** | 底层工具（yt-dlp、bird、Jina Reader 等）定期追踪更新到最新版，你不用自己盯 |
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
| 🐦 **Twitter/X** | 读单条推文 | 搜索推文、浏览时间线、发推 | 告诉 Agent「帮我配 Twitter」 |
| 📺 **B站** | 本地：字幕提取 + 搜索 | 服务器也能用 | 告诉 Agent「帮我配代理」 |
| 📖 **Reddit** | 搜索（通过 Exa 免费） | 读帖子和评论 | 告诉 Agent「帮我配代理」 |
| 📕 **小红书** | — | 阅读、搜索、发帖、评论、点赞 | 告诉 Agent「帮我配小红书」 |
| 💼 **LinkedIn** | Jina Reader 读公开页面 | Profile 详情、公司页面、职位搜索 | 告诉 Agent「帮我配 LinkedIn」 |
| 🏢 **Boss直聘** | Jina Reader 读职位页 | 搜索职位、向 HR 打招呼 | 告诉 Agent「帮我配 Boss直聘」 |

> **不知道怎么配？不用查文档。** 直接告诉 Agent「帮我配 XXX」，它知道需要什么、会一步一步引导你。
>
> 🍪 需要 Cookie 的平台（Twitter、小红书等），建议使用 Chrome 插件 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 一键导出。**服务器用户**没有浏览器界面，请在自己的电脑上登录对应网站后导出 Cookie，再发给 Agent 配置。
>
> 🔒 Cookie 只存在你本地，不上传不外传。代码完全开源，随时可审查。
> 💻 本地电脑不需要代理。代理只有部署在服务器上才需要（~$1/月）。

---

## 快速上手

复制这句话给你的 AI Agent（Claude Code、OpenClaw、Cursor 等）：

```
帮我安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
```

就这一步。Agent 会自己完成剩下的所有事情。

> 🛡️ **担心安全？** 可以用安全模式——不会自动装系统包，只告诉你需要什么：
> ```
> 帮我安装 Agent Reach（安全模式）：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> 安装时使用 --safe 参数
> ```

<details>
<summary>它会做什么？（点击展开）</summary>

1. **安装 CLI 工具** — `pip install` 装好 `agent-reach` 命令行
2. **安装系统依赖** — 自动检测并安装 Node.js、gh CLI、mcporter、bird 等
3. **配置搜索引擎** — 通过 MCP 接入 Exa（免费，无需 API Key）
4. **检测环境** — 判断是本地电脑还是服务器，给出对应的配置建议
5. **注册 SKILL.md** — 在 Agent 的 skills 目录安装使用指南，以后 Agent 遇到"搜推特"、"看视频"这类需求，会自动知道该调哪个上游工具

安装完之后，`agent-reach doctor` 一条命令告诉你每个渠道的状态。
</details>

---

## 装好就能用

不需要任何配置，告诉 Agent 就行：

- "帮我看看这个链接" → `curl https://r.jina.ai/URL` 读任意网页
- "这个 GitHub 仓库是做什么的" → `gh repo view owner/repo`
- "这个视频讲了什么" → `yt-dlp --dump-json URL` 提取字幕
- "帮我看看这条推文" → `bird read URL --json`
- "订阅这个 RSS" → `feedparser` 解析
- "搜一下 GitHub 上有什么 LLM 框架" → `gh search repos "LLM framework"`

**不需要记命令。** Agent 读了 SKILL.md 之后自己知道该调什么。

---

## 设计理念

**Agent Reach 是一个脚手架（scaffolding），不是框架。**

你给一个新 Agent 装环境的时候，总要花时间去找工具、装依赖、调配置——Twitter 用什么读？Reddit 怎么绕封？YouTube 字幕怎么提取？每次都要重新踩一遍。

Agent Reach 做的事情很简单：**帮你把这些选型和配置的活儿做完了。**

安装完成后，Agent 直接调用上游工具（bird CLI、yt-dlp、mcporter、gh CLI 等），不需要经过 Agent Reach 的包装层。

### 🔌 每个渠道都是可插拔的

每个平台背后是一个独立的上游工具。**不满意？换掉就行。**

```
channels/
├── web.py          → Jina Reader     ← 可以换成 Firecrawl、Crawl4AI……
├── twitter.py      → bird            ← 可以换成 Nitter、官方 API……
├── youtube.py      → yt-dlp          ← 可以换成 YouTube API、Whisper……
├── github.py       → gh CLI          ← 可以换成 REST API、PyGithub……
├── bilibili.py     → yt-dlp          ← 可以换成 bilibili-api……
├── reddit.py       → JSON API + Exa  ← 可以换成 PRAW、Pushshift……
├── xiaohongshu.py  → mcporter MCP    ← 可以换成其他 XHS 工具……
├── linkedin.py     → linkedin-mcp    ← 可以换成 LinkedIn API……
├── bosszhipin.py   → mcp-bosszp      ← 可以换成其他招聘工具……
├── rss.py          → feedparser      ← 可以换成 atoma……
├── exa_search.py   → mcporter MCP    ← 可以换成 Tavily、SerpAPI……
└── __init__.py     → 渠道注册（doctor 检测用）
```

每个渠道文件只负责检测对应上游工具是否可用（`check()` 方法），给 `agent-reach doctor` 提供状态信息。实际的读取和搜索由 Agent 直接调用上游工具完成。

### 当前选型

| 场景 | 选型 | 为什么选它 |
|------|------|-----------|
| 读网页 | [Jina Reader](https://github.com/jina-ai/reader) | 9.8K Star，免费，不需要 API Key |
| 读推特 | [bird](https://www.npmjs.com/package/@steipete/bird) | Cookie 登录，免费。官方 API 按量付费（读一条 $0.005） |
| 视频字幕 + 搜索 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 148K Star，YouTube + B站 + 1800 站通吃 |
| 搜全网 | [Exa](https://exa.ai) via [mcporter](https://github.com/steipete/mcporter) | AI 语义搜索，MCP 接入免 Key |
| GitHub | [gh CLI](https://cli.github.com) | 官方工具，认证后完整 API 能力 |
| 读 RSS | [feedparser](https://github.com/kurtmckee/feedparser) | Python 生态标准选择，2.3K Star |
| 小红书 | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) | ⭐9K+，Go 语言，Docker 一键部署 |
| LinkedIn | [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) | ⭐900+，MCP 服务，浏览器自动化 |
| Boss直聘 | [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp) | MCP 服务，支持职位搜索和打招呼 |

> 📌 这些都是「当前选型」。不满意？换掉对应文件就行。这正是脚手架的意义。

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

需要 Cookie 的平台（Twitter、小红书）建议使用**专用小号**，不要用主账号。Cookie 等同于完整登录权限，用小号可以在凭据泄露时限制影响范围。

### 📦 安装方式

| 方式 | 命令 | 适合场景 |
|------|------|---------|
| 一键全自动（默认） | `agent-reach install --env=auto` | 个人电脑、开发环境 |
| 安全模式 | `agent-reach install --env=auto --safe` | 生产服务器、多人共用机器 |
| 仅预览 | `agent-reach install --env=auto --dry-run` | 先看看会做什么 |

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

Agent Reach 使用 [bird CLI](https://www.npmjs.com/package/@steipete/bird) 通过 Cookie 认证访问 Twitter，完全免费。安装 Agent Reach 后，用 Cookie-Editor 导出你的 Twitter Cookie，运行 `agent-reach configure twitter-cookies "your_cookies"` 即可。之后 Agent 就可以用 `bird search "关键词" --json` 搜索推文了。
</details>

<details>
<summary><strong>How to search Twitter/X with AI agent for free (no API)?</strong></summary>

Agent Reach uses the bird CLI with cookie auth — zero API fees. After installing, export your Twitter cookies with the Cookie-Editor extension, run `agent-reach configure twitter-cookies "your_cookies"`, then your agent can search with `bird search "query" --json`.
</details>

<details>
<summary><strong>Reddit 返回 403 / 服务器 IP 被封怎么办？</strong></summary>

Reddit 封锁数据中心 IP。配置一个住宅代理即可解决：`agent-reach configure proxy http://user:pass@ip:port`。推荐 Webshare ($1/月)。本地电脑一般不会遇到这个问题。
</details>

<details>
<summary><strong>How to get YouTube video transcripts for AI?</strong></summary>

`yt-dlp --dump-json "https://youtube.com/watch?v=xxx"` extracts video metadata; `yt-dlp --write-sub --skip-download "URL"` extracts subtitles. Uses yt-dlp under the hood, supports multiple languages. No API key needed.
</details>

<details>
<summary><strong>怎么让 AI Agent 读小红书？</strong></summary>

小红书需要通过 Docker 运行一个 MCP 服务。安装 Docker 后，运行 `agent-reach install` 会自动配置。之后 Agent 就能用 `mcporter call 'xiaohongshu.get_feed_detail(...)'` 读取笔记或 `mcporter call 'xiaohongshu.search_feeds(keyword: "关键词")'` 搜索了。
</details>

<details>
<summary><strong>Compatible with Claude Code / Cursor / OpenClaw / Windsurf?</strong></summary>

Yes! Agent Reach is an installer + configuration tool — any AI coding agent that can run shell commands can use it. Works with Claude Code, Cursor, OpenClaw, Windsurf, Codex, and more. Just `pip install agent-reach`, run `agent-reach install`, and the agent can start using the upstream tools immediately.
</details>

<details>
<summary><strong>Is this free? Any API costs?</strong></summary>

100% free. All backends are open-source tools (bird CLI, yt-dlp, Jina Reader, Exa, etc.) that don't require paid API keys. The only optional cost is a residential proxy (~$1/month) if you need Reddit/Bilibili access from a server.
</details>

---

## 致谢

[Jina Reader](https://github.com/jina-ai/reader) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [bird](https://www.npmjs.com/package/@steipete/bird) · [Exa](https://exa.ai) · [mcporter](https://github.com/steipete/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) · [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server) · [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp)

## License

[MIT](LICENSE)
