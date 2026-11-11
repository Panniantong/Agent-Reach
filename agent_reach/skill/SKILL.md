---
name: agent-reach
description: >
  只读读取各平台内容：搜索、读帖、看评论、取字幕、查行情和职位。
  Use when 用户提到或贴出链接：小红书/xiaohongshu、B站/bilibili、Twitter/X、Reddit、
  YouTube（字幕、转录）、GitHub、V2EX、雪球/股票行情、LinkedIn/Boss直聘 职位、
  Instagram、Facebook、小宇宙播客；或说"帮我搜/看看/读一下这个链接"而自带网页搜索/读取不可用、失败或拿不到正文；
  或要安装、加上/去掉某个平台、登录/退出、看状态、更新、卸载 Agent Reach。
  不做：发帖、评论、点赞、私信等任何写操作；不替用户登录、不索要密码。
  公开内容优先用 Agent 自带工具，Reach 补缺口。
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

一个命令读所有平台：`agent-reach`。只读，默认输出一行 JSON。

动手前先说一句"用 agent-reach skill（X 渠道）"。本 skill 被调用后全程有效，以下规则一直适用。

## 每次使用前检查登录

- 每次使用 Reach 读取平台内容前，检查目标渠道的当前认证状态；不能用 Cookie 文件存在、`channels` 的缓存信息或上一次成功代替实时验证。无需认证的公开渠道明确按「不需要登录」处理，不为它们强加登录。
- 查看视频默认先完成登录验证，再读视频内容、字幕和评论。只有用户明确说「不登录简览」「仅看公开信息」时才跳过登录；结果必须标明只是公开简介，不能声称看过视频。
- B 站运行 `agent-reach bilibili auth`；读取、搜索和字幕动作也会实时检查。已有效的托管会话自动复用；未登录时自动返回 `NEED_LOGIN` 和 `error.details.login.qr_path`。立即把该本地图片展示在当前对话中，让用户用 B 站 App 扫码并确认。不要只给命令，也不要把二维码发送给其他人或其他服务。
- 用户扫码后运行 `agent-reach login bilibili --poll`；只有返回 `logged_in: true` 且 `verified: true` 才重试原任务。等待扫码/手机确认不算登录成功。二维码过期后重新运行登录命令获取新码，不在后台循环换码或轮询。
- 其他需要认证的渠道使用其支持的实时状态检查或官方页面确认；没有通用状态接口时明确说尚未验证，不伪造「已登录」。平台不支持二维码时使用原有登录入口，不声称已经生成二维码。
- B 站不登录简览：`agent-reach bilibili read <链接> --no-login`（搜索和热门也支持）；该模式不检查凭据、不生成二维码，仅返回公开元数据。
- 网络失败、限流或验证码不能推断为未登录；停止并保留原始错误。没有拿到字幕不等于视频没有字幕。

## 选路

- 公开内容先用你自带的搜索/读取工具（可加 `site:域名`）。正文、评论、字幕分别核对是否已拿到；公开信息足够且不涉及默认登录的视频阅读时，可直接回答；视频阅读遵循上面的登录检查规则。
- 自带工具不可用、结果缺了用户要的部分、或用户要的是渠道声明的站内动作时，再用 Reach。不确定有哪些动作和参数先跑 `agent-reach channels`。
- 渠道已经加上（默认渠道或 `add` 过）时，搜索/阅读直接走该站工具；还没加的渠道，搜索/阅读先试免登录公开网页，结果里 `backend: public-web` 标明来源。`--backend public-web` 只查公开网页；`--backend <后端>` 指定站内工具。
- 平台名或链接只用来认出来源，不自动触发安装；视频阅读按上述规则检查登录。
- 摘要、页面壳、评论计数、字幕轨道列表不等于正文、评论或字幕本身，要分别说明。用户跳过登录时，已拿到的公开结果照样交付。

```bash
agent-reach channels                      # 每个渠道的动作和参数
agent-reach <渠道> <动作> [参数]          # 例：agent-reach xiaohongshu search "咖啡" --limit 5
agent-reach read <链接>                   # 按链接自动选渠道
```

## 结果与错误

- `ok: true` → 内容在 `items`，每条有 `title / url / author / published_at / text`，原始数据在 `raw`。
- `ok: false` → 看 `error.code`，照 `error.hint` 做：

| error.code | 怎么办 |
|---|---|
| `NEED_SETUP` | 缺依赖或密钥。按提示 `agent-reach add <渠道>`；要密钥时请用户本人提供，再 `agent-reach configure <key>` |
| `NEED_LOGIN` | 停止读取；B 站自动展示返回的 `qr_path`，用户扫码后用 `--poll` 验证。其他渠道使用已有登录入口。保留已有结果，不代替用户确认、不索要密码 |
| `UPSTREAM_BROKEN` | 这个平台暂时有问题，`message` 是出错时的原话。用平台名告诉用户哪个平台暂时用不了、大概是什么原因，不说工具名；原话说明工具过时，才在用户同意后跑一次 `agent-reach update`；不循环重试 |
| `TIMEOUT` | 看失败阶段和渠道状态（`agent-reach doctor --text`）；不反复重试、不反复开窗 |
| `RATE_LIMITED` | 平台限流，Reach 已暂停该渠道；按 `retry_after_seconds` 等，不换后端 |
| `PLATFORM_BLOCKED` | 平台要求验证（验证码/风控）。停下，请用户在官方页面处理；不换账号、不换后端 |
| `BUSY` | 排队等了 2 分钟浏览器仍然满，或用户正开着登录窗口。过一会儿、或等用户说登好了再试；不关窗口、不切换配置 |
| `NOT_FOUND` | 内容不存在，核对链接或 ID |
| `BAD_INPUT` | 参数不对，跑 `agent-reach channels` 看用法 |

遇到 `PLATFORM_BLOCKED`、`RATE_LIMITED`、`BUSY` 停止本次尝试；`NEED_LOGIN` 停止内容读取并展示登录入口，验证成功后才能重试，不换账号、后端或浏览器反复请求。网络失败或某台机器的失败不能说成"平台必须登录"。

## 登录与专用浏览器

所有浏览器渠道共用一个专用浏览器（优先 CloakBrowser，装不上时用本机 Chrome），默认无头不弹窗，闲置 10 分钟自动关闭，下次调用自动重开。可以并行调用（包括子代理同时查）：同一平台最多同时 2 条，所有平台合计 4 条，多出来的自动排队；同一平台的两次搜索之间至少隔 10 秒。

优先复用并验证 Reach 已保存的会话。导入个人浏览器登录必须是用户明确授权的一次、指定站点的导入；不保留长期导出授权。B 站失效时自动准备官方二维码，由用户本人扫码确认；不自动读取个人浏览器 Cookie 数据库。刷新、选来源、退出等细节见 [会话与专用浏览器](references/sessions.md)：用户要登录、退出、换账号，或遇到 `NEED_LOGIN` 时读它。

## 平台注意

- 小红书 read 只返回文字描述，不要声称看懂了图片或视频。
- Boss 直聘搜索结果 `salary_encoded=true` 时绝不猜薪资数字；read 职位链接拿详情里的可读薪资。
- 各平台公开能做什么、Reach 补什么，见 [能力边界](references/capabilities.md)：用户问"能查什么/查得全吗"或要判断结果完整度时读它。

## 渠道

{{CHANNEL_TABLE}}

`default` 是默认安装的渠道，也可以去掉，去掉后更新不会加回来。`login` 列是认证入口；无需登录的渠道继续支持公开读取，视频阅读和用户明确选择的不登录简览按上面的规则执行。

## 安装完成时

`agent-reach setup` 后，把 `result.installation_report.markdown` 原样展示给用户，不增删、不重排、不自己补问候或表格；报告由程序生成。

## 用户要管理 Agent Reach 时

| 用户说 | 你运行 |
|---|---|
| 加上某个平台 | `agent-reach add <渠道>`，依赖自动装好；只告诉用户他必须做的事（登录或提供密钥） |
| 去掉某个平台 | `agent-reach remove <渠道>` |
| 登录 / 登录过期 | `agent-reach login <渠道>`，由用户本人在打开的窗口里登录 |
| 退出登录 | `agent-reach logout <渠道>` |
| 看看状态 / 哪些能用 | `agent-reach doctor --text`；要实测跑 `agent-reach check <渠道> --text` |
| 升级 / 更新 | `agent-reach update` |
| 卸载 | 先 `agent-reach uninstall --dry-run` 给用户看，确认后 `agent-reach uninstall` |
| 让另一个 AI 也能用 | `agent-reach skill link <那个 AI 的 skill 目录>`；`agent-reach skill` 查看现在放在哪 |
| 某个 AI 不要用户级的 skill（比如只按项目注册） | `agent-reach skill unlink <那个 AI 的 skill 目录>`；之后 setup 和 update 不再放回去 |

故障排查、浏览器维护和卸载细节见 [维护说明](references/maintenance.md)：更新失败、浏览器起不来或要卸载时读它。

## 有新版本时

结果里出现 `meta.update` 就说明有新版本。每次对话只提一次，用用户的语言、大白话：

1. 告诉用户有新版本（`meta.update.latest`）。
2. 从 `meta.update.notes` 挑 1 到 3 个要点说清改了什么。
3. 问要不要更新；用户同意后才跑 `agent-reach update`。

## 红线

- 只读。发帖、评论、点赞、私信一律不做。
- 不替用户登录，不索要或输出密码、Cookie 等凭据。
- 普通查询不改依赖、不自动更新。
