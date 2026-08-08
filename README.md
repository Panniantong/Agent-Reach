<h1 align="center">👁️ Agent Reach</h1>

<p align="center">
  <strong>给你的 AI Agent 一键装上互联网能力</strong>
</p>

<p align="center">
  当下最稳的接入方式，替你选好、装好、体检好——接入方式会换代，你不用操心
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/24387"><img src="https://trendshift.io/api/badge/repositories/24387" alt="Trendshift GitHub Trending #1 Repository of the Day"></a>
  <a href="https://star-history.com/#Panniantong/Agent-Reach&Date"><img src="https://api.star-history.com/badge?repo=Panniantong/Agent-Reach" alt="Star History Rank" width="196" height="55"></a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://github.com/Panniantong/agent-reach/stargazers"><img src="https://img.shields.io/github/stars/Panniantong/agent-reach?style=for-the-badge" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#快速上手">快速开始</a> · <a href="docs/README_en.md">English</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_ko.md">한국어</a> · <a href="#支持的平台">支持平台</a> · <a href="#设计理念">设计理念</a>
</p>

---

## ❤️赞助商

> [想出现在这里？](mailto:pnt01@foxmail.com)

<details open>
<summary>点击折叠</summary>

<table>
<tr>
<td width="180" align="center"><a href="https://www.browseract.ai/Agent"><img src="docs/assets/sponsors/browseract.png" alt="BrowserAct" width="150"></a></td>
<td><a href="https://www.browseract.ai/Agent">BrowserAct</a> 支持从 Amazon、LinkedIn、X、Google Maps 等复杂网站提取你需要的任意数据。你只需用自然语言描述抓取需求，Agent 就会基于真实浏览器自动探索并测试页面流程，生成可靠、可复用的数据采集 Bot，并返回结构化结果。无需手动构建爬虫，无需编写代码。BrowserAct 内置隐身浏览、验证码处理和高质量住宅代理，帮助你更稳定地完成复杂网页数据采集。新用户注册即送 1000 积分，<a href="https://www.browseract.ai/Agent">立即免费试用</a>。</td>
</tr>
<tr>
<td width="180" align="center"><a href="https://www.tencentcloud.com/act/pro/intl-openclaw?referral_code=G76Y819A&amp;lang=zh&amp;pg="><img src="docs/assets/sponsors/tencent-cloud.svg" alt="腾讯云 OpenClaw" width="150"></a></td>
<td>在腾讯云 Lighthouse 秒级部署 OpenClaw 全能助手，可通过对话丝滑接入 Agent Reach，给你的 OpenClaw 一键装上互联网能力。</td>
</tr>
<tr>
<td width="180" align="center"><a href="https://www.coreclaw.com/?utm_source=github&amp;utm_medium=referral&amp;utm_campaign=Reach&amp;utm_term=Reach&amp;utm_id=Reach"><img src="docs/assets/sponsors/coreclaw.png" alt="CoreClaw" width="150"></a></td>
<td><a href="https://www.coreclaw.com/?utm_source=github&amp;utm_medium=referral&amp;utm_campaign=Reach&amp;utm_term=Reach&amp;utm_id=Reach">CoreClaw</a> | 网页抓取平台与现成数据采集工具，CoreClaw 提供 100+ 现成数据采集工具，支持 Amazon、TikTok、Google Maps、Instagram、Facebook、YouTube 等平台，无需代码，支持 JSON/CSV 导出，仅对成功结果计费。<a href="https://www.coreclaw.com/?utm_source=github&amp;utm_medium=referral&amp;utm_campaign=Reach&amp;utm_term=Reach&amp;utm_id=Reach">免费$3测试！</a></td>
</tr>
</table>

</details>

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
| 📘 **Facebook** | — | 搜索、主页、Feed、群组列表 | 桌面装 OpenCLI（复用 Chrome 登录态） |
| 📷 **Instagram** | — | 用户搜索、Profile、用户最近帖子、Explore | 桌面装 OpenCLI（复用 Chrome 登录态） |
| 📕 **小红书** | — | 搜索、阅读、评论 | OpenCLI 只用用户已有 Chrome 会话；MCP/存量工具用 Cookie-Editor |
| 💼 **LinkedIn** | Jina Reader 读公开页面 | Profile 详情、公司页面、职位搜索 | 告诉 Agent「帮我配 LinkedIn」 |
| 💻 **V2EX** | 热门帖子、节点帖子、帖子详情+回复、用户信息 | — | 无需配置 |
| 📰 **Substack** | 出版物近期文章列表、公开文章读取（RSS / JSON API） | — | 无需配置 |
| 📈 **雪球** | 股票行情、搜索股票、热门帖子、热门股票排行 | — | 告诉 Agent「帮我配雪球」 |
| 🎙️ **小宇宙播客** | — | 播客音频转文字（Whisper 转录，免费 Key） | 告诉 Agent「帮我配小宇宙播客」 |

> **不知道怎么配？不用查文档。** 直接告诉 Agent「帮我配 XXX」，它知道需要什么、会一步一步引导你。
>
> 🍪 Twitter 只接受用户通过 Cookie-Editor 手工导出的内容。Agent Reach 不替用户执行小红书登录，也不读取小红书浏览器 Cookie；OpenCLI 只使用用户已经存在且明确控制的 Chrome 会话。`agent-reach configure xhs-cookies` 不会把 Cookie 注入 OpenCLI / Chrome；没有现成会话时，改用 Cookie-Editor 导出后配置 xiaohongshu-mcp / 存量工具。
>
> Twitter Cookie 保存后仅供 `agent-reach doctor` 检查配置是否齐全；直接运行上游 `twitter` 命令前，仍需在当前进程环境中显式设置 `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`。
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

> 🛡️ **默认安全：** `agent-reach install` 默认只检查环境，不会自动装系统包或写入配置：
> ```
> 帮我安全检查并安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
> ```
> 只有在你明确允许修改系统后，才使用 `agent-reach install --system`。

<details>
<summary>它会做什么？（点击展开）</summary>

1. **安装 CLI 工具** — 从本仓库安装 `agent-reach` 命令行（自带 yt-dlp、feedparser；不要从 PyPI 安装同名包，它不是本项目）
2. **检查系统基建** — 检查 Node.js、gh CLI、mcporter，并给出缺失项的安装方式
3. **按授权安装与配置** — 仅在显式传入 `--system` 时安装依赖并通过 MCP 接入 Exa
4. **检测环境** — 判断是本地电脑还是服务器，给出对应的配置建议
5. **按授权注册 SKILL.md** — 仅在显式 `--system` 时写入 Agent 的 skills 目录；默认检查不改文件
6. **问你要不要更多** — 默认只激活 6 个零配置渠道；小红书、Twitter、Reddit、Facebook、Instagram 这些需要登录态的，Agent 会列菜单问你要哪些，点名才装

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

**不需要记命令。** Agent 读了 SKILL.md 之后自己知道该调什么。需要登录的平台（小红书、Twitter、Reddit、Facebook、Instagram），告诉 Agent「帮我配 XXX」即可解锁。

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
├── facebook.py     → OpenCLI（桌面浏览器登录态）
├── instagram.py    → OpenCLI（桌面浏览器登录态）
├── xiaohongshu.py  → OpenCLI ▸ xiaohongshu-mcp ▸ xhs-cli
├── linkedin.py     → mcp-server-linkedin ▸ Jina Reader
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
| Facebook | [OpenCLI](https://github.com/jackwener/opencli)（桌面） | — | Graph API/Groups API 权限收紧；浏览器登录态是当前最实用路径 |
| Instagram | [OpenCLI](https://github.com/jackwener/opencli)（桌面） | 官方 Graph API（Business/Creator + 审批） | instaloader 类路径不稳定；OpenCLI 复用真实浏览器会话 |
| YouTube 字幕 + 搜索 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | — | 154K Star，YouTube 仍是最佳（注意：不再用于 B站） |
| B站 | [bili-cli](https://github.com/public-clis/bilibili-cli) | OpenCLI ▸ 搜索 API | yt-dlp 被 B站风控 412 封死（2026-06 实测），bili-cli 无登录可搜可读 |
| 搜全网 | [Exa](https://exa.ai) via [mcporter](https://github.com/nicobailon/mcporter) | — | AI 语义搜索，MCP 接入免 Key |
| GitHub | [gh CLI](https://cli.github.com) | — | 官方工具，认证后完整 API 能力 |
| 读 RSS | [feedparser](https://github.com/kurtmckee/feedparser) | — | Python 生态标准选择 |
| 小红书 | [OpenCLI](https://github.com/jackwener/opencli)（桌面） | [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（服务器）▸ xhs-cli | OpenCLI 只用用户已有会话；其余后端用 Cookie-Editor 手工导出 |
| LinkedIn | [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server) | Jina Reader | MCP 服务，浏览器自动化 |

> 📌 这些都是「当前选型」，基于真机实测定期复核。某条路失效了我们换下一条——`agent-reach doctor` 永远告诉你现在走的是哪条。

---

## 安全性

Agent Reach 在设计上重视安全：

| 措施 | 说明 |
|------|------|
| 🔒 **凭据本地存储** | Cookie、Token 只存在你本机 `~/.agent-reach/config.yaml`，文件权限 600（仅所有者可读写），不上传不外传 |
| 🛡️ **默认安全** | `agent-reach install` 默认不修改系统；只有显式 `--system` 才安装外部工具和写入配置 |
| 👀 **完全开源** | 代码透明，随时可审查。所有依赖工具也是开源项目 |
| 🔍 **Dry Run** | `agent-reach install --dry-run` 预览所有操作，不做任何改动 |
| 🧩 **可插拔架构** | 不信任某个组件？换掉对应的 channel 文件即可，不影响其他 |

### 🍪 Cookie 安全建议

> ⚠️ **封号风险提醒：** 使用 Cookie 登录的平台（Twitter、小红书等），通过脚本/API 调用**存在被平台检测并封号的风险**。请务必使用**专用小号**，不要用你的主账号。

需要 Cookie 或登录态的平台（Twitter、小红书、Reddit、Facebook、Instagram 等）建议使用**专用小号**，不要用主账号。原因有二：
1. **封号风险** — 平台可能检测到非正常浏览器的 API 调用行为，导致账号被限制或封禁
2. **安全风险** — Cookie 等同于完整登录权限，用小号可以在凭据泄露时限制影响范围

### 📦 安装方式

| 方式 | 命令 | 适合场景 |
|------|------|---------|
| 默认安全检查 | `agent-reach install --env=auto` | 所有环境；只读检查并列出缺失项 |
| 显式安装系统依赖 | `agent-reach install --env=auto --system` | 你明确允许修改当前机器时 |
| 兼容安全参数 | `agent-reach install --env=auto --safe` | 与默认行为相同 |
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

## ⭐ 为什么值得 Star

这个项目我自己每天在用，所以我会一直维护它。

- 有新需求或者大家提了想要的渠道，我会陆续加上
- 每个渠道我会尽量保证**能用、好用、免费**
- 平台改了反爬或者 API 变了，我会想办法解决

为 Web 4.0 基建贡献一份自己的力量。

Star 一下，下次需要的时候能找到。⭐

---

## 致谢

[OpenCLI](https://github.com/jackwener/opencli) · [twitter-cli](https://github.com/public-clis/twitter-cli) · [rdt-cli](https://github.com/public-clis/rdt-cli) · [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) · [xhs-cli](https://github.com/jackwener/xiaohongshu-cli) · [bili-cli](https://github.com/public-clis/bilibili-cli) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Jina Reader](https://github.com/jina-ai/reader) · [Exa](https://exa.ai) · [mcporter](https://github.com/nicobailon/mcporter) · [feedparser](https://github.com/kurtmckee/feedparser) · [mcp-server-linkedin](https://github.com/stickerdaniel/linkedin-mcp-server)

## 联系

- 📧 **Email:** pnt01@foxmail.com
- 🐦 **Twitter/X:** [@Neo_Reidlab](https://x.com/Neo_Reidlab)

## 业务合作 / Agent 落地

我正在承接 Agent 相关的定制与落地合作。

如果你在企业生产、运营、市场、投研、数据处理、内容处理或其他业务流程里，有希望用 Agent 自动化的环节，欢迎加我微信交流。

不需要你已经想清楚方案。只要你有真实流程、真实问题或真实需求，我可以一起判断 Agent 能不能解决、怎么做。

加好友请备注：`业务 + 你想让 Agent 帮你做什么`

Builder 也欢迎备注：`Builder + 你在做什么`

只是想进交流群，备注：`加群`

<p align="center">
  <img src="docs/wechat-group-qr.jpg" width="280" alt="WeChat QR">
</p>

> Bug 反馈和功能请求请用 [GitHub Issues](https://github.com/Panniantong/Agent-Reach/issues)，更容易跟踪。

## License

[MIT](LICENSE)

## 友情链接

[Agent Skills Hub](https://agentskillshub.top/) — 找 Claude 技能和 MCP 服务器，不用猜哪个安全：133,000+ 个条目全部安全分级、质量评分，每 8 小时刷新。

[AtomGit 镜像](https://atomgit.com/qq_51337814/Agent-Reach) — Agent Reach 的 AtomGit 同步镜像，便于国内访问与克隆。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Panniantong/Agent-Reach&type=Date&v=20260309)](https://star-history.com/#Panniantong/Agent-Reach&Date)
