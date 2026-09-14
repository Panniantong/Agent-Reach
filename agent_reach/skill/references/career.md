# 职场招聘

LinkedIn、牛客面经。

## LinkedIn

```bash
# 获取个人资料
mcporter call linkedin.get_person_profile linkedin_username="username" sections="experience,education"

# 搜索人才
mcporter call linkedin.search_people keywords="AI engineer" location="Shanghai"

# 获取公司资料
mcporter call linkedin.get_company_profile company_name="openai" sections="posts,jobs"

# 搜索职位
mcporter call linkedin.search_jobs keywords="software engineer" location="Remote" max_pages=2
```

> **需要登录**: 首次使用前运行 `uvx mcp-server-linkedin@latest --login`，保存有效登录态。

### Fallback 方案

如果 MCP 不可用，可以用 Jina Reader：

```bash
curl -s "https://r.jina.ai/https://linkedin.com/in/username"
```

## 牛客面经 / Nowcoder

牛客的搜索、面经列表和帖子详情通过 OpenCLI 浏览器适配器完成。它们是只读命令；
不自动调用登录、不读取或保存浏览器 Cookie。默认使用后台窗口和临时站点会话：

```bash
# 搜索面经或其他求职内容
opencli nowcoder search "query" --type post --limit 10 \
  --window background --site-session ephemeral -f yaml

# 获取面经列表
opencli nowcoder experience --limit 15 \
  --window background --site-session ephemeral -f yaml

# 用搜索结果中的 id 或 URL 获取正文
opencli nowcoder detail "<id-or-url>" \
  --window background --site-session ephemeral -f yaml
```

如果页面要求登录，让用户先在 Chrome 中手动登录牛客，再重试只读命令。
