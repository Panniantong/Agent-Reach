# 网页阅读

通用网页、RSS。

## 通用网页 (Jina Reader)

```bash
# 读取任意网页内容
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

**适用场景**: 大多数网页可以直接用 Jina Reader 读取。

## Web Reader (MCP)

```bash
# 读取网页内容 (Markdown 格式)
mcporter call web-reader.webReader url="https://example.com"

# 保留图片
mcporter call web-reader.webReader url="https://example.com" retain_images=true

# 纯文本格式
mcporter call web-reader.webReader url="https://example.com" return_format="text"
```

**适用场景**: 需要更精确控制输出格式时使用。

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**适用场景**: 订阅博客、新闻源、播客等 RSS feed。

### 从站点根 URL 发现 feed

```python
from agent_reach.channels.rss import RSSChannel

for feed in RSSChannel().discover_feeds("https://example.com"):
    print(feed["url"], feed.get("title"), feed.get("type"))
```

会解析首页的 `<link rel="alternate">`，再探测常见路径（`/feed`、`/rss`、`/atom.xml` 等），用 feedparser 校验后去重返回。不覆盖 robots.txt / 外部 registry / 定时重扫——由调用方按需调度。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |
| 从站点根发现 feed | `RSSChannel.discover_feeds` |
