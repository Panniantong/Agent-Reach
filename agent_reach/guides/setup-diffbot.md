# Diffbot Web Search 配置指南

## 功能说明
Diffbot Web Search 是基于 Diffbot Web Index 的全网搜索，作为 Exa 之外的 **可选搜索后端**。每条结果带 **相关性评分** 和 **发布时间**，并可用 `-m/--max-tokens` 控制响应大小，适合 agentic 场景。

通过 diffbot-python 的 `db` 命令行工具调用——装好后 Agent 直接 `db web-search "query"`，agent-reach 只负责安装 / 配置 / 体检。**需要一个免费 Token**（与 Exa 的零配置不同）。

## Agent 可自动完成的步骤

`agent-reach install --channels=diffbot` 会安装 CLI；Token 需用户提供一次。

### 1. 安装 Diffbot CLI
```bash
pipx install diffbot-python        # 或：uv tool install diffbot-python
```

### 2. 配置 API Token
```bash
# 免费 Token：https://app.diffbot.com/get-started/
agent-reach configure diffbot-token <token>
```
这会把 Token 同时写入 agent-reach 配置和 `~/.diffbot/credentials`（`db` 默认读取该文件），之后无需再 export 任何环境变量。

### 3. 验证
```bash
agent-reach doctor --json        # 确认 diffbot_search 为 ok
db web-search "test" -n 1 -f text
```

### 4. 知识图谱（DQL）——可选，同一个 Token

同一个 `db` CLI 还能对 Diffbot 知识图谱做结构化检索（DQL）。配好 Token 后再跑一次性的本体缓存：

```bash
db dql init                       # 缓存本体（ontology），重置 ~/.diffbot/tmp，校验 Token
agent-reach doctor --json         # 确认 diffbot_kg 为 ok
```

查询构造（导航本体 → 写 DQL → probe → export）见 `references/diffbot-kg.md`。

## 需要用户手动做的步骤

**只有一步：提供 Token。** 在 https://app.diffbot.com/get-started/ 注册即可拿到带免费额度的 Token，发给 Agent 或运行上面的 `configure` 命令。

## 常见问题

**Q: 和 Exa 有什么区别？该用哪个？**
A: Exa 免费、零配置、擅长英文/技术/代码搜索；Diffbot 需免费 Token，结果带相关性评分和发布时间、可控 token 预算。两者都可用，按任务选择，调研类任务也可并用。

**Q: Token 存在哪里？安全吗？**
A: 写入 `~/.diffbot/credentials`（权限 0600）和 `~/.agent-reach/config.yaml`（同样 0600）。不会上传到任何第三方。

**Q: `db` 报 "Invalid or unauthorized API token." 怎么办？**
A: Token 缺失或无效。重新运行 `agent-reach configure diffbot-token <token>`，确认 Token 正确且额度未耗尽。

**Q: `db` 命令找不到？**
A: 没装或 PATH 没生效。运行 `pipx install diffbot-python`；若提示存在但无法执行（升级 Python 后 venv 断链），用 `pipx reinstall diffbot-python`。
