# YouTube

Use `yt-dlp` for metadata and subtitles.

```powershell
yt-dlp --dump-single-json "https://www.youtube.com/watch?v=VIDEO_ID"
yt-dlp --skip-download --write-auto-sub --sub-langs "en.*,ja.*" -o "%(id)s" "https://www.youtube.com/watch?v=VIDEO_ID"
```

If `agent-reach doctor` warns about the JS runtime, run the fix command shown there before retrying.
