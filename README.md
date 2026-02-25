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
  <a href="#30-秒上手">快速开始</a> · <a href="docs/README_en.md">English</a> · <a href="#支持的平台">支持平台</a> · <a href="#设计理念">设计理念</a>
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
| 📕 **小红书** | — | 阅读、搜索、发帖、评论、点赞 | `docker run -d -p 18060:18060 xpzouying/xiaohongshu-mcp` 然后告诉 Agent「帮我配置小红书」 |

> **不知道怎么配？不用查文档。** 直接告诉 Agent「帮我配 XXX」，它知道需要什么、会一步一步引导你。
>
> 🍪 需要 Cookie 的平台（Twitter、小红书等），建议使用 Chrome 插件 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 一键导出。
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

<details>
<summary>它会做什么？（点击展开）</summary>

1. **安装 CLI 工具** — `pip install` 装好 `agent-reach` 命令行
2. **安装系统依赖** — 自动检测并安装 Node.js、gh CLI、mcporter、bird 等
3. **配置搜索引擎** — 通过 MCP 接入 Exa（免费，无需 API Key）
4. **检测环境** — 判断是本地电脑还是服务器，给出对应的配置建议
5. **注册 Skill** — 在 Agent 的 skills 目录安装 SKILL.md，以后 Agent 遇到"搜推特"、"看视频"这类需求，会自动知道调用 Agent Reach

安装完之后，`agent-reach doctor` 一条命令告诉你每个渠道的状态。
</details>

---

## 装好就能用

不需要任何配置，告诉 Agent 就行：

- "帮我看看这个链接" → 任意网页
- "这个 GitHub 仓库是做什么的" → GitHub 仓库、Issue、代码
- "这个视频讲了什么" → YouTube / B站字幕提取
- "帮我看看这条推文" → Twitter 推文
- "订阅这个 RSS" → RSS / Atom 源
- "搜一下 GitHub 上有什么 LLM 框架" → GitHub 搜索

**不需要记命令。** Agent 自己知道该调什么。

---

## 设计理念

**Agent Reach 是一个脚手架（scaffolding），不是框架。**

你给一个新 Agent 装环境的时候，总要花时间去找工具、装依赖、调配置——Twitter 用什么读？Reddit 怎么绕封？YouTube 字幕怎么提取？每次都要重新踩一遍。

Agent Reach 做的事情很简单：**帮你把这些选型和配置的活儿做完了。**

### 🔌 每个渠道都是可插拔的

每个平台对应一个独立的 Python 文件，实现统一接口。**后端工具随时可以换**——哪天出了更好的工具，改一个文件就行，其他不用动。

```
channels/
├── web.py          → Jina Reader     ← 可以换成 Firecrawl、Crawl4AI……
├── twitter.py      → bird           ← 可以换成 Nitter、官方 API……
├── youtube.py      → yt-dlp           ← 可以换成 YouTube API、Whisper……
├── github.py       → gh CLI          ← 可以换成 REST API、PyGithub……
├── bilibili.py     → yt-dlp           ← 可以换成 bilibili-api……
├── reddit.py       → JSON API + Exa  ← 可以换成 PRAW、Pushshift……
├── xiaohongshu.py  → mcporter MCP    ← 可以换成其他 XHS 工具……
├── rss.py          → feedparser       ← 可以换成 atoma……
├── exa_search.py   → mcporter MCP    ← 可以换成 Tavily、SerpAPI……
└── __init__.py     → 渠道注册
```

### 当前选型

| 场景 | 选型 | 为什么选它 |
|------|------|-----------|
| 读网页 | [Jina Reader](https://github.com/jina-ai/reader) | 9.8K Star，免费，不需要 API Key |
| 读推特 | [bird](https://github.com/steipete/bird) | Cookie 登录，免费。官方 API 按量付费（读一条 $0.005） |
| 视频字幕 + 搜索 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 148K Star，YouTube + B站 + 1800 站通吃 |
| 搜全网 | [Exa](https://exa.ai) via [mcporter](https://github.com/nicepkg/mcporter) | AI 语义搜索，MCP 接入免 Key |
| GitHub | [gh CLI](https://cli.github.com) | 官方工具，认证后完整 API 能力 |
| 读 RSS | [feedparser](https://github.com/kurtmckee/feedparser) | Python 生态标准选择，2.3K Star |
| 小红书 | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) | ⭐9K+，Go 语言，Docker 一键部署 |

> 📌 这些都是「当前选型」。不满意？换掉对应文件就行。这正是脚手架的意义。

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

## 致谢

[Jina Reader](https://github.com/jina-ai/reader) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [bird](https://github.com/steipete/bird) · [Exa](https://exa.ai) · [feedparser](https://github.com/kurtmckee/feedparser)

## License

[MIT](LICENSE)
