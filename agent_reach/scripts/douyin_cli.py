#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI for Douyin info/download/extract workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from agent_reach.scripts.douyin_common import DouyinProcessor, save_transcript


def cmd_info(link: str) -> int:
    info = DouyinProcessor().parse_share_url(link)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_download(link: str, output: str, quiet: bool) -> int:
    processor = DouyinProcessor()
    info = processor.parse_share_url(link)
    video_path = processor.download_video(info, Path(output), show_progress=not quiet)
    print(json.dumps({"video_info": info, "video_path": str(video_path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_extract(link: str, output: str, api_key: str | None, save_video: bool, quiet: bool) -> int:
    api_key = api_key or os.getenv("API_KEY")
    if not api_key:
        raise ValueError("未设置 API_KEY 环境变量，请先配置硅基流动 API 密钥")

    processor = DouyinProcessor(api_key=api_key)
    info = processor.parse_share_url(link)
    video_path = processor.download_video(info, show_progress=not quiet)
    audio_path = processor.extract_audio(video_path, show_progress=not quiet)
    text = processor.extract_text_from_audio(audio_path, show_progress=not quiet)
    warning = None
    if not text or not text.strip():
        warning = "语音识别完成，但未提取到有效文本；可能是视频无清晰口播、仅环境音/BGM，或模型未识别出可用内容。"
        text = ""
    saved_dir = save_transcript(info, text if text else "（未识别到有效文本，可能是视频无清晰口播或仅背景音）", output, save_video_path=video_path if save_video else None)
    processor.cleanup_files(video_path, audio_path)
    payload = {"video_info": info, "text": text, "output_path": saved_dir}
    if warning:
        payload["warning"] = warning
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Reach Douyin workflow")
    parser.add_argument("--link", "-l", required=True, help="抖音分享链接或包含链接的文本")
    parser.add_argument("--action", "-a", choices=["info", "download", "extract"], default="info")
    parser.add_argument("--output", "-o", default="/tmp/agent-reach-douyin", help="输出目录")
    parser.add_argument("--api-key", "-k", help="硅基流动 API 密钥")
    parser.add_argument("--save-video", action="store_true", help="提取文案时同时保存视频")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")
    args = parser.parse_args()

    try:
        if args.action == "info":
            return cmd_info(args.link)
        if args.action == "download":
            return cmd_download(args.link, args.output, args.quiet)
        return cmd_extract(args.link, args.output, args.api_key, args.save_video, args.quiet)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
