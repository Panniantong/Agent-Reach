# Web Reading

Generic web pages, WeChat Official Account articles, RSS.

## Generic Web Pages (Jina Reader)

```bash
# Read any web page content
curl -s "https://r.jina.ai/URL"

# Example
curl -s "https://r.jina.ai/https://example.com/article"
```

**Use case**: Most web pages can be read directly with Jina Reader.

## Web Reader (MCP)

```bash
# Read web page content (Markdown format)
mcporter call 'web-reader.webReader(url: "https://example.com")'

# Keep images
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# Plain text format
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
```

**Use case**: Use when you need more precise control over the output format.

## WeChat Official Account / WeChat Articles

### Search Official Account articles (via Exa)

```bash
# Search WeChat Official Account articles
mcporter call 'exa.web_search_exa(query: "search keywords", numResults: 5, includeDomains: ["mp.weixin.qq.com"])'
```

### Read the full text of an Official Account article (via Exa)

```bash
# Crawl the full article text
mcporter call 'exa.crawling_exa(urls: ["https://mp.weixin.qq.com/s/ARTICLE_ID"], maxCharacters: 10000)'
```

### Optional: Camoufox reading (stronger anti-scraping)

```bash
cd ~/.agent-reach/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> **Note**: Jina Reader cannot read WeChat articles (blocked by CAPTCHA); Exa is recommended.

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**Use case**: Subscribing to blogs, news sources, podcasts, and other RSS feeds.

## Selection Guide

| Scenario | Recommended Tool |
|-----|---------|
| Generic web pages | Jina Reader (`curl r.jina.ai`) |
| Need images/format control | web-reader MCP |
| WeChat Official Account | Exa (search + read) / Camoufox (optional reading) |
| RSS subscriptions | feedparser |
| Weibo/Zhihu, etc. | Jina Reader |
