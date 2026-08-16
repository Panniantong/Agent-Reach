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
