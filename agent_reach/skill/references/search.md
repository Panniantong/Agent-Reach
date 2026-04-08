# Search

Use Exa for broad web discovery.

```powershell
mcporter --config "$HOME\.mcporter\mcporter.json" call "exa.web_search_exa(query: \"latest o3 vs gpt-5.4\", numResults: 5)"
```

For note, Qiita, Zenn, docs, and blogs:

1. Search with Exa.
2. Open the chosen result with Jina Reader.

```powershell
curl.exe -L "https://r.jina.ai/http://example.com/article"
```

If Exa is unavailable, fall back to GitHub/web search tools already available in the host environment.
