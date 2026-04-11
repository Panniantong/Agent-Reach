# Release Flow

Use this order for approved Agent Reach maintenance work.

## 1. Preflight

- inspect `git status --short --branch`
- confirm the approved proposal slice
- identify the affected public surfaces
- note whether the user asked for tests, smoke checks, push, and reinstall

## 2. Edit

- inspect adjacent code before patching
- use focused edits and keep unrelated diffs untouched
- update docs or metadata only where the changed surface actually requires it

## 3. Validation Modes

- `none`
  Use when the user explicitly says tests are not needed. skip test execution and say so in the final report.
- `targeted`
  Use for local unit tests, lint, or CLI smoke checks tied to the changed surface.
- `broader`
  Use only when the patch is cross-cutting enough that targeted checks are not credible.

## 4. Commit And Push

- stage only intended files
- review `git diff --cached --stat`
- use one focused commit message
- push the current branch unless the user asked for a different target

## 5. Reinstall After Push

When the user wants the latest pushed build reflected externally:

1. get the pushed commit with `git rev-parse HEAD`
2. reinstall with `uv tool install --force git+https://github.com/iwachacha/Agent-Reach.git@<commit>`
3. rerun `agent-reach skill --install`
4. run lightweight smoke commands only if requested or clearly warranted

## 6. Final Report

Include:

- what changed
- what was intentionally left out
- whether validation was run or intentionally skipped
- pushed commit or branch
- reinstall result when performed
