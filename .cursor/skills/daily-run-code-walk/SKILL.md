---
name: daily-run-code-walk
description: >-
  Daily-run 专业代码走读 + harness 自进化 + Phase G Grill 追问。Agent 必须执行
  scripts/run_walk.py；open high 时对每条 finding 借鉴 grill-me-skill 逐枝问清
  Bug Fix Plan 再改代码。改 portfolio/harness/走读、PR review、字段卡住时使用。
---

# Daily-run 代码走读 + Harness 自进化

**运行时双入口：**

| 入口 | 场景 |
|------|------|
| 收盘自动 | `close_code_review.run_close_code_review()` → `harness_evolve_on_walk` |
| Agent/Skill | `scripts/run_walk.py` 或 `run_agent_code_walk()` |

详细键表：[references/harness-evolution.md](references/harness-evolution.md)

**通用 diff 多 Agent 走读**（借鉴 [claude-review-loop](https://github.com/zjk1984/claude-review-loop)）：用 `.cursor/skills/code-review-loop/SKILL.md` — 并行 Diff + Holistic review，输出 `reviews/review-*.md`。

**Bug 全面解法追问**（借鉴 [grill-me-skill](https://github.com/zjk1984/grill-me-skill)）：对每条 **open high** 走 **Phase G** — 一次一问、多选选项、决策树闭合后再改代码。详见 [references/grill-me-bug-fix.md](references/grill-me-bug-fix.md)。

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
2. 若 **open_high > 0** → 进入 **Phase G Grill**（见下），逐条产出 Bug Fix Plan
3. 确认 **Harness 自进化** 块有 `refinement_id`（findings 已写入 harness）
4. 按 Bug Fix Plan 修复代码；rerun `run_walk.py` 直到 open_high=0 或已记录 plan
5. 跑测试金字塔（见 P3）

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
| macro sources 缺 flow/sentiment | memory + policy + plan | enrich_macro / collect_macro |
| diff review high | memory + plan | 修 diff 后再 `--review-diff` |
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

### P4 — Macro source audit（自动）

`run_agent_code_walk()` 始终执行 `scan_macro_source_audit()`：

- 读 `~/.agent-reach/daily_run/cache/<today>.json` 的 `macro_ctx.sources`
- 对照 `data_audit.required_source_categories`（默认 quote/flow/sentiment）
- **high**：enrich 后仍缺 flow/sentiment → 盘中 `intraday_block_on_audit_fail`（T10 类）

Finding → harness：`source` area 写入 memory/policy/plan（见 `finding_to_harness_lines`）。

### Phase R — 可选 diff review（`--review-diff`）

与 `code-review-loop` **编排**（不合并 skill）：

```bash
python3 .cursor/skills/daily-run-code-walk/scripts/run_walk.py --review-diff
python3 .cursor/skills/daily-run-code-walk/scripts/run_walk.py --review-diff --diff-scope uncommitted
```

| 层 | 职责 |
|----|------|
| **Deterministic** | `scan_diff_review()` — git diff `agent_reach/daily_run/`：裸读 evolved 键、load_settings 无 overlay、缺测试 diff |
| **Agent** | 输出 `agent_instructions` → 并行启动 `code-review-loop` Phase 2（Diff + Holistic + Domain/Test） |
| **Harness bridge** | 仅 **critical/high** diff findings → `findings_to_harness_evidence()`；medium/low 不污染 memory |

外部 agent findings 合并：

```python
from agent_reach.daily_run.code_walk_harness import external_review_to_findings, findings_to_harness_evidence

evidence = findings_to_harness_evidence(external_review_to_findings(agent_items))
```

推荐顺序：P0–P3 + macro audit → `--review-diff` → 若有 open_high 再跑 `code-review-loop` Phase 2–3 → **Phase G Grill** → 实现修复。

### Phase G — Grill 追问（借鉴 grill-me-skill）

**目的：** 把「发现 bug」变成「全面解决方法」— 根因、修复、测试、harness、回归、Done 条件全部闭合后再写代码。

**何时：** `run_walk.py` / `--review-diff` 存在 **critical/high** 且未关闭；或用户说「grill me / 追问怎么修彻底」。

**怎么做：**

| 规则 | 说明 |
|------|------|
| 一次一问 | 用 **AskUserQuestion**（或多选弹窗），禁止一次抛 5 个开放题 |
| 2–4 个具体选项 | 每项应是可执行的下一步，不是泛泛 Yes/No |
| 先自查后提问 | 真源/ grep / pytest / harness state 能确定的不要问用户 |
| 决策树 | 现象 → 真源 → 根因 → 修复 → 验证 → 回归 → harness/plan 闭环 |
| 输出 | 每条 finding 一份 **Bug Fix Plan**（模板见 reference） |

**按 finding area 选题库：** [references/grill-me-bug-fix.md](references/grill-me-bug-fix.md)

**Grill 结束标志：** 用户确认所有 high 的 Bug Fix Plan；然后才允许改代码。修完必须 rerun walk + P3。

```text
open_high finding
    → Phase G（逐枝 AskUserQuestion）
    → Bug Fix Plan（7 项 checklist 填满）
    → 实现 + pytest
    → rerun run_walk.py
    → finding 消失或 plan 条目关闭
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
- [ ] 所有 open **high** 已 Phase G 追问并产出 Bug Fix Plan（或已记入 harness plan）
- [ ] macro audit 无 open **high**（或已记入 plan）
- [ ] `list_static_config_pollution()` 为空（harness 模式）
- [ ] 无裸读 evolved 键 / days_held
- [ ] 测试通过（含 `test_daily_run_code_walk_harness.py`）
- [ ] daily-run PR：`--review-diff` 无 open high，或 code-review-loop 已 consolidate
- [ ] skill writeback 新项带 `evolution_mode` guard

---

## 参考

| 模块 | 职责 |
|------|------|
| `code_walk_harness.py` | Skill 运行时 + harness refine |
| `close_code_review.py` | 收盘走读 + auto_fix |
| `harness_policy.py` | 进化引擎 |
| `harness.py` | `refine_after_job("code_walk")` |
| [grill-me-bug-fix.md](references/grill-me-bug-fix.md) | Phase G 决策树 + Bug Fix Plan 模板 |
| [grill-me-skill](https://github.com/zjk1984/grill-me-skill) | 一次一问、多选追问方法论 |
