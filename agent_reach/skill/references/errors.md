# 错误处理与重试预算

Agent 遇到失败时**先查本表再动作**，禁止盲重试、禁止换无关参数反复试。

## 通用铁律

| 规则 | 说明 |
|------|------|
| **Retry budget** | 同一错误信号最多诊断 **1 次** + 按表修复 **1 次** + 业务重试 **1 次**；仍失败则汇报用户 |
| **先 doctor** | 多后端平台失败时先 `python3 -m agent_reach.cli doctor --json`，确认 `active_backend` 未变 |
| **禁止 TTY 交互** | Cloud Agent / cron 环境禁止 QR 扫码、交互式 login、`config init` 等需终端的命令 |
| **Cookie 路线** | Twitter/XHS 等 Cookie 平台只用 **Cookie-Editor 导出**，见 install.md |

## Exa / mcporter

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `tool not found` / `exa.` 前缀错误 | mcporter 未配置 Exa MCP | 检查 `MCPORTER_CONFIG`（默认 `config/mcporter.json`），确认 `exa` server 存在 |
| `401` / `invalid api key` | Exa Key 无效或未配 | 在 `~/.agent-reach/config.env` 设 `EXA_API_KEY`，或 MCP URL 加 `?exaApiKey=` |
| `429` / rate limit | 频率超限 | 降 `numResults`、换 `type: fast`、间隔 30s 后重试 **1 次** |
| 空结果 / 无关结果 | query 太关键词化 | 改语义化描述（见 search.md Query Craft），或换 `web_search_advanced_exa` + category |
| timeout | 网络或 deep 模式慢 | 换 `type: fast`；deep research 用 `deep_researcher_check` 轮询，勿重复 start |

## 小红书

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `AUTH_REQUIRED`（OpenCLI） | Chrome 未登录小红书 | 让用户在 Chrome 登录；**禁止** QR 扫码流程 |
| `check_login_status` false（MCP） | MCP 未登录 | **Cloud/cron：禁止** `get_login_qrcode`；改 Cookie-Editor 导出或 OpenCLI |
| search 挂死 / 无响应 | 未登录仍调 search | 先 `check_login_status`，未登录则停 |
| `406` / 签名错误 | xhs-cli 写操作或上游停更 | 只读；换 OpenCLI 或 MCP 后端 |
| 验证码 / 频繁限制 | 请求过快 | 间隔 2–3s；减批量；**不要**连点重试 |

## Twitter

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `401` / auth | Cookie 过期 | 重新 Cookie-Editor 导出到 config |
| `search` 空或报错 | twitter-cli 限流或 Cookie 问题 | 试 `twitter feed` 验证登录；失败则更新 Cookie |
| GraphQL / API 变更 | 上游 breaking | 查 doctor 是否有新 backend；汇报而非瞎改命令 |

## Reddit

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `401` / not logged in | 无登录态 | OpenCLI 浏览器登录或 rdt-cli 配置；**无零配置路径** |
| `403` / banned subreddit | 权限或封禁 | 换 subreddit 或停止，勿重试 |
| OpenCLI 不可用 | 非桌面环境 | 切 `rdt-cli`（doctor 指引） |

## B站

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `bili search` 失败 | bili-cli 未装或网络 | `pip install bili-cli` 或 doctor 检查 |
| 需登录内容 | 大会员/登录墙 | 用 OpenCLI 或告知用户无法匿名读取 |

## Jina Reader / 网页

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `curl r.jina.ai` 空 | URL 无效或反爬 | 换 Exa `crawling_exa` 或直接 curl 原站 |
| `403` / blocked | 站点拒绝 | 换搜索找镜像；勿无限重试同一 URL |

## Feishu 推送（daily-run 联动）

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `FeishuError` / 未配置 | webhook 或 app 缺失 | 查 `~/.agent-reach/config.env` 与 config.yaml |
| `99991663` 等 app 错误 | token / chat_id 错 | 核对 `FEISHU_*` 与群 chat_id，**勿**重复 send 同内容刷屏 |

## daily-run schedule / lock

| 错误信号 | 含义 | 必须动作 |
|---------|------|---------|
| `lockfile` / 任务正在运行 | 上一 job 未结束或僵尸锁 | 确认进程已退出后 `rm` 对应 lock；补跑加 `--force` |
| manifest 去重 skip | 今日已成功跑过 | 补跑必须 `schedule run <job> --force` |
| `IndentationError` / import 错 | 代码/deploy 不一致 | 修复后重跑；**勿** `--force` 并行两个 intraday |

## 失败升级路径

```
失败 → 匹配上表信号 → 执行必须动作（≤1 次）
     → 仍失败 → 换 documented 备用后端（social.md 重试链）
     → 仍失败 → 向用户汇报：平台、信号、已尝试步骤、建议人工操作
```
