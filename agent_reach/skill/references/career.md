# 职场招聘

LinkedIn 和 Indeed。先运行 `agent-reach doctor --json`，再使用已配置的 MCP 后端。

## LinkedIn

推荐使用 `mcp-server-linkedin`。Hermes 会把服务器工具作为原生 MCP 工具暴露；其他客户端可以通过 mcporter 调用同名服务器。

```bash
# 获取个人资料。参数是 LinkedIn 用户名，不是完整 URL。
mcporter call 'linkedin.get_person_profile(linkedin_username: "username")'

# 搜索人才
mcporter call 'linkedin.search_people(keywords: "AI engineer", location: "Denmark")'

# 获取公司资料。参数是 /company/ 后的 URL slug。
mcporter call 'linkedin.get_company_profile(company_name: "company-slug")'

# 搜索职位
mcporter call 'linkedin.search_jobs(keywords: "software engineer", location: "Denmark", max_pages: 2)'
```

> **需要登录**：LinkedIn MCP 使用独立的浏览器 profile。登录、2FA 和安全挑战必须由用户在浏览器窗口中手动完成。不要自动读取常用浏览器 Cookie。

### LinkedIn fallback

公开页面可以尝试 Jina Reader：

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

Jina Reader 不提供完整人才搜索、公司员工列表或登录后职位功能。

## Indeed

推荐使用基于 [JobSpy](https://github.com/speedyapply/JobSpy) 的 MCP 服务器，并将服务器命名为 `jobspy` 或 `indeed`。Agent Reach 只按显式服务器名称检测配置，不会验证服务器身份、连通性、登录状态、工具名称或参数 schema，也不会在自身代码中复制 Indeed 抓取逻辑。

首次调用前，必须先查看 MCP 客户端发现的工具和参数 schema。不同 JobSpy MCP 适配器并不共享统一接口：有些把站点固定为 Indeed，有些要求 `site_name`，另一些使用 `site_names`。只调用服务器实际公布的工具，并按其 schema 传参。

下面仅是适配器特定的示意，不是通用复制粘贴命令：

```text
search_jobs(
  search_term="IT Operations",
  location="Denmark",
  country_indeed="Denmark",
  results_wanted=20,
  hours_old=168
)
```

注意：

- 如果适配器暴露站点参数，必须显式选择 Indeed。
- Indeed 搜索通常需要正确的 `country_indeed`；以实际工具 schema 为准。
- JobSpy 的某些过滤器不能同时组合；以所安装版本和适配器文档为准。
- 大批量查询要限速。遇到封锁时等待后重试；不要绕过登录、验证码或访问控制。
- 单个公开职位页可以尝试 Jina Reader，但它不是结构化职位搜索的替代品。
