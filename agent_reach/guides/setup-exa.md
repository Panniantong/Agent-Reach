# Exa Search 配置指南

## 功能说明

Exa 是一个 AI 语义搜索引擎。Agent Reach 支持两条调用路径：

1. 已配置个人 API Key：通过 `agent-reach-exa` 直连 REST，减少中间传输；
2. 未配置个人 API Key：保留现有 `mcporter + Exa MCP` 免 Key 路径。

REST 只替换传输路径，不改变 MCP 默认行为：`type: auto`、默认 10 条、
搜索返回 Highlights、内联 `category:` 解析、正文默认 3000 字符，以及
60 秒总超时和 500/502/503/504 重试。

## 方案一：个人 API Key 直连 REST

先在 Exa 控制台创建 API Key，然后通过隐藏输入保存：

```bash
agent-reach configure exa-key
agent-reach-exa status --json
agent-reach-exa search "test" --num-results 1
```

自动化场景使用标准输入，避免 Key 出现在 shell history 和进程参数里：

```bash
printf '%s' "$EXA_API_KEY" | agent-reach configure exa-key --stdin
```

`status` 只确认本地配置，不发起计费请求。网络、额度和限流会在首次真实搜索时验证。

## 方案二：免 Key MCP

用户明确授权后，`agent-reach install --env=auto --system` 会安装并配置
mcporter。也可以手动执行：

```bash
npm install -g mcporter
mcporter config add exa https://mcp.exa.ai/mcp --scope home
mcporter call exa.web_search_exa query="test" numResults=1
```

## 常见问题

**Q: 两条路径会改变搜索结果数量或正文吗？**

A: 不会。REST 客户端固定复刻当前 MCP 的请求默认值；只有传输路径不同。

**Q: 直连 REST 如何计费？**

A: 使用个人 API Key 时，费用、额度和速率限制由对应 Exa 账户承担。

**Q: MCP 会被删除吗？**

A: 不会。免 Key MCP 是未配置个人 Key 时的兼容路径，也可以通过
`exa_search_backend` 配置显式优先选择。
