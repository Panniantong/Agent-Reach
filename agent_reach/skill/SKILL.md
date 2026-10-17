---
name: agent-reach
description: >
  Use when the user names a supported platform, shares its URL, or asks to configure or diagnose its channel:
  小红书/xiaohongshu, B站/bilibili, Twitter/X, Reddit, Facebook, Instagram,
  YouTube (subtitles, transcripts), V2EX, 雪球/股票行情, GitHub, LinkedIn/Boss直聘 jobs,
  or when your built-in web search / fetch is missing or fails.
  Read-only: never post, comment, like, or log in on the user's behalf.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

一个命令接所有平台：`agent-reach`。只读，输出永远是一段 JSON。

## 怎么用

按意图选择入口：指定平台 → 对应渠道动作；给链接 → `read`；安装、登录、导入或退出 → 先读 [会话配置](references/sessions.md)；故障、升级或卸载 → 先读 [维护说明](references/maintenance.md)。普通查询不加载这两份文档。

用户用一句话要求“去某平台找内容并总结”时，优先调用 Reach MCP 的 `reach_execute`；CLI 环境可用 `agent-reach ask "用户原话"`，由已配置的模型选动作并总结。渠道未准备好时，执行入口会返回 `required_action` 与 `operation_id`；用户完成登录后调用 `reach_resume` 或 `agent-reach resume OPERATION_ID`。不要自行拼安装、导入、重试的命令链。

```bash
agent-reach channels                      # 每个渠道有哪些动作、要什么参数（不确定就先跑这个）
agent-reach ask "去小红书找数据平台笔记并总结" # 已配置模型时的一句话入口
agent-reach ensure <渠道>                 # 安装、复用授权会话并实测
agent-reach <渠道> <动作> [参数]          # 例：agent-reach xiaohongshu search "咖啡" --limit 5
agent-reach read <链接>                   # 给链接，自动认出渠道
```

结果：

- `ok: true` → 内容在 `items` 里，每条有 `title / url / author / published_at / text`，原始数据在 `raw`。
- `ok: false` → 看 `error.code`，按 `error.hint` 做：

| error.code | 怎么办 |
|---|---|
| `NEED_SETUP` | 调用 `reach_ensure` 或 `agent-reach ensure <渠道>`，按结构化结果继续 |
| `NEED_LOGIN` | 用户本人完成登录；保留 `operation_id`，随后调用 `reach_resume` |
| `UPSTREAM_BROKEN` | 这个渠道暂时不可用，告诉用户，不要反复重试 |
| `TIMEOUT` / `RATE_LIMITED` | 稍后再试 |
| `NOT_FOUND` / `BAD_INPUT` | 检查链接或参数，必要时跑 `agent-reach channels` |

## 规则

1. 用户指定平台或平台链接时，优先对应渠道；通用网页查询先用已有网页工具，`web` 渠道只当保底。
2. 开始前说一句"用 agent-reach 的 X 渠道"。
3. 多平台调研按会话分组；共用浏览器的命令串行，独立会话可以并行。
4. 只做读取。发帖、评论、点赞一律不做。
5. 禁止隐式提取登录态。用户明确授权后，只导入指定站点的登录态；不得输出 Cookie、Token 或凭据。已有授权无需反复询问。

## 渠道

{{CHANNEL_TABLE}}

`default` 装好就能用；其余要用户先 `agent-reach add <渠道>`。默认渠道也可以去掉，去掉后更新不会再加回来。

## 会话复用：先检查，再决定是否需要登录

Cloak 查询和导入验收默认 `headless=True`。独立登录使用 `agent-reach cloak login CHANNEL`：由用户在可视窗口登录，完成后关闭窗口保存会话，再验收查询。此路径不需要 OpenCLI；OpenCLI 使用自己的 Chrome 会话，Cookie 导入仅为可选迁移方式。

登录时只应弹出一个 Cloak 窗口；普通 Cloak 查询在后台运行并自动关闭窗口。`cloak login` 最多等待 15 分钟，用户未完成并关窗时返回超时，不能自行反复重开。旧的 `browser setup` 会另开标有 OpenCLI Browser 的专用 Chrome，只有用户明确选择该路径时才执行；它闲置约 10 分钟后关闭。复用用户已有 Chrome 时，不要关闭原窗口。

安装和 `add` 不打开浏览器。`ensure <渠道>` 优先复用已有会话并执行正式验收；显式 `--reuse-profile ID` 授权从该 Chrome 配置导入指定站点的 Cookie，该授权在本机保存，可用 `--forget-source` 撤销。`login <渠道>` 默认只查看现有连接。连接正常或保存过状态不等于当前已登录。

后端按动作选择：小红书 search/read、Twitter/Reddit search、Facebook search、Instagram search/profile/posts 使用 CloakBrowser → OpenCLI；BOSS search 使用 CloakBrowser → OpenCLI → boss-agent-cli，BOSS read 仅支持 CloakBrowser；LinkedIn jobs 使用 CloakBrowser → linkedin-mcp。其他动作以 `agent-reach channels` 中的后端声明为准。具体会话选择见 [会话配置](references/sessions.md)。

小红书 read 仅返回文字描述，不声称理解图片/视频。BOSS 搜索若 salary_encoded=true，不能猜数字；read 职位链接获取详情中的可读薪资。

遇到 PLATFORM_BLOCKED、RATE_LIMITED、NEED_LOGIN、BUSY 就停止本次降级，不换账号或后端反复请求。同一 profile 的 Reach 命令互斥；多渠道共用同一 profile 时串行。

依赖修复和发布升级见 [维护说明](references/maintenance.md)；普通查询不修改依赖。

## 用户要管理 Agent Reach 时

| 用户说 | 你运行 |
|---|---|
| 看看状态 / 哪些能用 | `agent-reach doctor --text`（要实测再跑 `agent-reach check <渠道> --search --text`） |
| 加上某个平台（如"加上小红书"） | `reach_ensure` 或 `agent-reach ensure <渠道>`；需要本人操作时按 `required_action` 提示，再 `resume` |
| 登录过期了 | 先读会话配置；`agent-reach login <渠道>` 默认仅检查，实际登录由用户本人完成 |
| 去掉某个平台 / 退出登录 | `agent-reach remove <渠道>`；Cloak 主后端用 `agent-reach logout <渠道>` 删除 Reach 管理的会话 |
| 升级 / 更新 | 先读 [维护说明](references/maintenance.md)，确认当前安装来源和版本，再执行更新。 |
| 卸载 | 先 `agent-reach uninstall --dry-run` 给用户看，确认后 `agent-reach uninstall` |
| 让另一个 AI 也能用 | `agent-reach skill link <那个 AI 的 skill 目录>`；`agent-reach skill` 查看现在放在哪 |

首次安装：`agent-reach setup`。

## 有新版本时

任何结果里出现 `meta.update`，就说明有新版本。每次对话只提一次，用用户的语言、大白话：

1. 告诉用户 Agent Reach 有新版本（`meta.update.latest`）。
2. 从 `meta.update.notes` 里挑 1 到 3 个简短要点，说清楚这次改了什么。
3. 问用户要不要更新。

用户同意更新后，先读 [维护说明](references/maintenance.md)，确认安装来源；从相同来源更新，避免将本地构建覆盖为其他版本。更新后说明实际改动和仍需用户完成的操作。

Facebook search 已接入 CloakBrowser → OpenCLI；profile 仍使用 OpenCLI。可用 `cloak login facebook` 独立登录，或显式 `cloak import facebook --opencli-profile ID` 迁移站点 Cookie。
