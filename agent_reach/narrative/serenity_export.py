# -*- coding: utf-8 -*-
"""Standalone, inert HTML export for the local Serenity research archive."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

TAIPEI = timezone(timedelta(hours=8))
_STATUS_ID = re.compile(r"/status/([0-9]{5,30})(?:\b|/)")
_ALLOWED_POST_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
_ALLOWED_IMAGE_HOSTS = {"pbs.twimg.com"}


def _text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True).replace("\n", "<br>\n")


def _safe_https_url(value: Any, *, hosts: set[str]) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.casefold() != "https" or (parsed.hostname or "").casefold() not in hosts:
        return ""
    return urlunsplit(parsed)


def _post_id(row: dict) -> str:
    match = _STATUS_ID.search(str(row.get("source_url") or ""))
    if match:
        return match.group(1)
    fallback = re.sub(r"[^a-zA-Z0-9_-]", "", str(row.get("document_id") or ""))
    return fallback[:80] or "unknown"


def _taipei_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:80]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(TAIPEI).isoformat(timespec="seconds")


def _image_urls(value: Any) -> tuple[str, str] | None:
    safe = _safe_https_url(value, hosts=_ALLOWED_IMAGE_HOSTS)
    if not safe:
        return None
    parsed = urlsplit(safe)
    base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return (
        f"{base}?format=jpg&amp;name=orig",
        f"{base}?format=jpg&amp;name=medium",
    )


def render_serenity_archive(
    units: Iterable[dict],
    *,
    handle: str = "aleabitoreddit",
    as_of: str = "",
    title_suffix: str = "",
) -> dict:
    """Render the documented bilingual card format without executable scripts."""

    rows = list(units)
    rows.sort(
        key=lambda row: (
            str(row.get("published_at") or ""),
            str(row.get("document_id") or ""),
        ),
        reverse=True,
    )
    missing_zh = sum(not str(row.get("zh_hant") or "").strip() for row in rows)
    escaped_suffix = html.escape(str(title_suffix or ""), quote=True)
    escaped_handle = html.escape(handle.lstrip("@"), quote=True)
    escaped_as_of = html.escape(str(as_of or ""), quote=True)
    parts = [
        f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Serenity 貼文存檔{escaped_suffix}</title>
<style>
  :root {{ color-scheme: light; --x-blue:#1d9bf0; --ink:#0f1419; --muted:#536471; --line:#eff3f4; --paper:#fff; --wash:#f7f9fa; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", Arial, sans-serif; background:var(--wash); color:var(--ink); max-width:900px; margin:0 auto; padding:20px; }}
  h1 {{ font-size:1.4rem; border-bottom:2px solid var(--x-blue); padding-bottom:8px; margin:0 0 10px; }}
  .meta {{ color:var(--muted); font-size:.9rem; line-height:1.55; margin-bottom:20px; }}
  .post {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:16px 20px; margin-bottom:24px; scroll-margin-top:12px; }}
  .post-time {{ color:var(--muted); font-size:.85rem; line-height:1.5; margin-bottom:10px; }}
  .post-id {{ color:#8b98a5; font-size:.75rem; }}
  .lang-block {{ margin-bottom:14px; }}
  .lang-label {{ display:inline-block; font-weight:650; font-size:.75rem; color:var(--x-blue); background:#e8f5fd; padding:2px 8px; border-radius:6px; margin-bottom:6px; }}
  .lang-label.pending {{ color:#7a4b00; background:#fff1cc; }}
  .lang-text {{ line-height:1.65; overflow-wrap:anywhere; font-size:.98rem; }}
  .lang-text.pending {{ color:var(--muted); font-style:italic; }}
  .imgs {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
  .imgs img {{ display:block; width:auto; max-width:260px; max-height:260px; border-radius:8px; border:1px solid #eee; object-fit:cover; }}
  hr.sep {{ border:0; border-top:1px solid #eee; margin:14px 0; }}
  a {{ color:var(--x-blue); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  a:focus-visible {{ outline:3px solid #8fd3ff; outline-offset:3px; border-radius:3px; }}
  @media (max-width:600px) {{
    body {{ padding:12px; }}
    .post {{ border-radius:10px; padding:14px; margin-bottom:16px; }}
    .imgs a, .imgs img {{ width:100%; max-width:100%; max-height:none; }}
  }}
  @media (prefers-reduced-motion:reduce) {{ * {{ scroll-behavior:auto !important; }} }}
</style>
</head>
<body>
<main>
<h1>Serenity (@{escaped_handle}) 貼文存檔{escaped_suffix}</h1>
<div class="meta">共 {len(rows)} 則貼文，依時間新到舊排序。中文翻譯待補 {missing_zh} 則；翻譯只供閱讀，不作獨立證據。圖片使用 X 直連圖床，需連網顯示。資料截止日：{escaped_as_of or "未指定"}。</div>
"""
    ]
    for row in rows:
        pid = _post_id(row)
        source_url = _safe_https_url(row.get("source_url"), hosts=_ALLOWED_POST_HOSTS)
        timestamp = _taipei_timestamp(row.get("published_at"))
        zh = str(row.get("zh_hant") or "").strip()
        original = str(row.get("original") or "").strip()
        english = str(row.get("en") or "").strip() or original
        if source_url:
            source_link = (
                f'<a href="{html.escape(source_url, quote=True)}" target="_blank" '
                'rel="noopener noreferrer">原貼文連結</a>'
            )
        else:
            source_link = "原貼文連結不可用"
        zh_block = (
            f'<span class="lang-label">中文</span><div class="lang-text" lang="zh-Hant">{_text(zh)}</div>'
            if zh
            else '<span class="lang-label pending">中文 · 待翻譯</span>'
                 '<div class="lang-text pending" lang="zh-Hant">尚無來源提供或人工核准的繁中翻譯。</div>'
        )
        image_tags = []
        for index, image in enumerate(row.get("images") or [], start=1):
            pair = _image_urls(image)
            if not pair:
                continue
            full, medium = pair
            image_tags.append(
                f'<a href="{full}" target="_blank" rel="noopener noreferrer">'
                f'<img src="{medium}" loading="lazy" '
                f'alt="Serenity 貼文 {html.escape(pid)} 圖片 {index}"></a>'
            )
        images_html = (
            '<div class="imgs">' + "\n".join(image_tags) + "</div>"
            if image_tags else ""
        )
        parts.append(
            f"""<article class="post" id="p{html.escape(pid, quote=True)}">
  <div class="post-time">{html.escape(timestamp)} &nbsp;·&nbsp; {source_link} &nbsp;<span class="post-id">#{html.escape(pid)}</span></div>
  <div class="lang-block">{zh_block}</div>
  <hr class="sep">
  <div class="lang-block"><span class="lang-label">EN / 原文</span><div class="lang-text" lang="en">{_text(english)}</div></div>
  {images_html}
</article>
"""
        )
    parts.append("</main>\n</body>\n</html>\n")
    rendered = "".join(parts)
    return {
        "html": rendered,
        "posts": len(rows),
        "missing_zh": missing_zh,
        "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "inert": True,
    }
