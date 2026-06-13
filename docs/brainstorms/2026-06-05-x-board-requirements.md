---
title: "X Board — a simple local frontend to view fetched X posts"
type: requirements
status: ready-for-planning
date: 2026-06-05
---

# X Board — a simple local frontend to view fetched X posts

## Problem / Context

Agent-Reach's Twitter/X access is now installed and verified, but the only proof
is CLI output (`scripts/verify_twitter.ps1`, raw `twitter` commands). The user
wants a **visual** way to (a) confirm fetching is genuinely working and (b) read
recent posts from a small, hand-picked set of people — in one glance.

Agent-Reach today is a CLI + library + MCP "glue layer" with **no frontend**.
The fetch path is 100% Python (`twitter-cli` → `curl-cffi` → x.com's own API →
JSON); no LLM is involved in fetching. This feature is a thin **view** over that
same Python-fetched data — it must not reimplement fetching or add an LLM.

## Goal

A small, standalone **"X Board"**: one command reads a follow-list, fetches each
person's recent original posts via the existing `twitter-cli`, and writes a
self-contained HTML page (auto-opened in the browser) that both **displays the
posts** and **proves the fetch worked**. Re-running the command refreshes it.

## Users

- **Primary (only):** the repo owner, running locally on their own machine. Single-user, local-only. No auth, no hosting, no sharing in v1.

## Success Criteria

- Running one command produces an HTML page showing recent original posts for every handle in the follow-list, opened in the default browser.
- The page makes it unambiguous that real data was fetched: a per-account "N posts fetched" badge and a top-level status line (overall OK + account count + timestamp).
- If a handle fails (suspended / rate-limited / network / bad handle), that is visible per-account as an error card — the rest of the page still renders.
- No new credentials, no LLM calls, no long-running server. Uses the cookies already stored in `~/.agent-reach/config.yaml`.

## Requirements

### Follow-list
- **R1.** The set of people is read from a plain-text file the user edits — one `@handle` per line (leading `@` optional). Blank lines and `#` comments ignored.
- **R2.** Default file location is `~/.agent-reach/follow.txt`, overridable (e.g. a `--file` argument). If the file is missing, the tool prints a clear message and how to create it (with a sample line), and exits non-zero.

### Fetch
- **R3.** For each handle, fetch that person's recent **original** posts — excluding pure replies and reposts. Default ~10 per person, configurable (e.g. `-n`).
- **R4.** Fetching goes through the existing `twitter-cli` (e.g. `user-posts`/equivalent with `--json`); cookies are loaded from `~/.agent-reach/config.yaml` and passed via the `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` env vars, mirroring `scripts/verify_twitter.ps1`. No direct HTTP/scraping is written here.
- **R5.** Reply/repost exclusion is applied client-side from the returned JSON if the CLI does not filter it, so behavior is consistent regardless of CLI flags.
- **R6.** A per-handle failure (suspended, rate-limited, network error, unknown handle, empty result) is captured and surfaced for that account without aborting the whole run.

### Output / view
- **R7.** The tool writes a single self-contained HTML file (inline CSS, no external assets/CDN) and opens it in the default browser. Default output path `~/.agent-reach/x-board.html`, overridable.
- **R8.** Layout is **grouped by account**: one section per handle, each with a header showing the handle, display name if available, and a "N posts fetched" badge. Posts show text, relative time/date, and like/repost counts; a permalink to the post on x.com when available.
- **R9.** A top status bar shows overall result (✅ all OK / ⚠️ partial — M of N accounts), the account count, and the fetch timestamp.
- **R10.** The page degrades gracefully: accounts with errors render an error card with the reason and a hint (e.g. "cookies may be stale — re-run `configure twitter-cookies`").

### Delivery / non-functional
- **R11.** Ships as a standalone script `scripts/x_board.py`, runnable via the Agent-Reach venv on any OS. No new runtime dependencies beyond what the venv already has (`twitter-cli`, plus stdlib for HTML; `rich` optional for console progress).
- **R12.** Read-only and side-effect-free except for writing the HTML output file. No posting/liking/following; no database; no telemetry; no network beyond `twitter-cli`'s own calls.
- **R13.** Does not modify Agent-Reach or upstream source; lives only under `scripts/`. Credentials are never written to the output file (no tokens embedded in the HTML).

## Key Decisions

- **Static HTML report over a live web app or TUI.** Smallest form that delivers both "proof" and "reader" value; no server process, near-zero carrying cost. Re-running the command is an acceptable "refresh." (Live web app + Refresh button deferred.)
- **Editable follow-file over auto-pulling the account's real X following list.** Matches "give it a few people to follow," keeps the user in control, avoids large/noisy lists and an extra fetch. (Auto-pull deferred.)
- **Original posts only (no replies/reposts).** Cleanest to read; article-announcement posts still appear as normal posts. (Reposts/replies deferred.)
- **Grouped-by-account layout.** The per-account "N posts fetched" badge is the proof signal; also reads naturally. (Merged chronological feed deferred.)
- **Files live under `~/.agent-reach/`, not the repo.** Keeps the git clone clean (consistent with how cookies/config are already stored).
- **Reuse `twitter-cli`, mirror the `verify_twitter.ps1` cookie-loading pattern.** Stays a glue layer; no reimplementation of fetching; no LLM.

## Scope Boundaries

### In scope (v1)
- Read follow-file → fetch original posts per handle → render grouped HTML with proof badges + status bar → open in browser, with per-account error handling.

### Deferred (easy to add later, no rework)
- Live local web app with a Refresh button; merged chronological feed; image/video/media thumbnails; auto-refresh or scheduled runs; in-page search/filter; including reposts & replies; pulling the account's real following list; per-person "articles" beyond what appears in the timeline.

### Out of scope
- Any write actions (post / like / follow / bookmark) — strictly read-only.
- Persisting a post-history database or caching across runs.
- Multi-user, hosting, or remote/shared access.
- Re-implementing X fetching or adding any LLM/AI step to the fetch or render.

## Assumptions / Dependencies

- Twitter/X is already configured and working (`twitter status` → `ok: true`); cookies in `~/.agent-reach/config.yaml`. If cookies are stale, accounts will error and the page will say so.
- `twitter-cli` can list a user's posts as JSON; exact subcommand/flags and the JSON shape are an **implementation-time detail for `/ce-plan`** (confirm `user-posts` flags and fields). If reply/repost filtering isn't available as a flag, filter client-side (R5).
- Network access from this machine works for `twitter-cli` (already verified for search).

## Open Questions (non-blocking — sensible default chosen)

- Exact relative-time formatting and whether to show avatars (avatars need image URLs from the JSON; default: text-only, no remote images, to keep the page self-contained). Resolve during planning.

## Handoff

Ready for `/ce-plan` (or `/ce-work` for a direct build). Suggested first
implementation reference: `scripts/verify_twitter.ps1` (cookie loading + venv
PATH + `twitter-cli` invocation pattern), `agent_reach/config.py` (config keys),
`agent_reach/channels/twitter.py` (how Agent-Reach shells out to `twitter`).
