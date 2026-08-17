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

## 收盘自动

`run_close()` → `run_close_harness_refinements()` 依次 refine verify / close_improve / data_audit / **pnl_overview**；
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
- 周六顺序：`apply_weekly_skill_closure` → `run_weekly_harness_refinements` → `run_weekly_layer_a_refinement`

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
"close_improvements": { "harness_evolve": true },
"data_audit": { "harness_evolve": true },
"optimizer": { "harness_evolve": true },
"experience": { "harness_evolve": true, "harness_consolidate": true },
"schedule": { "guard": { "harness_evolve": true } }
```

## P3/P4 运维

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
python3 -m pytest tests/test_daily_run_harness_p3.py tests/test_daily_run_harness_p2.py tests/test_daily_run_harness_p1.py -q
```
