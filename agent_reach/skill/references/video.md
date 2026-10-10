# 视频/播客

YouTube、B站、小宇宙播客的字幕和转录。

## YouTube (yt-dlp)

### 获取视频元数据

```bash
yt-dlp --dump-json "URL"
```

### 下载字幕

```bash
# 下载字幕 (不下载视频)
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# 然后读取 .vtt 文件
cat /tmp/VIDEO_ID.*.vtt
```

### 获取评论

```bash
# 提取评论（best-effort，不保证完整）
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# 评论在 .info.json 的 comments 字段中
```

### 搜索视频

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> **字幕注意**: 手动上传的字幕提取可靠；自动生成字幕可能存在行间重复，需后处理。
> **评论注意**: `--write-comments` 基于网页抓取（非 YouTube Data API），部分评论可能丢失。

### 字幕失败时的重试链（按序执行，拿到实质内容即停）

`doctor` 只确认 yt-dlp 本体与 JS runtime 能执行，不会请求具体视频；因此
`active_backend: yt-dlp` 不等于目标视频的字幕已经通过实时验证。

1. 先用上面的 `yt-dlp --write-sub --write-auto-sub` 命令。
2. 若出现 bot 校验、字幕响应为空或没有生成字幕文件，且 OpenCLI 已连接：
   `opencli youtube transcript "URL" -f yaml`。
3. OpenCLI 若返回 `Caption URL returned empty response`，最多重试 3 次；这是带
   过期时间的字幕 URL 偶发失效，不能把空响应当成“视频没有字幕”。
4. 仍失败（或在没有 OpenCLI 的服务器上），且 `doctor` 的 YouTube 一栏显示“已配置托管字幕后端”：
   `agent-reach youtube-transcript "URL"`（见下方“可选：托管字幕后端”）。
5. 仍失败或视频本来就没有字幕：`agent-reach transcribe "URL"` 下载音频转写。

成功标准是实际得到非空字幕/转录内容，不是命令退出码或 `doctor` 的版本探测结果。

### 可选：托管字幕后端（服务器 / 云主机）

VPS 和云主机的 IP 常被 YouTube 要求 "Sign in to confirm you're not a bot"，yt-dlp
和音频下载都会失败。此时可以让托管服务在它自己的网络上抓字幕。默认关闭；
只有用户显式选择后端并提供凭据后才会使用，yt-dlp 始终是首选。

```bash
agent-reach youtube-transcript "https://www.youtube.com/watch?v=VIDEO_ID"
agent-reach youtube-transcript VIDEO_ID --lang en,es        # 语言偏好
agent-reach youtube-transcript VIDEO_ID --json              # 带时间轴 segments 和元数据
```

目前支持的后端：

| 后端 | 需要的配置 | 说明 |
|-----|-----------|------|
| `apify` | `apify_token`（或环境变量 `APIFY_TOKEN`） | 通过 `run-sync-get-dataset-items` 一次请求运行 Apify 上的字幕 Actor；默认 Actor `apimint/youtube-transcript-scraper`，可用 `apify_transcript_actor`（或 `APIFY_TRANSCRIPT_ACTOR`）换成任意字幕 Actor |

```bash
# 启用（隐藏输入保存 token；也可以直接设置环境变量）
agent-reach configure apify-token
agent-reach configure youtube-transcript-backend apify
# 或：export APIFY_TOKEN=... YOUTUBE_TRANSCRIPT_BACKEND=apify

# 可选：换成其他 Actor（Store 页面上的 owner/name）
export APIFY_TRANSCRIPT_ACTOR=owner/actor-name
# 该 Actor 的输入字段不叫 urls 时，给一个 JSON 模板，{url} 会被替换成视频链接
export APIFY_TRANSCRIPT_INPUT='{"startUrls": [{"url": "{url}"}]}'
```

> 托管服务按调用计费，费用由用户自己的服务商账户承担。只把公开视频链接发给用户选定的服务；
> 命令只接受 YouTube 链接或 11 位视频 ID。输出里的 `text` 字段统一为纯文本字幕。
> 新增服务商：在 `agent_reach/transcript_backends.py` 的 `BACKENDS` 里加一个类即可。

### 无字幕兜底：Whisper 音频转写

```bash
# 视频没有字幕时的兜底：下载音频并用 Whisper 转写（Groq 免费 key 即可）
agent-reach transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
agent-reach transcribe ./local_audio.mp3 -o /tmp/transcript.txt
```

> `agent-reach transcribe` 只接收公开 http(s) URL 或本地音频文件。用 `ytsearch5:` 搜索时，先从 yt-dlp 结果里选出具体视频 URL，再转写。
> 需要先配置 key：`agent-reach configure groq-key`（隐藏输入；免费，console.groq.com）
> 或 `agent-reach configure openai-key`。默认 auto 模式只使用第一个已配置服务商
>（优先 Groq，否则 OpenAI），失败即停止，不会把音频自动发给另一家。
> `--allow-provider-fallback` 会显式授权跨服务商降级；同一音频内容可能被 Groq 和
> OpenAI 分别处理，并可能产生 OpenAI 费用，只应在确认内容可分享给两家后使用。

## B站 / Bilibili（bili-cli 为主，OpenCLI 补字幕）

> ⚠️ **不要用 yt-dlp 读 B站**：B站风控已全面 412 拦截 yt-dlp（实测最新版、直连/代理/带 Cookie 全部无效）。yt-dlp 只用于 YouTube。

### 视频详情/搜索/热门/排行 (bili-cli，只读无需登录)

```bash
# 视频详情（标题/UP主/时长/播放互动数据/字幕可用性）
bili video BVxxx

# 搜索视频
bili search "query" --type video -n 5

# 热门视频 / 排行榜
bili hot -n 10
bili rank -n 10

# 下载音频并切分为 ASR-ready WAV（无字幕时配合 agent-reach transcribe 转写）
bili audio BVxxx
```

### 字幕 (OpenCLI，需要桌面 Chrome)

```bash
# 字幕逐句带时间轴
opencli bilibili subtitle BVxxx

# OpenCLI 也能搜索/读视频元数据（备选）
opencli bilibili search "query" -f yaml
opencli bilibili video BVxxx -f yaml
```

### 零配置兜底：搜索 API 直连

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

> **安装 bili-cli**: `pipx install bilibili-cli`（上游 2026-03 起停更但实测健康；只读场景无需登录，`bili login` 扫码可解锁动态/收藏等个人功能）。

## 小宇宙播客 / Xiaoyuzhou Podcast

### 转录单集播客（可选 --polish 增强标点）

```bash
# 输出 Markdown 文件到 /tmp/。--polish 让 Llama 3.3 70B 给文稿补中文标点+合理分段
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh --polish "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

> 转写 prompt 已要求 Whisper 输出中文标点；若标点效果仍不理想，可加 `--polish` 用 Groq 上免费的 Llama 3.3 70B 补标点+合理分段（9 分钟播客约多 ~7 秒）。每次转写多一轮 LLM 调用，按需使用。

### 前置要求

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API Key** (免费): https://console.groq.com/keys
3. **配置 Key**: `agent-reach configure groq-key`（隐藏输入）
4. **首次运行**: `agent-reach install --env=auto --system --channels=xiaoyuzhou`（需用户明确授权）

### 检查状态

```bash
agent-reach doctor
```

> 输出 Markdown 文件默认保存到 `/tmp/`。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| YouTube 字幕 | yt-dlp；失败时 OpenCLI（最多 3 次）→ 已配置时托管字幕后端 → agent-reach transcribe |
| B站视频详情/搜索 | bili-cli |
| B站字幕 | opencli bilibili subtitle |
| 播客转录 | 小宇宙 transcribe.sh |
| 无字幕音视频 | agent-reach transcribe（B站音频先 `bili audio`） |
