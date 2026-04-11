# Review Output

Use this shape when reporting proposal decisions.

## Per-Proposal Record

- `proposal`: short label
- `decision`: `adopt_now` | `reject` | `defer`
- `why`: concise rationale tied to Agent Reach policy and existing repo surfaces
- `boundary`: smallest safe implementation slice, or `none`
- `touchpoints`: files, commands, schemas, docs, or skills likely to change
- `verification`: `none` | `targeted` | `broader`

## Bundle Rule

Only combine proposals into one implementation group when all of these are true:

- they share one thin primitive or one release boundary
- they do not mix accepted and deferred policy questions
- they can be explained as one focused patch

Otherwise, keep them separate.

## Implementation Handoff

When at least one proposal is `adopt_now`, hand off only:

- the approved proposal labels
- the explicit patch boundary
- the likely touchpoints
- the expected verification level

Do not hand off rejected or deferred ideas as "nice to have" extras.
