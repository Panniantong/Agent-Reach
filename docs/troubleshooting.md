# Troubleshooting

Start with:

```bash
agent-reach doctor --text     # offline status of every channel
agent-reach check <channel> --text   # live test of one channel
```

## Error codes

Every failed command returns `ok: false` and an `error` with `code`, `message` and `hint`. The `hint` is usually the exact next step.

| Code | Meaning | What to do |
|---|---|---|
| `NEED_SETUP` | a tool, key or selected browser connection is missing | run `agent-reach doctor --text` and follow the problem listed for the channel; use `agent-reach add <channel>` to install the channel's tools |
| `NEED_LOGIN` | login is missing or expired | the user runs `agent-reach login <channel>` and logs in themselves; do not delete credentials to fix a connection or platform-verification error |
| `UPSTREAM_BROKEN` | the upstream tool or platform failed | don't retry in a loop; try again later, inspect the upstream error and pinned dependency version, then `agent-reach check <channel>`; still broken → open an issue with the `message` |
| `TIMEOUT` | no backend answered in time | retry later, or pass a larger `--timeout SECONDS`; on a restricted network set a proxy (below) |
| `RATE_LIMITED` | the platform is throttling | wait for `retry_after_seconds`; do not switch accounts or backends to continue requesting |
| `NOT_FOUND` | the content does not exist | check the link, id or username |
| `BAD_INPUT` | wrong arguments or unknown channel/action | run `agent-reach channels` for valid actions and usage |

## Doctor statuses

| Status | Meaning | What to do |
|---|---|---|
| `not_added` | optional channel not turned on | `agent-reach add <channel>` |
| `needs_setup` | something is missing; `problems` says what | use `agent-reach add <channel>` or follow the specific setup step |
| `needs_login` | the last live check failed only on login | `agent-reach login <channel>` (the user logs in) |
| `unverified` | set up, but no live check in the last 24 hours | `agent-reach check <channel>` |
| `search_ready` | search returned nonempty results in the last 24 hours | read and other actions need their own checks |
| `ready` | passed the recorded live checks in the last 24 hours | inspect verified actions for the requested capability |
| `cooldown` | a rate limit is still active | wait for `retry_after_seconds` |
| `broken` | the last live check failed for another reason | `agent-reach update`, then `agent-reach check <channel> --text`; see `UPSTREAM_BROKEN` |

Run `agent-reach check` first if you want fresh live results. In the `doctor` output, `regressed: true` on a channel means an action passed in the previous check and fails in the latest one.

## Tool versions

Some channel tools install at tested versions; others use a supported range. `agent-reach doctor` shows installed versions. If a version fails, inspect the exact backend attempt before changing it.

## Reusing existing sessions

`login CHANNEL` opens the Reach dedicated window. The user logs in there. Personal Chrome sessions are never imported. `browser setup` prepares the dedicated extension and connection; an incompatible existing Bridge is left untouched and reported.

Boss requires an existing CDP BOSS page. Select it with `browser bind boss http://127.0.0.1:PORT`. Only explicit `login boss --new-browser` may open its persistent dedicated profile. After the user confirms login and stability, run `login boss --sync`. Do not clear risk locks or switch profiles to retry a platform block.

LinkedIn/Bilibili preserve existing native sessions. `login CHANNEL --native` explicitly runs their own authentication if necessary. Saved state is not proof of authentication: use `check CHANNEL --search`.

Search-only acceptance is shown as search_ready, not proof that every action works. PLATFORM_BLOCKED means stop and have the user check the official page. BUSY means another Reach command owns the same browser; schedule later.

## Skill not picked up by an AI

`agent-reach skill` shows the one real copy of the instructions (`~/.agents/skills/agent-reach/SKILL.md`) and the links made for other AIs. An AI not covered automatically: `agent-reach skill link <its skills folder>`. On Windows, where links may not be allowed, a copy is made instead and refreshed by `agent-reach update`.

## Install, update and roll back

Agent Reach is installed with uv. A copy installed another way (pip or pipx, as 1.5 was) moves itself to uv on the next `agent-reach update`; your channels, keys and logins under `~/.agent-reach/` are kept.

A new version broke something? Go back to the previous release, then line the tools and skill up with it:

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v<previous>.zip
agent-reach update --sync-only
```

Removed default channels stay removed across updates; `agent-reach add <channel>` brings one back.

## Proxy

Some platforms block certain networks or regions. Save a proxy once (the address is asked for with hidden input, since it may contain a password):

```bash
agent-reach configure proxy
```

An agent without a terminal prompt can pipe the value in: `agent-reach configure proxy --stdin`.

It is used for every Agent Reach command. An `HTTPS_PROXY` set in your shell takes precedence.

## Still stuck

- `agent-reach update` and try again.
- Remove and re-add a channel: `agent-reach remove <channel>` then `agent-reach add <channel>` (remove also clears its login, its site cookies in the Agent Reach browser, and its private tools nobody else uses).
- Open an issue at https://github.com/Panniantong/Agent-Reach/issues with the output of `agent-reach doctor --text` (it starts with the version) and `agent-reach check <channel> --text`. Remove any personal data first.
