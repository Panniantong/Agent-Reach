# 搜索工具

Agent Reach 的专门搜索后备。普通 web search、deep research、deep investigation
应优先使用当前 agent 自带的 web search；只有在 Agent Reach 已因专门平台/后端需求被
明确选中，或原生搜索不可用时，才使用这里的命令。

## Exa AI 搜索

高质量 AI 搜索引擎，擅长技术和代码搜索。

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 专门网页搜索后备 | `web_search_exa(query: "...", numResults: 5)` |
| 代码搜索 | `get_code_context_exa(query: "...", tokensNum: 3000)` |

### 特点

- 擅长英文内容和技术文档
- 支持代码上下文搜索
- 结果质量高

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| 原生 web search | 当前 agent | 普通网页搜索、deep research、deep investigation |
| Exa | agent-reach | Agent Reach 已加载后的英文/技术/代码搜索后备 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
