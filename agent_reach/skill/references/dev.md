# Dev Tools

GitHub CLI

## GitHub (gh CLI)

GitHub's official command-line tool, for repos, issues, PRs, Actions, releases, and API access.

```bash
# Authentication
gh auth login
gh auth status

# Search
gh search repos "query" --sort stars --limit 10
gh search code "query" --language python

# Repositories
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

# JSON output
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```


## Selection Guide

| Tool | Source | Purpose |
|-----|------|------|
| gh CLI | agent-reach | Git operations |
| zread | my-mcp-tools | Read repo content |
| context7 | my-mcp-tools | Look up technical docs |
