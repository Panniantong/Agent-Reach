# Change Boundaries

Keep maintenance patches inside the approved scope.

## Must-Stay-True Rules

- Agent Reach stays a thin capability and diagnostics layer.
- The caller still owns scope, routing, ranking, summarization, publishing, and final selection.
- Prefer extending an existing surface over adding a second parallel workflow.
- Prefer neutral metadata over interpreted scores.
- Keep maintainer convenience explicit and bounded.

## Scope Control

- Implement the smallest approved slice first.
- Split mixed proposals instead of sneaking in "while we're here" extras.
- Do not refactor unrelated modules unless required to land the approved slice safely.
- If a change reveals a new policy decision, stop and review it explicitly instead of burying it inside the patch.

## Consistency Checklist

When the public or packaged surface changes, review whether these also need updates:

- `README.md`
- install or downstream docs under `docs/`
- `agent_reach/integrations/codex.py`
- packaged skill metadata and references
- version and changelog files
- tests that lock exported names or skill lists

## Maintainer-Only Bundles

Bundled maintainer skills may ship with the public package, but label them as maintainer-only in docs and guidance. Do not blur them into ordinary downstream collection guidance.
