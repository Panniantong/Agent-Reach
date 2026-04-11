---
name: agent-reach-maintain-proposals
description: Evaluate proposed changes to Agent Reach itself. Use when Codex needs to review external research findings or other AI-generated improvement ideas against Agent Reach's thin-interface policy, caller-control rules, existing features, and packaged surfaces, then decide adopt_now, reject, or defer before any edits.
---

# Agent Reach Maintain Proposals

Review proposed changes to Agent Reach before code changes.

## Workflow

1. Read [references/policy-tests.md](references/policy-tests.md) to apply hard accept and reject rules.
2. Read [references/review-output.md](references/review-output.md) to keep the decision record compact and reusable.
3. Inspect the current repo surface before judging overlap. Check `README.md`, `agent_reach/integrations/codex.py`, the relevant CLI or adapter modules, and existing skills when needed.
4. Judge each proposal independently first. Only bundle accepted items when they clearly share one thin primitive or one release boundary.
5. If at least one item is `adopt_now`, define the smallest safe implementation slice before editing.

## Core Rules

- Keep Agent Reach thin. The caller owns scope, routing, ranking, summarization, publishing, and selection.
- Prefer explicit opt-in flags, neutral metadata, contract clarity, install ergonomics, and ledger ergonomics.
- Prefer new primitives that expose capability or diagnostics over features that decide what the caller should do next.
- Reject silent fan-out, hidden deep reads, automatic source prioritization, impact or trust scoring, and auto-expansion from narrow asks.
- Reject or defer proposals that mostly duplicate `collect`, `doctor`, `channels`, `batch`, `plan candidates`, `ledger`, or existing diagnostics.
- If a proposal mixes a good primitive with a caller-policy layer, split it and only adopt the primitive.
- When uncertain, choose `reject` or `defer`, not a broadened implementation.

## Output

For each proposal, return:

- `decision`: `adopt_now`, `reject`, or `defer`
- `why`: 1-3 sentences tied to policy and existing surfaces
- `boundary`: smallest safe patch scope if adopted, otherwise `none`
- `touchpoints`: likely files or surfaces
- `verification`: `none`, `targeted`, or `broader`

Do not start editing unless the user also wants implementation or already approved the adopted slice.

## References

- Policy and overlap checks: [references/policy-tests.md](references/policy-tests.md)
- Review record shape: [references/review-output.md](references/review-output.md)
