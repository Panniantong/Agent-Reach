# -*- coding: utf-8 -*-
"""Tests for Zhihu and Quora channels."""

import unittest
from agent_reach.channels.zhihu import ZhihuChannel
from agent_reach.channels.quora import QuoraChannel


class TestZhihuChannel(unittest.TestCase):
    def setUp(self):
        self.ch = ZhihuChannel()

    def test_name(self):
        self.assertEqual(self.ch.name, "zhihu")

    def test_tier(self):
        self.assertEqual(self.ch.tier, 2)

    def test_backends(self):
        self.assertIn("zhihuMcpServer", self.ch.backends)

    def test_handle_question(self):
        self.assertTrue(self.ch.can_handle("https://www.zhihu.com/question/19550225"))

    def test_handle_zhuanlan(self):
        self.assertTrue(self.ch.can_handle("https://zhuanlan.zhihu.com/p/123456"))

    def test_handle_answer(self):
        self.assertTrue(self.ch.can_handle("https://www.zhihu.com/question/123/answer/456"))

    def test_handle_hot(self):
        self.assertTrue(self.ch.can_handle("https://www.zhihu.com/hot"))

    def test_reject_non_zhihu(self):
        self.assertFalse(self.ch.can_handle("https://www.google.com"))

    def test_reject_quora(self):
        self.assertFalse(self.ch.can_handle("https://www.quora.com/question"))

    def test_check_returns_tuple(self):
        status, msg = self.ch.check()
        self.assertIn(status, ("ok", "warn", "off"))
        self.assertIsInstance(msg, str)

    def test_registered(self):
        from agent_reach.channels import ALL_CHANNELS
        names = [c.name for c in ALL_CHANNELS]
        self.assertIn("zhihu", names)


class TestQuoraChannel(unittest.TestCase):
    def setUp(self):
        self.ch = QuoraChannel()

    def test_name(self):
        self.assertEqual(self.ch.name, "quora")

    def test_tier(self):
        self.assertEqual(self.ch.tier, 1)

    def test_backends(self):
        self.assertIn("Exa", self.ch.backends)

    def test_handle_question(self):
        self.assertTrue(self.ch.can_handle("https://www.quora.com/What-is-AI"))

    def test_handle_profile(self):
        self.assertTrue(self.ch.can_handle("https://www.quora.com/profile/Someone"))

    def test_handle_subdomain(self):
        self.assertTrue(self.ch.can_handle("https://fr.quora.com/question"))

    def test_reject_non_quora(self):
        self.assertFalse(self.ch.can_handle("https://www.google.com"))

    def test_reject_zhihu(self):
        self.assertFalse(self.ch.can_handle("https://www.zhihu.com/question/123"))

    def test_reject_stackoverflow(self):
        self.assertFalse(self.ch.can_handle("https://stackoverflow.com/questions/123"))

    def test_check_returns_tuple(self):
        status, msg = self.ch.check()
        self.assertIn(status, ("ok", "warn", "off"))
        self.assertIsInstance(msg, str)

    def test_registered(self):
        from agent_reach.channels import ALL_CHANNELS
        names = [c.name for c in ALL_CHANNELS]
        self.assertIn("quora", names)


if __name__ == "__main__":
    unittest.main()
