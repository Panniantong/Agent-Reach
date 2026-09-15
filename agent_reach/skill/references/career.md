# 职场招聘

LinkedIn。

## LinkedIn

```bash
# 注意：mcporter 的 key=value 不会剥离引号——写成 key="value" 时引号会进入值本身，
# 导致校验失败或搜索词带引号。值含空格时请给「整个 key=value token」加引号。
mcporter call linkedin.get_person_profile linkedin_username=username sections=experience,education

# 搜索人才
mcporter call linkedin.search_people "keywords=AI engineer" location=Shanghai

# 获取公司资料
mcporter call linkedin.get_company_profile company_name=openai sections=posts,jobs

# 搜索职位
mcporter call linkedin.search_jobs "keywords=software engineer" location=Remote max_pages=2
```

> **需要登录**: 首次使用前运行 `uvx mcp-server-linkedin@latest --login`，保存有效登录态。

### Fallback 方案

如果 MCP 不可用，可以用 Jina Reader：

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```
