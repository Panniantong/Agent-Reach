# 搜索工具

两个全网搜索后端：Exa（免费、零配置）和 Diffbot（需免费 Token，结果带相关性评分/时效）。

## Exa AI 搜索

高质量 AI 搜索引擎，擅长技术和代码搜索。

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `web_search_exa(query: "...", numResults: 5)` |
| 代码搜索 | `get_code_context_exa(query: "...", tokensNum: 3000)` |

### 特点

- 擅长英文内容和技术文档
- 支持代码上下文搜索
- 结果质量高

## Diffbot 全网搜索

基于 Diffbot Web Index 的全网搜索，每条结果带 **相关性评分** 和 **发布时间**，适合需要排序/时效判断或要控制 token 预算的场景。通过 diffbot-python 的 `db` CLI 调用，**需免费 Token**。

```bash
db web-search "query" -n 5 -f text      # -f text：纯文本，适合 agent 解析
db web-search "query" -f json           # 结构化结果（score / title / pageUrl / date / content）
db web-search "query" -n 8 -m 4000      # -m 限制总 token 数（agentic 场景控预算）
```

### 参数

| 参数 | 含义 |
|-----|------|
| `-n / --num-results` | 返回结果数 |
| `-m / --max-tokens` | 限制响应总 token 数（高亮片段按比例缩减） |
| `-f / --format` | `list`（默认，富文本）/ `json` / `text`（纯文本，agent 友好） |

### 配置

```bash
# 免费 Token：https://app.diffbot.com/get-started/
agent-reach configure diffbot-token <token>     # 写入 ~/.diffbot/credentials，db 自动读取
agent-reach doctor --json                      # 确认 diffbot_search 为 ok
```

未配置时 `db` 会报 “Invalid or unauthorized API token.”，按上面配置 Token 即可。

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | agent-reach | 英文/技术/代码搜索；免费零配置 |
| Diffbot | agent-reach | 全网搜索，结果带相关性评分/时效；需免费 Token |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
