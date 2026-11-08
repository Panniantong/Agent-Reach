# Dedicated browser and release policy implementation plan

**Goal:** Respect all eight user rules and fix the five reviewed defects, without claiming a release or a channel pass from unit tests.

**Architecture:** Keep one Reach-owned Cloak profile and watcher. Keep the verified official OpenCLI 1.8.7 Bridge path. The user approved Bridge supervision bound to the dedicated browser lifetime after official 2.0.1 CDP failed the new Xiaohongshu layout. Personal-browser login is never inspected. Browser login happens only in this profile. BOSS detail uses an existing upstream browser-backed action. Owned paths and failed cleanup remain visible in the local ledger.

**Tech stack:** Python standard library, existing CloakBrowser SDK, untouched OpenCLI and boss-agent-cli.

1. Reproduce the reviewed issues; record facts and limits. Work on a feature branch, never main. Keep unrelated local API/research files out of commits and packages.
2. Remove external cookie import/profile discovery and all writes to other programs' configuration. Keep dedicated saved sessions and explicit user login. Replace misleading login hints.
3. Verify OpenCLI direct CDP against the owned browser. Keep automatic prepare/reopen, record its compatibility result, and supervise the verified Bridge route without spawning CLI discovery or background update checks. The watcher observes real browser activity and explicit login time.
4. Fix BOSS ZIP provenance reuse. Route detail through an upstream browser adapter. Never modify upstream files or silently upgrade an existing dependency.
5. Make removal fail before deleting channel registration when site cleanup fails. Clear observed subdomain origins and validate the result; preserve other sites. Restrict deletion to recorded owned paths and skill files/links.
6. Separate the latest real official release install from unreleased candidate installation. Add an executable release gate requiring real per-action channel evidence; pending/blocked channels prevent release. No tag, merge or release this turn.
7. Run discriminating regressions, full tests, lint/types, and owned-browser live checks. Stop on verification/rate-limit errors. Build a sanitized candidate with an explicit pending-channel record, update the PR as draft, and report what passed and what did not.
