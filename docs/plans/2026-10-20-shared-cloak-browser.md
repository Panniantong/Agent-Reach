# Shared dedicated browser implementation and acceptance

**Goal:** Ship the user-confirmed 1.6.0 scope with one Reach-owned browser, upstream extraction, and predictable setup/login/removal.

**Architecture:** Keep the existing browser watcher and 600-second idle timeout. Prefer CloakBrowser's public persistent-context launcher in its private Python environment; use system Chrome when the Cloak installation/download fails. All browser channels share `~/.agent-reach/browser/profile`. OpenCLI's own extension and adapters handle website extraction; BOSS uses its upstream CLI against this same browser.

## Changes and acceptance

1. Remove the Reach MCP server/registration, model planner, local OpenCLI patch command, and handwritten website extraction workers. Keep deterministic CLI preparation/execution/resumption without a model key.
2. Restore upstream Xiaoyuzhou channel/script, version 1.6.0, official-release install and `agent-reach update` instructions. Keep public-first routing and the compact installation receipt.
3. Restore automatic dedicated-browser preparation/reopening. Prefer one shared Cloak profile, load OpenCLI automatically, keep the watcher responsible for cleanup, and retain a clear Chrome fallback.
4. Browser-channel add installs Node, OpenCLI, browser runtime and extension. BOSS uses the same dedicated endpoint. Remove clears only the removed site's browser data, native session and saved import authorization.
5. Login reuse is an explicit, site-scoped import from a user-selected connected profile or local state file. Never read Chrome's cookie database; never disclose cookies. Existing Reach-owned per-site snapshots merge once without overwriting newer shared cookies. No indefinite import grant.
6. Add meaningful tests for cold start/reopen, shared profile, idle shutdown, Chrome fallback, extension loading, dependency completeness, site-only removal, login import authorization and removal of retired commands.
7. Run focused tests, full tracked test suite, lint/type checks, wheel inspection, and live local browser/OpenCLI acceptance. Record live failures separately from unit-test success. Preserve all untracked API/research work and original source-browser data.

## Live acceptance record

387 local core tests, Ruff and Mypy passed. Live Xiaohongshu search/read/comments, explicit session import, scoped cleanup and shortened idle/reopen tests passed. BOSS returned PLATFORM_BLOCKED and requires manual verification. Browser creation and test imports are authorized by the user's current implementation request. Do not mark a platform authenticated merely because cookies were copied; verify with the upstream channel action. Do not send messages, submit applications, post comments, or otherwise write to platforms.
