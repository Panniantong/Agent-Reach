## 🤖 自动 Snapshot + 定时任务

### 持仓配置 → 自动 Snapshot

复制并编辑持仓文件（或使用示例）：

```bash
cp config/daily_run_portfolio.example.json ~/.agent-reach/daily_run/portfolio.json
agent-reach daily-run build-snapshot --save
# 预览：agent-reach daily-run build-snapshot
# 跳过行情拉取：--no-enrich
```

自动填充：主标的 `price/ma20`、持仓/观察池现价、sources.quote、portfolio 块。

数据源优先级：**雪球 Cookie** → AKShare 兜底。

### 60s 热点新闻（自建 API，无需 Docker）

daily-run 会从 [60s API](https://github.com/vikiboss/60s) 拉取微博/知乎/IT 新闻等平台热搜，以及「每天 60 秒读懂世界」要闻，并匹配持仓关键词写入宏观摘要。

**依赖：** Node.js 22.6+、git、npm

```bash
# 一键部署（Node.js 本机进程，默认端口 8787）
bash scripts/60s-local-setup.sh
# 或
agent-reach daily-run hot-news install

# 状态 / 停止
agent-reach daily-run hot-news status
agent-reach daily-run hot-news stop
```

可选 Docker：`agent-reach daily-run hot-news install --mode docker`

`daily-run-local-setup.sh` 已包含 60s native 部署。无 Node.js 时自动 fallback 到 `https://60s.viki.moe`。

配置：`config/daily_run_settings.json` → `hot_news`（用户覆盖：`~/.agent-reach/daily_run_settings.json`）。Skill 参考：[references/daily_run_hot_news.md](references/daily_run_hot_news.md)。

### Cron 定时（北京时间 Asia/Shanghai）

```bash
# 查看推荐 crontab（本地 Mac/Linux，已含 CRON_TZ=Asia/Shanghai）
agent-reach daily-run schedule print

# 安装到当前用户 crontab
agent-reach daily-run schedule install

# 立即执行（等同 cron 触发）
agent-reach daily-run schedule run morning
agent-reach daily-run schedule run intraday
agent-reach daily-run schedule run close
agent-reach daily-run schedule run weekly
agent-reach daily-run schedule run forecast
```

默认时间表（**北京时间**）：
| 时间 | 任务 |
|------|------|
| 07:00 | 盘前 S1 扫描 + 飞书（smart 模式推送） |
| 08:00 | 早盘全量分析 + S2 + 飞书 + 保存基线 |
| 09:30–15:00 **11 次**扫描 | 盘中 S3–S12 + 条件调仓 T_n（smart 推送：S1/S2/S12 或调仓时） |
| 18:00 | 收盘复盘（Team + 曲线 + Exa + 验证 + 预测校准） |
| **周六 08:30** | **周报**：盈亏、持股、观察池、热门板块 → 飞书；**闭环** 写回 skill + settings + 本地同步 + skill 审视 |
| **周日 08:30** | **下周预测**：MSS/标的日走势、新闻热点 → 飞书 + `forecasts/` |

**周六 skill 机械门禁**（`weekly_report.skill_gates`）：写回后校验必备章节、行数上限、playbook/experience 标记与 snapshot 块尺寸；未通过则**阻断周报飞书推送**并单独发红色告警卡。配置见 `config/daily_run_settings.json`。

**Harness 计划闭环**：周六 refine 写入 `plan`（status=open）；**周一早盘**自动标记 done；收盘经验卡注入 harness XML。

**Skill 外链片段**（`weekly_report.skill_external`）：playbook / experience 写入 `~/.agent-reach/daily_run/skill/*.md`；canonical skill 仅保留 stub（<150 行），Agent L0 读外链而非 skill 正文。

定时任务默认 **doctor 日缓存**、**macro/technicals 日缓存**（intraday 仅刷新 quotes）、**Exa TTL 缓存**、**A 股交易日历跳过休市**。

**盘中飞书推送策略**（`schedule.intraday_push_mode`）：
- `smart`（默认）：S1、S2、S12 或发生调仓时推送
- `trade_only`：仅调仓时推送
- `all`：每次扫描都推送

**收盘预测校准**：每个交易日收盘自动对比 `forecasts/{week_start}.json` 中当日预测 vs 实盘，更新 `calibration.json` 并写入经验库 `forecast_review` 字段。

### GitHub Actions（无 iOS / 无 crontab 时推荐）

仓库已含 `.github/workflows/daily-run-schedule.yml`，在 GitHub 云端按 **北京时间（Asia/Shanghai）** 交易日自动跑 Snapshot + MSS + 飞书推送。Cron 使用 `timezone: Asia/Shanghai`，无需手动换算 UTC。

**一次性配置（GitHub 仓库 Settings → Secrets → Actions）：**

| Secret | 内容 |
|--------|------|
| `AGENT_REACH_CONFIG_YAML` | 本地 `~/.agent-reach/config.yaml` 全文（飞书、雪球 Cookie、Twitter 等） |
| `AGENT_REACH_PORTFOLIO_JSON` | （可选）`~/.agent-reach/daily_run/portfolio.json` 全文 |

**手动试跑：** Actions → `daily-run schedule` → Run workflow → 选 `morning` / `intraday` / `close` / `weekly` / `forecast`。

**说明：** 盘中状态（S1–S12、早盘基线、weekly_digest、forecasts）通过 Actions Cache **按上海日期**持久化（同一交易日所有 run 共享 key）；GitHub cron 可能延迟数分钟，属正常现象。所有触发时间均为 **北京时间**。

### Phase 5 — Exa / Channel / 经验沉淀

```bash
# 收盘自动 Exa 调研（需 mcporter + Exa MCP）
agent-reach daily-run close -i eod_snapshot.json

# 经验库
cat ~/.agent-reach/daily_run/experience/experience.jsonl
cat ~/.agent-reach/daily_run/experience/rules_summary.json

# 休市配置（可选）
cp config/daily_run_holidays.example.json ~/.agent-reach/daily_run/holidays.json
```

- **Exa 自动调用**：收盘 `run_exa_research()` → 飞书卡片展示摘要与链接
- **Channel 专家**：macro/sentiment 默认雪球 + Exa 增强评分
- **经验 writeback**：收盘结论写入 `experience.jsonl` + `rules_summary.json`

---

系统在交易日内（9:15 - 15:00）均匀或按盘口波动密集度执行 **10 次全球市场与舆情数据收集**。

### 3. 每次量化调仓前审视前 3 次收集结论 (加权 Lookback 机制)
每日最多进行 **5 次调仓量化机会 (T1 - T5)**。在执行任何买卖操作前，系统必须审视前 3 次收集结论，计算 MSS 评分。
**加权 Lookback 算法：** 
为了使决策既具备大局观，又对最新异动保持极高的敏感度，系统对前 3 次收集到的数据结论（由近到远）执行**非等权加权计算**：
*   **最近一次数据 (S_n，时效 100%)：** 权重占比 **50%**（决定性影响，捕捉即时拐点）。
*   **次近一次数据 (S_n-1，时效中等)：** 权重占比 **30%**（趋势确认）。
*   **最远一次数据 (S_n-2，时效偏低)：** 权重占比 **20%**（基线参考）。
$$\text{Final\_MSS} = 0.5 \cdot \text{MSS}(S_n) + 0.3 \cdot \text{MSS}(S_{n-1}) + 0.2 \cdot \text{MSS}(S_{n-2})$$
只有当加权后的 $\text{Final\_MSS}$ 发生趋势性转向，或个股技术指标触发硬性买卖阈值时，才执行调仓。

### 4. 调仓时间动态自适应调整 (0 - 120 分钟实时重算)
系统根据当前收集到的全球多市场数据分析，在 0 - 120 分钟内动态设定基础间隔。
**极致动态重算机制：** 调仓时间并非固化计算，而是**在每日 10 次高频数据收集（S1 - S10）的每一次执行完毕后，系统都会根据最新抓取的多市场波动率和资金流速，重新研判并实时修正下一次调仓（T_n）的精确触发时间**。这确保了在市场突发异动时，系统能瞬间将调仓时间压缩至 0-30 分钟内，实现秒级响应；而在市场横盘时，自动拉长间隔，实现完美潜伏。
在**极速调仓模式**下，**随机潜伏延迟强制设定为 0 分钟**。

### 5. 自动化飞书主动推送与量化决策分析披露
每次交易执行完毕后，量化引擎将自动调用飞书开放平台 API，向绑定的飞书群聊推送精美的富文本 Markdown 卡片简报。
推送内容不仅包含交易明细，还**必须完整披露本次调仓前量化引擎的深度决策分析过程（包括前 3 次数据审视结论、MSS 评分拆解、宏观与技术面共振研判逻辑）**，让老板对每一次买卖背后的“算法大脑”了然于胸。

### 6. 每日收盘后深度复盘与 Exa 智能调研 (Post-Market Review & Exa Research)

> 全市场「四卡复盘」（情绪 / 板块主线 / 龙虎榜 / 历史对比）设计见 **Phase-2.6 [a-stock-review-skill](https://github.com/zjk1984/a-stock-review-skill)**；跨平台舆情/热榜/公众号大V 见 **Phase-2.7 [redfox-community](https://github.com/zjk1984/redfox-community)**；本节侧重 **持仓组合 + MSS + Exa 深度**。

每个交易日 **18:00**，系统自动触发收盘深度复盘，并调用 **Exa AI 搜索引擎** 执行全方位穿透式调研：
*   **Exa 深度调研指令：**
    ```bash
    # 1. 热点公司与最新财报深度调研 (分析营收、净利、毛利率及管理层展望)
    mcporter call 'exa.web_search_exa(query: "兆易创新 603986 latest financial report earnings margin Q2 2026", numResults: 5)'
    
    # 2. 核心竞品与行业格局分析 (分析市场份额、技术路线及价格战情况)
    mcporter call 'exa.web_search_exa(query: "DDR5 memory interface chip Rambus Montage semiconductor market share competitors", numResults: 5)'
    
    # 3. 行业市场研究 (分析供应链瓶颈、产能周期及上下游供需)
    mcporter call 'exa.web_search_exa(query: "TGV glass substrate advanced packaging supply chain bottleneck Corning BOE 2026", numResults: 5)'
    
    # 4. 公司关键人物 LinkedIn 穿透 (分析高管变动、核心技术团队背景及履历)
    mcporter call 'exa.web_search_exa(query: "Montage Technology 澜起科技 key executives founder profile LinkedIn", numResults: 3)'
    ```
*   **MSS 曲线拟态分析与明日预测 (MSS Curve Fitting & Prediction)：**
    *   **曲线拟态分析：** 系统自动提取今日 10 次高频数据收集（S1 - S10）计算出的真实 MSS 评分，通过**最小二乘法进行多项式曲线拟合（Curve Fitting）**，绘制出今日宏观情绪的日内演变曲线，分析其一阶导数（斜率）和二阶导数（加速度），研判尾盘情绪是加速杀跌、减速筑底还是反弹拉升。
    *   **预测与实盘对比说明 (Prediction vs. Actual Comparison)：** 
        1.  将今日 10 次数据收集的**真实 MSS 值**与今日早上 8:00 早报中预测的 **MSS 波动范围**进行重合度对比。
        2.  **深度剖析偏差原因：** 详细拆解并说明导致预测偏差的盘中突发变量（如：*“今日真实 MSS 触及 34 分，跌破早报预测下沿 38 分，主因是 13:30 外资砸盘流速超预期，且离岸人民币贬值突破 7.2910 阻力位，导致流动性超预期收紧”*），实现算法模型的每日迭代与自我修正。
        3.  **明日 MSS 范围预测：** 结合尾盘拟合曲线的切线斜率、美股期指夜盘走势、以及隔夜政策预期，通过**蒙特卡洛模拟**进行 1000 次路径演推，预估明日早盘 8:00 的 MSS 初始分值范围（如：*“今日尾盘 MSS 呈现减速筑底态势（斜率由负转正），预估明日早盘 MSS 初始分值范围为 [45, 58] 分”*），为明天的操盘策略提供极具前瞻性的量化支撑。
*   **生成明日早盘指导建议：**
    *   将 Exa 调研获取的**财报硬数据、竞品核心参数、行业供需拐点、高管变动舆情**进行交叉验证。
    *   为明天的 8:00 早盘分析提供高置信度、可落地的核心指导建议（如：*“澜起科技核心竞品 Rambus 最新财报超预期，验证 DDR5 强劲需求，明日早盘建议维持高配”*）。
