# Search Tools

Exa AI search.

## Exa AI Search

A high-quality AI search engine that is useful for technical documentation, official examples, and relevant web pages.

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### Common use cases

| Use case | Parameters |
|---|---|
| General web search | `web_search_exa(query: "...", numResults: 5)` |
| Technical/code research | `web_search_exa(query: "framework API example", numResults: 5)` |

> Exa MCP's `get_code_context_exa` is deprecated and is not registered by default. Use `web_search_exa` for code-related research too. For exact repository/code search, use GitHub search from `dev.md`.

### Strengths

- Strong coverage of English and technical content
- Good for locating official documentation and code examples
- High-quality semantic search results

## Comparison

| Tool | Source | Best for |
|---|---|---|
| Exa | agent-reach | English/technical/code-oriented web search |
| Zhipu Search | my-mcp-tools | Chinese-language web search |
| GitHub Search | agent-reach (`dev.md`) | Repository/code search |
