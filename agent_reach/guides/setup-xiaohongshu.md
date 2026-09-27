# XiaoHongShu Configuration Guide

## Function description
Read and search XiaoHongShu notes. Desktop uses OpenCLI first, server uses
[xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp);
xhs-cli is only available as a legacy fallback for installed users.

## Preconditions
- OpenCLI: Chrome XiaoHongShu session that already exists and is explicitly controlled by the user
- xiaohongshu-mcp / Legacy tool: Cookie-Editor browser extension

## Authentication Boundary

Agent Reach does not perform XiaoHongShu login for users, nor does it read browser cookies.

OpenCLI only uses an existing and explicitly controlled Chrome session.
`agent-reach configure xhs-cookies` does not inject cookies into OpenCLI or Chrome.
If no such session exists, do not automate login. Use a manual Cookie-Editor
export with xiaohongshu-mcp or a legacy tool:

1. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension in Chrome
2. The user prepares the session to be exported on xiaohongshu.com
3. Click the Cookie-Editor icon → Export → Header String
4. Send the exported string to Agent and run:

```bash
agent-reach configure xhs-cookies
agent-reach doctor
```

This explicit command saves/imports the user-provided xiaohongshu.com same-domain cookie set.
Confirm cookie names and scope first. Non-xiaohongshu.com domain cookies are ignored.

If the xiaohongshu-mcp container is running, the command imports the cookies into it.
Otherwise, it writes an owner-only local file and prints manual import instructions.

## Usage example

Use `active_backend` from `agent-reach doctor --json` to select the command group. Legacy xhs-cli example:

Search notes:
```bash
xhs search "keywords"
```

Read the note details:
```bash
xhs read NOTE_ID
```

View comments:
```bash
xhs comments NOTE_ID
```

## FAQ

**Q: Cookie expired?**
A: Re-export manually through Cookie-Editor and run again
`agent-reach configure xhs-cookies` and paste it into the hidden input prompt.

**Q: Does XiaoHongShu remind you about IP risks?**
A: It is recommended to use residential proxy: `export HTTP_PROXY="http://user:pass@ip:port"`.

**Q: xhs-cli does not support my system?**
A: Make sure Python 3.10+ and pipx are installed. Just run `pipx install xiaohongshu-cli`.

## Server solution: Docker MCP

If you are already using the [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Docker solution, it will also work fine:

```bash
docker run -d \
  --name xiaohongshu-mcp \
  -p 18060:18060 \
  xpzouying/xiaohongshu-mcp

mcporter config add xiaohongshu http://localhost:18060/mcp --scope home
```

The server backend uses the Cookie-Editor manual export process above.
