# 搜索工具

Agent Reach 提供多个搜索后端，按 `agent-reach doctor --json` 的 `active_backend` 字段选择命令。

## DuckDuckGo 搜索（免费，零配置）

装好即用，无需 API Key，无需登录。中文和英文搜索都支持。

```bash
# CLI 方式（推荐）
ddgs text "query" -n 5

# Python 方式（无 CLI 时）
python -c "from duckduckgo_search import DDGS; print(list(DDGS().text('query', max_results=5)))"
```

安装：
```bash
pip install duckduckgo-search   # 或 pipx install duckduckgo-search
```

### 特点

- 完全免费，无需注册或 API Key
- 中英文搜索都支持
- 结果来自 DuckDuckGo 搜索引擎
- 适合作为 Exa 不可用时的零配置替代
- 可用作查登录墙/地理墙后内容的备选路径

## Exa AI 搜索（高质量，需 mcporter）

高质量 AI 语义搜索引擎，擅长技术和代码搜索。需要先装 mcporter。

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

## 后端切换

如果想强制使用某个后端，设置环境变量或 config：

```bash
# 强制用 DuckDuckGo
export WEB_SEARCH_BACKEND="DuckDuckGo"

# 强制用 Exa
export WEB_SEARCH_BACKEND="Exa via mcporter"
```

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 | 配置难度 |
|-----|------|---------|---------|
| DuckDuckGo | agent-reach | 通用搜索（中英文），零配置 | ✅ 零配置 |
| Exa | agent-reach | 英文/技术/代码搜索 | 需 mcporter |
| 智谱搜索 | my-mcp-tools | 中文搜索 | 需 API Key |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 | 需 gh CLI |
