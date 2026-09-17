# Tavily Search 配置指南

Tavily 是 Agent Reach 的首选网页搜索后端；Exa MCP 继续作为无 Key 的备选。
Tavily 的 API key 只保存在 `~/.agent-reach/config.yaml`，不会写入仓库或输出到日志。

## 配置

```bash
agent-reach configure tavily-key --stdin
agent-reach doctor --json
```

当 `exa_search.active_backend` 为 `Tavily via REST` 时，Tavily 已通过 `/usage`
验证。Doctor 不执行搜索，因此不会消耗搜索 credit。

直接调用 Tavily API 时，需要在当前进程设置 `TAVILY_API_KEY`：

```bash
curl -sS https://api.tavily.com/search \
  -H "Authorization: Bearer $TAVILY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"query","search_depth":"advanced","max_results":5,"include_answer":false}'
```

研究任务建议先 Search，再对候选 URL 调用 Extract；只有需要完整综合报告时才调用
Research。Tavily 暂时不可用或没有 key 时使用 Exa：

```bash
mcporter call exa.web_search_exa query="query" numResults=5
```

可用 `EXA_SEARCH_BACKEND=exa` 临时优先 Exa；默认顺序仍是 Tavily → Exa。
