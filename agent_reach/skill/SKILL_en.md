---
name: agent-reach
description: >
  Use when the user names a supported platform, shares its URL, or asks to configure or diagnose its channel:
  Xiaohongshu, Bilibili, Twitter/X, Reddit, Facebook, Instagram, YouTube
  (subtitles, transcripts), V2EX, Xueqiu stock quotes,
  GitHub, LinkedIn / Boss Zhipin jobs, or when your built-in web search / fetch
  is missing or fails. Read-only: never post, comment, like, or log in on the
  user's behalf.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

One command for every platform: `agent-reach`. Read-only; output is always one JSON object.

## Usage

Route by intent: named platform → channel action; platform URL → `read`; setup, login, import or logout → read [Sessions](references/sessions.md); failures, updates or uninstall → read [Maintenance](references/maintenance.md). Ordinary queries need neither reference.

For a one-sentence request to search and summarize, use MCP `reach_execute` or `agent-reach ask "request"` when a model is configured. The runtime prepares the channel and returns `required_action` plus `operation_id` when the user must log in. Continue with `reach_resume` or `agent-reach resume OPERATION_ID` after they finish.

```bash
agent-reach channels                      # actions and params per channel (run this when unsure)
agent-reach ask "find and summarize..." # one-sentence model entry
agent-reach ensure <channel>             # setup, authorized reuse, live check
agent-reach <channel> <action> [args]     # e.g. agent-reach reddit search "rust async" --limit 5
agent-reach read <url>                    # picks the channel from the URL
```

Results:

- `ok: true` → content in `items`; each has `title / url / author / published_at / text`, upstream data in `raw`.
- `ok: false` → branch on `error.code` and follow `error.hint`:

| error.code | What to do |
|---|---|
| `NEED_SETUP` | Call `reach_ensure` or `agent-reach ensure <channel>` |
| `NEED_LOGIN` | The user logs in; keep `operation_id` and call `reach_resume` |
| `UPSTREAM_BROKEN` | Channel is down right now; tell the user, don't retry in a loop |
| `TIMEOUT` / `RATE_LIMITED` | Retry later |
| `NOT_FOUND` / `BAD_INPUT` | Check the link or args; run `agent-reach channels` if needed |

## Rules

1. For a named platform or platform URL, use its channel. For general web queries, prefer existing web tools; `web` is a fallback.
2. Say "using agent-reach channel X" before you start.
3. Serialize commands sharing one browser profile; independent sessions may run in parallel.
4. Read only. Never post, comment, or like.
5. Never extract login state implicitly. Explicit authorization permits importing only the selected site's state. Never output cookies, tokens or credentials. Do not ask again for existing authorization.

## Channels

{{CHANNEL_TABLE}}

`default` channels work right away; others need `agent-reach add <channel>` first. Default channels can be removed too; updates never add a removed one back.

## Reuse before login

Cloak uses `headless=True` for queries and import verification. For independent login, run `agent-reach cloak login CHANNEL`; the user logs in and closes the visible window to save the session, then verifies a query. OpenCLI has its own Chrome session. Cookie import is optional.

`setup` and `add` never open a browser. `login CHANNEL` inspects connection options and historical checks only; it does not authenticate or export cookies. Verify existing sessions before asking the user to log in again.

Routes are action-specific: XHS search/read use CloakBrowser → OpenCLI; BOSS search uses CloakBrowser → OpenCLI → boss-agent-cli. BOSS read currently supports only CloakBrowser. Instagram search/profile/posts use CloakBrowser → OpenCLI. See [Sessions](references/sessions.md) for selection, import, native login and logout.

XHS read returns text descriptions, not image/video understanding. Never guess BOSS salary digits when salary_encoded=true; read the job detail instead.

Stop on PLATFORM_BLOCKED/RATE_LIMITED/NEED_LOGIN/BUSY. Serialize commands sharing a profile. Use `check CHANNEL --search` for live verification. See [Maintenance](references/maintenance.md) for dependency repair and distribution. Never modify dependencies during queries.

## When the user wants to manage Agent Reach

| User asks | You run |
|---|---|
| Status / what works | `agent-reach doctor --text` (for a live test, `agent-reach check <channel> --search --text`) |
| Add a platform ("add Xiaohongshu") | `agent-reach add <channel>`; one command installs everything it needs. Tell the user only what they must do: follow the login instructions (`agent-reach login <channel>`), or provide a key |
| Login expired | Read Sessions first; `agent-reach login <channel>` only inspects by default. The user performs login |
| Remove a platform / log out | `agent-reach remove <channel>`; read Sessions before logout. `agent-reach logout <channel>` removes a managed Cloak session |
| Upgrade / update | Read [Maintenance](references/maintenance.md), check the installation source, then update from the same source |
| Uninstall | show `agent-reach uninstall --dry-run` first, then `agent-reach uninstall` once they confirm |
| Another AI should use it | `agent-reach skill link <that AI's skills folder>`; `agent-reach skill` shows where it is placed now |

First install: `agent-reach setup`.

## When there is a new version

Any result with `meta.update` means a newer version exists. Mention it once per conversation, in the user's language and plain words:

1. Agent Reach has a new version (`meta.update.latest`).
2. What changed: 1 to 3 short points taken from `meta.update.notes`.
3. Ask whether to update.

After the user agrees, read [Maintenance](references/maintenance.md) and confirm the installation source. Update from the same source, then report the actual changes and remaining user actions.

Facebook search uses CloakBrowser then OpenCLI; profile uses OpenCLI. Cloak login is independent; site-cookie import is optional.
