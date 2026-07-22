# Telegram 配置指南

## 功能说明
同步、搜索、导出和监听你 Telegram 账号里的对话与频道消息。通过 [tg-cli](https://github.com/jackwener/tg-cli)（PyPI 包 `kabi-tg-cli`，本地优先同步进 SQLite）实现。走 **MTProto 用户账号**（不是 Bot API），能读到你自己加入的私有群/频道。

## 前置条件
- Python 3.10+（pipx / uv 安装）
- 一个 Telegram 账号 + 能收验证码的手机号

## Agent 可自动完成的步骤

### 1. 安装 tg-cli
```bash
uv tool install kabi-tg-cli
# 或：pipx install kabi-tg-cli
```

## 需要用户手动做的步骤

### 2. 登录（首次需交互）

**输入手机号 + 短信/App 验证码，Agent 无法代填**，请用户自己跑一次：

```bash
tg chats
```

> 自带 Telegram Desktop API 凭据，无需自建应用。首次会提示输入手机号（含国家码，如 `+8613800138000`）和验证码，登录态保存在本地 session，后续命令免登录。

### 3. 验证
```bash
agent-reach doctor
```

应该看到 Telegram 显示为 ✅。也可单独查状态：`tg status`（退出码 0 = 已登录）。

## 使用示例

```bash
# 列对话 / 查当前用户
tg chats --type group
tg whoami --yaml

# 拉历史、增量同步
tg history CHAT -n 1000
tg sync CHAT

# 搜索（存量缓存）
tg search "Rust" -c "牛油果" --yaml
tg search "Rust|Golang" --regex

# 近实时缓存（后台监听）
tg listen --persist
```

> 结构化输出用 `--yaml`（非 TTY 默认即 YAML）。查询走本地 SQLite 缓存，先 `tg sync` / `tg refresh` 保持新鲜。

## 常见问题

**Q: 想用自己的 App 凭据？**
A: 设置环境变量后再登录：
```bash
export TG_API_ID=123456
export TG_API_HASH=your_telegram_app_hash
```

**Q: 命令存在但无法执行？**
A: 多为系统 Python 升级后 venv 断链，重装即可：`uv tool install --force kabi-tg-cli`。

**Q: doctor 一直显示未登录？**
A: `tg status` 非零退出即未登录，跑一次 `tg chats` 完成手机号登录。
