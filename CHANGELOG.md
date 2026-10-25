# Changelog / 更新日志

All notable changes to this project will be documented in this file.

本项目的所有重要变更都会记录在此文件中。

---


## [Unreleased]

中文：

- YouTube 新增 `transcript` 动作：用户自己配置托管转录 API 的 Key 后，由该服务取字幕，本机不向 YouTube 发请求。它是单独的动作，不会在 YouTube 验证拦截后自动切换，也不会在多个服务之间自动切换。

English:

- YouTube gets a `transcript` action that reads the transcript from a hosted transcript API the user configured (`agent-reach configure transcript-api-key`, optional `transcript-api-provider`). The provider fetches the captions, so nothing is requested from YouTube on this machine. It is a separate action: it never runs as a fallback after a YouTube verification challenge, and never switches between providers on its own. The provider table in `agent_reach/hosted_transcript.py` takes one entry per service.

## [1.6.0] - 2026-10-23

中文：

- 从旧版升级：把"帮我更新 Agent Reach"那句话发给你的 AI 就行。你的密钥和设置都保留，旧版程序会自动删掉。
- 加一个平台只要说一句，需要的软件都会自动装好，不需要管理员密码；你只需要登录或者填一个 Key。
- 小红书、推特这类要登录的平台，改用 Agent Reach 自己的专用浏览器，不弹窗、不占用你的浏览器；多个 AI 可以同时查。
- RSS 订阅和 Exa 全网搜索合并进了"网页"。以后有新版本，AI 会用大白话告诉你改了什么，你同意了才更新。

English:

- Upgrading from an older version: just send your AI the "update Agent Reach" sentence. Your keys and settings are kept, and the old program is removed for you.
- Adding a platform takes one sentence. Everything it needs is installed for you, with no admin password; you only log in or enter a key.
- Platforms that need a login, such as Xiaohongshu and X, now use Agent Reach's own browser in the background, never yours, and several AIs can search at once.
- RSS and Exa search are now part of "web". When a new version is out, your AI tells you in plain words what changed and updates only if you say yes.

1.6 is a rebuild. Agents call one command, `agent-reach`; everything Agent Reach installs or stores lives under `~/.agent-reach/`.
1.6 是重构版本：Agent 只调一个命令 `agent-reach`，Agent Reach 装的、存的东西全部在 `~/.agent-reach/` 下。

中文（技术细节）：
- 本版发布前已真实测通 28/40 个动作；以下未在发布机上测通，经维护者批准随本版发布：Reddit（测试网络被拦）、Instagram（限流）、B站字幕、LinkedIn、雪球热帖热股（未登录）、小宇宙（未配 Key）。
- 修复未登录 gh 阻断公开 API、公开行情触发浏览器、错误认证提示和未登记缓存清理；临时音频/字幕保存在 Reach 内。BOSS 站内搜索优先官方 OpenCLI，JD 上游适配故障单列；PR 与发版均检查真实验收和待验状态。
- CLI 对已声明的公开搜索/阅读先复用网页工具，成功后不准备浏览器；结果标注来源和内容范围，站内路径明确要求认证时才提示登录。可指定后端保留原有站内能力。
- 浏览器渠道共用一份登录，闲置十分钟自动关闭，下次使用自动打开。
- 添加渠道自动准备工具；删除时只清理该网站的登录。默认平台也能去掉，去掉后更新不会再加回来。
- 更新时，有已测版本的工具保持在已测版本，其他工具用兼容范围内的最新版。
- 公开内容继续先读，不强制登录；安装后用简短表格说明能查什么。
- 保留小宇宙转录；去掉额外模型配置和重复的网站抓取实现。
- Bridge 随专用浏览器管理；按真实页面操作计时、定期保存登录。清理失败保留渠道，卸载只删台账文件。发布前必须有渠道真实验收。
- 查询默认无头，优先只读复用本机已有的站点登录；显窗登录与无头查询共用配置。B站字幕、雪球社区自动同步登录，BOSS JD 使用上游浏览器接口。缺失接口和限流不再误报为需要重登。
- 专用浏览器按扩展保存在它自己配置里的编号识别，不会再把用户日常的 Chrome 认成专用浏览器；登录窗口开着时查询不再把它收掉。
- 浏览器渠道可以并行查询：同一平台最多 2 条、合计 4 条同时跑，多出来的排队而不是立刻报"正忙"；登录窗口、退出登录等操作等正在跑的查询结束再做。
- 没登录时报"需要登录"而不是"上游工具坏了"：雪球社区（错误码 400016）、B站字幕（没有 B站登录）、LinkedIn（专用浏览器里没有 LinkedIn 登录）。
- 从 1.5 升级更顺：安装和更新合成一份 install.md，先看版本再分流（旧版指向的 update.md 转到它）；`agent-reach update` 遇到 pip/pipx 装的旧版会自己换成 uv 安装；`setup` 删掉旧版 Agent Reach 程序（只删它自己，不动其他工具），安装汇报说明保留了什么、变了什么、以前用过哪些渠道可以加回来。安装地址改为始终指向最新正式版。
- 平台出错时，报错原话和自带的处理建议原样交给 AI，由 AI 用平台名告诉用户哪个平台暂时有问题；不再用 Reach 自己编的建议覆盖（"要登录"仍给 Reach 自己专用浏览器的登录步骤）。

English (technical):
- 28 of 40 actions passed real acceptance before release; these shipped untested with maintainer approval: Reddit (test network blocked), Instagram (rate limited), Bilibili subtitles, LinkedIn, Xueqiu hot posts/stocks (no login), Xiaoyuzhou (no key).
- Browser channels share one profile, close after ten idle minutes and reopen on demand.
- Adding a channel prepares its tools; removal clears only that site's login. Default platforms can be removed and updates won't add them back.
- Updating keeps tools that have a tested version at that version; other tools get the newest version inside their supported range.
- Public content remains public-first, with a compact capability receipt.
- Keep Xiaoyuzhou transcription; remove the extra planner and duplicate site extraction.
- Reuse existing local site sessions read-only; queries default to headless, with a visible window for human login.
- The dedicated browser is identified by the id its extension saves inside its own profile, so the user's own Chrome is never mistaken for it; a query no longer closes an open login window.
- Browser channels run queries in parallel: up to 2 per platform and 4 in total, with the rest queued instead of failing BUSY at once; login windows, logout and browser setup wait for running queries.
- Report NEED_LOGIN instead of UPSTREAM_BROKEN when not logged in: Xueqiu community (error 400016), Bilibili subtitles (no Bilibili login), LinkedIn (no LinkedIn login in the dedicated browser).
- Smoother upgrade from 1.5: install and update share one guide, install.md, which checks the version first (update.md, where 1.5 sends users, points to it); `agent-reach update` moves a pip/pipx install to uv by itself; `setup` removes the old Agent Reach program (only Agent Reach itself) and the install report explains what was kept, what changed and which old channels can be added back. Install URLs always point at the latest release.
- Upstream errors reach the agent unchanged (the original message and help); the agent tells the user which platform is temporarily unavailable, by platform name. Reach no longer replaces them with its own advice (NEED_LOGIN still gives Reach's dedicated-browser login steps).

### ✨ New / 新增

- **Unified entry / 统一入口**: `agent-reach <channel> <action>`, `agent-reach read <url>`, `agent-reach channels`. One JSON envelope per call, unified error codes with hints, per-call timeout, automatic fallback to the next backend.
- **Management / 管理命令**: `setup`, `add` / `remove <channel>`, `login` / `logout <channel>`, `doctor`, `check`, `skill`, `skill link <dir>`, `update`, `configure`, `uninstall`.
- **One-step setup / 一步装好**: `setup` adds every default channel through the same path as `add` (bili-cli goes into `~/.agent-reach/tools/`) and reports what works, which AIs can read the skill, optional channels and optional logins. / `setup` 用和 `add` 同一套逻辑开启全部默认渠道，并汇报哪些能用、哪些 AI 能读到 skill、可选渠道和可选登录。
- **Skill placement / skill 放置**: one real copy at `~/.agents/skills/agent-reach/SKILL.md` (read directly by Codex, OpenCode, Cline, Warp, Zed); a link to it in the skill folder of Claude Code, OpenClaw, Hermes, Cursor, Gemini CLI, GitHub Copilot and Windsurf when installed (a copy where links are not allowed, e.g. Windows). `agent-reach skill link <dir>` covers any other AI. / 只放一份真文件，其他 AI 的 skill 目录里放指向它的链接（链接：一个指向原文件的快捷方式）。
- **Private upstream installs, tested versions / 上游私有安装，用已测版本**: tools go into `~/.agent-reach/tools/`; the user's own copies are untouched. Tools with a declared tested version install at that version, and `update` keeps them there; other tools install the newest version inside `floor` and `exclude`, which also define acceptable existing tools. `state.json` records the version actually installed and `doctor` shows it. Single-instance tools (OpenCLI) reuse the user's copy; if it is outside the supported versions, it is upgraded only with `--allow-upgrade`. / 有已测版本的工具装已测版本，`update` 也保持不变；其他工具用兼容范围内的最新版；doctor 显示实际版本。
- **`add` gives a finished result / `add` 一步到位**: missing prerequisites are installed without an admin password: uv (official script), ffmpeg (`imageio-ffmpeg` in a private venv), Node.js (official release under `~/.agent-reach/tools/node/` when the system has none), CloakBrowser (falling back to installed Chrome on download failure). git is no longer needed (Boss installs from a GitHub archive). The user only logs in or enters a key. / 缺的依赖自动装好，用户只需登录或填 Key。
- **Login state under `~/.agent-reach/` / 登录状态统一管理**: CLI tool logins in `sessions/`, browser logins in a dedicated Agent Reach browser. The browser opens by itself when a channel needs it and closes after 10 minutes without use. The OpenCLI extension is loaded automatically on each CloakBrowser launch; Windows system-Chrome fallback may need one Web Store click. Only the requested site’s cookies are copied read-only from an existing connected local browser; the source remains unchanged. / 专用浏览器按需自动打开，10 分钟不用自动关闭；macOS/Linux 自动装好扩展。
- **remove cleans up / 去掉渠道会清理干净**: deletes the channel's private tools nobody else uses, its CLI session, its login keys and its site cookies in the Agent Reach browser. The shared browser profile is retained for explicit logout/reuse; unused private tools are pruned.
- **Removable default channels / 默认渠道可去掉**: `state.json` records `removed_defaults`; `setup` and `update` never add them back; `add` brings one back.
- **doctor states / 体检**: not_added, needs_setup, needs_login, unverified, ready, broken; plus `regressed` per channel (passed in the previous check, fails in the latest).
- **update** runs `uv tool install --force` on the latest release, reinstalls every added channel's tools at their declared versions (tested version when set, otherwise the newest version inside `floor`/`exclude`; also when Agent Reach itself has no new release), prunes tools no added channel uses, drops channels no longer in the registry, and refreshes the skill. `result.user_actions` lists in plain sentences what the user must do afterwards. Rollback: `uv tool install --force <previous release zip>`, then `agent-reach update --sync-only`. uv is the only supported installer. 1.5 and earlier installs are migrated on first `setup` / `update`; `config.yaml` keys are kept.
- **Update notice / 新版本提醒**: explicit `update --check` refreshes the release cache. Ordinary queries never start a background version check or update dependencies. Cached newer releases appear in `meta.update`; updating requires the user’s agreement. / 只在明确检查后提示新版本，用户同意才更新。
- **Release notes / 发布说明**: every CHANGELOG version section starts with a plain summary for users in Chinese and English; it becomes the GitHub release body the AI shows users.
- Xueqiu quotes and stock search via Tencent public quotes (no login); Xueqiu community data uses a session synced from the dedicated browser with `agent-reach login xueqiu --sync`.
- YouTube `transcribe`; LinkedIn reuses OpenCLI search and job-detail in the shared dedicated browser.

### 🔄 Changed / 变更

- Default channels: web (fallback only), YouTube, GitHub, V2EX, B站. Optional: 小红书, Reddit, LinkedIn, Boss直聘, 小宇宙, 雪球. Experimental: Twitter, Facebook, Instagram.
- The agent skill is generated from the channel list and replaced on every update.

### 🗑️ Removed / 移除

- RSS channel (agents read feeds themselves).
- xhs-cli, rdt-cli, twitter-cli backends: they read browser cookies by themselves.
- `configure --from-browser`, `twitter-cookies`, `xhs-cookies`, the old `install --channels`, the old `skill --install`, `format`, `check-update`, MCP server entry.
- `watch` (use `doctor`, which now reports `regressed`), `doctor --live` (use `check`), `browser start` (the browser opens by itself), pipx installs.

### 🐛 Bug Fixes / 修复

#### 🔐 Boss直聘 — 登录态误判（双凭据存储）

- **根因：** Boss 有两个互不代表的登录态存储——本地 `~/.boss-agent/auth/session.enc`
  和专用 Chrome profile 内的浏览器 cookie。`boss status` / `status --live` **只校验前者**
  （Bridge/httpx 时代的遗留凭据库），而 `existing-browser` 严格 CDP 模式下搜索走的是浏览器 cookie。
  「本地有旧凭据 + 浏览器未登录」时 `boss status` 会报 `logged_in: true`，误导 Agent
  跳过登录直接搜索，最终撞上 `AUTH_EXPIRED`；旧 runbook 又禁止把 `_security_check`
  当成未登录，两条规则叠加把 Agent 推向「反爬滑块」的错误分支。
- **修复：** `check()` 新增第 4 层只读探测 `_cdp_zhipin_login_cookie()`，用纯标准库
  实现的最小 WebSocket 客户端直接问 CDP 浏览器本体（`Storage.getCookies`）有无 zhipin
  的 `wt2` cookie，**以浏览器为准**，不引入新依赖、不拉起浏览器、不执行搜索。
  无 wt2 → 明确报「浏览器未登录，搜索会报 AUTH_EXPIRED」并指向「用户登录 +
  `login --cdp`」；探测失败 → 报「登录态未知」；安全校验页提示也附带浏览器 cookie 状态。
- **Runbook 修正：** 删除误导规则「判断登录态只信 `boss status`」，改为以 doctor 的
  浏览器 cookie 探测为准；拉起专用 Chrome 后**强制暂停让用户肉眼确认**登录状态；
  `AUTH_EXPIRED` 定为 ground truth（直接走登录流程，禁止往安全校验方向解释），
  `_security_check` 仅在无 `AUTH_EXPIRED` 时按滑块处理。

### ✨ Features / 新增

#### 🎯 Boss直聘 channel

- 新增 `boss` channel：经 boss-agent-cli + CDP 真 Chrome 搜岗位、取 JD 全文。
- `check()` 四层只读探测（boss-agent-cli 装没装 → 9222 端口通不通 → 有无 zhipin 页签
  → 浏览器内有无 `wt2` 登录 cookie）。
- 抓取走公开 API（`search_jobs` + `job_card_browser` + `browser_source="existing-browser"`）。
- `agent-reach install --system --channels=boss` 可安装锁定上游 boss-agent-cli
  （#403–#407 已合并入 master）固定提交的后端；上游发布正式版后切回版本约束。
- Skill 与安装指南支持“帮我配 Boss直聘”：Agent 启动仅监听回环地址的专用 Chrome，
  用户只负责手动登录，最后由 Agent 验证登录态与 CDP 链路。
- 固定依赖从 fork 快照 `8ff6bd3` 切换到上游 commit `4c991b7`（#403–#407 已合并入
  master）：已登录 CDP 会话可直接复用，搜索可通过 `--browser-source existing-browser`
  禁止 headless 降级。
- code 37 按原始文案分类：环境异常为 `ENVIRONMENT_RISK` 并立即停止；只有明确
  token/stoken 过期才允许一次刷新。专用 Chrome profile 应长期复用并降低频率。

## [1.3.1] - 2026-03-27

### 🐛 Bug Fixes / 修复

#### 📈 Xueqiu (雪球) — 全面修复

- **修复 400 错误根本原因：** `_ensure_cookies()` 仅访问首页只能获取 `acw_tc`（防 DDoS token），`xq_a_token` 由雪球前端 JS 动态生成，无法通过纯 HTTP 请求获取。新增三级 cookie 加载策略：① 读取 config 文件（`--from-browser` 保存的）→ ② 自动从本地 Chrome 浏览器提取（需安装 browser-cookie3）→ ③ homepage fallback
- **修复 User-Agent：** `"agent-reach/1.0"` 被雪球反爬系统识别拒绝，改为真实 Chrome UA
- **修复缺失 `Referer` 头：** 所有 API 请求加上 `Referer: https://xueqiu.com/`
- **修复 `get_hot_posts()` 端点：** 原端点 `/statuses/hot/listV3.json` 已废弃（返回空 body），改为 `/v4/statuses/public_timeline_by_category.json`，正确解析 `item.data` JSON 字符串获取 author/likes/text
- **修复 `urllib.request.quote` → `urllib.parse.quote`：** 明确使用正确模块
- **修复 `configure --from-browser` 不提取雪球 Cookie：** `PLATFORM_SPECS` 加入 Xueqiu，检测 `xq_a_token` 存在才保存
- **修正文档误导：** README/SKILL.md 中"无需配置"/"public API, no login required" → 准确描述需要 browser cookie
- **改善错误信息：** `check()` 失败时提示 `configure --from-browser chrome` 而非"可能需要代理"

---

## [1.3.0] - 2026-03-12

### 🆕 New Channels / 新增渠道

#### 💻 V2EX
- Hot topics, node topics, topic detail + replies, user profile via public JSON API
- Zero config — no auth, no proxy, no API key required
- `get_hot_topics(limit)`, `get_node_topics(node_name, limit)`, `get_topic(id)`, `get_user(username)`
- 通过公开 JSON API 获取热门帖子、节点帖子、帖子详情+回复、用户信息
- 零配置，无需认证、无需代理、无需 API Key

### 📈 Improvements / 改进

- Channel count: 14 → 15
- 渠道数量：14 → 15

---

## [1.1.0] - 2025-02-25

### 🆕 New Channels / 新增渠道

#### ~~📷 Instagram~~ (removed — upstream blocked)
- ~~Read public posts and profiles via [instaloader](https://github.com/instaloader/instaloader)~~
- **Removed:** Instagram's aggressive anti-scraping measures broke all available open-source tools (instaloader, etc.). See [instaloader#2585](https://github.com/instaloader/instaloader/issues/2585). Will re-add when upstream recovers.
- **已移除：** Instagram 反爬封杀导致所有开源工具（instaloader 等）失效。上游恢复后会重新加回。

#### 💼 LinkedIn
- Read person profiles, company pages, and job details via [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)
- Search people and jobs via MCP, with Exa fallback
- Fallback to Jina Reader when MCP is not configured
- 通过 linkedin-scraper-mcp 读取个人 Profile、公司页面、职位详情
- 通过 MCP 搜索人才和职位，Exa 兜底
- 未配置 MCP 时自动 fallback 到 Jina Reader

#### 🏢 Boss直聘
- QR code login via [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp)
- Job search and recruiter greeting via MCP
- Fallback to Jina Reader for reading job pages
- 通过 mcp-bosszp 扫码登录
- MCP 搜索职位、向 HR 打招呼
- Jina Reader 兜底读取职位页面

### 📈 Improvements / 改进

- Channel count: 9 → 12
- `agent-reach doctor` now detects all 12 channels
- CLI: added `search-linkedin`, `search-bosszhipin` subcommands
- Updated install guide with setup instructions for new channels
- 渠道数量：9 → 11
- `agent-reach doctor` 现在检测全部 11 个渠道
- CLI：新增 `search-linkedin`、`search-bosszhipin` 子命令
- 安装指南新增渠道配置说明

---

## [1.0.0] - 2025-02-24

### 🎉 Initial Release / 首次发布

- 9 channels: Web, Twitter/X, YouTube, Bilibili, GitHub, Reddit, XiaoHongShu, RSS, Exa Search
- CLI with `read`, `search`, `doctor`, `install` commands
- Unified channel interface — each platform is a single pluggable Python file
- Auto-detection of local vs server environments
- Built-in diagnostics via `agent-reach doctor`
- Skill registration for Claude Code / OpenClaw / Cursor
- 9 个渠道：网页、Twitter/X、YouTube、B站、GitHub、Reddit、小红书、RSS、Exa 搜索
- CLI 支持 `read`、`search`、`doctor`、`install` 命令
- 统一渠道接口 — 每个平台一个独立可插拔的 Python 文件
- 自动检测本地/服务器环境
- 内置诊断 `agent-reach doctor`
- Skill 注册支持 Claude Code / OpenClaw / Cursor
