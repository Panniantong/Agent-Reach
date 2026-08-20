---
name: code-review-loop
description: >-
  Multi-agent code review loop adapted from zjk1984/claude-review-loop.
  Use when the user asks for 代码走读, review-loop, 走读, independent code review,
  or wants implement-then-review cycles with consolidated findings by severity.
---

# Code Review Loop（借鉴 claude-review-loop）

Adapted from [zjk1984/claude-review-loop](https://github.com/zjk1984/claude-review-loop) for Cursor.
Two phases: **implement / inspect** → **parallel review** → **consolidate** → **address** (optional).

Daily-run harness 专用走读仍用 `daily-run-code-walk`；本 skill 负责 **通用 diff + 结构走读**。

---

## When to use

| 用户说法 | 动作 |
|---------|------|
| `/review-loop`、review-loop、走读循环 | 启动完整 loop |
| 代码走读、帮我 review 这批改动 | 至少跑 Review 阶段 |
| 实现完帮我二审 | Task 完成后进入 Phase 2 |
| daily-run harness / portfolio 进化 | 改用 `daily-run-code-walk` |

---

## Phase 0 — Setup（首次或新任务）

1. 确认仓库根目录 `REPO_ROOT`（绝对路径）。
2. 生成 review id：`YYYYMMDD-HHMMSS-<6hex>`（例：`20260820-143000-a1b2c3`）。
3. 创建目录：`mkdir -p reviews .cursor`
4. 可选状态文件 `.cursor/review-loop.local.md`：

```markdown
---
active: true
phase: task
review_id: 20260820-143000-a1b2c3
started_at: 2026-08-20T06:30:00Z
---

<用户任务或 diff 范围说明>
```

5. 确定 diff 范围（默认 **branch changes** vs `main`；用户指定则用 uncommitted / 指定 base）。

---

## Phase 1 — Task / Inspect

- 若用户已给出实现任务：先完成实现，再进入 Phase 2。
- 若用户只要走读：跳过实现，直接 Phase 2。
- 完成标准：相关测试已跑（至少 `python3 -m pytest -q` 针对改动模块），无已知 blocker。

---

## Phase 2 — Parallel review agents（核心，借鉴 review-loop）

**必须并行**启动子 agent（`Task` tool，`run_in_background: false`），最多 4 路：

| Agent | 何时跑 | subagent_type | 焦点 |
|-------|--------|---------------|------|
| **Diff Review** | 始终 | `generalPurpose` | `git diff` 变更：质量、测试、OWASP |
| **Holistic Review** | 始终 | `explore` | 目录结构、AGENTS.md、架构、agent harness |
| **Domain Review** | 有 daily-run 改动 | `explore` | harness_policy / intraday / snapshot / audit 一致性 |
| **Test Review** | 有 tests/ 改动 | `generalPurpose` | 测试是否覆盖真实行为、非 trivial assert |

每个 agent prompt 必须包含：

```text
Full Repository Path: <REPO_ROOT>
Review ID: <review_id>
Output: structured findings only (no file writes)

For each finding return:
- severity: critical | high | medium | low
- category: Diff | Holistic | Domain | Test | Security
- location: path:line or directory
- description: 1-3 sentences
- suggested_fix: concrete action

Focus: <见 references/*.md>
Diff scope: branch changes | uncommitted changes
Base branch: main (omit if uncommitted)
```

Prompt 模板见 [references/diff-review.md](references/diff-review.md)、[references/holistic-review.md](references/holistic-review.md)。

**不要**在 Phase 2 自行修代码；只收集 findings。

---

## Phase 3 — Consolidate

1. 合并各 agent 结果，**去重**（同文件同行保留描述最完整的一条）。
2. 按 severity 排序：critical → high → medium → low。
3. 写入 `reviews/review-<review_id>.md`，结构：

```markdown
# Code Review — <review_id>

## Summary
- Total: N | critical: … | high: … | …
- Agents: Diff, Holistic, …
- Diff: branch changes vs main

## Findings

### [critical] path:line — category
**Description:** …
**Suggested fix:** …

…
```

4. 向用户展示 **紧凑表格**（与 review-bugbot 一致）：

| Severity | Location | Finding |
|----------|----------|---------|

5. 更新 `.cursor/review-loop.local.md` → `phase: addressing`（若存在）。

---

## Phase 4 — Address（用户要求修时）

对每个 finding **独立判断** agree / skip：

- **Agree + critical/high**：必须修或给出明确 plan。
- **Agree + medium/low**：修或记入 plan。
- **Disagree**：一行说明理由，不盲目采纳。

修完后：

1. 重跑相关 pytest。
2. 可选：仅对 **变更文件** 再跑 Diff Review（单 agent）。
3. 在 review 文件末尾追加 `## Addressed` 小节。
4. 删除或归档 `.cursor/review-loop.local.md`（`active: false`）。

**默认**：Phase 3 结束后停止，不自动修，除非用户说「修」/「doit」。

---

## Cancel

用户说 cancel / 取消走读：删除 `.cursor/review-loop.local.md`，保留 `reviews/` 历史。

---

## 与现有 skill 分工

| Skill | 用途 |
|-------|------|
| **code-review-loop**（本 skill） | 通用 multi-agent diff + 结构走读 + 可选 fix loop |
| **daily-run-code-walk** | daily-run harness 进化、portfolio 真源、AST 裸读扫描 |
| **review-bugbot** | Cursor Bugbot 单路 review |
| **review-security** | 安全专项 subagent |

推荐组合：daily-run 功能改动 → 先 `run_walk.py`（harness）→ 再本 skill Phase 2–3（通用质量）。

---

## Definition of Done

- [ ] 至少 Diff + Holistic 两路 review 已并行完成
- [ ] `reviews/review-<id>.md` 已写入且含 summary
- [ ] 用户可见 severity 表格
- [ ] 若进入 Phase 4：pytest 通过 + Addressed 小节已更新

---

## Credits

Inspired by [zjk1984/claude-review-loop](https://github.com/zjk1984/claude-review-loop) (Codex multi-agent + stop-hook lifecycle), adapted for Cursor Task subagents.
