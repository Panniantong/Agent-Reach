# Diff Review Agent Prompt

Borrowed from claude-review-loop `stop-hook.sh` Agent 1.

## Scope

Run `git diff`, `git diff --cached`, and `git diff main...HEAD` (or merge-base with base branch).
Review **changed code only**.

## Criteria

### Code Quality
- Modular, readable, DRY
- Names consistent with codebase
- Right abstraction level — not over/under-engineered

### Test Coverage
- New behavior has tests; edge cases and error paths covered
- Tests assert behavior, not implementation trivia
- Bug fixes include regression tests

### Security (OWASP-oriented)
- Input validation and sanitization
- Auth on protected paths
- Injection (SQL, XSS, command, path traversal)
- No secrets in code or logs
- Safe error messages (no stack traces to users)

## Output format

Each finding:

```
severity: critical|high|medium|low
category: Diff|Security
location: path:line
description: ...
suggested_fix: ...
```
