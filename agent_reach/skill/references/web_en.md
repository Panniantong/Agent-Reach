# Web Reading

General web pages, WeChat articles, RSS.

## General Web Pages (Jina Reader)

```bash
# Read any web page content
curl -s "https://r.jina.ai/URL"

# Example
curl -s "https://r.jina.ai/https://example.com/article"
```

**Use case**: Most web pages can be read directly with Jina Reader.

## Web Reader (MCP)

```bash
# Read web page (Markdown format)
mcporter call 'web-reader.webReader(url: "https://example.com")'

# Retain images
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# Plain text format
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
```

**Use case**: When you need more precise control over output format.

## WeChat Official Account Articles

### Search articles (via Exa)

```bash
# Search WeChat Official Account articles
mcporter call 'exa.web_search_exa(query: "search keywords", numResults: 5, includeDomains: ["mp.weixin.qq.com"])'
```

### Read full article (via Exa)

```bash
# Crawl full article
mcporter call 'exa.crawling_exa(urls: ["https://mp.weixin.qq.com/s/ARTICLE_ID"], maxCharacters: 10000)'
```

### Optional: Camoufox (better anti-bot)

```bash
cd ~/.agent-reach/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> **Note**: Jina Reader cannot read WeChat articles (blocked by CAPTCHA). Use Exa instead.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**Use case**: Subscribe to blogs, news sources, podcast RSS feeds.

## Selection Guide

| Scenario | Recommended Tool |
|----------|-----------------|
| General web pages | Jina Reader (`curl r.jina.ai`) |
| Need images / format control | web-reader MCP |
| WeChat articles | Exa (search+read) / Camoufox (optional read) |
| RSS feeds | feedparser |
