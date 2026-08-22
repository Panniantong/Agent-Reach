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

```bash
# hold-out 回测（需 FaceCat-Kronos + torch；AKShare 拉历史 K 线）
python3 -m agent_reach.cli daily-run kronos backtest --code 688008
python3 -m agent_reach.cli daily-run kronos backtest --code 688008 --holdout 5 --folds 3 --json
```

### 集成状态（weekly skill 审视时更新）

**已完成：**

- [x] `kronos_predictor.py` — AKShare OHLCV + `KronosPredictor.predict()`
- [x] `week_forecast.kronos_paths` + MC blend（`blend_symbol_days_with_kronos`）
- [x] 收盘 `review_active_forecast` + `_kronos_review_summary` / 校准 notes
- [x] `technical_expert` Kronos 方向评分（≤12 分）
- [x] `close_improvements` 读取 Kronos 偏差建议

**待增强（FaceCat 可继续借鉴）：**

- [x] `kronos_paths.days` 持久化完整 OHLCV（供止损模拟 / 虚 K 线渲染）
- [x] `attach_kronos_to_snapshot` 改用交易所交易日历（`resolve_kronos_trading_days` + `use_trade_calendar`）
- [x] 基于预测 OHLC 的累计离散度 band（`dispersion_from_ohlc` / `band_kind=ohlc_cumulative`）
- [x] 飞书个股路径卡片附 Kronos 方向箭头 / 简易虚 K 线摘要（`render_kronos_path_markdown`）
- [x] 可选：AKShare 历史 hold-out 回测 helper（`kronos_holdout_backtest.py` + `daily-run kronos backtest`）

---
