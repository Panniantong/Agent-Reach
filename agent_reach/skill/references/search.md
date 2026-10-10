# 搜索工具

Exa AI 搜索引擎、Google 图片搜索。

## Exa AI 搜索

高质量 AI 搜索引擎，适合查找技术文档、官方示例和相关网页。

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `web_search_exa(query: "...", numResults: 5)` |
| 技术/代码资料 | `web_search_exa(query: "框架名 API 示例", numResults: 5)` |

> Exa MCP 的 `get_code_context_exa` 已弃用且默认不注册。代码问题也使用
> `web_search_exa`；需要精确搜索仓库内容时，改用 `dev.md` 中的 GitHub 搜索。

### 特点

- 擅长英文内容和技术文档
- 可通过查询词定位官方文档和代码示例
- 结果质量高

## Google 图片搜索（Custom Search API，需配置）

**不要抓取 google.com/搜图结果页**——Google 明确禁止自动化抓取，实测会被反爬拦截。
本渠道改走 Google 官方 Custom Search JSON API（`searchType=image`），免费额度
100 次/天，超出按 Google Cloud 计费。

```bash
curl -s "https://www.googleapis.com/customsearch/v1?key=$GOOGLE_API_KEY&cx=$GOOGLE_CX&q=QUERY&searchType=image&num=5"
```

先跑 `agent-reach doctor --json` 看 `google_images` 是否已配置齐全（`active_backend`
始终为 null——Doctor 不发起真实查询以免消耗每日额度，配置存在不代表凭据有效）。

> 配置：`agent-reach configure google-key` + `agent-reach configure google-cx`。
> 获取方式见 https://programmablesearchengine.google.com/（创建搜索引擎、开启
> 图片搜索）和 https://console.cloud.google.com/（启用 Custom Search API 拿 Key）。

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | agent-reach | 英文/技术/代码搜索 |
| Google 图片搜索 | agent-reach（需配置） | 找具体商品/实体的真实图片 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
