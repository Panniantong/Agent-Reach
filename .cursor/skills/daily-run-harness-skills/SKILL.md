---
name: daily-run-harness-skills
description: >-
  Daily-run harness 自进化 skills 集合：verify、close_improve、data_audit、pnl_overview、
  skill_closure、experience、morning、intraday、run_guard。收盘/定时/周六/Agent 改代码后运行。
---

# Daily-run Harness Skills

与 `code_walk` 同模式：**结构化 findings → refine_after_job → effective_settings() 进化**。

| Job | 模块 | 触发 |
|-----|------|------|
| `verify` | `verify_harness.py` | 收盘 verify 偏差 |
| `close_improve` | `close_improve_harness.py` | 收盘 improvements |
| `data_audit` | `data_audit_harness.py` | 数据审计失败/警告 |
| `skill_closure` | `skill_closure_harness.py` | 周六 weekly improvements |
| `code_walk` | `code_walk_harness.py` | 代码走读 |
| `optimize` | `optimizer_harness.py` | `daily-run optimize --save` |
| `experience` | `experience_harness.py` | 收盘 `append_experience_entry` |
| `morning` | `morning_harness.py` | `run_morning()` |
| `intraday` | `intraday_harness.py` | schedule intraday / morning S2 scan |
| `run_guard` | `run_guard_harness.py` | dedupe/lock/失败 + 周六 schedule gaps |
| `rejected_strategies` | `rejected_strategies_harness.py` | 证伪策略 / filter blocked |
| `skill_gates` | `skill_gates_harness.py` | 周六 skill gate 失败 |
| `watchlist_adjust` | `watchlist_adjust_harness.py` | 收盘/早盘观察池 adjust |
| `forecast_calibrate` | `forecast_calibrate_harness.py` | 周日 forecast MSS/校准 |
| `pnl_overview` | `pnl_overview_harness.py` | 收盘 FIFO 已实现 + 浮动盈亏总览 |
| `pnl_target` | `pnl_target_harness.py` | 下一交易日总盈亏目标 + 达成奖励/未达处罚 |
| `finance_close` | `finance_close_harness.py` | 收盘 dsh-finance 对账/风控/variance bridge |
| `finance_ledger_prep` | `finance_ledger_prep_harness.py` | 收盘 journal-entry-prep（approval matrix / memo） |
| `finance_ledger` | `finance_ledger_harness.py` | 收盘 trade ledger 分录校验（journal-entry check） |
| `finance_variance` | `finance_variance_harness.py` | 周六 weekly 盈亏 waterfall（stock/cash bridge） |
| `finance_statements` | `finance_statements_harness.py` | 周六 weekly 三表骨架（损益/资产负债/现金流） |
| `finance_research` | `finance_research_harness.py` | 周六/周日 structured research workflow（sources/queries/gaps） |
| `finance_close_plan` | `finance_close_plan_harness.py` | 周六 T+1~T+5 下周 close 日历 |

## 收盘自动

`run_close()` → `run_close_harness_refinements()` 依次 refine verify / close_improve / data_audit / **pnl_overview** / **pnl_target** / **finance_close** / **finance_ledger_prep** / **finance_ledger**；
`append_experience_entry()` → experience harness（harness 模式下 rules 同步进 memory/policy）；
随后 `run_close_layer_a_refinement()` 只写入组合盈亏等 residual。

## 定时任务

`run_scheduled()` 在 dedupe/lock/失败时写 run_guard harness；morning/intraday 成功后写对应 job harness。

**forecast 去重**：`forecast_calibrate` 开启时，`forecast` layer_a 只写 Kronos 偏强/偏弱。

## 静态 JSON 迁移

```bash
python3 -m agent_reach.cli daily-run harness migrate-settings --dry-run
python3 -m agent_reach.cli daily-run harness migrate-settings
```

## P2 合并

**experience 三轨合并**（`experience.harness_consolidate: true`）：
- harness 模式：`experience.jsonl` 只存 metadata（`rules=[]`, `rules_in_harness=true`），不再写 `rules_summary.json`
- 规则读取走 `load_experience_rules()` → harness memory

**weekly 去重**：
- `skill_closure` / `run_guard` 开启时，`weekly` layer_a 只写 PnL / experience_snippets / applied_config
- 周六顺序：`apply_weekly_skill_closure` → `run_weekly_harness_refinements`（**finance_variance** / **finance_statements** / **finance_research** / **finance_close_plan** / run_guard）→ `run_weekly_layer_a_refinement`
- 周日 forecast：`run_forecast_harness_refinements` 在 `forecast_calibrate` 后可再跑 **finance_research**（`finance_research.run_on_forecast`）

## 手动运行

```bash
# 收盘三件套（smoke）
python3 .cursor/skills/daily-run-harness-skills/scripts/run_close_harness.py --json

# 盈亏总览 harness
python3 .cursor/skills/daily-run-pnl-overview/scripts/run_pnl_harness.py --json

# 代码走读
python3 .cursor/skills/daily-run-code-walk/scripts/run_walk.py
```

## Harness 模式下 weekly JSON 写回

`apply_settings_from_improvements()` 在 `threshold_evolution_mode: harness` 时**跳过 JSON 写回**，改由 `skill_closure` job 写入 harness。

## LLM 分层（稳妥方案）

| 层 | 机制 | DeepSeek | 适用 job |
|----|------|----------|----------|
| Layer A | `refine_after_job` 规则写入 | ❌ | 全部（含 morning/intraday） |
| Layer B | `refine_after_job_llm` | ✅ 可选 | close / weekly / forecast |
| Summarize | `refine_after_job_llm_summarize` | ✅ 可选 | **仅** skill_closure、code_walk |

- Layer B：`use_llm_review: true` 时审查门控也走 DeepSeek；无 key 时规则兜底。
- Summarize：Layer A 成功后追加综合 edits；**禁止** morning/intraday；无 key 时 skip（不重复写 Layer A）。
- 周六 `sync_canonical_skill_to_local()` 同步 canonical skill 至 `~/.agents/skills/` **并**复制 repo `.cursor/skills/daily-run-*` 至 `~/.cursor/skills/`。
- 高频 job 的 Layer A **保持确定性**，不改为 LLM。

```json
"harness": {
  "llm_refine": {
    "enabled": true,
    "provider": "deepseek",
    "use_llm_review": true,
    "summarize_enabled": true,
    "summarize_jobs": ["skill_closure", "code_walk"],
    "summarize_cooldown_hours": 24,
    "jobs": { "close": true, "weekly": true, "forecast": true }
  }
}
```

## 配置

```json
"harness": { "jobs": { "verify": true, "close_improve": true, "data_audit": true, "pnl_overview": true, "skill_closure": true, "optimize": true, "experience": true, "morning": true, "intraday": true, "run_guard": true } },
"pnl_overview": { "harness_evolve": true },
"pnl_target": { "enabled": true, "harness_evolve": true, "base_target_pct": 0.5 },
"close_improvements": { "harness_evolve": true },
"data_audit": { "harness_evolve": true },
"optimizer": { "harness_evolve": true },
"experience": { "harness_evolve": true, "harness_consolidate": true },
"schedule": { "guard": { "harness_evolve": true } }
```

## P3/P4 运维

### Apply gate（rule-evolve / memory-gate 模式）

| 开关 | 行为 |
|------|------|
| `apply_gate.enabled` | 启用 verify-before-apply（默认 true） |
| `apply_gate.block_policy_on_audit_fail` | 审计未通过时不写入 `policy`（memory/plan/playbook 仍写） |
| `apply_gate.block_policy_on_structured_incomplete` | 结构化复核未完成时不写 `policy` |
| `injection.max_per_kind_per_job` | 单次 refine 每 kind 最多写入条数（默认 8） |
| `injection.max_overlay_claims` | runtime overlay 最多采纳 3 条 harness 声明 |
| `injection.max_overlay_chars` | overlay 扫描总字符上限（默认 1200） |

审计轨迹：`~/.agent-reach/daily_run/harness/apply_audit.jsonl`；Feishu harness 卡展示 verification_signals / 门控拦截。

### 改前快照 + Layer B Admission（dsh-guard / self-evolving）

| 能力 | 说明 |
|------|------|
| `snapshots.enabled` | 每次 refine 前写入 `harness/snapshots/*.json`（默认保留 20 份） |
| `layer_b_admission.enabled` | Layer B / summarize 应用前过滤危险 edits（阈值漂移、超长、过多条数） |
| claim 决策 | overlay 扫描输出 `adopted` / `verify` / `ignored` 写入 `injection_gate.claims` |

```bash
python3 -m agent_reach.cli daily-run harness list-snapshots
python3 -m agent_reach.cli daily-run harness restore-snapshot --path ~/.agent-reach/daily_run/harness/snapshots/....json
```

```json
"harness": {
  "snapshots": { "enabled": true, "max_keep": 20 },
  "layer_b_admission": {
    "enabled": true,
    "max_edits": 8,
    "max_score_drift": 15,
    "max_ratio_drift": 0.25
  },
  "forge_gates": {
    "enabled": true,
    "pnl_target": { "max_target_pct": 3.0, "max_target_cny": 50000 },
    "forecast_calibrate": { "use_week_forecast_bounds": true }
  },
  "weekly_narrative": {
    "enabled": true,
    "append_to_weekly_card": true,
    "audit_days": 7
  }
}
```

### Forge 数值门控 + 周度叙事（dsh-forge / period-report）

| 能力 | 说明 |
|------|------|
| `forge_gates.enabled` | `pnl_target` / `forecast_calibrate` refine 前校验 domain 数值 |
| `forge_gates.pnl_target.max_target_pct` | 下一日目标盈亏占比上限（默认 3%） |
| `forge_gates.pnl_target.max_target_cny` | 下一日目标盈亏绝对值上限（默认 50000） |
| `weekly_narrative.enabled` | 周六 harness 卡追加本周 apply_audit 聚合叙事 |
| `weekly_narrative.append_to_weekly_card` | 嵌入 weekly Feishu harness 卡（默认 true） |

- Forge 失败：`apply_skill_refinement` 返回 `reason=forge_gate_failed`，不写 harness。
- 周度叙事：统计 audit 事件数、变更项、gate 拦截、Layer B 拒绝、job 分布。

### 运行时 Claim  enforcement + 统一审计（round 4）

| 开关 | 行为 |
|------|------|
| `injection.enforce_claim_decisions` | runtime overlay 仅采纳 `adopted` 声明；含「假设/待验证/TODO」的 `verify` 声明不生效 |
| `apply_audit.jsonl` | 记录 Layer A/B/summarize 的 applied / skipped（forge、admission 拒绝） |

- Forge / Layer B 拒绝也会写入 audit，周六周度叙事会统计 `forge_blocks` 与 `layer_b_skips`。

### dsh-finance + dsh-rigorquant 移植（方案 2）

| 来源 | Agent Reach 模块 | 行为 |
|------|------------------|------|
| `dsh-finance` portfolio_risk / reconcile / variance_bridge | `harness_finance.py` + `finance_close_harness.py` | 收盘组合风控、净值对账、variance bridge → harness memory/policy |
| `dsh-finance` journal-entry check | `harness_finance.py` + `finance_ledger_harness.py` | trade ledger 分录平衡（amount vs shares×price、买卖借贷、cost_basis / trade_cash_flow） |
| `dsh-finance` journal-entry-prep | `harness_finance.py` + `finance_ledger_prep_harness.py` | approval matrix、material buy memo、preparer/approver 分离 |
| `dsh-finance` reconciliation snapshot | `harness_finance.py` + `finance_close_harness.py` | 收盘未平项账龄 / stale / sign-off readiness |
| `dsh-finance` financial-statements | `harness_finance.py` + `finance_statements_harness.py` | 周六 weekly 三表 + materiality tie-out |
| `dsh-finance` finance_research_workflow | `harness_finance.py` + `finance_research_harness.py` | sources/queries/evidence_gaps → harness plan |
| `dsh-rigorquant` 四重校验电池 | `harness_rigor_check.py` | closure / invariant / boundary / evidence；默认仅 **optimize** 失败时 block refine |
| `dsh-rigorquant` study.json schema | `harness_rigor_schema.py` + `harness_study_registry.py` | optimize 试验登记到 `study_registry.json` |
| `dsh-memory-evolve` git 分支感知 | `harness_git.py` | 非 main 分支 harness 状态隔离到 `harness/branches/<slug>/` |
| `dsh-context-doctor` 去重 | `harness_context_doctor.py` | Layer A apply 前按相似度剔除重复 memory/policy/playbook/plan |
| `dsh-context-doctor` 冲突检测 | `harness_context_doctor.py` | policy 偏防御 vs playbook 激进等跨 kind 冲突拦截 |
| forge 扩展 | `harness_forge_gates.py` | 新增 `finance_close`、`finance_ledger`、`optimize` 数值 sanity |

```json
"finance_close": {
  "enabled": true,
  "harness_evolve": true,
  "max_position_pct": 35,
  "min_cash_pct": 5
},
"harness": {
  "rigor_check": {
    "enabled": true,
    "block_on_fail": { "optimize": true },
    "jobs": { "finance_close": true, "finance_ledger": true, "optimize": true }
  },
  "jobs": { "finance_close": true, "finance_ledger": true }
}
```

- `finance_close` 对账/bridge 失败仍会写入 playbook（rigor 仅记录，不 block）。
- `optimize` rigor 或 forge 失败 → `reason=rigor_check_failed` / `forge_gate_failed`，不写 harness。

**周六 weekly 扩展（dsh-finance variance-analysis / close-management）**

| Job | 模块 | 行为 |
|-----|------|------|
| `finance_variance` | `finance_variance_harness.py` | 周盈亏 stock/cash bridge + materiality → harness |
| `finance_close_plan` | `finance_close_plan_harness.py` | T+1~T+5 下周 close 任务日历（manifest/skill gates/blockers） |

```json
"finance_variance": {
  "enabled": true,
  "variance_materiality_cny": 1000,
  "percent_materiality": 1.0
},
"finance_statements": {
  "enabled": true,
  "materiality_cny": 1000,
  "tie_tolerance_cny": 5.0
},
"finance_reconcile": {
  "stale_days": 3,
  "materiality_cny": 500
},
"harness": {
  "context_doctor": {
    "enabled": true,
    "similarity_threshold": 0.86
  },
  "rigor_schema": {
    "enabled": true,
    "jobs": ["optimize"]
  },
  "branch_overlay": {
    "enabled": true,
    "use_root_for_main": true
  },
  "study_registry": {
    "enabled": true,
    "jobs": ["optimize", "backtest"]
  }
}
```

### Feishu Harness 摘要卡

| 开关 | 行为 |
|------|------|
| `push_summary_on_close` | 收盘 harness 跑完 → 嵌入主复盘卡 |
| `push_summary_on_weekly` | 周六 Layer B 后 → 追加 harness 卡 |
| `push_summary_on_forecast` | 周日 forecast harness 后 → 追加 harness 卡 |
| `push_summary_on_morning` | 早盘 harness → 嵌入主卡（默认跟随 close） |
| `push_summary_on_intraday` | 盘中 harness → 追加卡（默认 **关**，避免高频刷屏） |
| `push_harness_errors_on_feishu` | harness 异常 → 独立红色卡或嵌入摘要 |
| `push_rollback_on_feishu` | 坏交易回滚 → 未嵌入主卡时独立红色通知 |

### 坏交易自动回滚

```json
"harness": {
  "auto_rollback_on_bad_trade": true,
  "bad_trade_pnl_pct": -1.0,
  "bad_trade_weekly_pnl_pct": -2.0
}
```

- **收盘**：`daily_pnl_pct ≤ bad_trade_pnl_pct` 时，回滚本次 session 全部 refine（含 verify/close_improve/data_audit/experience/layer_a/layer_b）
- **周报**：`weekly_pnl_pct ≤ bad_trade_weekly_pnl_pct` 时回滚 weekly session refine
- **预测**：无 PnL 阈值，不触发回滚

### Overlay 与配置同步

```bash
python3 -m agent_reach.cli daily-run harness show --overlay
python3 -m agent_reach.cli daily-run harness sync-settings --dry-run
python3 -m agent_reach.cli daily-run harness sync-settings
```

`sync-settings` 从 repo 默认补齐缺失的 harness 键（不覆盖已有用户值）。

## 测试

```bash
python3 -m pytest tests/test_daily_run_harness_p8.py tests/test_daily_run_harness_p7.py tests/test_daily_run_harness_p6.py tests/test_daily_run_harness_p5.py tests/test_daily_run_harness_p4.py tests/test_daily_run_harness_p3.py tests/test_daily_run_harness_p2.py tests/test_daily_run_harness_p1.py -q
```
