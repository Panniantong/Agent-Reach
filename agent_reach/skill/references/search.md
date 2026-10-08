# 搜索工具

Exa AI 搜索引擎。

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

## 与其他搜索工具对比

| 工具 | 本 Skill 调用说明 | 适用场景 |
|-----|------|---------|
| Exa | 本页 mcporter 示例 | 英文/技术/代码搜索 |
| GitHub 搜索 | [dev.md](dev.md) | 仓库/代码搜索 |

表格只列出本 Skill 已说明调用方式的路径，不代表相关工具已安装或服务已配置。
使用 Exa 前确认 mcporter 中已注册 Exa 服务；仓库/代码搜索的安装与认证检查见
[dev.md](dev.md)。其他搜索服务只有在用户自行配置并确认可用后才能使用，
不能从工具名称推断当前环境拥有该能力。
