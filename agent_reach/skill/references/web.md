# Webpage reading

General web pages, RSS.

## General web page (Jina Reader)

```bash
# Read the content of any web page
curl -s "https://r.jina.ai/URL"

# Example
curl -s "https://r.jina.ai/https://example.com/article"
```

**Applicable scenarios**: Most web pages can be read directly with Jina Reader.

## Web Reader (MCP)

```bash
# Read web content (Markdown Format)
mcporter call web-reader.webReader url="https://example.com"

# keep picture
mcporter call web-reader.webReader url="https://example.com" retain_images=true

# plain text format
mcporter call web-reader.webReader url="https://example.com" return_format="text"
```

**Applicable scenarios**: Use when more precise control of the output format is required.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**Applicable scenarios**: Subscribe to RSS feeds such as blogs, news sources, podcasts, etc.

## Selection Guide

| Scenario | Recommended Tools |
|-----|---------|
| General web page | Jina Reader (`curl r.jina.ai`) |
| Image/format control required | web-reader MCP |
| RSS Subscription | feedparser |
