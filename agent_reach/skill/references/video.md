# Video / Podcasts

Subtitles and transcripts for YouTube, Bilibili, and Xiaoyuzhou podcasts.

## YouTube (yt-dlp)

### Get video metadata

```bash
yt-dlp --dump-json "URL"
```

### Download subtitles

```bash
# Download subtitles (without downloading the video)
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# Then read the .vtt file
cat /tmp/VIDEO_ID.*.vtt
```

### Get comments

```bash
# Extract comments (best-effort, completeness not guaranteed)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# Comments are in the "comments" field of the .info.json file
```

### Search videos

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> **Subtitle note**: Manually uploaded subtitles extract reliably; auto-generated subtitles may have repeated lines and need post-processing.
> **Comment note**: `--write-comments` is based on web scraping (not the YouTube Data API), so some comments may be missing.

## Bilibili (yt-dlp + bili-cli)

### Video metadata (yt-dlp)

```bash
yt-dlp --dump-json "https://www.bilibili.com/video/BVxxx"
```

### Subtitles (yt-dlp)

```bash
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --convert-subs vtt --skip-download -o "/tmp/%(id)s" "URL"
```

### Search/hot/ranking (bili-cli)

```bash
# Search videos
bili search "query" --type video -n 5

# Hot videos
bili hot -n 10

# Ranking
bili rank -n 10
```

> **412 anti-abuse**: Overseas IPs must provide a Cookie (`--cookies-from-browser chrome` or `--cookies /path/to/cookies.txt`); domestic IPs are generally unaffected.
> **Install bili-cli**: `pipx install bilibili-cli`, then `bili login` and scan the QR code to log in.

## Xiaoyuzhou Podcast

### Transcribe a single podcast episode

```bash
# Outputs a Markdown file to /tmp/
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

### Prerequisites

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API Key** (free): https://console.groq.com/keys
3. **Configure the key**: `agent-reach configure groq-key YOUR_KEY`
4. **First run**: `agent-reach install --env=auto` to install the tools

### Check status

```bash
agent-reach doctor
```

> The output Markdown file is saved to `/tmp/` by default.

## Douyin Video Parsing

```bash
# Parse video info
mcporter call 'douyin.parse_douyin_video_info(share_link: "https://v.douyin.com/xxx/")'

# Get a watermark-free download link
mcporter call 'douyin.get_douyin_download_link(share_link: "https://v.douyin.com/xxx/")'
```

> See [social.md](social.md#douyin--douyin)

## Selection Guide

| Scenario | Recommended Tool |
|-----|---------|
| YouTube subtitles | yt-dlp |
| Bilibili subtitles | yt-dlp |
| Podcast transcription | Xiaoyuzhou transcribe.sh |
| Douyin video parsing | douyin MCP |
