# Exa Search 配置指南（Tavily 备选）

Agent Reach 默认优先 Tavily；本指南配置 Exa 作为无需 API key 的 fallback。
需要配置 Tavily 时请先阅读 `guides/setup-tavily.md`。

## 功能说明
Exa 是一个 AI 语义搜索引擎。通过 MCP 接入，**免费、无需 API Key**。配置后解锁：
- 全网语义搜索
- Reddit 搜索（通过 site:reddit.com）
- Twitter 搜索（通过 site:x.com）

## Agent 可自动完成的步骤

用户明确授权后，`agent-reach install --env=auto --system` 会完成以下步骤。
不带 `--system` 的默认命令只做只读检查。

### 1. 安装 mcporter
```bash
npm install -g mcporter
```

### 2. 注册 Exa MCP
```bash
mcporter config add exa https://mcp.exa.ai/mcp --scope home
```

### 3. 验证
```bash
agent-reach doctor | grep "Search"
mcporter call exa.web_search_exa query="test" numResults=1
```

## 需要用户手动做的步骤

**无。** Exa 通过 MCP 接入，免费、无需注册、无需 API Key。

如果 `agent-reach install --system` 因为网络问题没有配置 Exa，手动运行上面两条命令即可。

## 常见问题

**Q: 有搜索次数限制吗？**
A: MCP 端点由 Exa 官方提供（mcp.exa.ai），当前免费无限制。如果未来有变化，会在 agent-reach 更新中适配。

**Q: mcporter 是什么？**
A: MCP 协议的命令行桥接工具，用来调用 MCP Server。Agent Reach 用它来连接 Exa 和小红书。
