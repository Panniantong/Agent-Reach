# 搜索工具

Exa 神经网络搜索 + mcporter 调用。语义搜索（按「页面含义」而非纯关键词）。

## MCP 配置

**Server URL：** `https://mcp.exa.ai/mcp`  
**带 Key（推荐）：** `https://mcp.exa.ai/mcp?exaApiKey=YOUR_KEY`  
**本地 mcporter：** 默认读 `MCPORTER_CONFIG`（Agent-Reach 仓库 `config/mcporter.json`）

```bash
# 零配置快速搜索（与 SKILL.md 一致）
mcporter call 'exa.web_search_exa(query: "blog posts about vector DB recommendations", numResults: 5)'

# 代码上下文
mcporter call 'exa.get_code_context_exa(query: "Python asyncio connection pooling", tokensNum: 3000)'
```

Key 来源：`~/.agent-reach/config.env` → `EXA_API_KEY`，或 [dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys)。

## 工具选型（我要做 X → 用哪个）

| 需求 | 工具 | mcporter 示例 |
|------|------|---------------|
| 快速网页语义搜索 | `web_search_exa` | `exa.web_search_exa(query: "...", numResults: 8)` |
| 英文/技术/代码 | `get_code_context_exa` | `exa.get_code_context_exa(query: "...", tokensNum: 3000)` |
| 公司情报、竞品 | `company_research_exa` | `exa.company_research_exa(query: "Stripe overview competitors")` |
| 找人 / LinkedIn 向 | `people_search_exa` | `exa.people_search_exa(query: "VP Eng fintech SF")` |
| 指定 URL 读全文 | `crawling_exa` | `exa.crawling_exa(url: "https://...")` |
| 论文 / 新闻 / 推文 | `web_search_advanced_exa` | 加 `category: "research paper"` / `"news"` / `"tweet"` |
| 深度调研报告（异步） | `deep_researcher_start` → `check` | start 拿 `researchId`，轮询 check 至 completed |
| 单次深度问答+引用 | `deep_search_exa` | 需 API Key |

> 未在 mcporter 启用的 optional tool 会报 `tool not found` — 见 MCP URL `tools=` 参数或 errors.md。

## web_search_exa 参数要点

| 参数 | 说明 |
|------|------|
| `query` | **语义化**描述想要的页面（见下方 Query Craft） |
| `numResults` | 默认 10；Agent 调研常用 5–8 |
| `type` | `auto`（默认）/ `fast`（低延迟）/ `deep`（多步推理，慢） |
| `livecrawl` | `fallback`（默认）/ `preferred`（强制新鲜） |

## Query Craft（Exa 专用）

Exa 匹配**含义**而非关键词堆砌：

- ✅ `"blog post about embeddings for product recommendations at scale"`
- ❌ `"embeddings product recommendations"`

- ✅ `"latest semiconductor export policy news March 2026"`
- ❌ `"半导体 政策"`（中文可试，但英文技术/国际源更稳）

**全网调研：** 并行 2–3 个 query 变体，去重后汇总；中文场景补小红书/B站（social.md）。

## Token 效率

| 模式 | 何时用 |
|------|--------|
| 默认 snippet | 快速扫标题摘要 |
| `get_code_context_exa` | 限 `tokensNum`，避免整页 |
| advanced + `highlights` | 多步 Agent pipeline，比 full text 省 token |
| advanced + `text` | 需要全文精读时 |

daily-run 收盘 Exa 调研有 **86400s TTL 缓存**（`exa_cache`）— 同 query 24h 内不重复搜。

## 与其他工具分工

| 工具 | 适用 | 不适用 |
|------|------|--------|
| **Exa** | 英文/技术/公司/论文/深度调研 | 纯中文社区讨论（用 social） |
| **Jina Reader** | 已知 URL 转 markdown | 发现新页面（用 Exa search） |
| **gh search** (dev.md) | GitHub 仓库/issue/代码 | 非 GitHub 内容 |
| **V2EX API** | V2EX 热帖 | 其他平台 |
| **智谱等 MCP** | 中文网页搜索（若已配） | 与 Exa 重复时优先 Exa 技术向 |

## 失败处理

→ 完整信号表见 [errors.md](errors.md)（401/429/空结果/timeout）。

**重试链：** 换 query 表述 → 降 `numResults` / 换 `type: fast` → 换 `crawling_exa` 读具体 URL → 汇报失败。

## daily-run 联动

- **收盘 close：** Exa 调研热点公司/竞品/财报（`research-ok`）；遵守 exa_cache，勿重复 query。
- **盘中 intraday：** 默认**不**拉 Exa 全量；宏观走日缓存。
- **调研任务：** 配合 agent-reach 时先 Exa 广度，再 social.md 中文舆情，最后 Jina 精读关键 URL。
