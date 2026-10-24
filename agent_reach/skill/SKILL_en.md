---
name: agent-reach
description: >
  Read-only access to platform content: search, read posts, view comments, fetch subtitles, stock quotes and jobs.
  Use when the user mentions or pastes a link from Xiaohongshu, Bilibili, Twitter/X, Reddit,
  YouTube (subtitles, transcripts), GitHub, V2EX, Xueqiu/stock quotes, LinkedIn/Boss Zhipin jobs,
  Instagram, Facebook or Xiaoyuzhou podcasts; or says "search / look up / read this link" and your built-in
  web search or fetch is unavailable, fails, or misses the body;
  or wants to install, add/remove a platform, log in/out, check status, update or uninstall Agent Reach.
  Does not: post, comment, like, message or any other write; never logs in for the user or asks for passwords.
  Prefer your own tools for public content; Reach fills the gaps.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

One command for every platform: `agent-reach`. Read-only; prints one JSON object by default.

Before acting, say "using the agent-reach skill (channel X)". Once invoked, these rules apply for the whole session.

## Choosing a route

- For public content, use your own search/read tools first (optionally `site:domain`). Check body text, comments and subtitles separately; when they are enough, answer directly without adding channels or logging in.
- Use Reach when your tools are unavailable, the result lacks what the user needs, or the user wants a site action a channel declares. Unsure of actions and params? Run `agent-reach channels`.
- An added channel (a default one, or one added with `add`) sends search/read straight to its site tool. For channels not added yet, search/read first try anonymous public web access; results mark it with `backend: public-web`. `--backend public-web` limits to public web; `--backend <backend>` picks a site tool.
- A platform name or link only identifies the source; it never triggers install or login by itself.
- Snippets, page shells, comment counts and subtitle track lists are not body text, comments or subtitles; say which you have. If the user skips login, still deliver the public results already gathered.

```bash
agent-reach channels                      # actions and params per channel
agent-reach <channel> <action> [args]     # e.g. agent-reach bilibili search "rust async" --limit 5
agent-reach read <url>                    # picks the channel from the URL
```

## Results and errors

- `ok: true` → content in `items`; each has `title / url / author / published_at / text`, upstream data in `raw`.
- `ok: false` → branch on `error.code` and follow `error.hint`:

| error.code | What to do |
|---|---|
| `NEED_SETUP` | Missing dependency or key. Run `agent-reach add <channel>` as hinted; for a key, the user provides it, then `agent-reach configure <key>` |
| `NEED_LOGIN` | Keep existing results and tell the user login is needed; `agent-reach login <channel>` opens the browser and the user logs in themselves. Never log in for them or ask for a password |
| `UPSTREAM_BROKEN` | This platform is temporarily not working; `message` is what was reported. Tell the user which platform is unavailable and roughly why, by platform name, without naming tools; run `agent-reach update` once, after they agree, only if the message points to an outdated tool; never retry in a loop |
| `TIMEOUT` | Check the failed stage and channel status (`agent-reach doctor --text`); do not retry or reopen windows in a loop |
| `RATE_LIMITED` | The platform rate-limited; Reach paused the channel. Wait `retry_after_seconds`; do not switch backends |
| `PLATFORM_BLOCKED` | The platform wants verification (captcha/risk check). Stop; the user resolves it on the official page. Do not switch accounts or backends |
| `BUSY` | The browser stayed full for the 2-minute wait in line, or the user has a login window open. Retry later, or after the user says they are logged in; do not close the window or switch profiles |
| `NOT_FOUND` | Content does not exist; check the link or ID |
| `BAD_INPUT` | Wrong arguments; run `agent-reach channels` for usage |

On `PLATFORM_BLOCKED`, `RATE_LIMITED`, `NEED_LOGIN` or `BUSY`, stop this attempt; do not retry with other accounts, backends or browsers. A network failure or a failure on one machine does not mean "the platform requires login".

## Login and the dedicated browser

All browser channels share one dedicated browser (CloakBrowser preferred, falling back to installed Chrome). It runs headless by default, closes after 10 idle minutes and reopens on the next call. Calls may run in parallel, including from subagents: up to 2 per platform and 4 in total run at once, the rest wait in line, and two searches on the same platform start at least 10 seconds apart.

The first time a site is used, if the user's Chrome is connected to the OpenCLI extension, that site's login is copied once into the dedicated browser and reused afterwards; only that site is copied and the source browser is untouched. Only when the login has expired or there is no source to copy from does the user run `agent-reach login <channel>` and log in themselves. Refreshing, choosing a source and logging out are in [Sessions](references/sessions.md): read it when the user wants to log in, log out or switch accounts, or on `NEED_LOGIN`.

## Platform notes

- Xiaohongshu read returns text descriptions only; never claim to understand the images or video.
- When a Boss Zhipin search result has `salary_encoded=true`, never guess the salary digits; read the job link for the readable salary in the detail.
- What each platform offers publicly and what Reach adds is in [Capability scope](references/capabilities.md): read it when the user asks "what can it get / is it complete" or you need to judge completeness.

## Channels

{{CHANNEL_TABLE}}

`default` channels are installed by default and can be removed; updates never add a removed one back. The `login` column is the authentication entry point, not a prerequisite for public content.

## After installation

After `agent-reach setup`, show `result.installation_report.markdown` to the user as is: no additions, removals, reordering, extra greeting or tables. The program generates it.

## When the user wants to manage Agent Reach

| User says | You run |
|---|---|
| Add a platform | `agent-reach add <channel>`; dependencies install automatically. Tell the user only what they must do (log in or provide a key) |
| Remove a platform | `agent-reach remove <channel>` |
| Log in / login expired | `agent-reach login <channel>`; the user logs in themselves in the window that opens |
| Log out | `agent-reach logout <channel>` |
| Status / what works | `agent-reach doctor --text`; for a live test `agent-reach check <channel> --text` |
| Upgrade / update | `agent-reach update` |
| Uninstall | show `agent-reach uninstall --dry-run` first, then `agent-reach uninstall` once they confirm |
| Another AI should use it | `agent-reach skill link <that AI's skills folder>`; `agent-reach skill` shows where it is placed now |

Troubleshooting, browser maintenance and uninstall details are in [Maintenance](references/maintenance.md): read it when an update fails, the browser will not start, or the user wants to uninstall.

## When there is a new version

Any result with `meta.update` means a newer version exists. Mention it once per conversation, in the user's language and plain words:

1. Agent Reach has a new version (`meta.update.latest`).
2. What changed: 1 to 3 short points from `meta.update.notes`.
3. Ask whether to update; run `agent-reach update` only after the user agrees.

## Red lines

- Read only. Never post, comment, like or message.
- Never log in for the user; never ask for or print passwords, cookies or other credentials.
- Ordinary queries never change dependencies or update automatically.
