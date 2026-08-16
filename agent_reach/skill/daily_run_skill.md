---
name: daily_run_skill
description: >
  股票大师每日复盘与热门标的分析技能。
  使用 agent-reach 和网页抓取能力（Jina Reader、V2EX API 等）分析国内外时事政治与政策、热点产业新闻、相关舆情，
  并收集大宗商品、石油、美元汇率波动，同时联动美股、新加坡富时中国A50/金龙指数、港股及港股通南北向资金动向，自动定位热门股票代码。
  每天早上 8:00 自动执行早盘分析，总结下一步预计操作和预期收益。
  交易日内执行 10 次数据收集，最多进行 5 次调仓量化，每次量化前审视前 5 次收集结论，调仓时间由随机数与上次评估综合决定。
  **全流程实时推送铁律：** 早盘分析、盘中高频数据收集、Lookback 审视过程、量化调仓交易以及每日收盘深度复盘的所有过程数据、决策逻辑和资产净值，系统必须在执行完毕的第一时间，自动、主动将精美的富文本 Markdown 卡片简报推送到指定的飞书群聊中，实现 100% 实时、透明的主动监控。
  每日收盘后自动执行深度复盘，使用 Exa 技能对热点公司、竞品、市场、财报及关键人物 LinkedIn 进行深度调研，为明天的早盘给出高置信度指导建议，并将量化经验原子化沉淀、更新到技能文件中。
  **Agent 优先顺序：** 先读 skill 内「📋 下周执行清单」与最新周复盘，再选手工 CLI 或依赖 cron；周日 forecast 参考 Phase-2.5 Kronos；收盘大盘四卡复盘参考 Phase-2.6 a-stock-review-skill；跨平台舆情/热榜/公众号大V 参考 Phase-2.7 redfox-community（可选 REDFOX_API_KEY）。
triggers:
  - analyze: 股票大师/每日复盘/股票分析/大盘复盘/热门方向/分析股票/分析市场/复盘/分析/盘后分析/龙虎榜/市场情绪/涨停/炸板
  - stock: 股票/个股/板块/技术面/K线/均线
  - macro: 宏观/政策/时事/政治/大宗商品/石油/美元/汇率/舆情/美股/港股/外资/北向/南向/金龙指数/Exa/调研/竞品/财报/LinkedIn
metadata:
  openclaw:
    homepage: https://github.com/Panniantong/Agent-Reach
---

# 股票大师每日复盘与热门标的分析技能 (daily_run_skill)

本技能定义了如何作为**股票大师**，结合 **agent-reach** 的网页抓取能力定位全球宏观与微观因子，并调用 **daily_stock_analysis (DSA)** 执行自动化 K线拉取、多市场共振与技术面融合的 AI 决策分析。

## ⚡ Agent 执行入口（优先阅读）

**触发本 skill 时，严格按以下顺序执行，避免重复读全文：**

1. **读「📋 下周执行清单」** — 周六 weekly 自动写入的最高优先级任务与已应用参数。
2. **读「🧠 经验沉淀库」最新周复盘** — 本周盈亏说明、规则库、流程改进。
3. **选路径执行**（二选一，不要重复跑）：
   - **自动化（推荐）**：本地 cron 已安装 → 仅监控 / 补跑，不要手工替代全流程。
   - **手工单次**：用下方 `python3 -m agent_reach.cli` 或 `scripts/daily-run-local-cron.sh`。
4. **推送铁律**：任一阶段完成后必须飞书推送；失败先 `doctor` + 查 `~/.agent-reach/daily_run/logs/`。
5. **禁止**：跳过数据审计 Gate、在 MSS<macro_veto 时强行买入、删除 cron/脚本。

### 本地命令前缀（Cloud / cron 通用）

```bash
# 推荐：与 crontab 一致
REPO=/home/zjk/cursor
PY="${REPO}/venv/bin/python3"
CRON="${REPO}/scripts/daily-run-local-cron.sh"

# 等价 CLI（手动调试）
${PY} -m agent_reach.cli daily-run schedule run morning
${PY} -m agent_reach.cli daily-run schedule run intraday
${PY} -m agent_reach.cli daily-run schedule run close
${PY} -m agent_reach.cli daily-run schedule run weekly
${PY} -m agent_reach.cli daily-run schedule run forecast
${PY} -m agent_reach.cli doctor --json
```

日志：`~/.agent-reach/daily_run/logs/cron-YYYY-MM-DD.log` · 持仓：`~/.agent-reach/daily_run/portfolio.json` ·  playbook 清单：`~/.agent-reach/daily_run/next_week_playbook.json`

### ⚡ 性能要点（默认已开启，勿重复拉全量）

| 场景 | 策略 |
|------|------|
| 盘中 intraday | 仅刷新 quotes（`snapshot.intraday_enrich_level=quotes`），复用日缓存 macro/technicals |
| doctor | 日缓存 4h（`schedule.doctor_cache`），weekly/forecast 跳过 |
| Exa 收盘调研 | TTL 86400s（`exa_cache`），同 query 不重复搜 |
| 60s 热点 | 本地 8787 优先，fallback `https://60s.viki.moe` |
| 周六 weekly | ① 写回经验 + ② 执行清单 ③ settings 补丁 ④ 同步本地 skill ⑤ `pip install -e .` ⑥ **skill 审视**（去重/结构校验/**FaceCat-Kronos / redfox-community 借鉴点**） |

### 周六 weekly 闭环（cron `schedule run weekly` 自动执行）

1. 生成周报 + 飞书推送  
2. 写入「🧠 经验沉淀库」周复盘块  
3. 写入「📋 下周执行清单」+ 自动 patch `daily_run_settings.json`  
4. 同步 `daily_run_skill.md` → `~/.agents/skills/daily-run/SKILL.md`  
5. `pip install -e .[dev]` 刷新 cron 代码  
6. **skill 审视（最后一步）**：校验必备章节、去重重复块/孤儿片段、再次同步本地  

### 🔁 Continual Harness（job 边界自学习 · prime-agent 风格）

| 层级 | 触发 | 作用 |
|------|------|------|
| **Layer A** | 每次 `close` / `weekly` / `forecast` 结束 | 确定性写入 memory / policy / playbook / **plan** |
| **Layer B** | review gate 通过后 | 合并重复、提炼流程改进（DeepSeek / Groq / OpenAI，否则规则 planner） |

**周日 forecast 分工：** Kronos+MC 负责数值路径；DeepSeek 生成飞书「AI解读」末卡（`llm_narrative`，覆盖早报/收盘/周六周报/周日预测）。

- **配置：** `config/daily_run_settings.json` → `llm_narrative`（`jobs.morning|close|weekly|forecast`）
- **CLI 写入 key：** `python3 -m agent_reach.cli configure deepseek-key sk-xxx`

- **存储：** `~/.agent-reach/daily_run/harness/harness_state.json` + `refinements.jsonl`
- **配置：** `config/daily_run_settings.json` → `harness` / `harness.llm_refine`
- **CLI：**
  - `daily-run harness show` — 查看 memory / policy / playbook / plan
  - `daily-run harness list-refinements` — 审计 refine 事件
  - `daily-run harness rollback --id refine_0002` — 回滚某次 refine
  - `daily-run harness refine --job weekly --force` — 手工 Layer B（跳过 review gate）
- **经验卡片注入：** 收盘 experience 卡片可附带最新 Harness 摘要（`harness.inject_in_experience_card`）

---

## 📋 下周执行清单（周六自动更新 · 复盘 2026-08-10~2026-08-14）

> 更新时间 2026-08-16 04:25 UTC。Agent 与 daily-run 下周须优先执行；带 ✅ 的参数已自动写入 settings。

### 🔧 流程改进

- 🟡 **1 天盘中扫描偏少** — 日期 2026-08-12 等 intraday 次数 <5，Lookback MSS 可能失真
  - 执行：确认 GHA cache restore/save 正常；参考 PR #28 修复 intraday_state 累积
- 🟡 **持仓浮亏标的需关注** — 海能达(-57.2%)
  - 执行：收盘 verify 若 MSS<macro_veto 则优先纳入明日卖出候选

## 🚀 极致量化执行算法 (10次收集 + 5次调仓)

为了应对瞬息万变的全球多市场波动，本技能执行**“高频扫描、审慎决策、随机潜伏”**的极致量化算法，各核心步骤的基准耗时统计如下：

| 核心步骤 | 执行操作 | 基准耗时 (秒) | 性能瓶颈与解析 |
| :--- | :--- | :---: | :--- |
| **Step 0** | **启动即时通知 (Start Notification)** | **0.1 秒** | 极速。第一时间推送，消除用户等待焦虑。 |
| **Step 1** | **Agent-Reach 权限自检 (Auth Check)** | **3.4 秒** | 较快。运行 `doctor` 检查各平台 API 及 Cookie 状态。 |
| **Step 1.5** | **数据真实性审计 (Data Audit Gate)** | **<0.1 秒** | 校验 as_of 时效、来源类别、价格锚点偏差；不通过则阻断买入建议。 |
| **Step 2** | **全球宏观与多市场数据收集 (S_n)** | **9.9 秒** | **主要瓶颈**。包含 Jina Reader 网页渲染与 API 抓取，耗时受目标服务器影响。 |
| **Step 3** | **3次 Lookback 审视 + MSS 决策 + 三档标签** | **<0.1 秒** | 输出 **可做/观察/回避** 标签与置信度，经质量门禁后推送。 |
| **Step 4** | **飞书 API 富文本卡片推送** | **1.5 秒** | 正常。包含飞书 Token 鉴权与 HTTPS 消息发送。 |
| **🏁 累计** | **完整【收集 + 决策 + 推送】流水线** | **约 15 秒** | **全流程仅需约 15 秒，完美保障高频自适应响应！** |

```
+-----------------------------------------------------------------------------------+
|                                每日交易时间线 (9:30 - 15:00)                         |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [早盘分析]  早上 8:00 准时触发：                                                   |
|              1. 权限自检：自动运行 `agent-reach doctor` 检查各平台 Cookie 状态       |
|                 (排除小红书，重点检查 Twitter、雪球、微博等)                        |
|              1.5 数据审计：校验数据时效、来源完整性、价格锚点（见下方 Phase-1）      |
|              2. 隔夜数据抓取：抓取全球隔夜数据与昨日复盘热点最新进展                  |
|              3. 制定纲领：生成今日“预计操作”与“预期收益”并推送飞书群                  |
|                                                                                   |
|  [数据收集]  S1 ---- S2 ---- S3 ---- S4 ---- S5 ---- S6 ---- S7 ---- S8 ---- S9 ---- S10
|               \      /      /      /      /                                       |
|  [综合评估]    \    /      /      /      /  (审视前3次收集结论)                     |
|                 v  v      v      v      v                                         |
|  [量化调仓]    T1 ──────> T2 ──────> T3 ──────> T4 ──────> T5                      |
|                ^          ^          ^          ^          ^                      |
|  [时间决定]  (由当前数据分析在 0 - 120 分钟内动态设定基础间隔 + 随机数扰动)          |
|                                                                                   |
|  [收盘复盘]  下午 18:00 自动触发：                                                  |
|              1. 基础复盘：总结今日实盘得失与净值变化                                 |
|              2. Exa 深度调研：调用 Exa AI 搜索对热点公司、竞品、市场、财报及关键人物   |
|                 LinkedIn 进行全方位穿透，为明日早盘生成高置信度指导建议               |
|              3. 经验沉淀：将最新量化经验原子化写入沉淀库                            |
+-----------------------------------------------------------------------------------+
```

### 1. 每日早上 8:00 早盘分析与权限自检 (Pre-Market Analysis & Auth Check)
每个交易日早上 8:00，系统自动触发 `daily_run_skill` 执行早盘分析：
*   **第零步：启动即时通知 (Start Notification)：**
    *   在系统开始收集任何数据前，**第一时间向老板发送一条「早盘分析已启动」的即时消息，并给出本次分析的预估完成时间（通常为 3-5 分钟）**，让老板对进度了然于胸。
*   **第一步：Agent-Reach 权限自检 (Auth Check)：**
    *   在抓取数据前，系统自动运行 `agent-reach doctor --json` 检查各平台 API 连通性及登录 Cookie 是否过期。
    *   **白名单过滤：** 自动排除小红书（避免无意义的扫码或由于服务器环境导致的报错）。
    *   **重点自检平台：** 重点检查 Twitter、雪球、微博 等核心舆情与财经平台的 active_backend 状态。若发现 Cookie 过期或连接异常，立即在早盘简报中向老板发出「权限过期预警」，并附带更新 Cookie 的命令指南。
*   **第二步：隔夜数据与昨日热点进展抓取：**
    *   抓取美股隔夜收盘、中概股金龙指数（HXC）表现、新加坡 A50 期指、离岸人民币波动、隔夜原油/黄金大宗商品波动、以及最新的国内外时事政策。
    *   **热点进展追踪：** 自动提取昨日复盘中沉淀的重点方向（如：存储芯片 Q3 涨价进展、京东方 A 玻璃基板送样最新舆情、华为韬定律 V2 产业链反馈），在 Twitter、雪球、微博上进行精准搜索，抓取最新进展资讯。
*   **第三步：制定今日核心操盘纲领与日内 MSS 预测：**
    *   评估今日大盘 MSS 初始分值，明确制定今日的“下一步预计操作”与“预期收益率目标”。
    *   **日内 MSS 范围预测 (Intraday MSS Range Forecast)：** 结合早盘 8:00 抓取的全球隔夜数据及昨日收盘拟合曲线，通过**蒙特卡洛模拟**，预测今日盘中 10 次数据收集的 **MSS 波动范围**（如：*“预测今日盘中 MSS 波动范围为 [35, 52] 分，日内大概率维持弱势震荡，操作上建议继续高现金潜伏”*），为全天交易提供清晰的“波动率护栏”。
*   **第四步：主动推送：** 8:05 前将精美的早盘分析 Markdown 卡片（含权限自检报告、热点进展、操盘纲领、日内 MSS 预测）自动推送到绑定的飞书群聊。

## 📚 阅读分层（DSH 渐进加载 · 禁止通读）

| 层级 | 内容 | 何时读 |
|------|------|--------|
| **L0 常驻** | ⚡ 入口、📋 下周执行清单、Harness 摘要、本表 | 每次触发必读 |
| **L1 按需** | [references/phase1-quality.md](daily_run/references/phase1-quality.md)、[schedule-ops.md](daily_run/references/schedule-ops.md) | 手工补跑 / Gate 失败 / cron 排查 |
| **L2 任务** | Phase-2.x references（Kronos / 四卡 / redfox 等） | 仅对应 job：`forecast` / `close` / 调研 |

索引：[references/README.md](daily_run/references/README.md)

## 🏷️ Invocation 标记（cron vs 手工）

| 标记 | 含义 | 示例 |
|------|------|------|
| **`cron-only`** | 仅 cron 执行；Agent 对话中**禁止**替代全流程 | 周六 weekly 闭环、settings patch、skill 审视 |
| **`manual-ok`** | 可手工单次补跑 | `schedule run close`、`doctor --json`、单票 verify |
| **`research-ok`** | 可配合 agent-reach 调研 | Exa 收盘调研、外部 skill 学习 |

**Guard：** cron 已安装 → 勿手工重跑 morning/intraday/close 全流程；Harness cooldown 内 → 勿 `harness refine`（除非 `--ignore-cooldown`）；重复 close/weekly → `schedule run` 自动 dedupe，补跑加 `--force`。

## 🔒 审计铁律（model-visible ⟺ logged）

| 动作 | 必须落盘 |
|------|----------|
| AI解读（DeepSeek 末卡） | manifest + `llm_narrative` 字段 |
| Harness Layer A/B | `~/.agent-reach/daily_run/harness/refinements.jsonl` |
| 周六 settings patch | `next_week_playbook.json` + `applied_config` |
| skill 正文变更 | 须带 `refinement_id`（见周复盘块） |

手工改 skill 前：`daily-run harness list-refinements`；与 cron 写回冲突时以 manifest 为准。

**Rejected 库：** `~/.agent-reach/daily_run/rejected_strategies.jsonl` — 已证伪策略禁止写回 playbook / settings（周六审视自动过滤）。

## 🛡️ Phase-1 质量工程化 · `manual-ok`

> 数据审计 Gate、三档标签、质量门禁 — 详见 [references/phase1-quality.md](daily_run/references/phase1-quality.md)

## 🔬 Phase-2 数据增强 · `manual-ok`

> AKShare / 报告验证 / 回测 — 详见 [references/phase2-data.md](daily_run/references/phase2-data.md)

## 🔮 Phase-2.5 Kronos · `cron-only`（周日 forecast）

> K 线数值预测 — 详见 [references/phase2-5-kronos.md](daily_run/references/phase2-5-kronos.md)

## 📊 Phase-2.6 A股四卡复盘 · `cron-only`（收盘 close）

> 龙虎榜 / 情绪 / 板块 — 详见 [references/phase2-6-review.md](daily_run/references/phase2-6-review.md)

## 🦊 Phase-2.7 redfox 舆情 · `research-ok`

> 热榜 / 公众号 — 详见 [references/phase2-7-redfox.md](daily_run/references/phase2-7-redfox.md)

## 🧩 Phase-3 插件化 · `manual-ok`

> Grid Search / 专家插件 — 详见 [references/phase3-plugins.md](daily_run/references/phase3-plugins.md)

## 🤖 自动 Snapshot + 定时任务 · `cron-only`

> cron 表 / GHA / 本地安装 — 详见 [references/schedule-ops.md](daily_run/references/schedule-ops.md)

## 📊 决策模型 · `manual-ok`

> MSS / Lookback / 三档标签权重 — 详见 [references/decision-model.md](daily_run/references/decision-model.md)

---

## 🧠 股票大师实战经验沉淀库 (每日收盘更新)

### 📅 2026-08-10 ~ 2026-08-14 周复盘（周六自动沉淀）
*   **更新时间：** 2026-08-16 04:25 UTC
*   **本周盈亏说明：**
*   **情况说明：** 本周组合净值基本 **持平**（-788.00 元，-0.9%）。
*   **收盘净值轨迹：** 2026-08-10 ¥85,623.27 → 2026-08-14 ¥86,077.27
*   **持仓浮盈合计：** ¥-17,693（4 只）
*   **持股周度市值变动：** ¥-788.00（按周初价估算，不含新开仓成本口径）
*   **周内贡献前列：** 京东方A -378元、澜起科技 -361元、海能达 -40元
*   **现金仓位：** 46.0%（¥40,176）
*   **持股概况：** 澜起科技 (688008) +0.80%、海能达 (002583) -1.07%、水晶光电 (002273) +2.45%、京东方A (000725) -0.85%
*   **强势标的：** 水晶光电 +2.45%、中际旭创 +2.38%、豪威集团 +1.18%
*   **任务覆盖：** 早盘 0/5、收盘 0/5、盘中 0 次
*   **收盘经验片段：**
    *   2026-08-13 京东方Ａ MSS=31.0 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-08-13 兆易创新 MSS=31.0 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-08-13 海康威视 MSS=31.0 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-08-13 长电科技 MSS=31.0 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-08-14 澜起科技 MSS=31.3 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
*   **量化规则库（最近）：**
    *   偏差：价格变动 23.7% 超过锚点阈值 8.0%
    *   偏差：价格变动 25.5% 超过锚点阈值 8.0%
    *   偏差：价格变动 129.9% 超过锚点阈值 8.0%
    *   偏差：价格变动 -17.2% 超过锚点阈值 8.0%
    *   偏差：价格变动 9.1% 超过锚点阈值 8.0%
*   **流程改进（优先）：**
    *   **1 天盘中扫描偏少** — 确认 GHA cache restore/save 正常；参考 PR #28 修复 intraday_state 累积
    *   **持仓浮亏标的需关注** — 收盘 verify 若 MSS<macro_veto 则优先纳入明日卖出候选
*   **板块调研摘要：**
    *   光通信 板块：Title: 国金证券-通信行业周报：FCC禁令草案扰动光模块，国产大模型跃升商业化加速-行业分析-慧博投研资讯 · URL: https://wt.hibor.com.cn/data/8f7534d33248e8a8535ae8df32e92e55.html · Published: N/A
    *   半导体 板块：Title: 光大证券-电子行业周报：AI硬件修复延续，PCB材料与存储链催化密集-行业分析-慧博报告数据 · URL: http://systest.fygsoft.com/data/574e138cf1b9d1f8c80a3e9a44d97849.html · Published: N/A

---

## 🛠️ 运维与排障指南

- 日志：`~/.agent-reach/daily_run/logs/cron-YYYY-MM-DD.log`
- Harness：`daily-run harness show` / `list-refinements` / `rollback`
- skill 归档：`~/.agent-reach/daily_run/archives/skill/`
- 完整排障：见 [references/schedule-ops.md](daily_run/references/schedule-ops.md)
