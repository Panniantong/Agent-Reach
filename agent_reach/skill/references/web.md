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

## 微信公众号正文读取

先按 [公众号搜索指引](search.md#微信公众号文章搜索) 获取 `mp.weixin.qq.com`
原文链接，再检查 `mcporter list exa --schema` 是否提供 `web_fetch_exa`。
提供时可读取一篇文章；以下单 URL 写法已在 mcporter 0.14.2 验证，CLI 会将它转换为
工具要求的 `urls` 数组。

```bash
# ARTICLE_URL 替换为搜索结果里的公众号原文链接（保留完整 URL）
mcporter call exa.web_fetch_exa "urls=ARTICLE_URL" maxCharacters=8000 --timeout 30000
```

取得正文后核对标题、文章来源及用户关心的内容。`maxCharacters` 会限制返回长度，
输出可能截断；需要完整文章时提高上限并核对结尾，仍不完整则标为部分正文。
如果本机 Exa schema 没有该工具，或读取失败，可尝试已有的 Jina Reader 路径：

```bash
curl --fail --silent --show-error --connect-timeout 10 --max-time 30 "https://r.jina.ai/ARTICLE_URL"
```

登录提示、验证码、访问限制、空正文或工具错误都不算读取成功。两条路径均失败时，
保留已找到的原文链接，说明目前只有检索摘录，请用户在微信中打开原文或提供文章内容。
不要自动登录、反复重试挑战页，或把搜索摘录标成已核验全文。

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
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |
