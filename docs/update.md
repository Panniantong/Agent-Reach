# Agent Reach — Update Guide

## For Humans

Copy this to your AI Agent:

```
帮我更新 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

Or in English:

```
Update Agent Reach: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
```

---

## For AI Agents

### ⚠️ Workspace Rules

**Never create files, clone repos, or run commands in the agent workspace.** Use `/tmp/` for temporary work and `~/.agent-reach/` for persistent data.

### Goal

Update Agent Reach to the latest version, refresh upstream tools, migrate from retired backends, and verify everything works. The user should not need to do anything manually (except things only a human can do, like clicking a browser-extension install button).

### Step 1: Check current version

```bash
agent-reach check-update
```

If it says "已是最新版本", skip to Step 4 (verify). Otherwise continue.

### Step 2: Update Agent Reach package

```bash
pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip
```

> If pip complains about `externally-managed-environment` (PEP 668), the user
> originally installed via pipx or a venv — use the matching command:
> `pipx install --force https://github.com/Panniantong/agent-reach/archive/main.zip`
> or activate `~/.agent-reach-venv` first.

### Step 3: Refresh upstream tools

Run these to keep installed tools current. **Only upgrade what is already
installed — do not install new tools the user never asked for** (the one
exception: OpenCLI on desktop, see below).

```bash
# Python-based CLIs the user already has (upgrade keeps signatures fresh)
which twitter >/dev/null 2>&1 && { pipx upgrade twitter-cli 2>/dev/null || uv tool upgrade twitter-cli 2>/dev/null; }
which bili    >/dev/null 2>&1 && { pipx upgrade bilibili-cli 2>/dev/null || uv tool upgrade bilibili-cli 2>/dev/null; }
which xhs     >/dev/null 2>&1 && { pipx upgrade xiaohongshu-cli 2>/dev/null || uv tool upgrade xiaohongshu-cli 2>/dev/null; }
which yt-dlp  >/dev/null 2>&1 && { pipx upgrade yt-dlp 2>/dev/null || uv tool upgrade yt-dlp 2>/dev/null || pip install -U yt-dlp 2>/dev/null; }

# rdt-cli is pinned to a git source (PyPI lags upstream) — same pin as the code's _RDT_GIT_SOURCE
which rdt >/dev/null 2>&1 && pipx install --force 'git+https://github.com/public-clis/rdt-cli.git@5e4fb3720d5c174e976cd425ccc3b879d52cac66' 2>/dev/null

# npm-based
which mcporter >/dev/null 2>&1 && npm update -g mcporter 2>/dev/null
which opencli  >/dev/null 2>&1 && npm update -g @jackwener/opencli 2>/dev/null
```

**Desktop users without OpenCLI**: since v1.5.0 OpenCLI is the preferred
backend for 小红书/Reddit (and adds B站 subtitles) by riding the user's
browser session. Offer it once:

> "这次更新引入了 OpenCLI 后端（复用你的浏览器登录态，小红书/Reddit 零配置）。要装吗？装完只需你在 Chrome 商店点一次『添加扩展』。"

If yes: `agent-reach install --channels opencli` and guide them through the
extension click. If no, everything keeps working on existing backends.

### Step 4: Coexistence (DO NOT uninstall old tools)

**Never uninstall tools the user already has.** Retired backends (e.g. yt-dlp
no longer serves Bilibili; xhs-cli is no longer installed by default) keep
working as fallbacks where they still function. Agent Reach routes around
them automatically — removal is the user's call, not yours.

### Step 5: Verify

```bash
agent-reach version
agent-reach doctor
```

Running `agent-reach doctor` (text mode) also makes sure an Agent Reach skill
exists in detected agent skill directories. If the user already has a skill
there, doctor preserves it instead of overwriting local customizations. Use
`agent-reach skill --install` when you explicitly want to refresh the bundled
skill files.

Check the doctor output:

- Every channel shows ✅ / [!] with a clear message, and multi-backend
  channels (小红书/Reddit/B站/Twitter) report `当前后端：…`
- If a previously-working channel now shows [X]/error, the message contains
  the exact fix (e.g. a venv-reinstall prescription) — run it, then re-check
- `--json` gives the same data machine-readably (`active_backend` per channel)

### Step 6: Report to user

Tell the user:

1. What version they're on now (`agent-reach version`)
2. How many channels are available, and which backend each multi-backend
   platform is using (from doctor)
3. Anything that needs their action (e.g. Chrome extension click, `xhs login`,
   QR scan for xiaohongshu-mcp on servers)
4. What changed in this update (release notes shown by `check-update`)

Done.
