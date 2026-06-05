# Search Tools

Exa AI search engine.

## Exa AI Search

High-quality AI search engine, great for technical and code searches.

```bash
mcporter call 'exa.web_search_exa(query: "query", numResults: 5)'
mcporter call 'exa.get_code_context_exa(query: "code question", tokensNum: 3000)'
```

### Use Cases

| Scenario | Parameters |
|----------|------------|
| Web search | `web_search_exa(query: "...", numResults: 5)` |
| Code search | `get_code_context_exa(query: "...", tokensNum: 3000)` |

### Features

- Excels at English content and technical documentation
- Supports code context search
- High quality results