# Tavily Search 配置指南

## 功能说明
Tavily 是专为 AI/LLM 设计的搜索 API。配置后解锁：
- 全网搜索（通用、新闻、金融话题）
- 高相关性结果（针对 AI agent 优化）
- 每月 1000 次免费搜索

## Agent 可自动完成的步骤

### 1. 安装 tavily-python
```bash
pip install agent-reach[tavily]
```

### 2. 验证
```bash
agent-reach doctor | grep "Tavily"
```

## 需要用户手动做的步骤

### 1. 获取 API Key
1. 前往 https://app.tavily.com 注册账号
2. 获取 API Key（每月 1000 次免费，无需信用卡）

### 2. 设置环境变量
```bash
export TAVILY_API_KEY=tvly-xxx
```

或写入 `~/.agent-reach/config.yaml`：
```yaml
tavily_api_key: tvly-xxx
```

## 常见问题

**Q: 有搜索次数限制吗？**
A: 免费账户每月 1000 次 API 调用。付费方案可获得更高额度，详见 https://app.tavily.com。

**Q: Tavily 和 Exa 有什么区别？**
A: Exa 通过 MCP 接入，免费无限制但需要 mcporter。Tavily 通过 Python SDK 直接调用，需要 API Key 但无需额外工具。两者可同时配置，互不影响。
