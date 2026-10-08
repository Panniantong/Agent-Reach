# 常见问题排查

## 雪球 / Xueqiu: API 返回 400

**症状：** `agent-reach doctor` 显示雪球 ⚠️，报 `HTTP Error 400`

**判断：** HTTP 400 本身不能证明 Cookie 过期，也不表示股票不存在。
若结构化响应包含 `error_code=400016`，表示当前会话被拒绝；doctor 会区分
保存的配置、环境变量和匿名会话，不会自动删除凭据或切换身份。

**恢复路径：** 若提示当前使用 `config.yaml` 中保存的 `xueqiu_cookie`，并且你
决定停止使用它，可显式清除这一项：

```bash
agent-reach configure --unset xueqiu-cookie
```

该命令保留其他配置，不清除浏览器 Cookie，也不修改环境变量。
若 `XUEQIU_COOKIE` 仍存在，文件配置删除后它可能成为凭据来源；请在自己
控制的运行环境中移除或更新它，不要打印或分享变量值。
已有 Python 进程可能缓存旧会话，因此请在新进程中重新运行 doctor 或实际读取。

清除成功只表示本地配置项已移除，不代表雪球访问已恢复。没有有效凭据时将
尝试匿名会话，但匿名入口或网络也可能失败；当前首页入口问题的修复见
[PR #667](https://github.com/Panniantong/Agent-Reach/pull/667)。不要把清除凭据
当作该入口问题的修复，也不要自动重复登录。

如确实需要登录身份且用户明确同意导入，可使用已有命令：

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

以实际返回非空行情或内容确认恢复；网络失败、其他 HTTP 错误或格式异常应
分别排查，不能统一归因为 Cookie 过期。

---

## Boss直聘: `boss status` 说已登录，但搜索报 `AUTH_EXPIRED`

**症状：** `boss status` / `status --live` 返回 `logged_in: true`（甚至带用户名），
但 `boss ... search` 立刻报 `{"code": "AUTH_EXPIRED", "message": "用户未登录"}`。
专用 Chrome 可能同时停在带 `_security_check` 的 URL 上，看起来像反爬滑块。

**原因：** Boss 有两个登录态存储，认证的是不同通道：

| 存储 | 谁在用 |
|---|---|
| `~/.boss-agent/auth/session.enc` | `boss status` / `status --live`；httpx 通道的低危操作（`detail` / `cities` / `job_card_httpx`）。CDP 搜索也会读它（读不到直接报「未登录」），但复用真 Chrome context 时它的 cookie 从未真正生效 |
| `~/.boss-chrome-profile` 内的浏览器 cookie | `existing-browser` 严格 CDP 模式下 search / greet 等高危操作实际携带的凭据 |

`boss status` 只校验本地 session.enc。本地存着几天前的旧凭据、而专用 Chrome
profile 本身没登录时，它依然报 `logged_in: true`——这不是登录态有效的证明。
同时 `_security_check` 页面是反爬挑战，**已登录也会出现**，不能用它判断登录态；
两者叠加很容易把「浏览器未登录」误判成「卡在滑块」。

> 两个存储都不要删。session.enc 缺失会让 CDP 搜索在连上浏览器之前就失败；
> 需要刷新它时跑 `login --cdp`，不要手工删文件。

**判定顺序：**

1. `AUTH_EXPIRED` 是 ground truth——出现即浏览器未登录，不管 `boss status` 说什么；
2. `agent-reach doctor` 的 boss 行会直接探测浏览器内有无 `wt2` cookie，以它为准；
3. `boss status` 仅作参考；页面 URL 完全不作为判据。

**解决方案：** 在专用 Chrome 窗口里肉眼确认并手动登录 zhipin.com，然后同步登录态：

```bash
boss --cdp-url http://localhost:9222 login --cdp
agent-reach doctor    # boss 行 message 应显示「浏览器内有登录 cookie（wt2）」
```

> 拉起专用 Chrome 后的第一步永远是让用户肉眼确认登录状态，不要用 `boss status` 代替。

---

## Twitter/X: twitter-cli 连接失败

**症状：** `twitter search` 或其他命令返回错误

**原因：** twitter-cli 需要 `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`
环境变量才能访问 Twitter API。`agent-reach configure twitter-cookies`
保存的值只供 doctor 检查配置是否齐全；doctor 不执行上游认证，也不会设置当前
Shell。如果你的网络环境需要代理才能访问 x.com，还需要配置代理。

**解决方案：**

### 方案 1：设置环境变量代理

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
export HTTP_PROXY="http://user:pass@host:port"
export HTTPS_PROXY="http://user:pass@host:port"
twitter search "test" -n 1
```

### 方案 2：使用全局代理工具

让代理工具接管所有网络流量，这样 twitter-cli 的请求也会走代理：

```bash
# macOS — ClashX / Surge 开启"增强模式"
# Linux — proxychains 或 tun2socks
proxychains twitter search "test" -n 1
```

### 方案 3：不用 twitter-cli，用 Exa 搜索替代

twitter-cli 不可用时，可以直接用 Exa 搜索 Twitter 内容：

```bash
mcporter call exa.web_search_exa query="site:x.com 搜索词" numResults=5
```

### 方案 4：检查认证

```bash
twitter check
```

> 如果返回 "Missing credentials"，需要在运行该命令的进程环境中设置
> `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`。
>
> **Fallback：** 如果你已经安装了 bird CLI（`npm install -g @steipete/bird`），它也能正常工作。Agent Reach 会自动检测已安装的工具。
