# 搜索工具

Exa AI 搜索引擎。Agent Reach 提供两条路：已配置个人 API Key 时直连 REST，
否则保留免 Key 的 mcporter/MCP 路径。

## Exa AI 搜索

高质量 AI 搜索引擎，适合查找技术文档、官方示例和相关网页。

```bash
# Doctor 提示“Exa REST API Key 已配置”时优先使用
agent-reach-exa search "query" --num-results 5
agent-reach-exa search "library API code example" --num-results 5

# 未配置个人 Key 时使用现有 MCP
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

REST 只替换传输路径，默认值与 `web_search_exa` 保持一致：搜索类型为
`auto`；省略 `--num-results` 时返回 10 条；搜索始终请求 Highlights；
`category:company`、`category:publication`、`category:news`、
`category:personal site`、`category:people` 的解析方式不变。

Highlights 不够时，两条路径都可以继续抓正文：

```bash
agent-reach-exa contents "https://example.com/page"
mcporter call exa.web_fetch_exa urls='["https://example.com/page"]'
```

省略 `--max-characters` 时，REST 正文抓取仍使用 MCP 的 3000 字符默认值。
API Key 通过 `agent-reach configure exa-key` 的隐藏输入或 `--stdin` 保存；
不要把 Key 写在命令参数、URL、日志或普通项目配置里。Doctor 不会为了验证
Key 发起计费搜索，所以 `active_backend` 可能仍为 `null`；首次真实只读调用
才会验证网络、额度和限流。

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `agent-reach-exa search "..." --num-results 5` 或 `web_search_exa` |
| 技术/代码资料 | `agent-reach-exa search "框架名 API 示例" --num-results 5` 或 `web_search_exa` |

> Exa MCP 的 `get_code_context_exa` 已弃用且默认不注册。代码问题也使用
> `web_search_exa`；需要精确搜索仓库内容时，改用 `dev.md` 中的 GitHub 搜索。

### 特点

- 擅长英文内容和技术文档
- 可通过查询词定位官方文档和代码示例
- 结果质量高

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | agent-reach | 英文/技术/代码搜索 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
