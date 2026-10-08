# Search tools

Exa AI search engine.

## Exa AI search

High-quality AI search engine, good for finding technical documentation, official examples and related web pages.

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### When to use

| Scenario | Parameters |
|-----|------|
| Web search | `web_search_exa(query: "...", numResults: 5)` |
| Technical / code material | `web_search_exa(query: "framework name API example", numResults: 5)` |

> Exa MCP's `get_code_context_exa` is deprecated and not registered by default. Use
> `web_search_exa` for code questions too. When you need to search repo contents precisely,
> use the GitHub search in `dev.md` instead.

### Characteristics

- Strong on English content and technical documentation
- Query wording can pin down official docs and code examples
- High result quality

## Compared with other search tools

| Tool | Source | Best for |
|-----|------|---------|
| Exa | agent-reach | English / technical / code search |
| Zhipu search | my-mcp-tools | Chinese-language search |
| GitHub search | agent-reach (dev.md) | Repo / code search |
