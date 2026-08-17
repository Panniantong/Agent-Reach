---
name: daily-run-code-walk
description: >-
  Daily-run 专业代码走读 + harness 自进化。Agent 必须执行 scripts/run_walk.py，
  将 findings 写入 harness memory/policy/playbook。改 portfolio/harness/走读、
  PR review、或反馈字段卡住/阈值不生效时使用。
---

# Daily-run 代码走读 + Harness 自进化

**运行时双入口：**

| 入口 | 场景 |
|------|------|
| 收盘自动 | `close_code_review.run_close_code_review()` → `harness_evolve_on_walk` |
| Agent/Skill | `scripts/run_walk.py` 或 `run_agent_code_walk()` |

详细键表：[references/harness-evolution.md](references/harness-evolution.md)

---

## Agent 必须执行（不可只读文档）

改 daily-run 相关代码前或 PR 合入前，**运行走读并触发 harness 进化**：

```bash
cd /path/to/Agent-Reach   # 仓库根目录
python3 .cursor/skills/daily-run-code-walk/scripts/run_walk.py
```

JSON 报告（CI/脚本）：

```bash
python3 .cursor/skills/daily-run-code-walk/scripts/run_walk.py --json
```

Python API：

```python
from agent_reach.daily_run.code_walk_harness import run_agent_code_walk, render_code_walk_markdown

report = run_agent_code_walk(walk_source=True, evolve_harness=True)
print(render_code_walk_markdown(report))
```

### 执行后必做

1. 阅读输出中的 **待处理** findings（high 优先）
2. 确认 **Harness 自进化** 块有 `refinement_id`（findings 已写入 harness）
3. 修复代码；rerun `run_walk.py` 直到 open_high=0 或已记录 plan
4. 跑测试金字塔（见 P3）

---

## Harness 自进化链路

```
findings (portfolio/harness/intraday/source)
    ↓ findings_to_harness_evidence()
memory / policy / playbook / plan 文本
    ↓ refine_after_job("code_walk")
~/.agent-reach/daily_run/harness/harness_state.json
    ↓ effective_settings()  overlay
macro_veto / holding_lock_days / base_spread / … 运行时进化
```

### Finding → Harness 映射（自动）

| Finding | 写入 | 触发的进化方向 |
|---------|------|----------------|
| overlay 缺失 | policy + plan | 强制 effective_settings |
| days_held stale | memory + playbook | sync + effective_days_held |
| 静态 JSON 污染 | playbook + policy | list_static_config_pollution 清零 |
| defensive 不一致 | memory | macro_veto↓ / min_cash↑ |
| 模块裸读阈值 | policy + plan | 接入 threshold_default |
| auto_fix 成功 | playbook | 记录已修复模式 |

关闭进化：`close_code_review.harness_evolve_on_walk: false` 或 `--no-evolve`。

Layer A 保持规则写入；低频 job 可在 Layer A 后触发 `llm_summarize`（skill_closure、code_walk），见 `daily-run-harness-skills` SKILL。

---

## 走读四阶段

### P0 — 数据真源与读写对称

- 真源：`acquired_date` → `effective_days_held()`；harness → `effective_settings()` → `*_default()`
- `load_portfolio()` / `save_portfolio()` / `prepare_close_run()` 必须 sync + overlay

```bash
rg 'days_held|acquired_date|effective_days_held|sync_portfolio_holding_days' agent_reach/daily_run/
```

### P1 — Harness wiring

```bash
python3 -c "
from agent_reach.daily_run.settings import load_settings
from agent_reach.daily_run.harness_policy import list_static_config_pollution
print(list_static_config_pollution(load_settings()))
"
```

非空 → 从静态 JSON 移除进化项。

### P2 — 静态 AST（`walk_source=True` 时）

扫描 `list_walk_module_names()`：核心模块 + `*_harness.py` / `*_harness_skills.py`；裸读 evolved 键、裸读 `days_held`。

### P3 — 测试

```bash
python3 -m pytest \
  tests/test_daily_run_code_walk_harness.py \
  tests/test_daily_run_close_code_review.py \
  tests/test_daily_run_harness_policy.py \
  tests/test_daily_run_portfolio_manager.py -q
```

---

## 案例库

### A. days_held 卡在 0
load 不同步 + 裸读 → `load_portfolio` sync + 走读写入 harness playbook。

### B. harness 阈值不生效
双源 JSON + 未 overlay → 移出进化项 + effective_settings + policy 记忆。

### C. 走读漏检
只验 None → 比对 stored vs recomputed + 静态 scan + harness refine 沉淀规则。

---

## Definition of Done

- [ ] 已运行 `run_walk.py` 且 harness refinement 成功
- [ ] `list_static_config_pollution()` 为空（harness 模式）
- [ ] 无裸读 evolved 键 / days_held
- [ ] 测试通过（含 `test_daily_run_code_walk_harness.py`）
- [ ] skill writeback 新项带 `evolution_mode` guard

---

## 参考

| 模块 | 职责 |
|------|------|
| `code_walk_harness.py` | Skill 运行时 + harness refine |
| `close_code_review.py` | 收盘走读 + auto_fix |
| `harness_policy.py` | 进化引擎 |
| `harness.py` | `refine_after_job("code_walk")` |
