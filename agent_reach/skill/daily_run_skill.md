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
| **Layer A** | 每次 `close` / `weekly` / `forecast` 结束 | 确定性写入 memory / policy / playbook |
| **Layer B** | review gate 通过后 | 合并重复、提炼流程改进（DeepSeek / Groq / OpenAI，否则规则 planner） |

**周日 forecast 分工：** Kronos+MC 负责数值路径；DeepSeek 仅生成飞书「AI解读」卡片（`week_forecast.llm_narrative`），不改 blend 结果。

- **LLM 配置：** `~/.agent-reach/config.env` 中 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL=https://api.deepseek.com`；模型见 `harness.llm_refine.model`（当前 `deepseek-v4-flash`）
- **CLI 写入 key：** `python3 -m agent_reach.cli configure deepseek-key sk-xxx`

- **存储：** `~/.agent-reach/daily_run/harness/harness_state.json` + `refinements.jsonl`
- **配置：** `config/daily_run_settings.json` → `harness` / `harness.llm_refine`
- **CLI：**
  - `daily-run harness show` — 查看 memory / policy / playbook
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
|  [收盘复盘]  下午 15:30 自动触发：                                                  |
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


## 🛡️ Phase-1 质量工程化（数据审计 + 三档标签 + 质量门禁）

> 借鉴 [zjk1984/china-stock-analyst](https://github.com/zjk1984/china-stock-analyst)（v3.1 Team-First + 插件化 + 质量门禁）的审计/门禁思路，已落地为可执行 Python 流水线。

### 外置配置

所有阈值与权重位于 `config/daily_run_settings.json`（可被 `~/.agent-reach/daily_run_settings.json` 覆盖）：

- `mss_weights` / `lookback_weights` — MSS 与 Lookback 权重
- `thresholds.macro_veto` — 宏观一票否决线（默认 40）
- `thresholds.aggressive_entry` — 进攻阈值（默认 50）
- `quality_gate.required_fields` — 飞书推送前必填字段
- `data_audit.required_source_categories` — 必须覆盖 quote / flow / sentiment

### 数据审计 Gate（Step 1.5）

推送或调仓前，必须构造 **snapshot JSON** 并通过审计：

| 检查项 | 规则 | 失败后果 |
|--------|------|----------|
| `as_of` 时效 | 不超过 24h | 阻断 |
| `sources` | 含 quote + flow + sentiment | 阻断 |
| 价格锚点 | `\|现价-参考价\| / 参考价 ≤ 8%` | 阻断 |
| 结构化复核 | `structured_review_complete=false` | 标签上限「观察」 |

```bash
agent-reach daily-run sample > /tmp/snapshot.json
# 编辑 snapshot 填入真实数据后：
agent-reach daily-run evaluate -i /tmp/snapshot.json --with-doctor
```

### 三档标签（可做 / 观察 / 回避）

| 标签 | 触发条件 |
|------|----------|
| **回避** | MSS < 40（宏观一票否决）；或 VWAP 偏离过大且量比不足 |
| **观察** | MSS 40–50；或缺少完整技术面；或 20 日位置偏高 |
| **可做** | MSS ≥ 50 且技术面完整、审计通过 |

标签与 MSS **并存**：MSS 负责量化择时，标签负责可读性与推送摘要。

### 报告质量门禁

飞书推送前 `quality_gate` 校验必填：

`verdict` · `confidence` · `mss_final` · `reasoning` · `invalidation` · `evidence_chain`

缺字段时自动降级为「观察」；关键字段缺失则 **阻断推送**。

### CLI 一键流水线

```bash
# 1. 评估（输出 JSON + markdown 预览）
agent-reach daily-run evaluate -i config/daily_run_snapshot.example.json

# 2. 推送飞书（审计+门禁通过后）
agent-reach daily-run push -i config/daily_run_snapshot.example.json --title "🌅 早盘分析"

# 3. 仅预览不发送
agent-reach daily-run push -i snapshot.json --dry-run
```

示例 snapshot：`config/daily_run_snapshot.example.json`

### 与 china-stock-analyst 对齐（Phase-1 映射）

| china-stock-analyst 概念 | daily-run 落地 | 模块 |
|--------------------------|----------------|------|
| `run_data_auditor` 前置 | `run_data_audit()` | `auditor.py` |
| 来源类别 quote/flow/sentiment | `data_audit.required_source_categories` | `config/daily_run_settings.json` |
| 价格锚点 `\|现价-参考价\|≤8%` | `thresholds.max_price_deviation_pct` | `auditor.py` |
| 结构化复核未完成 → 标签上限「观察」 | `structured_review_complete=false` | `verdict.py` |
| 双轨评分 40/35/25 | MSS 权重 `mss_weights` + 专家分回填 | `verdict.py` / `plugins/` |
| 三档标签 可做/观察/回避 | `verdict_labels` + `compute_verdict()` | `verdict.py` |
| VWAP 偏离 + 量比降级 | `max_vwap_deviation_pct` + `min_volume_ratio` | `verdict.py` |
| 报告质量门禁 | `quality_gate.required_fields` | `quality_gate.py` |
| 证据链 | snapshot `evidence_chain` 必填 | `pipeline.py` → 飞书 |

**数据源优先级（与 upstream skill 一致）：**

1. **主路径**：Agent-Reach Web / 舆情 / 宏观采集（高覆盖、时效性）
2. **结构化复核**：东方财富行情 API（`quote_fetch.sources` 首选 `eastmoney`）— 缺失时 **不阻断**，仅 `structured_review_complete=false`
3. **兜底**：AKShare 历史 K 线 / 量比 / MA（`daily-run fetch`）

**降级铁律（borrowed）：**

- 缺 VWAP / 量比 / 完整技术面 → 标签上限 **观察**，置信度上限 **中**
- `\|VWAP偏离\|≥4%` 且 `量比<1.0` → **回避**（宏观一票否决 MSS<40 同理）
- 审计失败或 identifier 阻断 → **阻断推送** 或强制降级

**风控表述：** 所有结论须附证据链；输出仅为决策支持，不得表述为自动交易指令。

---

## 🔬 Phase-2 数据增强与验证（AKShare + 报告验证 + 回测）

### AKShare 结构化兜底

当 Jina/DSA 不稳定时，用 AKShare 拉取行情并 enrich snapshot：

```bash
pip install 'agent-reach[daily-run]'   # 或 pip install akshare
agent-reach daily-run fetch --code 688008 -o /tmp/snapshot.json
agent-reach daily-run evaluate -i /tmp/snapshot.json
```

自动填充：`price` · `ma20` · `position_20d` · `volume_ratio` · `sources.quote`

### 历史报告验证（收盘复盘）

对比早盘基线 vs 收盘现状，检验 MSS 预测区间与标签变化：

```bash
agent-reach daily-run verify \
  -b config/daily_run_snapshot.example.json \
  -c /tmp/eod_snapshot.json

# 验证并推送飞书紫色卡片
agent-reach daily-run verify -b morning.json -c eod.json --push
```

输出：价格/MSS/标签变化、预测命中与否、偏差拆解、明日建议。

### MSS 规则回测

验证「MSS≥50 买入 / MSS<40 卖出」历史表现：

```bash
agent-reach daily-run backtest -i config/daily_run_history.example.json
```

示例 history 格式：`[{ "date", "mss", "price", "return" }, ...]`

---

## 🔮 Phase-2.5 Kronos K 线预测借鉴（[FaceCat-Kronos](https://github.com/zjk1984/FaceCat-Kronos)）

> 花卷猫量化团队基于清华 **Kronos** 的 K 线预测 + 回测 GUI。daily-run **不跑 FaceCat UI**，但已接入 `model/kronos.py` 推理链，借鉴其 **预测 → 验证 → 调参** 闭环，用于周日 forecast 与收盘 technical 校准。

### FaceCat-Kronos 仓库结构

| 目录 | 作用 | daily-run 是否使用 |
|------|------|-------------------|
| `model/kronos.py` | 核心：`KronosTokenizer` + `Kronos` + `KronosPredictor` | ✅ 通过 `kronos.repo_path` 导入 |
| `facecat/` | PySide GUI：虚 K 线、回测对比、多周期面板 | ❌ 仅借鉴交互思路 |
| `finetune/` | Qlib 微调 + 滑动窗口 + TopkDropout 组合回测 | ❌ 仅借鉴参数默认值 |
| `examples/` | GPU/CPU 预测示例（含 5 分钟 K 线 CSV） | 参考环境验证 |

**推理流水线（与 FaceCat 一致）：**

```
AKShare 日 K (OHLCV+amount)
  → 窗口 z-score 归一化 + clip(±5)
  → 时间戳特征 (weekday/month 等)
  → Tokenizer 半量化 encode
  → 自回归采样 s1→s2 token（sample_count 条路径取均值）
  → decode → 反归一化 → 虚拟 K 线
```

默认 HuggingFace 模型：`NeoQuasar/Kronos-Tokenizer-base` + `NeoQuasar/Kronos-small`（`max_context=512`）。

### 三套默认参数（勿混用）

| 场景 | lookback | pred | T | top_p | sample_count | 说明 |
|------|----------|------|---|-------|--------------|------|
| **FaceCat GUI** | 50 | 5 | 1.0 | 0.9 | **1**（写死） | 快速可视化 what-if |
| **finetune/config** | 90 | 10 | 0.6 | 0.9 | **5** | 研究/回测推荐 |
| **daily-run** | 90 | 10 | 0.6 | 0.9 | **5** | `kronos_predictor.py` + settings |

注意：FaceCat README 写「T 0–100」是误导；代码里 T 是 **0.4–1.0 浮点温度**。GUI 的 `sample_count=1` 比 finetune 更激进，**Agent 调参以 daily-run settings 为准**。

### 与 daily-run 模块映射

| FaceCat-Kronos 概念 | daily-run 对应 | 状态 |
|---------------------|----------------|------|
| 预测 vs 真值回测 | `verify` + `week_forecast_tracker.review_active_forecast()` | ✅ MSS/价格命中率 |
| OHLCV 日 K 输入 | `kronos_predictor.fetch_ohlcv_history()`（AKShare qfq） | ✅ 已接入 |
| `lookback=90` / `pred=10` | 周日 `week_forecast` + 交易日历 | ✅ `predict_symbol_paths()` |
| 多路径 `sample_count=5` | 推理内部均值；与 MC 路径 `blend` | ✅ `week_forecast_blend_weight=0.35` |
| 实例归一化 + `clip=5` | `KronosPredictor(clip=5)` | ✅ |
| `hold_thresh=5` 最小持仓 | 持股 3 交易日禁卖 | ✅ 风控哲学对齐 |
| 预测界面虚 K 线 | 飞书「个股路径」+ Kronos 方向备注 | 🟡 仅 close/change_pct，非 OHLC 蜡烛图 |
| Qlib TopkDropout 组合回测 | — | ❌ 未集成 |
| 多周期面板（分时/周/月） | — | ❌ daily-run 仅用日 K |
| 完整 OHLC 预测落盘 | `kronos_paths.days` 仅存 **close** | 🟡 推理有 OHLCV，输出裁剪 |
| `confidence_band` | 预测日涨跌幅 min/max | 🟡 **非** sample 方差置信区间 |

### daily-run 两条执行路径

1. **周日 forecast**（`generate_week_forecast`）
   - 对持仓 + 观察池跑 `predict_symbol_paths(code, trading_days)`
   - 写入 `forecast.kronos_paths[code]`，与蒙特卡洛路径 `blend_symbol_days_with_kronos()` 混合
   - 分歧日写入 `kronos_divergence_days`，飞书可标注「Kronos 分歧」

2. **每日收盘 / technical**（`workflows.run_close` → `attach_kronos_to_snapshot`）
   - 主标的 snapshot 附加 `snapshot.kronos`
   - `technical_expert._apply_kronos_adjustment` 最多 ±12 分（`technical_max_score_delta`）
   - 注意：`attach_kronos_to_snapshot` 默认用**日历日** future timestamp；forecast 用**交易所交易日历**（更准确）

### 输出字段（`kronos_paths` / `snapshot.kronos`）

```json
{
  "available": true,
  "direction_nd": "up|down|flat",
  "cum_change_pct": 2.5,
  "confidence_band": [-1.2, 3.1],
  "sample_count": 5,
  "days": {
    "2026-08-11": { "close": 208.5, "change_pct": 0.8, "direction": "up" }
  }
}
```

- **方向判定**：单日 `change_pct` > +0.3% → up，< −0.3% → down，否则 flat
- **收盘验证命中**（`week_forecast_tracker`）：Kronos 方向与实盘一致，或 `|actual − kronos| ≤ max(1.5%, 50%·|kronos|)` 可挽救 MC 未命中
- **校准提示**：`|mean_error_pct| > 1.0%` → 建议微调 `week_forecast.calibration.vol_scale`
- **`confidence_band`**：预测序列日涨跌幅的 min/max，**不是** ensemble 标准差，勿当统计置信区间

### 推荐 settings（完整块）

```json
{
  "kronos": {
    "enabled": false,
    "repo_path": "~/.agent-reach/vendor/FaceCat-Kronos",
    "tokenizer_model": "NeoQuasar/Kronos-Tokenizer-base",
    "predictor_model": "NeoQuasar/Kronos-small",
    "lookback_window": 90,
    "predict_window": 10,
    "max_context": 512,
    "clip": 5.0,
    "inference_T": 0.6,
    "inference_top_p": 0.9,
    "inference_top_k": 0,
    "inference_sample_count": 5,
    "week_forecast_blend_weight": 0.35,
    "technical_max_score_delta": 12,
    "attach_to_snapshot": true,
    "attach_predict_days": 5,
    "device": "auto",
    "local_files_only": false,
    "verbose": false,
    "log_errors": true
  }
}
```

**调参预设：**

- **保守**（贴近现价）：`T=0.4`，`top_p=0.95`，`sample_count=3`
- **探索**（宽幅情景）：`T=1.0`，`top_p=0.9`，`sample_count=5`（非 10；10 会显著拖慢周日 forecast）

### Agent 执行指引

1. **周日 forecast**：持仓 + 观察池各拉 ≥90 根日 K → Kronos 5–10 日路径 → 与 MC 交叉验证；`kronos_divergence_days` 非空时在卡片注明分歧。
2. **收盘 verify**：`review_active_forecast` 对比 Kronos 预测 close vs 实盘，写入 `forecast_review.kronos_review` 与 `optimization_notes`。
3. **technical 专家**：Kronos 5 日累计方向与 MA20 趋势相反 → 标签上限「观察」，不强行「可做」。
4. **CPU / 离线**：无 CUDA 时 `device` 留 `"auto"` 或 `"cpu"`；首次运行下载 HF 权重后设 `local_files_only: true`；模型可缓存到 `~/.cache/huggingface` 或 settings 里的 `tokenizer_model` / `predictor_model` 本地路径。
5. **仓库校验**：必须存在 `{repo_path}/model/kronos.py`（根目录 `model/`，非仅 `facecat/model/`）。

```bash
# 依赖 + 仓库
pip install 'agent-reach[daily-run-kronos]'
git clone --depth 1 https://github.com/zjk1984/FaceCat-Kronos ~/.agent-reach/vendor/FaceCat-Kronos

# 环境冒烟（FaceCat 官方 CPU 示例，可选）
cd ~/.agent-reach/vendor/FaceCat-Kronos/examples && python3 cpu_prediction_example.py

# 启用并跑周日预测
# settings: "kronos": { "enabled": true, "repo_path": "~/.agent-reach/vendor/FaceCat-Kronos" }
python3 -m agent_reach.cli daily-run schedule run forecast
```

### 集成状态（weekly skill 审视时更新）

**已完成：**

- [x] `kronos_predictor.py` — AKShare OHLCV + `KronosPredictor.predict()`
- [x] `week_forecast.kronos_paths` + MC blend（`blend_symbol_days_with_kronos`）
- [x] 收盘 `review_active_forecast` + `_kronos_review_summary` / 校准 notes
- [x] `technical_expert` Kronos 方向评分（≤12 分）
- [x] `close_improvements` 读取 Kronos 偏差建议

**待增强（FaceCat 可继续借鉴）：**

- [ ] `kronos_paths.days` 持久化完整 OHLCV（供止损模拟 / 虚 K 线渲染）
- [ ] `attach_kronos_to_snapshot` 改用交易所交易日历（与 forecast 一致）
- [ ] 基于 `sample_count` 多路径的真实离散度 band（非 min/max 日涨跌）
- [ ] 可选：AKShare 历史 hold-out 回测 helper（对标 FaceCat 回测模式）
- [ ] 飞书个股路径卡片附 Kronos 方向箭头 / 简易虚 K 线摘要

---

## 📊 Phase-2.6 A股每日复盘四卡（[a-stock-review-skill](https://github.com/zjk1984/a-stock-review-skill)）

> 「散户复盘找机会，高手复盘改毛病。」upstream 是纯前端 + Node 零依赖代理，约 5–10 秒拉东财全市场数据，输出 **四张复盘卡片**。daily-run **不嵌入其 HTML UI**，但收盘 15:30 / 周六 weekly 已部分覆盖同类能力；缺项列入 roadmap。

### upstream 架构

```
浏览器 → node server.js (:8080) → push2.eastmoney.com / datacenter.eastmoney.com
       ← CORS 代理 + JSONP 兜底    ← 东财公开行情 API
```

- **零 npm 依赖**：`server.js` 仅 `http` + `fs` + Node 18+ `fetch`
- **存储**：复盘快照存浏览器 `localStorage`（最多 60 日），支持 vs 昨日 / vs 上周对比
- **最佳实践**：15:30 后数据完整；须 `node server.js` 启动（直接开 HTML 可能 CORS 失败）

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

**每日 15:30 `daily-run close`（已有）：**

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

**待增强：**

- [ ] gzh 订阅 CLI 管理命令（对标 upstream `manage_subscriptions.py`）
- [ ] stock-analysis 反面检验 enrich supervisor prompt（非仅 markdown 一行）

**参考文件（upstream）：** `skills/stock-feed/SKILL.md` · `skills/trending-hub/SKILL.md` · `skills/gzh-astock-top/SKILL.md` · `skills/stock-analysis/SKILL.md` · `skills/investor-distiller/SKILL.md`

---

## 🧩 Phase-3 插件化专家 + Grid Search 优化（[zjk1984/china-stock-analyst](https://github.com/zjk1984/china-stock-analyst)）

> upstream skill 采用 **Team-First 默认并行** + **Supervisor 质量门控** + **ExpertPlugin 插件化**。daily-run 已将核心编排 Python 化，cron 工作流可直接调用，无需 Claude Agent 文件。

### Team-First 固定链路

```
run_data_audit → collect/enrich snapshot
  → 8 experts (parallel)
  → supervisor_review → fuse_verdict_with_team
  → quality_gate → Feishu push
```

| 步骤 | china-stock-analyst | daily-run |
|------|---------------------|-----------|
| 数据审计 | `run_data_auditor` | `auditor.run_data_audit()` |
| 采集 | `collect_data` + Web/东财/AKShare | `build-snapshot` / `macro_collector` / `quote_fetch` |
| 8 专家 | `team_router` + `agents/*.md` | `team.run_team_first()` + `plugins/*_expert.py` |
| Supervisor | `supervisor_review` | `team.supervisor_review()` |
| 标签融合 | 双轨评分 + 冲突仲裁 | `fuse_verdict_with_team()` |
| 报告门禁 | `report_quality_gate.py` | `quality_gate.validate_report()` |
| 渲染 | `generate_report.py` | `report_push.py` / 飞书卡片 |

### 执行模式（lite vs full）

| 模式 | 触发场景 | 专家子集 |
|------|----------|----------|
| `lite_parallel` | 单标的轻量分析 | 基本面 + 技术 + 量化 + 风控 + identifier |
| `full_parallel` | 多标的对比 / 验证复盘 / 股票池 / 高意图串联 | **全部 8 位** |

upstream 触发词（对比、验证、复盘、冲突、股票池、筛选、审计…）→ daily-run 对应：`morning` / `close` / `verify` / `weekly` 工作流。配置项 `team.mode` 默认 `full_parallel`。

### 8 专家并行

| 插件名 | 角色 | upstream Agent | 主要输入 |
|--------|------|----------------|----------|
| `fundamental` | 基本面大师 | `stock-fundamental-expert` | 财报口径 / 估值 |
| `technical` | 技术分析派 | `stock-technical-expert` | price / ma20 / Kronos |
| `quant` | 量化模型师 | `stock-quant-flow-expert` | 资金流 / 量价 |
| `risk` | 风险控制官 | `stock-risk-expert` | 波动 / 止损 / 仓位 |
| `macro` | 宏观策略师 | `stock-macro-expert` | fx / global / 政策 |
| `industry` | 行业研究家 | `stock-industry-researcher` | 景气 / 竞争格局 |
| `sentiment` | 消息面猎手 | `stock-event-hunter` | 公告 / 舆情 / 60s 热点 |
| `identifier` | 专家鉴别 Agent | `stock-identity-auditor` | 代码-名称-价格锚点一致性 |

```bash
# 早报：8 专家 → Supervisor → 审计 → 飞书（需 team.enabled=true）
python3 -m agent_reach.cli daily-run morning -i snapshot.json --save-baseline

# 收盘：Team + 基线 verify + 组合 P&L
python3 -m agent_reach.cli daily-run close -i eod_snapshot.json

python3 -m agent_reach.cli daily-run plugins list
python3 -m agent_reach.cli daily-run plugins run -i snapshot.json --names macro,technical,risk
```

**Supervisor 冲突仲裁（已落地）：**

- 技术面 ≥ 进攻线 且 风控 < 否决线+5 → 记录冲突，倾向 **观察**
- 宏观 vs 舆情分差 > 20 → 记录分歧
- `identifier` 失败 → `identifier_blocked=true`，标签上限 **观察**，阻断买入

共识分 = 8 专家均分；映射：`≥aggressive_entry` → 可做，`≥macro_veto` → 观察，否则回避。再与 MSS `compute_verdict()` 取 **更保守** 标签（`fuse_verdict_with_team`）。

### 配置开关（`team` 块）

```json
{
  "team": {
    "enabled": true,
    "parallel": true,
    "supervisor": true,
    "mode": "full_parallel",
    "experts": ["fundamental", "technical", "quant", "risk", "macro", "industry", "sentiment", "identifier"],
    "morning_team_first": true,
    "close_team_first": true,
    "morning_experts": true,
    "close_experts": true,
    "mss_experts": true
  }
}
```

- `team.enabled=false` 时仍可用 `mss_experts` 跑 technical/quant/risk 打分（不渲染 8 专家卡片）
- `morning_experts` / `close_experts` 控制各工作流是否跑全专家 + 飞书专家面板
- 用户覆盖：`~/.agent-reach/daily_run_settings.json`

### 插件系统对比

| upstream | daily-run |
|----------|-----------|
| `ExpertPlugin` / `FilterPlugin` / `TransformPlugin` | `ExpertPlugin`（8 内置） |
| `plugins/expert/technical_indicators_plugin` | 逻辑并入 `technical_expert` |
| `plugins/expert/fund_flow_plugin` | 逻辑并入 `quant_expert` |
| 动态 `plugin_loader` | `plugins/loader.py` + `ThreadPoolExecutor` |

插件输出：`expert_results` · `expert_scores` → 回填 `mss_breakdown` → `evaluate` / `push` 流水线。

### Grid Search 参数优化

```bash
agent-reach daily-run optimize -i config/daily_run_history.example.json
agent-reach daily-run optimize -i config/daily_run_history_factors.example.json --objective sharpe_proxy
agent-reach daily-run optimize -i history.json --save --push
```

优化维度：
- `macro_veto` × `aggressive_entry` 阈值网格
- 若 history 含 `fx/flow/global/sentiment` 字段，同时搜索 `mss_weights`

`--save` 写入 `~/.agent-reach/daily_run_settings.json`

upstream 还包含 `StrategyOptimizer` / `BacktestAttributor`（夏普寻优 + 盈亏因子归因）；daily-run 当前以 `optimize` + `backtest` CLI 覆盖 MSS 阈值与规则回测，**归因报告**尚未 1:1 移植。

### 集成状态（weekly skill 审视时更新）

**已完成：**

- [x] `team.py` — 8 专家并行 + `supervisor_review` + 冲突检测
- [x] `plugins/` — 8 内置 ExpertPlugin，异常降级不中断流水线
- [x] `fuse_verdict_with_team()` — MSS 标签与 Supervisor 共识取保守合并
- [x] `pipeline.py` — audit → experts → verdict → quality_gate 串联
- [x] `morning` / `close` 工作流接入 Team-First（配置开关）
- [x] 飞书专家共识卡片 `render_team_markdown()`

**待增强（可继续借鉴 upstream）：**

- [ ] `FilterPlugin` / `TransformPlugin` 独立扩展点
- [ ] 东财意图路由 `news-search` / `query` / `stock-screen`（upstream `team_router.route_eastmoney_intent`）
- [ ] Markdown 报告后置门禁 `report_quality_gate.py`（候选股表格 vs 推荐段交叉校验）
- [ ] `BacktestAttributor` 盈亏因子分解写入收盘复盘
- [ ] 高意图串联缓存 / 重复请求限流（upstream `intent` 块）
- [ ] 默认 `team.enabled=true` + `morning_team_first`（当前 repo 默认 false，需用户显式开启）

**参考文件（upstream）：** `SKILL.md` · `scripts/team_router.py` · `docs/agent-teams-blueprint.md` · `config/settings.json`

### 一键工作流（推荐）

**早盘（专家 → 审计 → 推送）：**
```bash
agent-reach daily-run morning -i snapshot.json --save-baseline
# 可选 AKShare 补全：--code 688008 --fetch
# 预览：--dry-run
```

**收盘（对比早盘基线 → 验证推送）：**
```bash
agent-reach daily-run close -i eod_snapshot.json
# 自动读取 ~/.agent-reach/daily_run/last_morning.json
# 或指定：-b morning.json
```

**盘中（S1-S10 扫描 + T1-T5 调仓 · Lookback MSS）：**
```bash
# 记录一次数据收集 S_n 并推送飞书
agent-reach daily-run intraday -i snapshot.json --scan

# 扫描 + 调仓评估（Lookback 加权 MSS → 买/卖/观望）
agent-reach daily-run intraday -i snapshot.json --scan --trade

# 仅调仓评估（需已有扫描记录）
agent-reach daily-run intraday -i snapshot.json --trade

# 查看/重置今日状态
agent-reach daily-run intraday --status
agent-reach daily-run intraday --reset

# 预览不推送
agent-reach daily-run intraday -i snapshot.json --scan --dry-run
```

Lookback 权重（默认 50%/30%/20%）来自 `config/daily_run_settings.json` 的 `lookback_weights`。
状态持久化：`~/.agent-reach/daily_run/intraday_state.json`（按日自动重置）。

---

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
| 15:30 | 收盘复盘（Team + 曲线 + Exa + 验证 + 预测校准） |
| **周六 09:00** | **周报**：盈亏、持股、观察池、热门板块 → 飞书；**闭环** 写回 skill + settings + 本地同步 + skill 审视 |
| **周日 09:00** | **下周预测**：MSS/标的日走势、新闻热点 → 飞书 + `forecasts/` |

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

每个交易日下午 15:30，系统自动触发收盘深度复盘，并调用 **Exa AI 搜索引擎** 执行全方位穿透式调研：
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


## 📊 股票大师多市场共振与技术面量化决策模型 (巴菲特价值选股 × 量化择时融合版)

本模型将**巴菲特的“安全边际与护城河”价值选股法则**与**专业量化交易员的“多市场共振与技术面”择时算法**深度融合，作为每日买卖操作的最高准则：

### 1. 第一道关卡：巴菲特价值选股过滤器 (Moat & Safety Margin Filter)
任何标的在进入盘中量化择时前，必须通过巴菲特价值选股过滤器的硬性筛选，**不满足以下定性与定量指标的标的，系统直接一票否决，禁止买入**：
*   **企业护城河 (Moat)：** 必须具备极高的技术壁垒或行业垄断地位。毛利率必须 **>35%**（如澜起科技互连芯片毛利率高达 71.5%），且核心技术团队（在 LinkedIn 穿透中）必须保持高度稳定。
*   **绝对安全边际 (Margin of Safety)：** 
    *   **定量硬约束：** 动态 **PEG（市盈率相对盈利增长比率）必须 < 1.2**（如兆易创新 Q1 净利暴增 523% 对应 PEG 仅为 0.15），且 **ROE（净资产收益率）> 15%**，确保不是无业绩支撑的纯概念炒作。
    *   **定性硬约束：** 核心管理层无丑闻、无大股东非正常大额减持预案。

### 2. 第二道关卡：量化交易员择时决策矩阵 (MSS & Technical Resonance)
通过巴菲特过滤器筛选后的顶级企业，系统将启动多市场共振与技术面择时算法，执行最优价格猎杀：

| 全球共振因子 (美股/港股/资金) | 宏观因子 (美元/大宗) | 技术面均线 (MA5/MA20) | 20日价格位置 | 操盘策略 | 典型案例 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **金龙指数/A50大涨** + **南北向资金大幅流入** | 美元走弱 / 人民币升值 | **强烈多头** (收盘>MA20 且 MA5>MA20) | **40% - 60%** (合理区间) | **强烈买入 / 重仓布局** | `688008` 澜起科技 (DDR5高景气) |
| **美股科技股(费半)大涨** + **外资(北向)流入** | 产业政策利好 | **多头趋势** (收盘>MA20) | **50% - 60%** (中位) | **防守型买入 / 顺周期配置** | 兆易创新 (存储芯片) |
| **美股大跌** + **外资(北向)大幅净流出** | 美元指数走强 | **强烈多头** (收盘>MA20 且 MA5>MA20) | **>70%** (偏高) | **等回踩 MA5/MA20，不追高** | `000725`京东方A (玻璃基板热点) |
| **中概股暴跌** + **南北向资金全线流出** | 全球流动性收紧 | **震荡/破位** (收盘<MA20) | **<40%** (偏低) | **严格风控，暂时观望** | `688256` 寒武纪 (算力回调) |

### 3. 极致风控与交易摩擦控制 (Anti-Churning & Slippage Control)
*   **滑点与摩擦惩罚 (Slippage Penalty)：** 引入交易摩擦惩罚函数。如果 Final_MSS 算出的预期收益率不能覆盖双边交易成本（0.15%）与预估滑点（0.1%），系统强制取消交易，以对抗频繁交易带来的损耗。
*   **持股生命周期硬约束 (Holding Lifecycle)：** 极度厌恶频繁换手。个股买入后，除触发硬性止损（跌破 MA20 且亏损 > -4%）或宏观极速避险（MSS < 40分）外，**3 个交易日内禁止执行任何主动卖出操作**，以静制动，对抗日内噪音。

---

## 🧠 股票大师实战经验沉淀库 (每日收盘更新)

### 📅 ### 📅 ### 📅 ### 📅 2026-08-10 ~ 2026-08-14 周复盘（周六自动沉淀）
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

ine`
- **CLI：**
  - `daily-run harness show` — 查看 memory / policy / playbook
  - `daily-run harness list-refinements` — 审计 refine 事件
  - `daily-run harness rollback --id refine_0002` — 回滚某次 refine
  - `daily-run harness refine --job weekly --force` — 手工 Layer B（跳过 review gate）
- **经验卡片注入：** 收盘 experience 卡片可附带最新 Harness 摘要（`harness.inject_in_experience_card`）

---
