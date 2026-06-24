# 百科 & 参考

Wikipedia（维基百科）。

## Wikipedia (公开 API)

无需认证，两个官方公开 API：REST（词条摘要）+ MediaWiki Action API（全文搜索、正文、章节）。**多语言**：把子域名 `en` 换成 `zh` / `ja` / `de` 等即可切换语言。

### 全文搜索（Action API，无需 key）

```bash
curl -s "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=QUERY&srlimit=10&format=json"
# 中文维基：
curl -s "https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=人工智能&format=json"
```

### 词条摘要（REST API，含简介段落、描述、缩略图）

```bash
# TITLE 用下划线代替空格，如 Python_(programming_language)
curl -s "https://en.wikipedia.org/api/rest_v1/page/summary/TITLE"
```

### 词条正文（Action API，纯文本全文）

```bash
curl -s "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&redirects=1&titles=TITLE&format=json"
```

### 章节目录（Action API）

```bash
curl -s "https://en.wikipedia.org/w/api.php?action=parse&page=TITLE&prop=sections&format=json"
```

### Python 调用示例

```python
from agent_reach.channels.wikipedia import WikipediaChannel

ch = WikipediaChannel()

# 全文搜索（lang 默认 "en"，可换 "zh"/"ja"/...）
for r in ch.search("alan turing", limit=5):
    print(f"{r['title']} ({r['wordcount']}w) — {r['url']}")

# 词条摘要（简介段落 + 描述 + 缩略图）
s = ch.get_summary("Python (programming language)")
print(s["description"], "—", s["extract"])

# 词条正文（纯文本全文）
article = ch.get_article("Alan Turing")
print(len(article["extract"]), "chars")

# 章节目录
for sec in ch.get_sections("Alan Turing"):
    print(f"{'  ' * (int(sec['level']) - 1)}{sec['title']}")
```

> **摘要 vs 正文**：先用 `get_summary` 拿简介（一段话，便宜）；需要细节再用 `get_article` 拉全文。
> **标题歧义**：先 `search` 拿到准确 title，再去 `get_summary` / `get_article`，避免消歧义页。
