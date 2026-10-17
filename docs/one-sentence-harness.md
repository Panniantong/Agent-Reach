# One-sentence channel harness

## User contract

The user can request a read-only search in one sentence. The local model chooses a
declared channel/action and parameters. Reach prepares the machine, runs the
normal channel route once, and the model summarizes the returned evidence.

```
user -> ask / external agent -> Reach MCP -> flow.prepare -> declared backend
                                  |                  |
                                  +-> flow.execute -> local check evidence
                                  +-> pending operation -> flow.resume
```

The same `flow` functions back `ensure`, `execute`, `resume` and the MCP tools.
The Skill only maps intent to these entries and explains a `required_action`.
The model cannot select arbitrary executables or undeclared channel methods.

## Decisions

**ADR 1: shared in-process runtime.** CLI and stdio MCP call the existing Python
runtime. This reuses backend priority, parameters, result envelopes, timeouts,
and session locks. A separate orchestration service would duplicate those
rules and add a process to install and maintain. The tradeoff is that the MCP
server and CLI share the Python tool environment.

**ADR 2: scoped reuse grants.** `ensure CHANNEL --reuse-profile ID` stores a
grant for one site in `~/.agent-reach/state.json`; `--forget-source` revokes it.
Reach uses an already configured Cloak profile first. If an authorized source
is recorded, it can import that site's cookies through the connected OpenCLI
Bridge. If no grant exists, a connected OpenCLI fallback may execute directly.
The user completes login and platform verification. The tradeoff is that a
Bridge must be installed to migrate from Chrome; Cloak's own login and
execution do not depend on it.

**ADR 3: persisted operations and evidence.** A request paused for login is
stored with an operation ID in the private state file. `resume` rechecks the
session and runs the original action. For a request started with `ask`, it also
finishes the original summary; a temporary model failure can be retried with
the same operation ID without running the site query again. Results are recorded per action with
backend, time, item count and a build/tool/browser/network fingerprint. Records
expire after 24 hours or a relevant environment change. This is a local
single-machine design; a SaaS scheduler would replace state storage and the
operation lock, keeping the same action API.

## Failure behavior

- Missing dependency: `ensure` installs the declared primary backend once.
- Missing session: return `needs_user_action`, top-level `required_actions`,
  and a resumable operation ID. Summarization waits for the login step.
- Mixed success and tool failure: return `partial` with the successful sources
  and the failed channel in `results`, without claiming all channels passed.
- Phone verification or platform block: stop the route; user resolves it in
  the official page.
- Rate limit: cache a one-hour channel cooldown and return
  `retry_after_seconds`; do not switch accounts or repeatedly retry. Both
  import verification and normal queries use this gate.
- Tool/network failure: return the structured error and backend attempts.
- Empty success: record it as failed verification, never as `ready`.

`configured`, `prepared`, and `ready` are distinct. `ready` requires at least
one nonempty result from the formal Reach action. A pilot script does not
qualify. Pending queries remain private to this machine and expire after seven
days; at most 32 are retained.

## Interfaces

```text
agent-reach configure model-key --stdin
agent-reach configure model-base-url https://your-provider.example/v1
agent-reach configure model-name YOUR_MODEL
agent-reach ask "帮我去小红书找深圳数据平台的笔记并总结"
agent-reach ensure boss --reuse-profile CONTEXT_ID
agent-reach resume OPERATION_ID
agent-reach mcp
```

The MCP tools are `reach_status`, `reach_ensure`, `reach_execute`, and
`reach_resume`. `reach_execute` accepts only a declared channel action and
parameter object. The model key is read from the private config or
`AGENT_REACH_MODEL_KEY`; no key or site cookie is returned in tool results.

## Acceptance gates

1. Cold install on Mac and Windows, with no previous Reach state.
2. Existing browser source chosen explicitly, then recorded for each site.
3. Cloak and OpenCLI can each execute with their own session.
4. Restart the agent during a login pause; resume with the same operation ID
   and receive the requested summary, not only raw search results.
5. Verify a real result through CLI and MCP, including an item URL.
6. Repeat after a tool/build/network change and confirm the old check becomes
   unverified.

Platform logins, CAPTCHAs, and phone verification remain user steps. Search
availability also depends on the platform and current network route.
