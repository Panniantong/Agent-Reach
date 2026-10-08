# 开发工具

GitHub CLI 

## GitHub (gh CLI)

GitHub 官方命令行工具，用于仓库、Issue、PR、Actions、Release 以及 API 访问。
安装与命令说明见 [GitHub CLI 官方手册](https://cli.github.com/manual/)。
运行前确认 `gh --version` 与 `gh auth status`；以下命令需要相应仓库访问权限，
列出命令不代表当前环境已安装或已完成认证。

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

| 工具 | 官方来源 | 用途 |
|-----|------|------|
| gh CLI | [GitHub CLI](https://cli.github.com/manual/) | GitHub 仓库、代码搜索与协作 |

此处只推荐上文有调用说明的 GitHub CLI。额外的 MCP 工具不随 Agent Reach
自动提供；只有在用户自行配置并确认工具存在、来源和权限后才能调用。
