## 🦊 Phase-2.7 多平台舆情与热榜（[redfox-community](https://github.com/zjk1984/redfox-community)）

> upstream 收录 **112 枚** RedFox Agent Skills（`skills/<name>/SKILL.md` + 脚本），API 驱动小红书 / 抖音 / 公众号 / 微博等真实数据。daily-run **不嵌入 RedFox 脚本 UI**，但借鉴其 **跨平台舆情聚合、热榜关键词泛化、公众号大V 订阅、大V 风格蒸馏与质量审计**；免费路径已用 **60s + 雪球 + 东财**，`REDFOX_API_KEY` 为 **可选增强**。

### upstream 架构

```
Agent → SKILL.md 工作流 → scripts/*.py → RedFox API (redfox.hk)
                              ↑
                    REDFOX_API_KEY 鉴权（`~/.agent-reach/config.env` 或 cron 自动加载）
```

- **技能目录约定**：每技能自包含 `SKILL.md` + `scripts/` + `references/`
- **鉴权**：`export REDFOX_API_KEY=ak_…` 写入 `~/.agent-reach/config.env`（600 权限，勿提交 git）；Key 从 [红狐 Hub](https://redfox.hk/settings/api-keys?source=github) 获取
- **与 Agent-Reach 关系**：RedFox 是 **舆情/热榜/大V 内容层**；daily-run 是 **量化编排 + MSS + 飞书推送** — 代码在 `redfox_client.py` + `redfox_collector.py`，收盘 **复用 snapshot 缓存**，不重复扣费

本地浏览技能（与 cron **并行**，互不冲突）：

```bash
git clone https://github.com/zjk1984/redfox-community ~/redfox-community
ls ~/redfox-community/skills/stock-feed ~/redfox-community/skills/trending-hub
# 试跑（需 REDFOX_API_KEY）
export REDFOX_API_KEY=ak_你的密钥
python3 ~/redfox-community/skills/stock-feed/scripts/stock_feed.py --days 7 --output-format json
python3 ~/redfox-community/skills/trending-hub/scripts/fetch_hotspot.py --source "全平台热点事件"
```

### 与 daily-run 最相关的技能映射

| RedFox Skill | 核心能力 | daily-run 对应 | 状态 |
|--------------|----------|----------------|------|
| **stock-feed** | 17 个 A 股关键词 · XHS/DY/GZH 三平台 · 近 7 天 | `redfox_client.fetch_stock_feed` → `macro_collector.sources.redfox` | ✅ |
| **trending-hub** | 7 平台热榜 · 关键词泛化 | `redfox_client.fetch_trending_hub` + 60s 并行 | ✅ Path B |
| **gzh-astock-top** | 49 公众号官媒/大V · dailyPublish | `fetch_gzh_astock`（morning 查 **上一交易日**） | ✅ |
| **stock-analysis** | 5 大V 蒸馏 · 质量审计 | close `cross_validate_emotion` + `quality_gate` | 🟡 方法论 |
| **investor-distiller** | 七维 DNA 画像 | weekly `experience.jsonl` / skill 审视 | 🟡 方法论 |
| **weibo-hot-search** | 微博热搜榜 | 60s `/v2/weibo` | ✅ 60s 覆盖 |
| **weibo-realtime-search** | 微博实时关键词搜索 | — | ❌ 未集成 |
| **weibo-comment-search** | 微博评论舆情 | — | ❌ 未集成 |

### 双路径策略（免费 vs RedFox API）

| 维度 | Path A 免费（cron 默认） | Path B RedFox API（`REDFOX_API_KEY`） |
|------|--------------------------|--------------------------------------|
| 热榜 | 60s：weibo/zhihu/douyin/baidu/bili/toutiao | trending-hub：7 平台 + 关键词泛化 + 事件去重 |
| A 股散户舆情 | 雪球 `macro_collector._fetch_xueqiu_sentiment` | stock-feed：XHS/DY/GZH 17 词一键 + HTML 报告 |
| 机构/大V 观点 | Exa 收盘深度调研 | gzh-astock-top：官媒/大V 当日文章 + 订阅推送 |
| 质量门禁 | `quality_gate` + 数据审计 Gate | stock-analysis：双层审计 + 合规硬规则 + 来源标注 |
| 成本 | 零 API 费（60s 自托管 / 公开实例） | 按 RedFox 积分扣费（如同步大V文章） |

**Agent 决策**：无 `REDFOX_API_KEY` 时走 Path A，不阻断 cron；有 Key 且 `redfox.enabled=true` 时，早盘/收盘 **补充** Path B，不替换东财/AKShare 行情源。

### 借鉴的设计模式

**stock-feed — 跨平台舆情验证**

| 平台 | 信号特征 | daily-run 借鉴点 |
|------|----------|------------------|
| 小红书 | 散户心得、收藏/点赞比 | 持仓 sector 关键词 → `hot_news.matched` 加权 |
| 抖音 | 盘中速评、分享传播力 | intraday 热点突变检测 |
| 公众号 | 深度复盘、阅读量 | 早盘 macro 段「大V 标题一行」 |

- 每条叙事 **≥2 平台来源** 才写入高置信结论（对标 stock-feed 输出规则）
- 内置 17 词：`A股,A股市场,A股大盘,涨停,涨跌,潜力股,选股,加仓,…` — 可 merge 进 `hot_news.portfolio_keywords`

**trending-hub — 热榜与时间窗**

| 用户意图 | 查询窗口 | daily-run 映射 |
|----------|----------|----------------|
| 最新热榜 | 前一完整小时 | intraday 默认 |
| 今日热榜 | 今日 0:00 → 当前整点 | morning macro |
| 昨日热榜 | T-1 0:00 → T 0:00 | close 对比 / weekly |

- **关键词泛化**：大词（体育/科技/财经）→ 10 个扩展词；精确词不扩展 — 可 enrich `watchlist_manager` sector 别名
- **compact 模式**：stdout 摘要 + `dataFile` 完整 JSON — 大 payload 写 `~/.agent-reach/daily_run/cache/redfox/`

**stock-analysis — 质量与合规铁律**

| 规则 | upstream | daily-run 已有 / 待增强 |
|------|----------|-------------------------|
| 禁止 LLM 编造涨跌停/资金流 | Phase 1 强制 WebSearch/东财 | ✅ `auditor` + 东财 live |
| 关键指标 ≥2 源交叉验证 | 交易所 + 东财/同花顺 | 🟡 收盘 Exa 与东财并列 |
| 信息丰富度 A/B/C 级 | Phase 0 偏见自查 | 可写入 `supervisor_review` prompt |
| 质量审计 >70 准出 | `quality_audit.py` | ✅ `quality_gate.validate_report()` |
| AI 模拟免责声明 | 强制标注 | 飞书卡片 footer |

**gzh-astock-top — 早盘大V 订阅**

- 红狐 **07:00** 更新昨日爆款 → cron morning **08:00** 可安全查询
- `--dual-category`：官媒/机构 vs 个人大V 分表 — 映射 morning 卡「政策线 / 情绪线」
- 订阅模型：`manage_subscriptions.py` + `fetch_subscribed_updates.py` — 减少 API 调用，适合固定关注列表

**investor-distiller — 经验沉淀**

- 七维 DNA → weekly `experience.jsonl` 规则原子化时可对照「交易体系 / 市场判断 / 热点图谱」
- **raw 全文原则**：禁止依赖过度 clean 的 NER — 与 daily-run「数据审计 Gate 不通过则阻断买入」同构

### 与工作流衔接

| 阶段 | 已实现 | 模块 |
|------|--------|------|
| **morning** | 60s + 雪球 + RedFox gzh/stock-feed/trending | `collect_macro_context(workflow=premarket)` |
| **intraday** | quotes + trending-hub 关键词 | `workflow=intraday` |
| **close** | 四卡 + RedFox 交叉验证（**复用 snapshot，不二次请求**） | `attach_redfox_close_markdown` |
| **weekly** | RedFox vs 60s diff + 四卡周汇总 | ✅ `redfox_weekly.py` |

**收盘去重铁律：** `build_snapshot(close)` 已写入 `macro_signals.redfox` → `run_close` 只读缓存做 `cross_validate_emotion`，避免重复扣积分。

### 默认配置（`config/daily_run_settings.json` + user override）

```json
"redfox": {
  "enabled": false,
  "api_key_env": "REDFOX_API_KEY",
  "cache_ttl_seconds": 3600,
  "timeout_seconds": 20,
  "sentiment_boost_per_hit": 1.5,
  "cache_dir": "~/.agent-reach/daily_run/cache/redfox",
  "stock_feed": {
    "enabled": true,
    "days": 7,
    "platforms": ["xhs", "dy", "gzh"],
    "count_per_platform": 50,
    "workflows": ["morning", "close"]
  },
  "trending_hub": {
    "enabled": true,
    "platforms": ["wb", "dy", "zh"],
    "expand_keywords": true,
    "workflows": ["morning", "intraday", "close"]
  },
  "gzh_astock": {
    "enabled": true,
    "dual_category": true,
    "max_accounts_per_category": 5,
    "workflows": ["morning"]
  }
}
```

`.env` / cron：`~/.agent-reach/config.env` 中 `REDFOX_API_KEY=ak_…`；`scripts/daily-run-local-cron.sh` 自动 source。

### 集成 checklist

**已完成（Path A + B 代码）：**

- [x] 60s 多平台热榜 — `hot_news_collector.py`
- [x] `redfox_client.py` / `redfox_collector.py`
- [x] `macro_collector` → `sources.redfox` + MSS boost
- [x] 收盘复用 snapshot + 情绪交叉验证 — `attach_redfox_close_markdown`
- [x] user settings 缺块时 merge repo 默认 — `settings._merge_repo_defaults`
- [x] gzh 早盘查上一交易日 · 上海时区热榜窗口
- [x] Key 存 `~/.agent-reach/config.env`（勿提交 git）

**已完成（Path B 扩展）：**

- [x] weekly RedFox vs 60s 热榜 diff — `build_hot_topic_diff` + 周报「板块·热点」卡
- [x] 本周四卡汇总（主线标签 / 情绪 / 龙虎榜累计）— `summarize_week_market_reviews`
- [x] gzh 订阅文件 — `~/.agent-reach/daily_run/redfox/gzh_subscriptions.json`
- [x] weibo-realtime-search — `fetch_weibo_search`（intraday/close）
- [x] supervisor 反面检验 — `team._build_counter_thesis`（共识「可做」时）
- [x] supervisor 反面检验 LLM — `supervisor_counter_llm.enrich_counter_thesis_llm`（`team.counter_thesis_llm.enabled`）

**待增强：**

- [x] gzh 订阅 CLI 管理命令 — `daily-run redfox gzh list|add|remove`
- [x] stock-analysis 反面检验 enrich supervisor LLM prompt — `supervisor_counter_llm.py`（Batch 12）

**参考文件（upstream）：** `skills/stock-feed/SKILL.md` · `skills/trending-hub/SKILL.md` · `skills/gzh-astock-top/SKILL.md` · `skills/stock-analysis/SKILL.md` · `skills/investor-distiller/SKILL.md`

---
