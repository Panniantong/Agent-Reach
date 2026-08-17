# Harness 自进化 — 走读与测试参考

## 架构（三层）

```
静态 JSON (load_settings)
    ↓ effective_settings()
harness overlay (memory / policy / playbook / signals)
    ↓ apply_harness_policy_overlay
运行时 cfg（thresholds + schedule + portfolio + trading + mss_forecast + lookback_weights）
    ↓ threshold_default / runtime_*_default / effective_days_held
业务消费者（intraday / verdict / portfolio_manager / …）
```

**铁律：** 进化项不进静态 JSON（`threshold_evolution_mode: harness` 时）；消费者不读裸 config。

## 进化项目录

| 键 | 写入 section | 读取 helper |
|----|--------------|-------------|
| macro_veto, aggressive_entry, min_cash_ratio, max_price_deviation_pct | thresholds | threshold_default / min_cash_ratio_default |
| high_position_20d, min_volume_ratio, max_vwap_deviation_pct | thresholds | threshold_default |
| trade_min_scans, trade_every_n_scans | schedule | runtime_int_default |
| max_holdings, max_total_symbols | portfolio | runtime_int_default |
| holding_lock_days, stop_loss_ma20_pct, friction_min_return_pct | trading | runtime_int_default / runtime_float_default / friction_min_return_default |
| base_spread, vol_multiplier | mss_forecast | forecast_int_default |
| lookback_weights | 顶层 | lookback_weights_default |

源码真源：`agent_reach/daily_run/harness_policy.py` → `EVOLVED_CONFIG_KEYS_BY_SECTION`, `HARNESS_CONSUMER_HELPERS`。

## 信号 → 阈值一致性（防御期）

当 `resolve_harness_trade_signals()` 返回 `defensive_trim=True` 时，effective 值应满足：

| 项 | 期望 |
|----|------|
| macro_veto | ≤ 30 |
| aggressive_entry | ≤ 45 |
| min_cash_ratio | ≥ 45% |
| holding_lock_days | ≥ 2 |
| max_holdings | ≤ 5 |
| base_spread | ≥ 10（有预测偏离时） |

收盘走读 `_review_harness_evolution()` 自动校验；不一致 → harness area finding → **code_walk refine 写入 memory/policy**。

## code_walk job（Skill 自进化）

Agent 执行 `.cursor/skills/daily-run-code-walk/scripts/run_walk.py` 时：

1. `run_close_code_review()` + `scan_static_wiring()`
2. `findings_to_harness_evidence()` 映射 finding → memory/policy/playbook/plan
3. `refine_after_job("code_walk", …)` 持久化到 `harness_state.json`
4. 下次 `effective_settings()` overlay 读取新 memory/policy

配置：`harness.jobs.code_walk: true`，`close_code_review.harness_evolve_on_walk: true`。

## skill writeback _guard

`skill_improvements_apply.apply_settings_from_improvements()` 在 harness 模式下**不得**写回：

- `thresholds.macro_veto`（须 `threshold_mode == fixed`）
- `mss_forecast.base_spread`（须 `evolution_mode(base_spread) == fixed`）

新增 writeback 路径必须加相同 guard。

## 必测矩阵

| 场景 | 断言 |
|------|------|
| 无 overlay | raw settings 无 `harness_runtime` → 走报 high |
| 防御 memory | effective macro_veto ≤ 30 |
| 进攻 memory | min_cash_ratio 下调 |
| load_portfolio | acquired_date + days_held=0 → sync 后 ≥1 |
| prepare_close_run | 传入 code_review 的 cfg 已 effective_settings |
| 静态污染 | list_static_config_pollution 返回空（repo + user JSON） |

## Grep 命令

```bash
# 进化项是否泄漏到 JSON
rg 'macro_veto|aggressive_entry|holding_lock_days|base_spread' config/ ~/.agent-reach/daily_run_settings.json

# 消费者是否绕过 helper
rg '\.get\("(macro_veto|days_held|holding_lock_days)"' agent_reach/daily_run/ --glob '!harness_policy.py'

# effective_settings 入口
rg 'load_settings\(\)' agent_reach/daily_run/ | rg -v 'effective_settings|settings\.py|test_'
```
