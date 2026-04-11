---
name: agent-reach-maintain-release
description: Safely implement approved Agent Reach maintainer changes. Use when Codex should apply only already-approved proposal slices, keep public surfaces and packaged skills consistent, optionally run requested validation, then commit, push, and reinstall the latest exact ref when asked.
---

# Agent Reach Maintain Release

Carry approved Agent Reach maintenance changes through implementation and shipping.

## Workflow

1. Read [references/change-boundaries.md](references/change-boundaries.md) before editing.
2. Read [references/release-flow.md](references/release-flow.md) before commit, push, or reinstall.
3. Inspect `git status`, affected modules, and existing overlap before editing.
4. Implement only the approved slice. If new policy questions appear, stop and switch back to proposal review.
5. Keep versioning, docs, export metadata, packaged skill metadata, and tests consistent with the changed surface.
6. Run only the validation the user asked for, plus any minimal checks needed to avoid shipping a clearly broken state. If the user explicitly says no tests, skip test execution and say so.
7. Before push, stage only intended files and review the diff.
8. If the user asked for shipping, commit, push, reinstall from the pushed exact commit or ref, rerun `agent-reach skill --install`, and do a lightweight smoke check when requested or clearly warranted.

## Guardrails

- Never implement rejected or deferred proposal pieces.
- Never widen caller-policy ownership during "small" maintenance work.
- Never push unrelated dirty-tree changes.
- Prefer exact-commit reinstall commands after push.
- If push or reinstall fails, report the exact stopped state instead of improvising.

## References

- Scope and consistency checks: [references/change-boundaries.md](references/change-boundaries.md)
- Commit, push, reinstall flow: [references/release-flow.md](references/release-flow.md)
