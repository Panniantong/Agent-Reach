---
name: agent-reach
description: >
  仅在用户显式点名时使用：斜杠命令 /agent-reach，或「使用 agent-reach」
  这类直接指令。

  禁止自主激活：无论用户提到链接/URL、平台名称（小红书、推特/X、B站、
  Reddit、Facebook、Instagram、V2EX、LinkedIn、YouTube、GitHub、小宇宙、
  雪球、RSS 等）、搜索/调研/查找需求，还是在读取文件时看到相关内容，
  都不要选用本 skill。用户没有明确点名，就当本 skill 不存在，用其他方式
  完成任务。

  Use ONLY when the user explicitly invokes it: the /agent-reach slash
  command, or a direct request such as "use agent-reach". NEVER activate on
  your own — not for URLs, platform names, search/research intent, or while
  reading files. If the user did not name this skill, ignore that it exists.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — 互联网能力路由器

15 平台、多后端。**本 skill 存在时必须用它访问这些平台，不要自己发明方案。**

## 常驻规则（全程适用）

1. **动手前先体检**：多后端/登录态平台（小红书/Reddit/B站/Twitter/Facebook/Instagram）先跑
   `agent-reach doctor --json`。`active_backend` 有值时按它选命令组；`active_backend: null`
   表示 Doctor 为避免触发浏览器 Cookie 读取或远端写入而没有做实时验证，不代表后端不存在。
   只有用户任务明确需要该平台时，才按对应 reference 的只读命令手动验证。
2. **声明你在用什么**：开始干活前说一句「使用 agent-reach 的 X 平台 / Y 后端」。
3. **失败按 references 里的重试链处理**，不要瞎猜命令。
4. **全网调研类任务**：组合多平台（Exa 搜索 + Twitter/Reddit 看讨论 + 小红书/B站看中文场景），并行收集再汇总。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 网页搜索/代码搜索 | search | [references/search.md](references/search.md) |
| 小红书/推特/B站/V2EX/Reddit/Facebook/Instagram | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub/代码 | dev | [references/dev.md](references/dev.md) |
| 网页/文章/RSS | web | [references/web.md](references/web.md) |
| YouTube/B站/播客字幕 | video | [references/video.md](references/video.md) |
| 雪球/股票行情 | finance | [references/finance.md](references/finance.md) |

## 零配置快速命令

```bash
# Exa 网页搜索
mcporter call exa.web_search_exa query="query" numResults=5

# 通用网页阅读
curl -s "https://r.jina.ai/URL"

# GitHub 搜索
gh search repos "query" --sort stars --limit 10

# YouTube 字幕（注意：B站不要用 yt-dlp，失败重试链见 video.md）
yt-dlp --write-sub --write-auto-sub --skip-download -o "/tmp/%(id)s" "URL"

# V2EX 热门
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"

# B站搜索（bili-cli，无需登录）
bili search "query" --type video -n 5
```

## 需登录态的平台（按 doctor 的 active_backend 选命令）

Twitter 注意：`agent-reach configure twitter-cookies` 保存的 Cookie 只供
`doctor` 检查配置是否齐全；`doctor` 不执行 `twitter status`，也不会设置当前
Shell。直接运行 `twitter` 前，必须在子进程环境中显式提供
`TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`，不得在日志或命令回显中暴露值。

小红书注意：Agent Reach 不替用户登录，也不读取浏览器 Cookie。OpenCLI 只用
用户已有且明确控制的 Chrome 会话；没有现成会话时不要自动登录，改用
Cookie-Editor 手工导出后配置 xiaohongshu-mcp / 存量工具。

```bash
# Twitter 搜索（twitter-cli 首选；失败重试链见 social.md）
twitter search "query" -n 10

# Reddit（无零配置路径：OpenCLI 或 rdt-cli，必须登录态）
opencli reddit search "query" -f yaml   # 桌面
rdt search "query" --limit 10            # 存量/服务器

# 小红书（桌面首选 OpenCLI）
opencli xiaohongshu search "query" -f yaml

# Facebook / Instagram（桌面 OpenCLI，复用浏览器登录态）
opencli facebook search "query" -f yaml
opencli facebook groups -f yaml
opencli instagram search "query" -f yaml       # 搜用户
opencli instagram user USERNAME -f yaml        # 读指定用户最近帖子
```

## 环境检查

```bash
# 检查可用 channel 与每个平台当前激活的后端
agent-reach doctor --json
```

## OpenCLI 适配器发现

路由表没有覆盖用户需要的平台或命令时，先用 `opencli list` 查已有适配器，再用
`opencli <平台> --help` 查看公开命令。发现适配器只证明命令存在，不证明登录态或
目标内容可用；仅在用户任务明确需要该平台时执行只读命令，并以实际非空内容验收。

## 工作区规则

**不要在 agent workspace 创建文件。** 使用 `/tmp/` 存放临时输出，`~/.agent-reach/` 存放持久数据。

## 详细文档

根据用户需求，阅读对应的详细文档：

- [搜索工具](references/search.md) — Exa AI 搜索
- [社交媒体](references/social.md) — 小红书, Twitter, B站, V2EX, Reddit, Facebook, Instagram（多后端/登录态命令组）
- [职场招聘](references/career.md) — LinkedIn
- [开发工具](references/dev.md) — GitHub CLI
- [网页阅读](references/web.md) — Jina Reader, RSS
- [视频播客](references/video.md) — YouTube, B站, 小宇宙
- [金融行情](references/finance.md) — 雪球股票行情、搜索、热门内容

## 配置渠道

如果某个 channel 需要配置，获取安装指南：
https://raw.githubusercontent.com/Fatoom333/Agent-Reach/main/docs/install.md

用户只需提供 cookies，其他配置由 agent 完成。
