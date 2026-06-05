# Video / Podcast

Subtitles and transcription for YouTube, Bilibili, and Xiaoyuzhou podcasts.

## YouTube (yt-dlp)

### Get video metadata

```bash
yt-dlp --dump-json "URL"
```

### Download subtitles

```bash
# Download subtitles (no video download)
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# Then read the .vtt file
cat /tmp/VIDEO_ID.*.vtt
```

### Get comments

```bash
# Extract comments (best-effort, not guaranteed complete)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# Comments are in the .info.json comments field
```

### Search videos

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> **Subtitle note**: Manually uploaded subtitles are reliable; auto-generated subtitles may have duplicate lines between segments.
> **Comment note**: `--write-comments` is web-scraping based (not YouTube Data API), some comments may be missing.

## Bilibili (yt-dlp + bili-cli)

### Video metadata (yt-dlp)

```bash
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"
```

### Subtitles (yt-dlp)

```bash
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

### Search / Hot / Rankings (bili-cli)

```bash
# Search videos
bili search "query" --type video -n 5

# Hot videos
bili hot -n 10

# Rankings
bili rank -n 10
```

> **412 protection**: Overseas IPs must provide cookies (`--cookies-from-browser chrome` or `--cookies /path/to/cookies.txt`). Domestic IPs are generally fine.
> **Install bili-cli**: `pipx install bilibili-cli`, then `bili login` (scan QR code).

## Xiaoyuzhou Podcast

### Transcribe a single episode

```bash
# Outputs Markdown files to /tmp/
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

### Prerequisites

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API Key** (free): https://console.groq.com/keys
3. **Configure Key**: `agent-reach configure groq-key YOUR_KEY`
4. **First run**: `agent-reach install --env=auto` to install tools

### Check status

```bash
agent-reach doctor
```

> Output Markdown files default to `/tmp/`.

## Douyin Video Parsing

```bash
# Parse video info
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# Get watermark-free download link
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'
```

> See [social_en.md](social_en.md) for details.

## Selection Guide

| Scenario | Recommended Tool |
|----------|-----------------|
| YouTube subtitles | yt-dlp |
| Bilibili subtitles | yt-dlp |
| Podcast transcription | Xiaoyuzhou transcribe.sh |
| Douyin video parsing | douyin MCP |
