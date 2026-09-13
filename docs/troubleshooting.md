# 常见问题排查

## 雪球 / Xueqiu: API 返回 400

**症状：** `agent-reach doctor` 显示雪球 ⚠️，报 `HTTP Error 400`

**原因：** 雪球 API 需要登录 Cookie，无法通过匿名访问获取。

**解决方案：** 在 Chrome 里登录 xueqiu.com，然后运行：

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

再次运行 `agent-reach doctor` 确认恢复 ✅。Cookie 过期后重新运行即可。

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
