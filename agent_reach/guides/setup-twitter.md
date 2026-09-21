# Twitter 高级功能配置指南（twitter-cli）

Twitter 基础阅读通过 Jina Reader 免费可用，无需配置。

高级功能需要 twitter-cli（@public-clis/twitter-cli）：

- 读取完整推文和对话链（`twitter tweet`）
- 用户时间线（`twitter user-posts`、`twitter feed`）
- 当前账号（`twitter whoami`）
- 长文阅读（`twitter article`）

关键词搜索在 PyPI twitter-cli **0.8.5**（目前没有更新的 release）上不可用，见文末。不要把 `pipx install twitter-cli` 换成某个未合并的 PR 分支。

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

3. 确认命令已安装（此时不做认证请求）：

```bash
twitter --help
```

## 获取 Cookie（Cookie-Editor 方式，推荐）

1. 安装 [Cookie-Editor](https://cookie-editor.com/) 浏览器扩展
2. 登录 x.com
3. 点击 Cookie-Editor 图标 → Export → Header String
4. 运行配置命令：

```bash
agent-reach configure twitter-cookies
```

这会提取 `auth_token` 和 `ct0`，安全保存到
`~/.agent-reach/config.yaml`，供 `agent-reach doctor` 检查显式凭据是否齐全。
`doctor` 不会执行 `twitter status`，不会实时验证账号是否可用，也不会修改当前 Shell。

默认只写 `~/.agent-reach/config.yaml`。只有用户明确同意复制凭据并显式增加
`--sync-legacy-twitter` 时，才会额外写入：

- `~/.config/xfetch/session.json`
- `~/.config/bird/credentials.env`

```bash
agent-reach configure twitter-cookies --sync-legacy-twitter
```

`agent-reach uninstall` 只会提醒这些 legacy 副本，不会自动删除。需要清理时，
先让用户确认，再手工删除上述两个文件。

`twitter` 是独立的上游命令，不会读取 Agent Reach 的配置文件。直接运行
`twitter whoami` / `user-posts` / `feed` 时，必须按下节在当前 Shell 或子进程环境中
显式设置 `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`。不要依赖自动读取浏览器 Cookie。
关键词搜索不要用 `twitter search`，见文末。

## 手动设置 Cookie

如果你已经知道 `auth_token` 和 `ct0`：

1. 安装 twitter-cli（如果没装）：`pipx install twitter-cli`

2. 设置环境变量：

```bash
export TWITTER_AUTH_TOKEN="你的auth_token"
export TWITTER_CT0="你的ct0"
```

3. 测试凭据（不要用 `twitter search`，0.8.5 上它会 404）：

```bash
twitter whoami
```

## 代理配置

> twitter-cli 支持通过环境变量设置代理：

```bash
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter whoami
```

也可以使用全局代理工具：

```bash
proxychains twitter whoami
```

## 关键词搜索：ClientTransaction + HTTP 404

`twitter whoami` / `twitter user-posts` 成功，并不代表 `twitter search` 可用。
0.8.5 初始化 ClientTransaction 时匿名抓取 `https://x.com`，登出首页匹配不到
`ondemand.s`，于是出现：

```text
WARNING twitter_cli.client: Failed to init ClientTransaction: 'NoneType' object has no attribute 'group'
Twitter API error (HTTP 404)
```

这条警告也会出现在成功的 whoami / user-posts 上；只有 search 接着 HTTP 404
才是这个故障。不要重试 `twitter search`，也不要 `pipx upgrade twitter-cli`
（会停在 0.8.5）。`twitter feed` 和 `twitter user-posts` 不是关键词搜索。
上游修复尚未发布：<https://github.com/public-clis/twitter-cli/issues/78>。

```bash
# 桌面，Chrome 已登录 x.com
opencli twitter search "query" -f yaml

# 否则：Exa 公开网页（不是登录态 SearchTimeline）
mcporter call exa.web_search_exa "query=site:x.com 搜索词" numResults=5
```

`twitter --version` 高于 0.8.5，且该版本已经用登录态请求首页来初始化
ClientTransaction 之后，再使用 `twitter search`。

## Fallback：bird CLI

如果你已经安装了 [bird CLI](https://www.npmjs.com/package/@steipete/bird)（`npm install -g @steipete/bird`），它也能正常工作。Agent Reach 会自动检测并使用已安装的 bird。两者功能类似，twitter-cli 是当前推荐方案。
