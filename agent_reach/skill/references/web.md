# Web And RSS

Use Jina Reader for readable markdown from normal pages.

```powershell
curl.exe -L "https://r.jina.ai/http://example.com"
```

Use RSS feeds when the source exposes one:

```python
import feedparser
feed = feedparser.parse("https://example.com/feed.xml")
print(feed.entries[0].title)
```

Prefer `web` over bespoke scraping for documentation, release notes, blog posts, note, Qiita, and Zenn.
