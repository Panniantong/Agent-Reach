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
