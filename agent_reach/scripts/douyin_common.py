#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common helpers for Douyin video parsing, downloading, and transcription."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import ffmpeg
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1"
}
DEFAULT_API_BASE_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"


class DouyinProcessor:
    def __init__(self, api_key: str = "", api_base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.api_base_url = api_base_url or DEFAULT_API_BASE_URL
        self.model = model or DEFAULT_MODEL
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent-reach-douyin-"))

    def __del__(self):
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def parse_share_url(self, share_text: str) -> dict:
        urls = re.findall(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", share_text)
        if not urls:
            raise ValueError("未找到有效的抖音分享链接")

        share_url = urls[0]
        share_response = requests.get(share_url, headers=HEADERS, timeout=30)
        share_response.raise_for_status()
        video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}"

        response = requests.get(share_url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        pattern = re.compile(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", flags=re.DOTALL)
        find_res = pattern.search(response.text)
        if not find_res or not find_res.group(1):
            raise ValueError("从 HTML 中解析视频信息失败")

        json_data = json.loads(find_res.group(1).strip())
        video_page_key = "video_(id)/page"
        note_page_key = "note_(id)/page"

        if video_page_key in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][video_page_key]["videoInfoRes"]
        elif note_page_key in json_data["loaderData"]:
            original_video_info = json_data["loaderData"][note_page_key]["videoInfoRes"]
        else:
            raise ValueError("无法从 JSON 中解析视频或图集信息")

        data = original_video_info["item_list"][0]
        video_url = data["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        desc = data.get("desc", "").strip() or f"douyin_{video_id}"
        desc = re.sub(r'[\\/:*?"<>|]', '_', desc)

        return {"url": video_url, "title": desc, "video_id": video_id}

    def download_video(self, video_info: dict, output_dir: Optional[Path] = None, show_progress: bool = True) -> Path:
        output_dir = Path(output_dir) if output_dir else self.temp_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{video_info['video_id']}.mp4"

        response = requests.get(video_info["url"], headers=HEADERS, stream=True, timeout=60)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        if show_progress:
            print(f"正在下载视频: {video_info['title']}")

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if show_progress and total_size > 0:
                        progress = downloaded / total_size * 100
                        print(f"\r下载进度: {progress:.1f}%", end="", flush=True)
        if show_progress:
            print(f"\n视频下载完成: {filepath}")
        return filepath

    def extract_audio(self, video_path: Path, show_progress: bool = True) -> Path:
        audio_path = video_path.with_suffix(".mp3")
        if show_progress:
            print("正在提取音频...")
        (
            ffmpeg.input(str(video_path))
            .output(str(audio_path), acodec="libmp3lame", q=0)
            .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        )
        if show_progress:
            print(f"音频提取完成: {audio_path}")
        return audio_path

    def get_audio_info(self, audio_path: Path) -> dict:
        try:
            probe = ffmpeg.probe(str(audio_path))
            duration = float(probe["format"].get("duration", 0))
            size = audio_path.stat().st_size
            return {"duration": duration, "size": size}
        except Exception:
            return {"duration": 0, "size": audio_path.stat().st_size}

    def split_audio(self, audio_path: Path, segment_duration: int = 540, show_progress: bool = True) -> list[Path]:
        audio_info = self.get_audio_info(audio_path)
        duration = audio_info["duration"]
        if duration <= segment_duration:
            return [audio_path]

        segments: list[Path] = []
        segment_index = 0
        current_time = 0
        if show_progress:
            total_segments = int(duration / segment_duration) + 1
            print(f"音频时长 {duration:.0f} 秒，将分割为 {total_segments} 段...")

        while current_time < duration:
            segment_path = self.temp_dir / f"segment_{segment_index}.mp3"
            (
                ffmpeg.input(str(audio_path), ss=current_time, t=segment_duration)
                .output(str(segment_path), acodec="libmp3lame", q=0)
                .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
            )
            segments.append(segment_path)
            current_time += segment_duration
            segment_index += 1
        return segments

    def transcribe_single_audio(self, audio_path: Path) -> str:
        files = {
            "file": (audio_path.name, open(audio_path, "rb"), "audio/mpeg"),
            "model": (None, self.model),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.post(self.api_base_url, files=files, headers=headers, timeout=300)
            response.raise_for_status()
            result = response.json()
            return result.get("text", response.text)
        finally:
            files["file"][1].close()

    def extract_text_from_audio(self, audio_path: Path, show_progress: bool = True) -> str:
        if not self.api_key:
            raise ValueError("未设置 API_KEY 环境变量，无法提取文案")

        audio_info = self.get_audio_info(audio_path)
        max_duration = 3600
        max_size = 50 * 1024 * 1024
        need_split = audio_info["duration"] > max_duration or audio_info["size"] > max_size

        if not need_split:
            if show_progress:
                print("正在识别语音...")
            return self.transcribe_single_audio(audio_path)

        if show_progress:
            print(f"音频文件较大（时长: {audio_info['duration']:.0f}秒, 大小: {audio_info['size'] / 1024 / 1024:.1f}MB），将自动分段处理...")
        segments = self.split_audio(audio_path, segment_duration=540, show_progress=show_progress)
        all_texts = []
        for i, segment_path in enumerate(segments):
            if show_progress:
                print(f"正在识别第 {i + 1}/{len(segments)} 段...")
            all_texts.append(self.transcribe_single_audio(segment_path))
            if segment_path != audio_path:
                self.cleanup_files(segment_path)
        return "".join(all_texts)

    def cleanup_files(self, *file_paths: Path):
        for file_path in file_paths:
            if file_path.exists():
                file_path.unlink()


def save_transcript(video_info: dict, text_content: str, output_dir: str, save_video_path: Optional[Path] = None) -> str:
    output_base = Path(output_dir)
    video_folder = output_base / video_info["video_id"]
    video_folder.mkdir(parents=True, exist_ok=True)

    transcript_path = video_folder / "transcript.md"
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"# {video_info['title']}\n\n")
        f.write("| 属性 | 值 |\n")
        f.write("|------|----|\n")
        f.write(f"| 视频ID | `{video_info['video_id']}` |\n")
        f.write(f"| 提取时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n")
        f.write(f"| 下载链接 | [点击下载]({video_info['url']}) |\n\n")
        f.write("---\n\n## 文案内容\n\n")
        f.write(text_content)

    if save_video_path:
        shutil.copy2(save_video_path, video_folder / f"{video_info['video_id']}.mp4")
    return str(video_folder)
