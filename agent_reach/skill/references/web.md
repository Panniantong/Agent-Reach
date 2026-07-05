# 网页阅读

RSS 和受限网页后备。普通 URL 阅读、web fetch、网页摘要应优先使用当前 agent
自带的 web fetch；只有在 Agent Reach 已因专门平台/后端需求被明确选中，或原生
fetch 不可用时，才使用这里的后备命令。

## 受限网页后备 (Jina Reader)

```bash
# 读取任意网页内容
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

**适用场景**: 原生 web fetch 不可用、输出格式需要后备控制，或用户明确要求走 Agent Reach。

## Web Reader (MCP)

```bash
# 读取网页内容 (Markdown 格式)
mcporter call 'web-reader.webReader(url: "https://example.com")'

# 保留图片
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# 纯文本格式
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
```

**适用场景**: 原生 web fetch 不可用，且需要更精确控制输出格式时使用。

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
| 普通 URL/web fetch | 当前 agent 自带 web fetch |
| 受限网页后备 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制的后备读取 | web-reader MCP |
| RSS 订阅 | feedparser |
