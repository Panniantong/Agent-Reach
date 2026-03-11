# Douyin Output Reference

This document describes the current output format of Agent Reach's built-in Douyin workflow.

## CLI entrypoint

```bash
python3 -m agent_reach.scripts.douyin_cli --link "分享链接" --action <info|download|extract>
```

## `--action info`

Returns JSON:

```json
{
  "url": "https://aweme.snssdk.com/...",
  "title": "视频标题",
  "video_id": "7608424103746230948"
}
```

Use this mode to verify the share link resolves correctly before downloading or transcribing.

## `--action download`

Returns JSON:

```json
{
  "video_info": {
    "url": "https://aweme.snssdk.com/...",
    "title": "视频标题",
    "video_id": "7608424103746230948"
  },
  "video_path": "/tmp/agent-reach-douyin/7608424103746230948.mp4"
}
```

Use this mode when the user only needs the local video file.

## `--action extract`

Returns JSON:

```json
{
  "video_info": {
    "url": "https://aweme.snssdk.com/...",
    "title": "视频标题",
    "video_id": "7608424103746230948"
  },
  "text": "识别出的文案内容",
  "output_path": "/tmp/agent-reach-douyin/7608424103746230948"
}
```

When no useful transcript is extracted, the command still succeeds but returns a warning:

```json
{
  "video_info": {"...": "..."},
  "text": "",
  "output_path": "/tmp/agent-reach-douyin/7608424103746230948",
  "warning": "语音识别完成，但未提取到有效文本；可能是视频无清晰口播、仅环境音/BGM，或模型未识别出可用内容。"
}
```

## Output directory layout

`extract` writes files under the output directory using `video_id` as the folder name:

```text
<output>/
└── <video_id>/
    ├── transcript.md
    └── <video_id>.mp4   # only when --save-video is set
```

## `transcript.md`

The transcript file contains:

- Title
- Video ID
- Extraction timestamp
- Direct download link
- Transcript body

If no useful text is extracted, the transcript body contains a fallback note instead of staying blank.
