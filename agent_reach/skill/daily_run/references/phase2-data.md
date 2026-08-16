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
