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


## 评论读取与搜索

GitHub 的 Issue / PR 对话评论与 PR 代码行评论是两类数据。搜索代码不会搜索评论，
搜索 Issue / PR 评论也不覆盖 GitHub Discussions 或小红书评论。先用 `gh auth status`
确认 GitHub CLI 认证；私有仓库还需要相应权限。

```bash
# 搜索一个仓库的 Issue / PR 评论；返回的是匹配的 Issue / PR，不是评论明细
gh search issues "keyword" --repo OWNER/REPO --include-prs --match comments --limit 20

# 阅读指定 Issue 的对话（包含正文和评论）
gh issue view NUMBER --repo OWNER/REPO --comments

# 阅读指定 PR 的对话
gh pr view NUMBER --repo OWNER/REPO --comments

# 获取指定 Issue 或 PR 的对话评论，逐页读取并保留评论原始链接
gh api --paginate repos/OWNER/REPO/issues/NUMBER/comments --jq '.[] | {id, body, html_url}'

# 获取指定 PR 的代码行评论；与上面的对话评论分开读取
gh api --paginate repos/OWNER/REPO/pulls/NUMBER/comments --jq '.[] | {id, body, path, line, html_url}'
```

`gh search issues` 用于发现匹配的讨论；需要定位某一条评论时，再读取该讨论的评论明细，
按 `body` 筛选并保留 `html_url`。`--limit 20` 是本次返回的讨论数量上限，不能据此声称
搜索了所有评论。以上路径不写入评论，也不提供小红书全站评论索引。

## 选择指南

| 工具 | 来源 | 用途 |
|-----|------|------|
| gh CLI | agent-reach | Git 操作 |
| zread | my-mcp-tools | 读仓库内容 |
| context7 | my-mcp-tools | 查技术文档 |
