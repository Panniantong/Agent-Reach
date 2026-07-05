---
name: agent-reach
description: >
  Use only when the user explicitly asks to use Agent Reach, asks for
  multi-platform/social-platform collection, or mentions one of Agent Reach's
  specialized platforms/backends.

  Specialized platforms:
  小红书/xiaohongshu/xhs, Twitter/推特/X, B站/bilibili, Reddit, Facebook,
  Instagram, V2EX, LinkedIn/领英/招聘/求职/jobs, YouTube, GitHub code search, 小宇宙播客,
  雪球/股票行情, RSS feeds.

  15 platforms, multi-backend routing (OpenCLI / per-platform CLIs / APIs).
  Zero config for 6 channels. Run `agent-reach doctor --json` to see which
  backend serves each platform right now.

  NOT for: ordinary web search, web fetch/page reading, generic "deep research",
  "deep investigation", "look this up", or arbitrary URLs. Use the agent's native
  web search / web fetch tools for those unless a specialized platform above is
  explicitly required.

  NOT for: 写报告/数据分析/翻译等内容加工（本 skill 只负责从互联网获取内容）；
  发帖/评论/点赞等写操作；已有专门 skill 的平台（先用专门 skill）。

  【路由方式】SKILL.md 包含路由表和常用命令，复杂场景需按需阅读对应分类的 references/*.md。
  分类：search(代码/专门搜索后备) / social(小红书/推特/B站/V2EX/Reddit/Facebook/Instagram) /
  career(LinkedIn/jobs) / dev(GitHub code search) / web(RSS/受限网页后备) /
  video(YouTube/B站/播客字幕)。
triggers:
  - explicit: agent-reach/Agent Reach/use agent-reach/用 agent-reach
  - multi_platform: 全网讨论/多平台/跨平台/社交平台/看看大家怎么评价/大家怎么说
  - social:
    - 小红书: xiaohongshu/xhs/小红书/红书
    - Twitter: twitter/推特/x.com/推文
    - B站: bilibili/b站/哔哩哔哩
    - V2EX: v2ex
    - Reddit: reddit
    - Facebook: facebook/fb/facebook groups
    - Instagram: instagram/ig
  - career: 招聘/职位/求职/linkedin/领英/找工作
  - dev: github code search/github search/gh search/repo search/代码搜索
  - web: rss/feed/订阅源
  - video: youtube/视频/播客/字幕/小宇宙/转录/yt
  - finance: 雪球/股票/stock/xueqiu/行情/基金
metadata:
  openclaw:
    homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — 互联网能力路由器

15 平台、多后端。**仅当任务明确需要下列专门平台/后端时使用本 skill。普通网页搜索、网页读取、deep research/deep investigation、任意 URL 阅读优先使用当前 agent 自带的 web search / web fetch。**

## 常驻规则（全程适用）

1. **动手前先体检**：多后端/登录态平台（小红书/Reddit/B站/Twitter/Facebook/Instagram）先跑
   `agent-reach doctor --json`，按各平台 `active_backend` 字段选命令组。
2. **声明你在用什么**：开始干活前说一句「使用 agent-reach 的 X 平台 / Y 后端」。
3. **失败按 references 里的重试链处理**，不要瞎猜命令。
4. **多平台讨论类任务**：仅当用户明确需要社交/社区/平台讨论时，组合对应平台（Twitter/Reddit/小红书/B站/V2EX/Facebook/Instagram 等）并行收集再汇总。普通 deep research 不走本 skill。
5. **替用户盯版本**：完成一次较大的调研/多平台任务后，顺手跑
   `agent-reach check-update`（很快，一个 API 调用）。有新版就在收尾汇报里附一句：
   「Agent Reach 有新版 vX.Y.Z，复制这句话给我即可更新：帮我更新 Agent Reach：
   https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md」。
   不要中断当前任务去更新，也不要重复提醒同一个版本。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 代码/专门搜索 | search | [references/search.md](references/search.md) |
| 小红书/推特/B站/V2EX/Reddit/Facebook/Instagram | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub code search | dev | [references/dev.md](references/dev.md) |
| RSS/受限网页后备 | web | [references/web.md](references/web.md) |
| YouTube/B站/播客字幕 | video | [references/video.md](references/video.md) |

## 零配置快速命令

```bash
# Agent Reach 专门搜索后备；普通 web search 优先用当前 agent 自带工具
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'

# RSS/受限网页后备；普通 URL/web fetch 优先用当前 agent 自带工具
curl -s "https://r.jina.ai/URL"

# GitHub 搜索
gh search repos "query" --sort stars --limit 10

# YouTube 字幕（注意：B站不要用 yt-dlp，见 video.md）
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"

# V2EX 热门
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: agent-reach/1.0"

# B站搜索（bili-cli，无需登录）
bili search "query" --type video -n 5
```

## 需登录态的平台（按 doctor 的 active_backend 选命令）

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

## 配置渠道

如果某个 channel 需要配置，获取安装指南：
https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md

用户只需提供 cookies，其他配置由 agent 完成。
