# 开发工具

GitHub CLI 

## GitHub (gh CLI)

GitHub 官方命令行工具，用于仓库、Issue、PR、Actions、Release 以及 API 访问。

```bash
# 认证
gh auth login
gh auth status

# 搜索
gh search repos "query" --sort stars --limit 10
gh search code "query" --language python

# 仓库
gh repo view owner/repo
gh repo clone owner/repo
gh repo create my-repo --private
gh repo fork owner/repo
gh repo fork owner/repo --clone
gh repo sync owner/repo

# Issues
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
gh issue create -R owner/repo --title "Title" --body "Body"

# Pull Requests
gh pr list -R owner/repo --state open
gh pr view 123 -R owner/repo
gh pr create -R owner/repo --title "Title" --body "Body"
gh pr checks 123 --repo owner/repo

# Actions / CI
gh run list --repo owner/repo --limit 10
gh run view <run-id> --repo owner/repo
gh run view <run-id> --repo owner/repo --log-failed
gh workflow list --repo owner/repo

# Releases
gh release list -R owner/repo
gh release create v1.0.0

# API
gh api /user
gh api repos/owner/repo

# JSON 输出
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```


## 选择指南

| 工具 | 来源 | 用途 |
|-----|------|------|
| gh CLI | agent-reach | Git 操作 |
| zread | my-mcp-tools | 读仓库内容 |
| context7 | my-mcp-tools | 查技术文档 |


## Stack Overflow (Stack Exchange API)

无需认证的官方 [Stack Exchange API v2.3](https://api.stackexchange.com/docs)。匿名访问按 IP 限流（约 300 次/天；注册免费 key 可升到 10k/天）。**所有响应都是 gzip 压缩的**——用 curl 记得加 `--compressed`。每个端点都带 `site=` 参数，默认 `stackoverflow`，也可换 `serverfault` / `superuser` / `askubuntu` / `math` 等。

### 搜索问题（按相关性）

```bash
curl -s --compressed "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=QUERY&site=stackoverflow"

# 限定标签
curl -s --compressed "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=QUERY&tagged=python&site=stackoverflow"
```

### 问题详情 + 回答（含正文 HTML，需 filter=withbody）

```bash
# question_id 从 URL 获取，如 .../questions/231767/...
curl -s --compressed "https://api.stackexchange.com/2.3/questions/QUESTION_ID?site=stackoverflow&filter=withbody"
curl -s --compressed "https://api.stackexchange.com/2.3/questions/QUESTION_ID/answers?order=desc&sort=votes&site=stackoverflow&filter=withbody"
```

### 标签下的高票问题 / 用户

```bash
curl -s --compressed "https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged=rust&site=stackoverflow"
curl -s --compressed "https://api.stackexchange.com/2.3/users/USER_ID?site=stackoverflow"
```

### Python 调用示例

```python
from agent_reach.channels.stackoverflow import StackOverflowChannel

ch = StackOverflowChannel()

# 搜索（gzip 自动解压；tag/site 可选）
for q in ch.search("asyncio gather exception", limit=5):
    print(f"[{q['score']}↑ {q['answer_count']}ans answered={q['is_answered']}] {q['title']}")

# 问题详情 + 高票回答（body 为 HTML）
q = ch.get_question(231767, answer_limit=3)
print(q["title"], "—", q["owner"])
for a in q["answers"]:
    print(f"  {a['score']}↑ accepted={a['is_accepted']} by {a['owner']}")

# 标签高票问题 / 用户
top = ch.get_tag_questions("rust", limit=10)
user = ch.get_user(22656)
```

> **正文是 HTML**：`get_question` 的 `body` 和 `answers[].body` 是 HTML（含代码块 `<pre><code>`），保留以免丢失代码格式。
> **限流**：匿名约 300 次/天；`get_question` 会发 2 个请求（问题 + 回答）。批量时注意 `answer_limit` 和总量。
