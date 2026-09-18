# Web Reading

General web pages and RSS.

## General web pages (Jina Reader)

```bash
# Read any web page
curl -s "https://r.jina.ai/URL"

# Example
curl -s "https://r.jina.ai/https://example.com/article"
```

**Use when:** most pages can be read directly through Jina Reader.

## Web Reader (MCP)

```bash
# Read page as Markdown
mcporter call web-reader.webReader url="https://example.com"

# Preserve images
mcporter call web-reader.webReader url="https://example.com" retain_images=true

# Plain-text output
mcporter call web-reader.webReader url="https://example.com" return_format="text"
```

**Use when:** you need more control over the returned format.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**Use when:** following blogs, news feeds, podcasts, and other RSS/Atom sources.

## Selection guide

| Scenario | Recommended tool |
|---|---|
| General web page | Jina Reader (`curl r.jina.ai`) |
| Images/format control | web-reader MCP |
| RSS/Atom | feedparser |
