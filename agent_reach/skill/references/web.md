# 网页阅读

通用网页、RSS。**微信公众号文章链接除外** — 见下方专用路由（非零配置）。

## 微信公众号 (`mp.weixin.qq.com`) — 勿用 Jina

微信对数据中心 IP 返回「环境异常」验证页。Jina Reader、WebFetch、Tavily extract 等**响应很快但内容无效**（拿到的是验证页，不是正文）。

**适用**：用户已提供单篇文章链接（`https://mp.weixin.qq.com/s/...`）。  
**不适用**：在公众号内「搜索关键词」— Exa 等搜索引擎对微信全文索引极差，应请用户提供直链。

### 推荐：独立工具（需安装浏览器自动化）

维护者提供的专用工具（Camoufox 反检测 + MCP/CLI）：

```bash
git clone https://github.com/Panniantong/wechat-article-for-ai.git
cd wechat-article-for-ai
pip install -r requirements.txt
python main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

- 遇 CAPTCHA：加 `--no-headless` 手动过验证后重试
- Agent 集成：仓库内含 MCP server 与 SKILL.md

### 备选：Agent 自带浏览器 MCP

若环境已有 Playwright / browser MCP（如 Cursor `user-Playwright`）：

1. `browser_navigate` 打开文章 URL
2. `browser_snapshot` 读取正文（通常比 Jina 可靠）

### 禁止

对 `mp.weixin.qq.com` 使用：

```bash
# BAD — returns verification page, not article body
curl -s "https://r.jina.ai/https://mp.weixin.qq.com/s/ARTICLE_ID"
```

### 已知坑

| 问题 | 处理 |
|------|------|
| Windows Python 输出中文报 `UnicodeEncodeError` | 设 `PYTHONUTF8=1` 或 `python -X utf8`，或输出到文件 |
| 页面显示环境异常 / CAPTCHA | 换浏览器自动化方案；`wechat-article-for-ai --no-headless` |
| 误以为 Jina 超时=网络慢 | 实际是反爬；不要用 Jina 重试 |

> Agent Reach v1.4+ 不再把微信公众号列为零配置 channel（#347）。有直链时用本节的 Tier-2 方案，避免虚假「已读取」。

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
| **微信公众号文章直链** | [wechat-article-for-ai](https://github.com/Panniantong/wechat-article-for-ai) 或 browser MCP（**勿用 Jina**） |
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| RSS 订阅 | feedparser |
