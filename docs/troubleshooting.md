# 常见问题排查

## YouTube: yt-dlp 报 "Sign in to confirm you're not a bot"

**症状：** `yt-dlp --dump-json` / `--write-sub` 等命令直接报错退出，提示需要登录验证；有些视频紧接着还会报 `Requested format is not available`。

**原因：** 部分视频被 YouTube 风控要求验证是否为真人。纯匿名请求（无 Cookie）会被拦截；即使带了 Cookie，YouTube 的 JS 挑战偶尔本地解不出来，导致可播放格式解析失败，如果没加 `--ignore-no-formats-error` 会连读元数据/字幕这种不需要下载视频的操作也一起报错。

**解决方案：** 仅限本地有浏览器的环境（服务器没有浏览器就跳过这条，改用下方的 Whisper 音频转写兜底）：

```bash
yt-dlp --ignore-no-formats-error --cookies-from-browser chrome --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
```

多 Chrome Profile 时默认的 `chrome` 可能读到没登录过的 Profile，用 `--cookies-from-browser "chrome:Profile 2"` 指定具体 profile。

如果重试后提示变成 "no subtitles for the requested languages"，先用 `yt-dlp --list-subs "URL"` 确认这条视频到底有没有字幕——很多视频压根没上字幕，不是 Cookie 或风控问题。这种情况下改用音频转写：

```bash
agent-reach configure groq-key gsk_xxx   # 免费，console.groq.com
agent-reach transcribe "URL"
```

---

## 雪球 / Xueqiu: API 返回 400

**症状：** `agent-reach doctor` 显示雪球 ⚠️，报 `HTTP Error 400`

**原因：** 雪球 API 需要登录 Cookie，无法通过匿名访问获取。

**解决方案：** 在 Chrome 里登录 xueqiu.com，然后运行：

```bash
agent-reach configure --from-browser chrome
```

再次运行 `agent-reach doctor` 确认恢复 ✅。Cookie 过期后重新运行即可。

---

## Twitter/X: twitter-cli 连接失败

**症状：** `twitter search` 或其他命令返回错误

**原因：** twitter-cli 需要 AUTH_TOKEN 和 CT0 环境变量才能访问 Twitter API。如果你的网络环境需要代理才能访问 x.com，需要配置代理。

**解决方案：**

### 方案 1：设置环境变量代理

```bash
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
mcporter call 'exa.web_search_exa(query: "site:x.com 搜索词", numResults: 5)'
```

### 方案 4：检查认证

```bash
twitter check
```

> 如果返回 "Missing credentials"，需要设置 AUTH_TOKEN 和 CT0 环境变量。
>
> **Fallback：** 如果你已经安装了 bird CLI（`npm install -g @steipete/bird`），它也能正常工作。Agent Reach 会自动检测已安装的工具。
