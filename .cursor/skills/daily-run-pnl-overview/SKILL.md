---
name: daily-run-pnl-overview
description: >-
  盈亏总览 harness 自进化 skill：FIFO 已实现盈亏、持仓浮盈浮亏、卖出胜率 →
  memory/policy/playbook/plan。收盘 run_close 自动 refine；可手动 overview/backfill。
---

# Daily-run PnL Overview Harness

与 `verify` / `data_audit` 同模式：**PnL findings → refine_after_job(`pnl_overview`) → harness 进化**。

## 数据流

```
trade_ledger.jsonl (sell 带 realized_pnl)
        ↓
build_pnl_overview() / build_close_pnl_overview()
        ↓
pnl_overview_to_harness_evidence()
        ↓
apply_pnl_overview_harness_refinement()  →  ~/.agent-reach/harness_state.json
```

## 触发

| 场景 | 入口 |
|------|------|
| 收盘自动 | `run_close()` → `run_close_harness_refinements(portfolio_summary=…)` |
| 手动总览 | `daily-run pnl overview` |
| 补录 ledger | `daily-run pnl backfill` |
| 手动 harness | 见下方脚本 |

## 进化规则（Layer A 确定性）

- **买入记录**：每笔写入 memory（数量、买入价、成交额、佣金、成交时间、trade_id）
- **卖出已实现**：每笔 FIFO 盈亏写入 memory（数量、买/卖价、已实现、时间）；大亏 → policy/plan；大盈 → playbook 止盈参考
- **持仓浮动**：每笔写入 memory（数量、买入价、现价、浮盈浮亏、买入时间）
- **浮亏警示**：超过 `large_unrealized_loss_cny` 或 `large_unrealized_loss_pct` → policy + 减仓 plan
- **ledger 缺成本**：cost_basis≈0 → playbook 提示 `pnl backfill`
- **入金剔除**：`capital_net_flow` 存在 → memory + capital CLI 提醒
- **close layer_a residual**：仅保留日 PnL headline（明细由本 job 承担）

## CLI

```bash
# 人类可读总览
python3 -m agent_reach.cli daily-run pnl overview

# JSON + 周期
python3 -m agent_reach.cli daily-run pnl overview --period week --json

# 补录历史卖出 realized_pnl
python3 -m agent_reach.cli daily-run pnl backfill

# 入金/出金（避免日 PnL 失真）
python3 -m agent_reach.cli daily-run capital deposit --amount 100000 --note "追加本金"
```

## 手动 harness smoke

```bash
python3 .cursor/skills/daily-run-pnl-overview/scripts/run_pnl_harness.py --json
```

## 配置

```json
"pnl_overview": {
  "harness_evolve": true,
  "large_unrealized_loss_cny": 5000,
  "large_realized_loss_cny": 500,
  "large_unrealized_loss_pct": 10
},
"harness": {
  "jobs": { "pnl_overview": true }
}
```

## 模块

- `agent_reach/daily_run/realized_pnl.py` — FIFO、overview、backfill
- `agent_reach/daily_run/pnl_overview_harness.py` — evidence + refine
- `close_harness_skills.py` — 收盘编排

## 测试

```bash
python3 -m pytest tests/test_daily_run_pnl_overview_harness.py tests/test_daily_run_realized_pnl.py -q
```
