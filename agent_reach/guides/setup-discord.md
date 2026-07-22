# Discord 配置指南

## 功能说明
读取、搜索、同步和导出你能访问的 Discord 服务器/频道消息。通过 [discord-cli](https://github.com/jackwener/discord-cli)（PyPI 包 `kabi-discord-cli`，本地优先同步进 SQLite）实现。

> ⚠️ **封号风险提醒**：discord-cli 用的是你账号的 **user token** 走 Discord HTTP API，属于 user-token 自动化，**违反 Discord ToS，可能被检测并限制/封禁账号**。请务必使用**专用小号**，不要用主账号，并自行评估风险。

## 前置条件
- Python 3.10+（pipx / uv 安装）
- 本地已登录 Discord（桌面客户端或浏览器，用于提取 user token）

## Agent 可自动完成的步骤

### 1. 安装 discord-cli
```bash
uv tool install kabi-discord-cli
# 或：pipx install kabi-discord-cli
```

### 2. 登录（提取 user token）
```bash
discord auth --save
```

> 自动从本地 Discord/浏览器会话提取 user token 并保存到 `.env`。

### 3. 验证
```bash
agent-reach doctor
```

应该看到 Discord 显示为 ✅。也可单独查状态：`discord status`（退出码 0 = 已认证）。

## 使用示例

```bash
# 列服务器 / 频道
discord dc guilds --yaml
discord dc channels <GUILD> --yaml

# 搜索某频道的消息
discord search "关键词" -c general --yaml

# 同步可访问的文本频道（首次引导）
discord dc sync-all

# 导出（大数据集写文件）
discord export -c general -o /tmp/general.yaml
```

> 结构化输出用 `--yaml`（非 TTY 默认即 YAML），`-n` 控制条数，输出契约见上游 SCHEMA.md。

## 常见问题

**Q: token 失效了？**
A: 重新运行 `discord auth --save`（`discord status` 会以非零退出码提示 `not_authenticated`）。

**Q: 命令存在但无法执行？**
A: 多为系统 Python 升级后 venv 断链，重装即可：`uv tool install --force kabi-discord-cli`。

**Q: 只能读到部分频道？**
A: 只能访问你账号有权限看到的服务器/频道；user token 无法越权。
