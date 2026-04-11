# Policy Tests

Use these checks before adopting any Agent Reach proposal.

## Fast Accept Signals

- The change exposes an existing capability more clearly without taking caller-owned decisions away.
- The change adds neutral metadata, diagnostics, schema clarity, or ledger ergonomics.
- The change adds an explicit opt-in helper for packaging, maintenance, or bounded collection.
- The change removes repeated maintainer friction without inventing new workflow policy.

## Fast Reject Signals

- The feature chooses source mix, routes, ranking, summarization, or posting policy for the caller.
- The feature silently deep-reads, fans out, auto-escalates, or auto-retries in a way that changes collection policy.
- The feature adds normalized importance, trust, impact, or recommendation scores instead of preserving raw signals.
- The feature hides real channel differences behind fake required operations or empty adapters.
- The feature creates a second orchestration path where `collect`, `batch`, `plan candidates`, or `ledger` already cover the need.

## Split-When-Possible Rule

If a proposal contains both:

- a thin primitive
- and a policy layer

keep only the thin primitive. Reject or defer the policy layer.

Examples:

- Keep neutral extraction diagnostics, reject content-quality scoring.
- Keep bulk input parsing if it is explicit and bounded, reject hidden fan-out defaults.
- Keep raw source metrics, reject cross-channel impact normalization.

## Overlap Checks

Before adopting, search whether the repo already provides the idea through:

- `agent-reach collect --json`
- `agent-reach doctor --json`
- `agent-reach channels --json`
- `agent-reach batch`
- `agent-reach plan candidates`
- `agent-reach ledger *`
- `agent-reach schema collection-result --json`
- `agent-reach export-integration --client codex --format json`
- bundled skills under `agent_reach/skills`

If a close surface already exists, prefer extending that surface instead of creating a parallel command or mode.

## Cross-Cutting Changes

Treat these as defer-by-default unless the value is unusually clear and the implementation stays bounded and observable:

- transparent retries or backoff
- global interface normalization across channels
- new automatic multi-step workflows
- packaging or install changes that affect every downstream user

## Decision Bias

When the tradeoff is ambiguous, bias toward:

- `reject` if the proposal broadens ownership
- `defer` if the idea may be useful but needs sharper boundaries
- `adopt_now` only when the patch can stay thin, explicit, and local
