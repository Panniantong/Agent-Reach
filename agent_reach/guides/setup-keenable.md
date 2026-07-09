# Keenable Search 配置指南

## 功能说明
Keenable 是一个面向 AI Agent 的搜索 API。通过 MCP 接入，**免费、无需 API Key**（默认公共端点，按小时限流；设置 API Key 可解除限流）。配置后解锁：
- 全网搜索（`search_web_pages`）
- 网页抓取为干净 Markdown（`fetch_page_content`），可深读某条搜索结果
- Reddit 搜索（通过 site:reddit.com）
- Twitter 搜索（通过 site:x.com）

## Agent 可自动完成的步骤

`agent-reach install --env=auto` 会自动完成以下步骤，通常不需要手动操作。

### 1. 安装 mcporter
```bash
npm install -g mcporter
```

### 2. 注册 Keenable MCP
```bash
mcporter config add keenable https://api.keenable.ai/mcp
```

### 3. 验证
```bash
agent-reach doctor | grep "Keenable"
mcporter call 'keenable.search_web_pages(query: "test")'
```

## 需要用户手动做的步骤

**无。** Keenable 通过 MCP 接入，默认免费、无需注册、无需 API Key。

如果 `agent-reach install` 因为网络问题没有自动配置 Keenable，手动运行上面两条命令即可。

## 常见问题

**Q: 有搜索次数限制吗？**
A: 公共端点（api.keenable.ai）默认按小时限流（1,000 次/小时），无需注册即可使用。需要更高额度可在 [keenable.ai/console](https://keenable.ai/console) 获取 API Key 解除限流。

**Q: 和 Exa 有什么区别？**
A: 两者都是免 Key 的 MCP 搜索后端，可互为备份。Keenable 额外提供网页抓取（返回干净 Markdown），适合搜索后深读页面。

**Q: mcporter 是什么？**
A: MCP 协议的命令行桥接工具，用来调用 MCP Server。Agent Reach 用它来连接 Exa、Keenable 和小红书。
