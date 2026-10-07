# 搜索工具

Exa AI 搜索引擎。

## Exa AI 搜索

高质量 AI 搜索引擎，适合查找技术文档、官方示例和相关网页。

```bash
mcporter call exa.web_search_exa query="query" objective="..." numResults=5
mcporter call exa.web_search_exa query="library API code example" objective="..." numResults=5
```

`objective` 为必填参数：说明哪些结果优先、哪些排除、要提取哪些事实，直接影响结果质量。

### 读取全文

搜索结果摘要不够时，用 `web_fetch_exa` 读取一个或多个 URL 的全文：

```bash
mcporter call exa.web_fetch_exa urls="https://example.com" maxCharacters=8000
```

### 多步调研

`agent_run` 做多步调研或列表整理，返回 `agent_run_...` ID；未完成时用 `runId` 续查：

```bash
mcporter call exa.agent_run query="..." effort=minimal --output json
mcporter call exa.agent_run runId="agent_run_..." --output json
```

（`effort` 档位 `minimal` 到 `ultra`，默认 `low`；以上在配置 API Key 时实测通过，免 Key 是否可用未经验证。）

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `web_search_exa(query: "...", objective: "...", numResults: 5)` |
| 技术/代码资料 | `web_search_exa(query: "框架名 API 示例", objective: "...", numResults: 5)` |
| 读取全文 | `web_fetch_exa(urls: "...", maxCharacters: 8000)` |
| 多步调研 | `agent_run(query: "...", effort: minimal)`，用 `runId` 续查 |

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
