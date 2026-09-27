# Video and podcasts

Subtitles and transcriptions for YouTube, Bilibili, and Xiaoyuzhou Podcast.

## YouTube (yt-dlp)

### Get video metadata

```bash
yt-dlp --dump-json "URL"
```

### Download subtitles

```bash
# Download subtitles (Don't download videos)
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"

# then read .vtt document
cat /tmp/VIDEO_ID.*.vtt
```

### Get comments

```bash
# Extract comments (best-effort, Not guaranteed to be complete)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"
# Comments on .info.json of comments in field
```

### Search videos

```bash
yt-dlp --dump-json "ytsearch5:query"
```

> **Subtitle Note**: Manually uploaded subtitles are extracted reliably; automatically generated subtitles may have line duplication and require post-processing.
> **Comment Note**: `--write-comments` is based on web scraping (not YouTube Data API), some comments may be lost.

### Retry chain when subtitles fail (execute in order, stop when the actual content is obtained)

`doctor` checks that yt-dlp and its JS runtime run; it does not request a specific video.
`active_backend: yt-dlp` therefore does not prove that subtitles are available for the target video.

1. First use the `yt-dlp --write-sub --write-auto-sub` command above.
2. If bot verification occurs, the subtitle response is empty or no subtitle file is generated, and OpenCLI is connected:
   `opencli youtube transcript "URL" -f yaml`.
3. If OpenCLI returns `Caption URL returned empty response`, retry up to 3 times.
   Expiring subtitle URLs can fail intermittently; an empty response does not prove
   that the video has no subtitles.
4. Still failed or the video does not have subtitles: `agent-reach transcribe "URL"` download audio transcription.

The success criterion is actually obtaining non-empty subtitles/transcription content, not the command exit code or the version detection result of `doctor`.

### No subtitles: Whisper Audio Transcription

```bash
# The bottom line when the video has no subtitles:Download the audio and use it Whisper Transcribe (Groq free key That’s it)
agent-reach transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
agent-reach transcribe ./local_audio.mp3 -o /tmp/transcript.txt
```

> `agent-reach transcribe` only accepts public http(s) URLs or local audio files. When searching with `ytsearch5:`, first select the specific video URL from the yt-dlp results and then transcribe it.
> Need to configure key first: `agent-reach configure groq-key` (hidden input; free, console.groq.com)
> or `agent-reach configure openai-key`. The default auto mode only uses the first configured service provider
> (Groq is preferred, otherwise OpenAI), it will stop if it fails, and the audio will not be automatically sent to another company.
> `--allow-provider-fallback` will explicitly authorize cross-service provider downgrade; the same audio content may be used by Groq and
> OpenAI handles it separately and may incur OpenAI fees. It should only be used after confirming that the content can be shared with both parties.

## Bilibili (based on bili-cli, with OpenCLI supplementing subtitles)

> ⚠️ **Do not use yt-dlp to read Bilibili**: Bilibili blocks yt-dlp with HTTP 412, including the tested direct, proxy, and cookie-based paths. yt-dlp is for YouTube only.

### Video details/search/popular/ranking (bili-cli, read-only without logging in)

```bash
# Video details (title/UPhost/duration/Play interactive data/Subtitle availability)
bili video BVxxx

# Search videos
bili search "query" --type video -n 5

# Popular videos / Ranking list
bili hot -n 10
bili rank -n 10

# Download audio and split into ASR-ready WAV (Cooperate when there are no subtitles agent-reach transcribe Transcribe)
bili audio BVxxx
```

### Subtitles (OpenCLI, requires desktop Chrome)

```bash
# Subtitles sentence by sentence with timeline
opencli bilibili subtitle BVxxx

# OpenCLI Can also search/Read video metadata (alternative)
opencli bilibili search "query" -f yaml
opencli bilibili video BVxxx -f yaml
```

### Zero configuration: search API direct connection

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

> **Install bili-cli**: `pipx install bilibili-cli` (upstream maintenance stopped in March 2026, but the tool still worked in testing; read-only scenes do not require login, `bili login` scans the code to unlock personal functions such as updates/favorites).

## Xiaoyuzhou Podcast

### Transcribe a single podcast episode (optional --polish to enhance punctuation)

```bash
# output Markdown file to /tmp/.--polish let Llama 3.3 70B Add Chinese punctuation to manuscripts+Reasonable segmentation
~/.agent-reach/tools/xiaoyuzhou/transcribe.sh --polish "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID"
```

> Transcription prompt has asked Whisper to output Chinese punctuation; if the punctuation effect is still not satisfactory, you can add `--polish` and use the free Llama 3.3 70B on Groq to add punctuation + reasonable segmentation (about 7 seconds longer for a 9-minute podcast). Each transfer adds one more round of LLM calls, which can be used as needed.

### Prerequisites

1. **ffmpeg**: `brew install ffmpeg`
2. **Groq API Key** (free): https://console.groq.com/keys
3. **Configuration Key**: `agent-reach configure groq-key` (hidden input)
4. **First run**: `agent-reach install --env=auto --system --channels=xiaoyuzhou` (requires explicit authorization from the user)

### Check status

```bash
agent-reach doctor
```

> The output Markdown file is saved to `/tmp/` by default.

## Selection Guide

| Scenario | Recommended Tools |
|-----|---------|
| YouTube subtitles | yt-dlp; OpenCLI on failure (up to 3 times) → agent-reach transcribe |
| Bilibili video details/search | bili-cli |
| Bilibili subtitles | opencli bilibili subtitle |
| Podcast Transcription | Xiaoyuzhou transcribe.sh |
| Audio and video without subtitles | agent-reach transcribe (audio from Bilibili first `bili audio`) |
