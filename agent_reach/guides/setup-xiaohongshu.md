# XiaoHongShu Setup Guide

## What it provides

Read and search XiaoHongShu notes.

Preferred backends:

- **Desktop:** OpenCLI using an existing Chrome session controlled by the user
- **Server:** [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)
- **Legacy fallback:** xhs-cli for users who already have it installed

## Prerequisites

- OpenCLI: an existing XiaoHongShu Chrome session the user explicitly controls
- xiaohongshu-mcp / legacy tools: a manual Cookie-Editor export

## Authentication boundary

Agent Reach must not perform XiaoHongShu login and must not read browser cookies automatically.

OpenCLI may use only an existing Chrome session explicitly controlled by the user. `agent-reach configure xhs-cookies` does not inject cookies into OpenCLI or Chrome.

If there is no existing session, do not automate login. Use Cookie-Editor and configure the MCP/legacy backend:

1. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm).
2. The user prepares/logs in to the XiaoHongShu session in their own browser.
3. Choose **Export → Header String**.
4. Provide the exported value through the secure configuration flow:

```bash
agent-reach configure xhs-cookies
agent-reach doctor
```

The command accepts only cookies for the `xiaohongshu.com` domain. Cookies from unrelated domains are ignored.

If a xiaohongshu-mcp container is already running, the configuration flow can import the supplied cookies into that backend. Otherwise it stores an owner-only local copy and prints the manual import path.

## Usage examples

Choose commands according to `agent-reach doctor --json` and its `active_backend`.

Legacy xhs-cli examples:

```bash
xhs search "query"
xhs read NOTE_ID
xhs comments NOTE_ID
```

## FAQ

**Cookie expired?**  
Export a fresh `xiaohongshu.com` cookie set with Cookie-Editor and rerun `agent-reach configure xhs-cookies`.

**IP risk warning?**  
A user-approved residential proxy may help in environments where the platform blocks the current IP:

```bash
export HTTP_PROXY="http://user:pass@ip:port"
```

**xhs-cli compatibility problem?**  
xhs-cli is a legacy fallback. Prefer OpenCLI or xiaohongshu-mcp for new setups.

## Server option: Docker MCP

If the user already uses the xiaohongshu-mcp Docker backend:

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp --scope home
```

Use the same manual Cookie-Editor flow described above for authentication.
