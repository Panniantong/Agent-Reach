# Phase G — Grill 追问（借鉴 [grill-me-skill](https://github.com/zjk1984/grill-me-skill)）

目标：**每个 open high/critical finding 都走完整决策树**，产出可执行的「全面解决方法」，而不是只列问题。

## 何时启动

| 触发 | 动作 |
|------|------|
| `run_walk.py` 输出 `open_high > 0` | 对每条 high 启动 Phase G |
| 用户说「grill me」「追问这个 bug」「怎么修彻底」 | 对指定 finding 启动 |
| `--review-diff` + code-review-loop 有 critical/high | 合并后逐条 grill |
| 修复后仍复现 / 字段仍卡住 | 从 P0 真源问题重新 grill |

**顺序：** P0–P4 → Phase R → **Phase G（每条 open high）** → 实现 → P3 复测 → rerun walk。

---

## 提问铁律（来自 grill-me-skill）

1. **一次只问一个问题** — 等用户答完再问下一个。
2. **必须用 AskUserQuestion**（或多选弹窗等价物）— 不要只在正文里抛开放题。
3. 每题提供 **2–4 个具体选项**（可执行的下一步），避免泛泛的 Yes/No。
4. **能自己查代码/跑命令就不要问用户** — 先 `rg`、读文件、`pytest`、看 harness state。
5. 每个分支决策后 **1–2 句确认**，立刻进入下一题。
6. 全部分支闭合后，输出 **Bug Fix Plan 摘要**（见文末模板）。

---

## 决策树（每条 finding 必走）

```text
Finding
  ├─ 1. 现象确认 — 用户看到什么？期望什么？哪条路径触发？
  ├─ 2. 真源定位 — 写路径 vs 读路径 vs overlay vs 缓存 哪一侧错了？
  ├─ 3. 根因分类 — 实现 bug / 配置双源 / harness 未接线 / 测试缺口 / 上游数据
  ├─ 4. 修复策略 — 最小 diff / 是否需要 harness 沉淀 / 是否 auto_fix
  ├─ 5. 验证计划 — 单测 / 集成 / doctor / 走读 rerun / 生产 smoke
  ├─ 6. 回归与边界 — 会破坏什么？是否需要 feature flag / evolution_mode guard
  └─ 7. 闭环 — plan 条目 + harness writeback + DoD checkbox
```

---

## 按 area 的示例问题（选项示意）

### portfolio / days_held

**Q1 现象：** 卡片/决策里 `days_held` 显示什么？

- A. 始终 0
- B. 比手工算少 1
- C. 只有部分持仓错
- D. Other

**Q2 真源（Agent 应先查）：** `load_portfolio` 是否调用了 `sync_portfolio_holding_days`？

- Agent 自行 grep；仅当无法确定再问用户是否「刚买入当日就决策」。

**Q3 修复：**

- A. 仅在 load 时 sync
- B. load + 所有裸读改 `effective_days_held()`
- C. 数据修复脚本 + 代码 fix
- D. Other

**Q4 验证：**

- A. `test_daily_run_portfolio_manager` 加 case
- B. 走读 rerun + 收盘 smoke
- C. 两者都要

### harness / overlay 不生效

**Q1：** 问题是「改了 JSON 不生效」还是「harness memory 写了但 runtime 没变」？

**Q2（Agent 查）：** `list_static_config_pollution()` 与 `effective_settings()` overlay 块。

**Q3 修复：**

- A. 从静态 JSON 移除进化项
- B. 消费者改 `*_default()` helper
- C. 补 playbook 解析（如 calibration playbook）
- D. Other

### source / macro audit

**Q1：** 缺的是 flow、sentiment 还是 quote？

**Q2（Agent 查）：** 当日 cache `macro_ctx.sources` + `enrich_macro_sources` 结果。

**Q3 修复：**

- A. 修 collector / fallback 链
- B. 调 `required_source_categories`
- C. 仅记 plan，等数据源恢复
- D. Other

### diff / 裸读 evolved 键

**Q1：** 新代码是读 `settings.get("macro_veto")` 还是已用 helper？

**Q3 修复：**

- A. 改为 `threshold_default(settings, "macro_veto")`
- B. 改为 `effective_settings()` 再读
- C. 该键改为 fixed 模式并写文档
- D. Other

---

## 「全面解决方法」验收清单

每条 finding 的 Bug Fix Plan 必须填满：

| # | 项 | 必填 |
|---|-----|------|
| 1 | **Root cause**（一句话 + 文件/函数） | ✓ |
| 2 | **Fix diff 范围**（哪些文件、不改什么） | ✓ |
| 3 | **Harness 动作**（memory/policy/playbook/plan 或「无」） | ✓ |
| 4 | **测试**（新增/修改的 test 名） | ✓ |
| 5 | **验证命令**（copy-paste 可跑） | ✓ |
| 6 | **回归风险**（列出 1–2 条） | ✓ |
| 7 | **Done 条件**（rerun walk 哪条 finding 消失） | ✓ |

---

## Bug Fix Plan 输出模板

```markdown
## Bug Fix Plan — <finding title>

- **Finding:** [<severity>] <area> — <detail>
- **Root cause:** …
- **Fix:** …
- **Harness:** …
- **Tests:** …
- **Verify:**
  ```bash
  …
  ```
- **Regression:** …
- **Done when:** open_high 中 `<finding key>` 消失 / plan 条目 `<id>` closed
```

Grill 结束后：若用户确认，**再动代码**；修完必须 `run_walk.py` + P3 pytest。

---

## 与 harness 的衔接

Grill 阶段产生的 **policy/plan** 结论，在实现前可写入 harness plan（可选）：

```python
from agent_reach.daily_run.code_walk_harness import external_review_to_findings, findings_to_harness_evidence
# 将 Bug Fix Plan 中「待办验证步骤」转为 plan 条目，供下次 walk 检查
```

已修复且验证通过的模式 → **playbook**（与 auto_fix 成功同理）。
