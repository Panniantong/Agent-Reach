# Search tool

Exa AI search engine.

## Exa AI Search

High-quality AI search engine for finding technical documentation, official examples, and related web pages.

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### Usage scenarios

| Scene | Parameters |
|-----|------|
| Web Search | `web_search_exa(query: "...", numResults: 5)` |
| Technical/Code Information | `web_search_exa(query: "framework name API example", numResults: 5)` |

> `get_code_context_exa` for Exa MCP is deprecated and not registered by default. Code issues also use
> `web_search_exa`; when you need to search the repository content accurately, use GitHub search in `dev.md` instead.

### Features

- Good at English content and technical documentation
- Official documents and code examples can be located by query words
- High quality results

## Compare with other search tools

| Tools | Source | Applicable scenarios |
|-----|------|---------|
| Exa | agent-reach | English/Technical/Code Search |
| Zhipu search | my-mcp-tools | Chinese search |
| GitHub Search | agent-reach (dev.md) | Repository/Code Search |
