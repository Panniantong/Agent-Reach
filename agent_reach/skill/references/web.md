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

**不可达时**: Jina Reader 是外部服务，在大陆直连、无代理等网络下不可达。
`agent-reach doctor` 会对该渠道做真实连通性探测，不可达时报 warn。
此时改用 Exa 后端读取全文：

```bash
mcporter call exa.web_fetch_exa urls='["https://example.com/article"]' maxCharacters=8000
```

支持一次传入多个 URL 批量读取。若返回 `CRAWL_NON_CANONICAL`，去掉 URL 尾部斜杠后重试。

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

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| Jina 不可达时的兜底 | Exa (`mcporter call exa.web_fetch_exa`) |
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |
