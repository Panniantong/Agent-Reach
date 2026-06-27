# 搜索工具

Exa AI 搜索引擎。

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

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | agent-reach | 英文/技术/代码搜索 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
| OKX News | agent-reach | 加密货币新闻搜索、币种情绪、趋势排行 |

## OKX 加密新闻 / 情绪追踪

先跑 `agent-reach doctor --json` 看 okx 的状态。OKX 使用官方
`@okx_ai/okx-trade-cli`，需要用户按 OKX CLI 提示登录或配置凭据。

```bash
# 安装/配置
agent-reach install --channels okx
okx config init

# 可选：安装 OKX 官方 sentiment skill
npx @okx_ai/okx-trade-cli@latest skill add okx-sentiment-tracker
```

常用命令：

```bash
# 新闻搜索（支持关键词、币种、情绪、来源过滤）
okx news search --keyword BTC --coins BTC --sentiment bullish --lang zh-CN --limit 10 --json

# 某些币种的当前情绪
okx news coin-sentiment --coins BTC,ETH --period 24h --json

# 单个币种的情绪趋势
okx news coin-trend BTC --period 24h --points 24 --json

# 情绪/热度排行
okx news sentiment-rank --period 24h --limit 20 --json

# 只按情绪浏览新闻
okx news by-sentiment --sentiment bearish --coins BTC --sort-by latest --json
```

> 如果 `okx news ...` 报 "Not logged in" 或 "No credentials found"，让用户先运行
> `okx config init`，或按 OKX CLI 的登录提示完成认证。
