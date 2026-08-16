## 📊 Phase-2.6 A股每日复盘四卡（[a-stock-review-skill](https://github.com/zjk1984/a-stock-review-skill)）

> 「散户复盘找机会，高手复盘改毛病。」upstream 是纯前端 + Node 零依赖代理，约 5–10 秒拉东财全市场数据，输出 **四张复盘卡片**。daily-run **不嵌入其 HTML UI**，但收盘 18:00 / 周六 weekly 已部分覆盖同类能力；缺项列入 roadmap。

### upstream 架构

```
浏览器 → node server.js (:8080) → push2.eastmoney.com / datacenter.eastmoney.com
       ← CORS 代理 + JSONP 兜底    ← 东财公开行情 API
```

- **零 npm 依赖**：`server.js` 仅 `http` + `fs` + Node 18+ `fetch`
- **存储**：复盘快照存浏览器 `localStorage`（最多 60 日），支持 vs 昨日 / vs 上周对比
- **最佳实践**：18:00 收盘复盘 cron；须 `node server.js` 启动（直接开 HTML 可能 CORS 失败）

本地试跑（与 daily-run cron **并行**，互不冲突）：

```bash
git clone https://github.com/zjk1984/a-stock-review-skill ~/a-stock-review-skill
cd ~/a-stock-review-skill && node server.js
# 浏览器 http://localhost:8080 → 选日期 →「开始复盘」
```

### 四卡结构与 daily-run 映射

| 卡片 | upstream 内容 | daily-run 对应 | 状态 |
|------|---------------|----------------|------|
| 🌡️ **市场情绪** | 上证/深证/创业板/科创50/沪深300 · 涨跌家数 · 涨跌停 · 炸板率 · 北向 · **情绪定级（强/中/弱）+ 建议仓位** | `market_breadth_collector` + `macro_collector` 北向/上证；MSS + `compute_verdict` | ✅ |
| 🔥 **板块主线** | 行业/概念 Top · **单主线/双主线/多题材轮动** · 龙头 · 连板梯队 · 板块主力流 | `sector_mainline.py` + `weekly_report.hot_sectors` + `industry_expert` | ✅ |
| 🐉 **龙虎榜 & 资金** | LHB 净买卖排行 · 资金偏好 · 个股主力流 · 涨停池 | `lhb_collector.py` + 收盘卡 `close_market` | ✅ |
| 📈 **历史对比** | vs 昨日 / vs 上周 · 本地历史条 | `market_review.py` vs 昨日/上周 + `verify` + `experience.jsonl` | ✅ |

### 情绪定级算法（可借鉴写入 MSS 宏观分）

upstream `analyzeEmotion()` 综合打分 → 定级 → 仓位：

| 信号 | 加分/扣分 | daily-run 近似 |
|------|-----------|----------------|
| 涨跌比 >2:1 | +3 | 可映射 `mss_breakdown.market_breadth` |
| 涨跌比 1–2:1 | +1 | 中性 |
| 涨跌比 <1:1 | -2 | MSS 宏观降分 |
| 涨停 ≥80 / ≥40 | +2 / +1 | — |
| 跌停 ≥50 / ≥20 | -2 / -1 | — |
| 炸板率 >30% / >20% | -2 / -1 | 可对标 `volume_ratio` + 高位回落 |
| 北向 >50亿 / <-50亿 | +1 / -1 | `macro_collector.northbound_flow_yi` ✅ |

**定级阈值：**

- 综合分 ≥4 → **强** → 建议仓位 **7–8 成**
- 综合分 1–3 → **中** → **5 成**
- 综合分 ≤0 → **弱** → **2–3 成**

与 daily-run MSS 择时 **并存**：upstream 偏「全市场宽度 + 短线情绪」；MSS 偏「全球共振 + 持仓标的 + 巴菲特过滤」。收盘飞书卡片宜 **并列展示**（待增强）。

### 板块主线判定（upstream `analyzeSectors`）

| 类型 | 条件 | daily-run 借鉴点 |
|------|------|------------------|
| **单主线** | 最强行业涨停 ≥15 且领先第二名 ≥5 家 | weekly `hot_sectors` + Exa 深度 |
| **双主线** | 前两名各 ≥8 涨停且差距 <5 | `watchlist_candidates` 多 sector |
| **多题材轮动** | 其余 | 高现金 + 观察池分散 |

连板梯队：upstream 按涨停股行业聚合估算；daily-run **尚无**全市场涨停池拉取。

### 东财 API 清单（upstream 已验证）

| 用途 | 路径 | daily-run |
|------|------|-----------|
| 五大指数 | `push2…/ulist.np/get` secids 000001/399001/… | `macro_collector._fetch_index_change` |
| 全 A 涨跌统计 | `push2…/clist/get` fs=m:0+t:6,… | `market_breadth_collector` ✅ |
| 北向 10 日 | `push2…/kamt.kline/get` | `macro_collector._fetch_northbound_flow` ✅ |
| 行业/概念板块 | `clist/get` fs=m:90+t:2/3 | `sector_mainline.py` ✅ |
| 板块主力流 | `clist/get` fid=f62 | 🟡 主线卡片间接覆盖 |
| 个股主力流 Top | `clist/get` fid=f62 | ❌ |
| 龙虎榜 | `datacenter…/RPT_DAILY_BILLRANKING` | `lhb_collector.py` ✅ |

行情个股报价：daily-run `quote_fetch._fetch_eastmoney()` 与 upstream 同源 **push2** 体系。

### 与收盘 / 周报工作流衔接

**每日 18:00 `daily-run close`（已有）：**

1. Team + MSS 曲线 + 组合 P&L + Exa 深度调研
2. `verify` 对比早盘 MSS 预测区间
3. `experience.jsonl` 沉淀规则

**已实现（四卡落地）：**

1. 收盘拉 **市场宽度快照** → `market_breadth_collector` 写入 snapshot + `market_review/{date}.json`
2. 飞书收盘卡 **全市场复盘** 段 → 情绪定级 + 主线 + 龙虎榜（与 MSS 并列）
3. 周六 `weekly_report` **龙虎榜周汇总 + 主线类型标签** — ✅ `redfox_weekly.summarize_week_market_reviews`
4. 持久化 `~/.agent-reach/daily_run/market_review/{date}.json` — ✅

### 集成状态

**已完成：**

- [x] 东财行情源 — `quote_fetch` eastmoney 首选
- [x] 北向资金 — `macro_collector._fetch_northbound_flow`
- [x] 上证涨跌幅 — `macro_collector._fetch_index_change`
- [x] 板块/热点（持仓视角）— `weekly_report.hot_sectors` + Exa
- [x] 历史对比（组合/MSS）— `verify` + `experience.jsonl`
- [x] `market_breadth_collector.py` — 全 A 涨跌家数、涨跌停、炸板率、情绪定级
- [x] `sector_mainline.py` — 单/双/多主线 + 连板梯队
- [x] `lhb_collector.py` — 龙虎榜净买卖 + 资金偏好
- [x] `market_review.py` — 编排 + `~/.agent-reach/daily_run/market_review/{date}.json` 持久化 + vs 昨日/上周
- [x] 收盘飞书卡「全市场复盘」— `render_close_sections(close_market)` + `run_close` 按日缓存

**待增强：**

- [ ] 情绪定级与 MSS 宏观分自动融合（当前并列展示）
- [ ] 全市场宽度失败时降级为 macro_collector 摘要（不阻断收盘）

**参考文件（upstream）：** `SKILL.md` · `index.html`（`analyzeEmotion` / `analyzeSectors` / `analyzeLHB`）· `server.js`

---
