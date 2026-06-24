# 学术论文搜索与质量分析

聚合 arXiv + Semantic Scholar，去重、打分、排序。

## 快速命令

```bash
# 按主题搜索论文（最常用）
agent-reach research search "speech recognition transformer" --max 15

# 指定年份范围
agent-reach research search "large language model reasoning" --year 2023-2025

# 指定学科领域
agent-reach research search "diffusion model" --fields "Computer Science"

# 搜索后按侧重点排序
agent-reach research search "federated learning" --emphasis latest    # 最新
agent-reach research search "transformer architecture" --emphasis classic  # 经典
agent-reach research search "medical AI" --emphasis open            # 开源优先
```

## 调用流程

**标准调研流程（推荐）：**

1. **搜索论文**：`agent-reach research search "你的主题" --max 15`
2. **阅读摘要**：从返回结果中筛选 3-5 篇最相关的
3. **深度分析**：`agent-reach research analyze "论文标题"`
4. **获取全文**：用 PDF 链接 + Jina Reader 或直接下载阅读

**结果包含的信息：**
- `title`: 标题
- `authors`: 作者列表
- `abstract`: 摘要（前 500 字符）
- `year`: 发表年份
- `citation_count` / `influential_citations`: 引用次数 / 有影响力引用
- `venue`: 发表会议/期刊
- `tldr`: Semantic Scholar 的 TL;DR 一句话摘要
- `pdf_url`: 开放获取 PDF 链接（如果有）
- `quality.rating`: 论文质量等级（excellent / good / ok / unknown）
- `quality.overall`: 综合质量分（0-1）
- `quality.citation_score`: 引用影响力分
- `quality.venue_score`: 会议/期刊声望分
- `quality.recency_score`: 时效性分

## 底层 API

两个后端都是免费公开 API，零配置可用：

### arXiv API

```bash
# 直接调用 arXiv API
curl "http://export.arxiv.org/api/query?search_query=all:speech+recognition&start=0&max_results=10&sortBy=relevance"

# Python 方式
python -c "
from agent_reach.channels.arxiv import search_arxiv
papers = search_arxiv('speech recognition', max_results=10)
for p in papers:
    print(p.title, p.pdf_url)
"
```

支持 arXiv 查询语法：
- `ti:"keyword"` — 标题搜索
- `au:"author"` — 作者搜索
- `all:"keyword"` — 全字段搜索（默认）
- `cat:cs.CL` — 按分类搜索
- 布尔运算：`AND`, `OR`, `ANDNOT`

### Semantic Scholar API

```bash
# 直接调用 S2 API
curl "https://api.semanticscholar.org/graph/v1/paper/search?query=speech+recognition&limit=10&fields=title,authors,abstract,year,citationCount,venue,tldr,openAccessPdf"

# Python 方式
python -c "
from agent_reach.channels.semantic_scholar import search_semantic_scholar, get_citations
papers = search_semantic_scholar('speech recognition', limit=5)
for p in papers:
    print(p.title, '—', p.citation_count, 'citations')
"
```

可选 API Key（提升速率限制）：
- 注册：https://api.semanticscholar.org/api-docs/#tag/Authentication
- 配置：`agent-reach configure s2-key YOUR_KEY`
- 无 Key 限制：100 次/5 分钟（科研场景足够）
- 有 Key 限制：1000 次/5 分钟

## 单篇论文分析

```bash
# 分析指定论文（自动查 S2 获取引用/会议/影响力数据）
agent-reach research analyze "Attention Is All You Need"
```

返回内容包含：
- 完整元数据（作者、年份、会议/期刊）
- 引用数据（总引用 + 有影响力引用）
- TL;DR 一句话摘要
- 质量评分（引用分 + 会议声望分 + 时效分）
- PDF 链接（如果有开放获取版本）

## 论文去重与合并

当同一篇论文同时出现在 arXiv 和 Semantic Scholar 时：
- 合并元数据（S2 提供引用数据，arXiv 提供 PDF 链接）
- 标记为 `source: "both"`
- 只保留一条记录

## 质量评分说明

每篇论文的 `quality.overall` 分数（0-1）由四个维度加权计算：

| 维度 | 默认权重 | 说明 |
|-----|---------|------|
| 引用影响力 | 40% | 引用次数 + 有影响力引用 |
| 会议声望 | 30% | 发表于顶会/顶刊得分高 |
| 时效性 | 20% | 越新分数越高，5 年以上衰减 |
| 开放获取 | 10% | 有公开 PDF 的论文有加分 |

**顶会列表（部分，Venue分数 1.0）**：
AI/ML: NeurIPS, ICML, ICLR, AAAI, IJCAI, CVPR, ICCV, ACL
System: SOSP, OSDI, NSDI, ASPLOS, PLDI
DB: SIGMOD, VLDB, KDD, SIGIR
Security: CCS, S&P, USENIX Security, NDSS

**优秀期刊（Venue分数 0.9）**：
JMLR, IEEE TPAMI, Nature, Science, JAIR

## 高级用法

### 定制排序权重

```python
from agent_reach.research.analyzer import rank_papers
from agent_reach.channels.research import ResearchChannel

ch = ResearchChannel()
results = ch.search("federated learning", max_results=20)

# 只看引用（找经典论文）
ranked = rank_papers(results, citation_weight=0.70, venue_weight=0.20, recency_weight=0.05, openness_weight=0.05)

# 只看时效（找最新进展）
ranked = rank_papers(results, citation_weight=0.10, venue_weight=0.10, recency_weight=0.70, openness_weight=0.10)
```

### 批量分析多篇论文

```python
from agent_reach.research.analyzer import analyze_paper

titles = [
    "Attention Is All You Need",
    "BERT: Pre-training of Deep Bidirectional Transformers",
    "GPT-3: Language Models are Few-Shot Learners",
]
for t in titles:
    result = analyze_paper(t)
    print(f"{result['quality']['rating']}: {t} — {result.get('citation_count', 0)} citations")
```

### 组合其他渠道做深度调研

对搜索结果中的每篇论文，可用其他 channel 做进一步分析：
- `curl https://r.jina.ai/<arxiv_url>` — 用 Jina Reader 读取论文网页版
- `mcporter call 'exa.web_search_exa(query: "paper title review")'` — 搜索相关评论/解读
- `gh search repos "paper title" --sort stars` — 查找论文的官方实现代码
