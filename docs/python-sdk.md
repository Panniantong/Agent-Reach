# Agent Reach Python SDK

`AgentReachClient` is the Python API for projects that install Agent Reach into their own Python environment.

## Install

CLI-only installs:

```powershell
uv tool install .
```

This gives you the `agent-reach` CLI, but it does not expose `import agent_reach` to arbitrary project Pythons.

SDK installs for a caller-managed Python environment:

```powershell
uv pip install -e .
```

Or install a built wheel into the host project:

```powershell
uv pip install C:\path\to\dist\agent_reach-<version>-py3-none-any.whl
```

## Basic usage

```python
from agent_reach import AgentReachClient

client = AgentReachClient()

github_repo = client.github.read("openai/openai-python")
web_page = client.web.read("https://example.com")
search_results = client.exa.search("latest gpt-5.4 release notes", limit=3)
qiita_results = client.qiita.search("python user:Qiita", limit=3)
bluesky_results = client.bluesky.search("OpenAI", limit=3)
hatena_reactions = client.hatena_bookmark.read("https://example.com", limit=5)
hacker_news_results = client.hacker_news.search("agent frameworks", limit=3)
mcp_servers = client.mcp_registry.search("docs mcp", limit=3)
reddit_posts = client.reddit.search("agent frameworks", limit=3)
twitter_posts = client.twitter.user_posts("openai", limit=5)
paged_github_search = client.collect("github", "search", "agent reach", limit=6, page_size=3, max_pages=2)
windowed_twitter_search = client.collect("twitter", "search", "OpenAI", limit=5, since="2026-01-01", until="2026-12-31")
```

If your host project only needs a machine-readable subprocess interface, prefer `agent-reach collect --json` instead.

Use the namespace helpers for simple default operations. Use `client.collect(...)` when the caller wants to choose per-channel options exposed by `channels --json` `operation_contracts`, such as `page_size`, `max_pages`, `cursor`, `page`, `since`, or `until`.

## Result shape

Every collection call returns the same envelope:

- `ok`
- `channel`
- `operation`
- `items`
- `raw`
- `meta`
- `error`

Each entry in `items` uses the same normalized shape:

- `id`
- `kind`
- `title`
- `url`
- `text`
- `author`
- `published_at`
- `source`
- `extras`

Use `items` for downstream automation and `raw` when you need backend-native details.

When a channel supports bounded pagination or continuation tokens, the result keeps the existing flat metadata keys and also mirrors them under `meta.pagination`. Agent Reach does not choose those controls for you; the caller decides whether to use them.

Diagnostics such as `extras.source_hints`, `extras.media_references`, YouTube `extras.thumbnail_url`, subtitle/caption availability fields, and social `extras.media` are evidence metadata only. Agent Reach does not rank sources or analyze image/video binaries.

## Discord bot style usage

```python
from agent_reach import AgentReachClient

client = AgentReachClient()

def collect_digest():
    results = []
    results.append(client.exa.search("OpenAI pricing", limit=3))
    results.append(client.github.read("openai/openai-python"))
    results.append(client.qiita.search("python user:Qiita", limit=3))
    results.append(client.bluesky.search("OpenAI", limit=3))
    results.append(client.rss.read("https://hnrss.org/frontpage", limit=3))
    results.append(client.hacker_news.search("agent frameworks", limit=3))
    results.append(client.mcp_registry.search("docs mcp", limit=3))

    messages = []
    for result in results:
        if not result["ok"]:
            messages.append(f"[{result['channel']}] {result['error']['message']}")
            continue
        for item in result["items"]:
            messages.append(f"{item['source']}: {item['title']} {item['url']}")
    return messages
```

## Non-interactive behavior

- collection never prompts interactively
- config values and environment variables are both supported
- failures still return the same JSON-compatible envelope

Useful environment variables:

- `GITHUB_TOKEN`
- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`

## Choosing CLI vs SDK

- Use `agent-reach collect --json` when the host project can shell out and wants the most portable integration surface.
- Use `AgentReachClient` when the host project already manages a Python environment and can install Agent Reach into it.
- Do not assume `uv tool install .` makes `from agent_reach import AgentReachClient` available in unrelated projects.
