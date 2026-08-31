# -*- coding: utf-8 -*-
"""Standalone Serenity HTML archive safety and presentation tests."""

from agent_reach.narrative.serenity_export import render_serenity_archive


def test_serenity_archive_matches_bilingual_card_format_and_is_inert():
    rendered = render_serenity_archive(
        [
            {
                "document_id": "doc_old",
                "source_url": "https://x.com/aleabitoreddit/status/10001",
                "published_at": "2026-08-29T00:00:00+00:00",
                "original": "older",
                "zh_hant": "",
                "en": "",
                "images": [],
            },
            {
                "document_id": "doc_new",
                "source_url": "https://x.com/aleabitoreddit/status/10002",
                "published_at": "2026-08-30T00:00:00+00:00",
                "original": "<script>alert('x')</script>\nEnglish",
                "zh_hant": "中文\n第二行",
                "en": "English original",
                "images": [
                    "https://pbs.twimg.com/media/fixture",
                    "javascript:alert(1)",
                    "https://example.com/not-x-media",
                ],
            },
        ],
        as_of="2026-08-31",
        title_suffix=" · 90D",
    )
    page = rendered["html"]

    assert rendered["posts"] == 2
    assert rendered["missing_zh"] == 1
    assert rendered["inert"] is True
    assert page.index('id="p10002"') < page.index('id="p10001"')
    assert "<script" not in page.casefold()
    assert "&lt;script&gt;" not in page  # explicit EN wins over original payload
    assert "中文<br>" in page
    assert "中文 · 待翻譯" in page
    assert "2026-08-30T08:00:00+08:00" in page
    assert "pbs.twimg.com/media/fixture?format=jpg&amp;name=medium" in page
    assert "javascript:" not in page
    assert "example.com/not-x-media" not in page
    assert 'rel="noopener noreferrer"' in page
    assert "<meta name=\"viewport\"" in page


def test_serenity_archive_escapes_original_when_no_english_display_text():
    page = render_serenity_archive(
        [
            {
                "document_id": "doc_fixture",
                "source_url": "https://x.com/aleabitoreddit/status/10003",
                "published_at": "2026-08-31T00:00:00+00:00",
                "original": "</div><script>alert(1)</script>",
                "zh_hant": "",
                "en": "",
                "images": [],
            }
        ]
    )["html"]

    assert "<script" not in page.casefold()
    assert "&lt;/div&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in page
