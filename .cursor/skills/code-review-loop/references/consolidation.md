# Consolidation Rules

After all review agents return:

1. **Deduplicate** — same file:line + same root cause → keep richest finding.
2. **Sort** — critical, high, medium, low.
3. **Summary block** — counts, agents run, diff scope, overall assessment (1 paragraph).
4. **Write** — `reviews/review-<review_id>.md` only the parent agent writes; subagents return text only.
5. **User table** — max 15 rows in chat; link to full markdown file for the rest.

## Severity guide

| Level | When |
|-------|------|
| critical | Data loss, security exploit, wrong money/trade decision, production crash |
| high | Audit bypass, missing tests on core path, harness overlay broken |
| medium | Maintainability, missing docs, suboptimal pattern |
| low | Style, nit, optional polish |

## Address phase

For each finding record in `## Addressed`:

```markdown
- [fixed|skipped|deferred] path:line — one line rationale
```
