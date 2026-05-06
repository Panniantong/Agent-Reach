# Twitter 高级功能配置指南（twitter-cli）

Twitter 基础阅读通过 Jina Reader 免费可用，无需配置。

高级功能需要 twitter-cli（@public-clis/twitter-cli）：

- 搜索推文（`twitter search`）
- 读取完整推文和对话链（`twitter tweet`、`twitter thread`）
- 用户时间线（`twitter timeline`）
- 长文阅读（`twitter article`）

twitter-cli 是免费开源工具（pipx 安装），但需要你的 Twitter 账号 cookie。

## 快速配置

1. 检查 twitter-cli 是否安装：

```bash
which twitter && echo "installed" || echo "not installed"
```

2. 安装 twitter-cli：

```bash
pipx install twitter-cli
```

3. 测试是否配置好：

```bash
twitter search "test" -n 1
```

## 获取 Cookie（Cookie-Editor 方式，推荐）

1. 安装 [Cookie-Editor](https://cookie-editor.com/) 浏览器扩展
2. 登录 x.com
3. 点击 Cookie-Editor 图标 → Export → 复制全部
4. 运行配置命令：

```bash
agent-reach configure twitter-cookies "粘贴的 cookie JSON"
```

这会自动提取 `auth_token` 和 `ct0`，并写入环境变量。

## 手动设置 Cookie

如果你已经知道 `auth_token` 和 `ct0`：

1. 安装 twitter-cli（如果没装）：`pipx install twitter-cli`

2. 设置环境变量：

```bash
export AUTH_TOKEN="你的auth_token"
export CT0="你的ct0"
```

3. 测试：

```bash
twitter search "test" -n 1
```

## 代理配置

> twitter-cli 支持通过环境变量设置代理：

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

也可以使用全局代理工具：

```bash
proxychains twitter search "test" -n 1
```

## Fallback：bird CLI

如果你已经安装了 [bird CLI](https://www.npmjs.com/package/@steipete/bird)（`npm install -g @steipete/bird`），它也能正常工作。Agent Reach 会自动检测并使用已安装的 bird。两者功能类似，twitter-cli 是当前推荐方案。
