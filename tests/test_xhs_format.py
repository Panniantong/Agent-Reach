# -*- coding: utf-8 -*-
"""Tests for XiaoHongShu output formatter (issue #134)."""

import unittest

from agent_reach.channels.xiaohongshu import format_xhs_result


class TestFormatXhsResult(unittest.TestCase):
    """Test format_xhs_result strips redundant fields."""

    SAMPLE_NOTE = {
        "id": "abc123",
        "title": "Test Note",
        "desc": "This is the note body",
        "type": "normal",
        "xsec_token": "tok_xxx",
        "user": {
            "nickname": "Alice",
            "user_id": "u123",
            "avatar": "https://example.com/avatar.jpg",
            "extra_field": "should be dropped",
        },
        "interact_info": {
            "liked_count": "100",
            "collected_count": "50",
            "comment_count": "20",
            "share_count": "10",
            "sticky_count": "0",
            "relation": "none",
        },
        "image_list": [
            {
                "url": "https://img.example.com/1.jpg",
                "info_list": [{"url": "https://img.example.com/1_small.jpg", "image_scene": "WB_DFT"}],
                "width": 1080,
                "height": 1440,
                "trace_id": "tr_123",
            },
            {
                "url": "https://img.example.com/2.jpg",
                "info_list": [{"url": "https://img.example.com/2_small.jpg"}],
                "width": 1080,
                "height": 1080,
            },
        ],
        "tag_list": [
            {"id": "t1", "name": "Travel", "type": "topic"},
            {"id": "t2", "name": "Food", "type": "topic"},
        ],
        "at_user_list": [],
        "geo_info": {"latitude": 0, "longitude": 0},
        "audit_info": {"audit_status": 0},
        "model_type": None,
        "note_flow_source": "search",
    }

    def test_single_note_keeps_useful_fields(self):
        result = format_xhs_result(self.SAMPLE_NOTE)
        self.assertEqual(result["id"], "abc123")
        self.assertEqual(result["title"], "Test Note")
        self.assertEqual(result["desc"], "This is the note body")
        self.assertEqual(result["type"], "normal")
        self.assertEqual(result["user"]["nickname"], "Alice")
        self.assertEqual(result["liked_count"], "100")
        self.assertEqual(result["collected_count"], "50")
        self.assertEqual(result["images"], [
            "https://img.example.com/1.jpg",
            "https://img.example.com/2.jpg",
        ])
        self.assertEqual(result["tags"], ["Travel", "Food"])

    def test_single_note_drops_useless_fields(self):
        result = format_xhs_result(self.SAMPLE_NOTE)
        self.assertNotIn("at_user_list", result)
        self.assertNotIn("geo_info", result)
        self.assertNotIn("audit_info", result)
        self.assertNotIn("model_type", result)
        self.assertNotIn("note_flow_source", result)
        # User should not have extra fields
        self.assertNotIn("avatar", result.get("user", {}))
        self.assertNotIn("extra_field", result.get("user", {}))

    def test_search_results_wrapper(self):
        """Handle {"items": [...]} wrapper from search_feeds."""
        wrapped = {"items": [self.SAMPLE_NOTE, self.SAMPLE_NOTE]}
        result = format_xhs_result(wrapped)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "Test Note")

    def test_list_input(self):
        result = format_xhs_result([self.SAMPLE_NOTE])
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Test Note")

    def test_note_card_wrapper(self):
        """Handle notes nested under 'note_card'."""
        wrapped = {"note_card": self.SAMPLE_NOTE}
        result = format_xhs_result(wrapped)
        self.assertEqual(result["title"], "Test Note")

    def test_with_comments(self):
        note = dict(self.SAMPLE_NOTE)
        note["comments"] = [
            {
                "content": "Great post!",
                "user_info": {"nickname": "Visitor A", "user_id": "u456"},
                "like_count": 5,
                "sub_comment_count": 1,
                "ip_location": "Shanghai",
                "status": 0,
            }
        ]
        result = format_xhs_result(note)
        self.assertEqual(len(result["comments"]), 1)
        self.assertEqual(result["comments"][0]["content"], "Great post!")
        self.assertEqual(result["comments"][0]["user"], "Visitor A")
        self.assertEqual(result["comments"][0]["like_count"], 5)
        self.assertNotIn("ip_location", result["comments"][0])

    def test_empty_input(self):
        self.assertEqual(format_xhs_result({}), {})
        self.assertEqual(format_xhs_result([]), [])

    def test_non_dict_passthrough(self):
        self.assertEqual(format_xhs_result("hello"), "hello")
        self.assertIsNone(format_xhs_result(None))


if __name__ == "__main__":
    unittest.main()
