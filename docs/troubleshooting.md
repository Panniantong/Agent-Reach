# 常见问题排查

## 雪球 / Xueqiu: API 返回 400

**症状：** `agent-reach doctor` 显示雪球 ⚠️，报 `HTTP Error 400`（`error_code: 400016`）

**原因：** 行情、搜索、热帖、热股只需要一个**匿名** `xq_a_token`，并不需要登录态。但雪球
首页 `https://xueqiu.com/` 已不再下发 `xq_a_token`（只下发反 DDoS 的 `acw_tc`），用它取
cookie 后续调用必然 400016。渠道改为访问 `https://xueqiu.com/hq`，该页仍下发完整的匿名
token 组（`xq_a_token`/`xqat`/`xq_r_token`/`xq_id_token`）。

**若升级后仍报 400：** 通常是 `~/.agent-reach/config.yaml` 里存过一个**已过期**的
`xueqiu_cookie`。配置里的 cookie 优先级高于匿名兜底，注入成功并不代表它仍然有效，过期后
会持续屏蔽兜底。删掉 `xueqiu_cookie:` 那一行，再运行 `agent-reach doctor` 确认恢复 ✅。

只有在需要登录态专属内容时，才需要显式导入 Cookie：

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

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
