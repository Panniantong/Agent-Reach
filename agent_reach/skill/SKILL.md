---
name: agent-reach
description: >
  MUST USE when user wants to 调研/research/搜索/search/查/找/look up anything
  on the internet — e.g. 全网调研 X / 帮我调研一下 X / 查一下 X / 搜搜 X /
  看看大家怎么评价 X / X 上有什么讨论 / research this topic。

  Also MUST USE when user mentions any platform or shares any URL/链接:
  小红书/xiaohongshu/xhs, Twitter/推特/X, B站/bilibili, Reddit, Facebook,
  Instagram, V2EX, LinkedIn/领英/Boss直聘/招聘/求职/jobs, YouTube, GitHub code search, 小宇宙播客,
  雪球/股票行情, RSS feeds, or any web URL.

  16 platforms, multi-backend routing (OpenCLI / per-platform CLIs / APIs).
  Zero config for 6 channels. Run `agent-reach doctor --json` to see which
  backend is available for each platform; match it to the requested capability.

  NOT for: 写报告/数据分析/翻译等内容加工（本 skill 只负责从互联网获取内容）；
  发帖/评论/点赞等写操作；已有专门 skill 的平台（先用专门 skill）。

  【路由方式】SKILL.md 包含路由表和常用命令，复杂场景需按需阅读对应分类的 references/*.md。
  分类：search / social (小红书/推特/B站/V2EX/Reddit/Facebook/Instagram) / career(LinkedIn/Boss直聘) / dev(github) / web(网页/文章/RSS) / video(YouTube/B站/播客) / finance(雪球/股票)。
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
---

# Agent Reach — 互联网能力路由器

16 平台、多后端。**本 skill 存在时必须用它访问这些平台，不要自己发明方案。**

## 常驻规则（全程适用）

1. **动手前先体检**：多后端/登录态平台（小红书/Reddit/B站/Twitter/Facebook/Instagram/Boss直聘）先跑
   `agent-reach doctor --json`。先确定需要搜索、正文、评论、字幕还是音频，再按对应
   reference 选择支持该能力的命令。`active_backend` 是平台级体检结果，不保证覆盖
   全部能力或目标内容；如 B站搜索 API 可用不能用于字幕。它也是某一时刻的快照，
   通道或登录态可能变化。它支持所需能力时优先使用，否则从 reference 中选择同能力候选。
   `active_backend: null` 时查看体检说明：可能未安装，也可能 Doctor 为避免触发
   浏览器 Cookie 读取或远端写入而未实时验证。只有用户任务明确需要该平台时，
   才按 reference 的只读命令或「体检与恢复」runbook 重新确认（如 career.md 的
   Boss直聘 CDP 排查）。
2. **声明你在用什么**：开始干活前说一句「使用 agent-reach 的 X 平台 / Y 后端」。
3. **失败按 references 里的同能力重试链处理**，不要瞎猜命令。备选路径要支持
   原任务的操作和内容范围；标题/搜索摘要不能替代正文或字幕，用户搜索不能替代
   帖子搜索。若只能拿到部分内容，说明缺失项，不把它当成原任务完成。
4. **全网调研类任务**：组合多平台（Exa 搜索 + Twitter/Reddit 看讨论 + 小红书/B站看中文场景），并行收集再汇总。
5. **替用户盯版本**：完成一次较大的调研/多平台任务后，顺手跑
   `agent-reach check-update`（很快，一个 API 调用）。有新版就在收尾汇报里附一句：
   「Agent Reach 有新版 vX.Y.Z，复制这句话给我即可更新：帮我更新 Agent Reach：
   https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md」。
   不要中断当前任务去更新，也不要重复提醒同一个版本。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 网页搜索/代码搜索 | search | [references/search.md](references/search.md) |
| 小红书/推特/B站/V2EX/Reddit/Facebook/Instagram | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn/Boss直聘 | career | [references/career.md](references/career.md) |
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

## 需登录态的平台（结合 doctor 和所需能力选命令）

Twitter 注意：`agent-reach configure twitter-cookies` 保存的 Cookie 只供
`doctor` 检查配置是否齐全；`doctor` 不执行 `twitter status`，也不会设置当前
Shell。直接运行 `twitter` 前，必须在子进程环境中显式提供
`TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`，不得在日志或命令回显中暴露值。

小红书注意：Agent Reach 不替用户登录，也不读取浏览器 Cookie。OpenCLI 只用
用户已有且明确控制的 Chrome 会话；没有现成会话时不要自动登录，改用
Cookie-Editor 手工导出后配置 xiaohongshu-mcp / 存量工具。

Boss直聘配置触发：当用户说“帮我配 Boss直聘”时，先读取 `references/career.md`
的 Boss 章节，然后在获得安装授权后运行
`agent-reach install --env=local --system --channels=boss`。Agent 负责按系统启动
只绑定 `127.0.0.1:9222` 的专用 Chrome；**拉起后第一步是暂停并让用户肉眼确认**
窗口内是已登录状态（右上角有头像），未登录则让用户登录/扫码，用户确认后再运行
`boss --cdp-url http://localhost:9222 login --cdp` 和 `agent-reach doctor` 验收。
不要让用户自己研究端口参数。
专用 Chrome profile 必须长期复用，不要每次创建，也不要默认改用日常主 Chrome。

判断 CDP 浏览器登录态**不要信 `boss status`**（它只校验本地 session.enc，与
浏览器登录态互不代表），以 `agent-reach doctor` 的浏览器 cookie 探测（wt2）
为准，并配合用户肉眼确认。绝不用当前页 URL 判断登录态：
`security-check` / `zhipin-security` / `_security_check` 安全校验页是 Boss 反爬挑战，
与登录无关——已登录也会出现（带 CDP 调试端口的 Chrome 几乎必现）。看到它不要
当成“未登录”，先跑 `agent-reach doctor` 看浏览器 cookie，再决定是否需要用户登录。
搜索报 `AUTH_EXPIRED` 即浏览器未登录的 ground truth：直接走登录流程 + `login --cdp`，
不要往安全校验方向解释。

执行搜索时必须使用
`boss --browser-source existing-browser --cdp-url http://localhost:9222 search ...`；
遇到 `ENVIRONMENT_RISK` 立即停止，不刷新、不重新登录、不自动重试。

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

> 本机 Python 环境默认是 conda `dl`；若 `agent-reach` 不在 PATH，用
> `conda run -n dl agent-reach ...` 前缀。

```bash
# 检查可用 channel 与每个平台当前激活的后端
conda run -n dl agent-reach doctor --json
```

## OpenCLI 适配器发现

路由表没有覆盖用户需要的平台或命令时，先用 `opencli list` 查已有适配器，再用
`opencli <平台> --help` 查看公开命令。发现适配器只证明命令存在，不证明登录态或
目标内容可用；仅在用户任务明确需要该平台时执行只读命令。阅读任务以实际非空
目标内容验收；搜索的有效零条结果可如实报告，错误或空响应不能当成零条结果。

## 工作区规则

**不要在 agent workspace 创建文件。** 使用 `/tmp/` 存放临时输出，`~/.agent-reach/` 存放持久数据。

## 详细文档

根据用户需求，阅读对应的详细文档：

- [搜索工具](references/search.md) — Exa AI 搜索
- [社交媒体](references/social.md) — 小红书, Twitter, B站, V2EX, Reddit, Facebook, Instagram（多后端/登录态命令组）
- [职场招聘](references/career.md) — LinkedIn, Boss直聘
- [开发工具](references/dev.md) — GitHub CLI
- [网页阅读](references/web.md) — Jina Reader, RSS
- [视频播客](references/video.md) — YouTube, B站, 小宇宙
- [金融行情](references/finance.md) — 雪球股票行情、搜索、热门内容

## 配置渠道

如果某个 channel 需要配置，获取安装指南：
https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md

用户只需提供 cookies，其他配置由 agent 完成。
