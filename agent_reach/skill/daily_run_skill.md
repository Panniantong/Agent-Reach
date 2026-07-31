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
  **Agent 优先顺序：** 先读 skill 内「📋 下周执行清单」与最新周复盘，再选手工 CLI 或依赖 cron；周日 forecast 可参考 Phase-2.5 FaceCat-Kronos K 线预测借鉴。
triggers:
  - analyze: 股票大师/每日复盘/股票分析/大盘复盘/热门方向/分析股票/分析市场/复盘/分析
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
| 周六 weekly | ① 写回经验 + ② 执行清单 ③ settings 补丁 ④ 同步本地 skill ⑤ `pip install -e .` ⑥ **skill 审视**（去重/结构校验/**FaceCat-Kronos 借鉴点**） |

### 周六 weekly 闭环（cron `schedule run weekly` 自动执行）

1. 生成周报 + 飞书推送  
2. 写入「🧠 经验沉淀库」周复盘块  
3. 写入「📋 下周执行清单」+ 自动 patch `daily_run_settings.json`  
4. 同步 `daily_run_skill.md` → `~/.agents/skills/daily-run/SKILL.md`  
5. `pip install -e .[dev]` 刷新 cron 代码  
6. **skill 审视（最后一步）**：校验必备章节、去重重复块/孤儿片段、再次同步本地  

---

## 📋 下周执行清单（周六自动更新 · 复盘 2026-07-27~2026-07-31）

> 更新时间 2026-07-29 13:56 UTC。Agent 与 daily-run 下周须优先执行；带 ✅ 的参数已自动写入 settings。

### 🔧 流程改进

- 🔴 **缺失 3 天早盘任务** — 日期：2026-07-27, 2026-07-30, 2026-07-31；无 morning manifest 会导致收盘 verify 缺基线
  - 执行：检查 GHA cron 0 8 * * 1-5 与 Fork 是否 Enable scheduled workflows
- 🔴 **缺失 3 天收盘复盘** — 日期：2026-07-27, 2026-07-30, 2026-07-31；经验沉淀与观察池 adjust 会中断
  - 执行：检查 GHA cron 30 15 * * 1-5；手动补跑 daily-run schedule run close
- 🟡 **1 天盘中扫描偏少** — 日期 2026-07-28 等 intraday 次数 <5，Lookback MSS 可能失真
  - 执行：确认 GHA cache restore/save 正常；参考 PR #28 修复 intraday_state 累积
- 🟡 **持仓浮亏标的需关注** — 海能达(-58.2%)
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

> 借鉴 [china-stock-analyst](https://github.com/wjt0321/china-stock-analyst) 的审计/门禁思路，已落地为可执行 Python 流水线。

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

> 花卷猫量化团队基于清华 **Kronos** 开源框架的 K 线预测 + 回测 GUI。daily-run 不直接依赖其 UI，但借鉴其**预测—验证—调参**闭环，增强周日预测与收盘校准。

### 核心能力摘要

| FaceCat-Kronos | 说明 |
|----------------|------|
| **Kronos 模型** | Transformer + BSQuantizer，对 OHLCV+amount 做多步自回归预测，输出「虚拟 K 线」 |
| **预测 / 回测双模式** | 同一界面切换：虚线 K 线 vs 历史真值，直观量化预测偏差 |
| **采样参数** | `T`（温度）、`top_p`（核采样）、`sample_count` 控制路径发散 vs 稳健 |
| **多周期面板** | 分时 / 日 / 周 / 月 K 线联动，适配不同 holding 周期 |
| **Qlib 微调回测** | 滑动窗口 `lookback + predict_window`，TopkDropout 组合 + 最小持仓 `hold_thresh` |

默认模型（HuggingFace）：`NeoQuasar/Kronos-Tokenizer-base` + `NeoQuasar/Kronos-small`（`max_context=512`）。

### 与 daily-run 模块映射（已借鉴 / 待落地）

| FaceCat-Kronos 概念 | daily-run 对应 | 状态 |
|---------------------|----------------|------|
| 预测 vs 真值回测 | `daily-run verify` + `week_forecast_tracker.review_active_forecast()` | ✅ 已有 MSS/价格命中率 |
| 多路径采样 `sample_count≥5` | `mss_forecast` 蒙特卡洛 + `week_forecast.calibration` | 🟡 可增 Kronos 收盘价置信带 |
| `lookback=90` / `pred=10` 滑动窗 | 周日 `week_forecast` 5 日路径 | 🟡 待接 Kronos OHLCV 输入 |
| 实例归一化 + `clip=5` | `data_audit` 价格锚点 8% + AKShare enrich | ✅ 思路一致 |
| `hold_thresh=5` 最小持仓 | 持股生命周期 3 交易日禁卖 | ✅ 已对齐风控哲学 |
| 时间特征 weekday/month | intraday S1–S12 时段权重 | 🟡 可写入 `mss_weights` 时段因子 |
| Qlib `open_cost=0.001` | 滑点摩擦 0.15%+0.1% 惩罚 | ✅ 已覆盖 |
| 预测界面虚 K 线 | 飞书「个股路径」卡片 | 🟡 可选附 Kronos 方向箭头 |

### 推荐推理参数（finetune/config 默认值，供 Agent 调参参考）

```json
{
  "kronos": {
    "lookback_window": 90,
    "predict_window": 10,
    "max_context": 512,
    "inference_T": 0.6,
    "inference_top_p": 0.9,
    "inference_sample_count": 5,
    "feature_list": ["open", "high", "low", "close", "vol", "amt"],
    "clip": 5.0
  }
}
```

- **保守**（贴近现价）：`T=0.4`，`top_p=0.95`，`sample_count=3`
- **探索**（宽幅情景）：`T=1.0`，`top_p=0.9`，`sample_count=10`（FaceCat 示例默认值）

### Agent 执行指引

1. **周日 forecast**：对持仓 + 观察池各拉 ≥90 根日 K（AKShare / 雪球），可选跑 Kronos 得 5–10 日虚拟路径；与 `week_forecast` 蒙特卡洛路径**交叉验证**，偏差大时在飞书标注「Kronos 分歧」。
2. **收盘 verify**：将 Kronos 预测收盘价 vs 实盘写入 `forecast_review.optimization_notes`（同 FaceCat 回测模式）。
3. **technical 专家**：若 Kronos 5 日累计方向与 MA20 趋势相反 → 标签上限「观察」，不强行「可做」。
4. **CPU 环境**：无 CUDA 时用仓库内 `examples/cpu_prediction_example.py`；模型离线放 `model/` 或 `facecat/model/`。

```bash
# 本地试跑（无需 FaceCat GUI）
git clone --depth 1 https://github.com/zjk1984/FaceCat-Kronos /tmp/FaceCat-Kronos
cd /tmp/FaceCat-Kronos && pip install -r requirements.txt safetensors
cd examples && python3 cpu_prediction_example.py   # 或 cpu_prediction_wo_vol_examples.py
```

### 集成路线图（weekly skill 审视时更新）

- [x] `week_forecast` 增加 `kronos_paths` 字段（每标的 OHLC 预测 + 置信区间）— `kronos_predictor.py` + `generate_week_forecast`
- [x] 收盘 `review_active_forecast` + `close_improvements` 读取 Kronos 偏差 — `week_forecast_tracker._kronos_review_summary`
- [x] `technical` 插件接入 Kronos 方向评分 — `technical_expert._apply_kronos_adjustment`（默认 ≤12 分）

**启用方式：**

```bash
# 1. 安装 Kronos 依赖 + 克隆 FaceCat-Kronos
pip install 'agent-reach[daily-run-kronos]'
git clone --depth 1 https://github.com/zjk1984/FaceCat-Kronos ~/.agent-reach/vendor/FaceCat-Kronos

# 2. 开启 settings（或 ~/.agent-reach/daily_run_settings.json）
#    "kronos": { "enabled": true, "repo_path": "~/.agent-reach/vendor/FaceCat-Kronos" }

# 3. 周日 forecast 自动混合 Kronos 路径；收盘 technical 专家自动读取 snapshot.kronos
python3 -m agent_reach.cli daily-run schedule run forecast
```

---

## 🧩 Phase-3 插件化专家 + Grid Search 优化

### Team-First 8 专家并行（早报 / 收盘复盘默认启用）

借鉴 [china-stock-analyst](https://github.com/wjt0321/china-stock-analyst) Team-First 架构：

| 专家 | 角色 |
|------|------|
| `fundamental` | 基本面大师 |
| `technical` | 技术分析派 |
| `quant` | 量化模型师 |
| `risk` | 风险控制官 |
| `macro` | 宏观策略师 |
| `industry` | 行业研究家 |
| `sentiment` | 消息面猎手 |
| `identifier` | 专家鉴别 Agent |

```bash
# 早报：8 专家 full_parallel → Supervisor 仲裁 → 飞书
agent-reach daily-run morning -i snapshot.json --save-baseline

# 收盘复盘：8 专家 + 基线验证 → 飞书
agent-reach daily-run close -i eod_snapshot.json

# 列出全部专家
agent-reach daily-run plugins list
```

配置：`config/daily_run_settings.json` → `team.experts` / `team.parallel`

### 专家插件（macro / technical / sentiment …）

```bash
agent-reach daily-run plugins list
agent-reach daily-run plugins run -i snapshot.json
agent-reach daily-run plugins run -i snapshot.json --names macro,technical
```

插件输出 `expert_scores` 并回填 `mss_breakdown`，随后可走 evaluate/push 流水线。

内置插件：

| 插件 | 角色 | 输入 |
|------|------|------|
| `macro` | 宏观策略师 | fx / global / macro_summary |
| `technical` | 技术分析派 | price / ma20 / position_20d / volume_ratio |
| `sentiment` | 消息面猎手 | flow / sentiment / sources |

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

### 📅 ### 📅 ### 📅 ### 📅 2026-07-27 ~ 2026-07-31 周复盘（周六自动沉淀）
*   **更新时间：** 2026-07-29 13:56 UTC
*   **本周盈亏说明：**
*   **情况说明：** 本周组合净值基本 **持平**（+0.00 元，+0.0%）。
*   **持仓浮盈合计：** ¥-18,845（4 只）
*   **现金仓位：** 46.0%（¥40,176）
*   **成交现金流（ledger）：** ¥-39,809.62，共 1 笔
    *   2026-07-29 买入京东方A 5300股 @ ¥7.50
*   _净值变动接近 0 但 ledger 有大额成交：可能缺少周初早盘净值基线，或买入使用既有现金、市值波动与成交相互抵消。_
*   _本周无早盘 manifest，周初净值用周末/当前估值代替_
*   **持股概况：** 澜起科技 (688008) +0.90%、海能达 (002583) +1.50%、京东方A (000725) +2.33%、水晶光电 (002273) +0.96%
*   **强势标的：** 中际旭创 +4.74%、京东方A +2.33%、海能达 +1.50%
*   **任务覆盖：** 早盘 0/5、收盘 0/5、盘中 0 次
*   **备注：** 本周无早盘 manifest，周初净值用周末/当前估值代替
*   **收盘经验片段：**
    *   2026-07-28 澜起科技 MSS=35.2 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-07-28 水晶光电 MSS=35.2 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-07-28 海能达 MSS=35.2 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-07-28 京东方A MSS=35.2 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
    *   2026-07-28 兆易创新 MSS=35.2 ✅ 宏观一票否决生效：维持高现金，禁止接飞刀；MSS 预测命中：维持当前权重配置
*   **量化规则库（最近）：**
    *   尾盘曲线 震荡走弱：次日早盘偏防御
    *   偏差：MSS 实际 35.7 高于预测上沿 33.2（偏差 2.5）
    *   偏差：标签由「可做」变为「回避」
    *   偏差：MSS 实际 29.8 低于预测下沿 45.0（偏差 -15.2）
    *   偏差：价格变动 -18.9% 超过锚点阈值 8.0%
*   **流程改进（优先）：**
    *   **缺失 3 天早盘任务** — 检查 GHA cron 0 8 * * 1-5 与 Fork 是否 Enable scheduled workflows
    *   **缺失 3 天收盘复盘** — 检查 GHA cron 30 15 * * 1-5；手动补跑 daily-run schedule run close
    *   **1 天盘中扫描偏少** — 确认 GHA cache restore/save 正常；参考 PR #28 修复 intraday_state 累积
    *   **持仓浮亏标的需关注** — 收盘 verify 若 MSS<macro_veto 则优先纳入明日卖出候选

---

   1. 基础复盘：总结今日实盘得失与净值变化                                 |
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


## 🛠️ 运维与排障指南

### 0. 飞书推送配置（App Bot 模式 · 当前使用）

目标群：**《每天股票量化交易》**

**方式 A — CLI 本地配置（推荐）：**
```bash
agent-reach configure feishu-app-id cli_xxxxxxxxxxxxx
agent-reach configure feishu-app-secret xxxxxxxxxxxxxxxx
agent-reach configure feishu-chat-id oc_xxxxxxxxxxxxx
agent-reach notify feishu --test
agent-reach doctor   # 通知集成应显示 ✅ 飞书消息推送
```

**方式 B — Cloud Agent Secrets（云端自动推送）：**
在 [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents) 配置：
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_CHAT_ID`

配置后重启 Agent 任务。推送命令：
```bash
agent-reach notify feishu --title "标题" --text "Markdown 正文"
```

**方式 C — Webhook 群机器人（更简单，无需 chat_id）：**
```bash
agent-reach configure feishu-webhook-url https://open.feishu.cn/open-apis/bot/v2/hook/your_key
agent-reach notify feishu --test
```

### 1. 提示 "LLM API Key 未配置"
*   **原因：** Cursor Cloud Agent 运行在隔离沙箱中，新配置的 Secrets 无法在当前热会话中生效。
*   **解决办法：** 
    1. 确保在 [Cursor Dashboard → Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents) 页面中配置了 `GEMINI_API_KEY` 或 `OPENAI_API_KEY`。
    2. **重启当前 Agent 任务**，使 Secrets 环境变量成功注入。

### 2. Efinance 历史 K 线接口失败 (RemoteDisconnected)
*   **原因：** 东方财富接口对高频连续请求有随机熔断限制。
*   **解决办法：** DSA 内部已集成多数据源自动切换。当 `EfinanceFetcher` 熔断后，系统会自动切换到 `TencentFetcher`（腾讯接口）进行兜底拉取，无需人工干预。
