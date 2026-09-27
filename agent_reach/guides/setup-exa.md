# Exa Search Configuration Guide

## Function description
Exa is an AI semantic search engine. Access through MCP, **free, no API Key required**. Unlock after configuration:
- Web-wide semantic search
- Reddit search (via site:reddit.com)
- Twitter search (via site:x.com)

## Steps that Agent can automatically complete

After the user explicitly authorizes it, `agent-reach install --env=auto --system` will complete the following steps.
The default command without `--system` does read-only checking.

### 1. Install mcporter
```bash
npm install -g mcporter
```

### 2. Register Exa MCP
```bash
mcporter config add exa https://mcp.exa.ai/mcp --scope home
```

### 3. Verification
```bash
agent-reach doctor | grep "Search"
mcporter call exa.web_search_exa query="test" numResults=1
```

## Steps that need to be done manually by the user

**none. ** Exa is accessed through MCP, free of charge, no registration required, no API Key required.

If `agent-reach install --system` does not configure Exa due to network problems, just run the above two commands manually.

## FAQ

**Q: Is there a limit to the number of searches?**
A: The MCP endpoint is officially provided by Exa (mcp.exa.ai) and is currently free and unlimited. If there are changes in the future, they will be adapted in the agent-reach update.

**Q: What is mcporter?**
A: The command line bridging tool of MCP protocol, used to call MCP Server. Agent Reach uses it to connect Exa and XiaoHongShu.
