# 搜索工具

Exa AI 搜索引擎。

## Exa AI 搜索

高质量 AI 搜索引擎，适合查找技术文档、官方示例和相关网页。

```bash
mcporter call exa.web_search_exa query="query" objective="..." numResults=5
mcporter call exa.web_search_exa query="library API code example" objective="..." numResults=5
```

`objective` 是 `web_search_exa` 的必填参数，用来说明想优先看哪些结果、排除哪些内容、需要提取哪些事实，会影响排序和摘要质量。服务端目前仍兼容不带它的旧调用，但新写法都应带上。

```bash
# 搜索摘要不够时，读一个或多个 URL 的全文
mcporter call exa.web_fetch_exa urls="https://example.com" maxCharacters=8000

# 多轮调研或整理列表时用 agent_run，未完成时用 runId 续查
mcporter call exa.agent_run query="..." effort=minimal --output json
mcporter call exa.agent_run runId="agent_run_..." --output json
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 单次网页搜索 | `web_search_exa(query: "...", objective: "...", numResults: 5)` |
| 技术/代码资料 | `web_search_exa(query: "框架名 API 示例", objective: "...", numResults: 5)` |
| 读搜索结果全文 | `web_fetch_exa(urls: ["https://..."], maxCharacters: 8000)` |
| 多轮搜索或交叉核对 | `agent_run(query: "...", effort: "minimal")`，续查用 `agent_run(runId: "agent_run_...")` |

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
