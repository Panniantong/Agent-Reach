# 搜索工具

网页搜索默认走 **Tavily**，Exa 作为无 Key 的备选。先运行
`agent-reach doctor --json`；当 `exa_search.active_backend` 为
`Tavily via REST` 时用 Tavily，否则回退到 Exa。

## Tavily（首选）

Tavily 适合需要来源、时效和正文抽取的研究任务。先 Search 找候选来源，
再 Extract 关键 URL；`include_answer` 只当作快速线索，不能替代来源核验。

```bash
# 保存给 doctor 使用（隐藏输入，不要把 key 放进命令参数）
agent-reach configure tavily-key --stdin

# 直接调用 API 时，在当前子进程提供 key（不要把真实 key 写入命令历史）
read -r -s TAVILY_API_KEY; export TAVILY_API_KEY
curl -sS https://api.tavily.com/search \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"query","search_depth":"advanced","max_results":5,"include_answer":false}'
```

常用参数：

| 参数 | 用途 |
|-----|-----|
| `search_depth=advanced` | 来源发现、比较和高置信答案；成本高于 `basic` |
| `topic=news` | 新闻、时事和近期事件 |
| `time_range=week` | 只看最近时间范围 |
| `include_domains` / `exclude_domains` | 限制来源范围 |
| `include_raw_content=markdown` | 需要搜索结果正文时使用；否则后续调用 Extract |

需要完整正文时调用 `/extract`；需要长篇、有引用的综合报告时调用 `/research`。
不要为每个普通查询直接调用 Research。

## Exa（备选）

Tavily 没有 API key、配额耗尽或 API 暂时不可用时，使用 Exa MCP：

```bash
mcporter call exa.web_search_exa query="query" numResults=5
```

可用 `EXA_SEARCH_BACKEND=exa` 临时把 Exa 提到第一顺位；未知覆盖值不会禁用其他后端。

## 选择原则

| 工具 | 适用场景 |
|-----|---------|
| Tavily | 研究、时效信息、可信域名过滤、Search → Extract → Research |
| Exa | 无 Key 的语义搜索、快速发现候选网页 |
| GitHub 搜索 | 仓库、代码、Issue、PR；见 `dev.md` |
