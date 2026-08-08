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

## Substack (公开 RSS / JSON API)

```python
from agent_reach.channels.substack import SubstackChannel

ch = SubstackChannel()
for post in ch.list_posts("platformer", limit=5):
    print(f"{post['title']} — {post['url']}")

# 单篇（不绕过付费墙；付费文可能只有元数据）
detail = ch.get_post("platformer", "some-slug")
print(detail["title"], detail.get("audience"))
```

**适用场景**: `*.substack.com` 出版物列表与公开文章。自定义域名出版物仍走通用网页通道。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |
| Substack 出版物 | `SubstackChannel` |
