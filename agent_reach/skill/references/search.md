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

## 微信公众号文章搜索

微信公众号文章使用 Exa 的网页搜索路径。当前 Agent Reach 没有独立的 `wechat`
渠道，也没有 `agent-reach check` 命令；用 `agent-reach doctor --json` 查看
`exa_search`，再用 `mcporter list exa --schema` 确认工具是否能连接。
如果尚未配置 Exa，按安装指南配置后再搜索。

可以给 Agent 这样的请求：

> 帮我搜索微信公众号中关于“中国科学院 人工智能”的文章。用 Exa 搜索
> `site:mp.weixin.qq.com 中国科学院 人工智能`，保留原文链接、标题、可确认的
> 公众号名和发布日期。再读取选中文章的正文；读不到时明确说明，搜索摘要不要当作全文。

```bash
# 引号包住整个 key=value 参数；objective 描述本次搜索要保留的来源
mcporter call exa.web_search_exa "query=site:mp.weixin.qq.com 中国科学院 人工智能" "objective=只返回微信公众号原文 mp.weixin.qq.com 链接，保留文章标题和来源；排除转载网站。" numResults=5 --timeout 30000

# 需要指定公众号时，把公众号名加入 query；它是查询条件，不保证搜索结果的账号身份
mcporter call exa.web_search_exa "query=site:mp.weixin.qq.com 公众号名 主题关键词" "objective=寻找指定公众号的相关文章，保留可核验的原文链接和来源，无法确认账号或日期时标为未知。" numResults=5 --timeout 30000
```

`site:` 与 `objective` 用来指导检索，返回后仍需检查每条原文 URL 的主机名确实为
`mp.weixin.qq.com`。保留原始标题与链接；日期或公众号身份缺失时标为未知，
不要从摘要推断。搜索受索引覆盖和更新延迟影响，空结果不代表公众号没有相关文章，
也不能据此声称列出了某个公众号的全部或最新文章。

选中原文后，按 [微信公众号正文读取](web.md#微信公众号正文读取) 继续。
搜索结果里的 `Highlights` 是检索摘录，不是已经读取并核验的完整正文。

验收这条 prompt 时，应从本次实际搜索结果中选一个已核对域名的原文链接，
将该链接传给正文读取工具，核对标题和正文对应关系，并记录是否截断。
不要用另一篇预先已知可读取的文章代替这个搜索结果来证明整条流程成功。

## 与其他搜索工具对比

| 工具 | 来源 | 适用场景 |
|-----|------|---------|
| Exa | agent-reach | 英文/技术/代码搜索 |
| 智谱搜索 | my-mcp-tools | 中文搜索 |
| GitHub 搜索 | agent-reach (dev.md) | 仓库/代码搜索 |
