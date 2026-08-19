# 网页阅读

通用网页、RSS。

> 失败信号 → [errors.md](errors.md)

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
mcporter call 'web-reader.webReader(url: "https://example.com")'

# 保留图片
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# 纯文本格式
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
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

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |

## 失败处理

| 信号 | 动作 |
|------|------|
| Jina 空/403 | 换 Exa `crawling_exa` 或原站 curl |
| MCP web-reader 超时 | 换 Jina；缩 `return_format` |
| feedparser 解析失败 | 检查 URL 是否 RSS/Atom |

Retry budget：同一 URL 最多 2 次不同工具，仍失败则换搜索找镜像。
