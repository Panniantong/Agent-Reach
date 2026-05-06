# Reddit 配置指南

## 功能说明

Reddit 封锁了几乎所有非浏览器的直接访问（包括数据中心和 ISP 代理 IP），JSON API 返回 403。

Agent Reach 通过 **rdt-cli** 实现 Reddit 的搜索和阅读功能：
- **搜索**：`rdt search "关键词"`
- **阅读完整帖子+评论**：`rdt read POST_ID`

免费，无需代理，无需 API Key，无需登录。

## Agent 可自动完成的步骤

1. 检查 rdt-cli 是否可用：
```bash
which rdt && echo "installed" || echo "not installed"
```

2. 如果未安装，自动安装：
```bash
pipx install rdt-cli
```

或一键安装：
```bash
agent-reach install --env=auto --channels=reddit
```

## 使用示例

搜索 Reddit 内容：
```bash
rdt search "python best practices" -n 5
```

阅读完整帖子和评论：
```bash
rdt read POST_ID
```

## 需要用户手动做的步骤

无。rdt-cli 通过 `agent-reach install --env=auto` 自动安装。

## Fallback：Exa 搜索

如果你已经配置了 Exa（通过 mcporter），也可以通过 Exa 搜索 Reddit 内容：

```bash
mcporter call 'exa.web_search_exa(query: "python best practices", numResults: 5, includeDomains: ["reddit.com"])'
```

rdt-cli 是当前推荐方案，无需额外配置即可使用。
