# Troubleshooting / 常见问题

## Twitter/X: bird CLI "fetch failed"

**症状：** `bird whoami` 或 `bird search` 返回 "fetch failed"

**原因：** bird CLI 使用 Node.js 原生 `fetch()` 发请求，而 Node.js 的 fetch **不走系统代理**（不读取 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量）。如果你的网络环境需要代理才能访问 x.com，bird 就连不上。

**解决方案（按推荐顺序）：**

### 方案 1：使用透明代理 / TUN 模式（推荐）

让代理工具接管所有网络流量，这样 bird 的 fetch 也会走代理：

- **Clash Verge / Clash for Windows：** 开启 TUN 模式或系统代理
- **Proxifier（Windows）：** 添加规则让 Node.js 进程走代理
- **macOS：** 在 Surge/ClashX Pro 中开启增强模式

### 方案 2：验证 Cookie 有效性

确认 Cookie 没过期：

1. 在浏览器里正常登录 x.com
2. 用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 重新导出 Header String
3. 重新配置：`agent-reach configure twitter-cookies "新的Cookie"`

### 方案 3：不用 bird，用 Exa 搜索替代

bird 不可用时，可以直接用 Exa 搜索 Twitter 内容：

```bash
mcporter call 'exa.web_search_exa(query: "site:x.com query", numResults: 10)'
```

### 方案 4：配置 Node.js 全局代理（高级）

安装 `global-agent` 让 Node.js 的 fetch 走代理：

```bash
npm install -g global-agent
```

然后在运行 bird 前设置环境变量：

```bash
# Linux / macOS
export GLOBAL_AGENT_HTTP_PROXY=http://127.0.0.1:7890
export NODE_OPTIONS="--require global-agent/bootstrap"
bird search "test"

# Windows (PowerShell)
$env:GLOBAL_AGENT_HTTP_PROXY = "http://127.0.0.1:7890"
$env:NODE_OPTIONS = "--require global-agent/bootstrap"
bird search "test"
```

> ⚠️ 注意：这个方案需要每次运行 bird 前都设置环境变量，不太方便。推荐用方案 1。

---

## Boss直聘: "访问行为异常"

**症状：** mcp-bosszp 登录成功，但 API 请求返回"您的访问行为异常"

**原因：** Boss直聘的反爬机制会检测请求指纹（不只是 IP），Python requests 库的特征与真实浏览器不同。

**解决方案：**
- **本地电脑：** 正常使用，一般不会被拦
- **服务器：** 使用 Jina Reader 读取职位页面 + Exa 搜索职位信息作为替代
