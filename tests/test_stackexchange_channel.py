# -*- coding: utf-8 -*-
"""Tests for the Stack Exchange channel."""

import unittest
from agent_reach.channels.stackexchange import StackExchangeChannel


class TestStackExchangeChannel(unittest.TestCase):
    def setUp(self):
        self.ch = StackExchangeChannel()

    # ---- metadata ----
    def test_name(self):
        self.assertEqual(self.ch.name, "stackexchange")

    def test_tier(self):
        self.assertEqual(self.ch.tier, 0)

    def test_backends(self):
        self.assertIn("Stack Exchange API", self.ch.backends)

    # ---- can_handle ----
    def test_handle_stackoverflow(self):
        self.assertTrue(self.ch.can_handle("https://stackoverflow.com/questions/12345"))

    def test_handle_stackoverflow_search(self):
        self.assertTrue(self.ch.can_handle("https://stackoverflow.com/search?q=python"))

    def test_handle_stackexchange_subdomain(self):
        self.assertTrue(self.ch.can_handle("https://bioinformatics.stackexchange.com/questions/123"))

    def test_handle_superuser(self):
        self.assertTrue(self.ch.can_handle("https://superuser.com/questions/123"))

    def test_handle_serverfault(self):
        self.assertTrue(self.ch.can_handle("https://serverfault.com/questions/123"))

    def test_handle_askubuntu(self):
        self.assertTrue(self.ch.can_handle("https://askubuntu.com/questions/123"))

    def test_handle_mathoverflow(self):
        self.assertTrue(self.ch.can_handle("https://mathoverflow.net/questions/123"))

    def test_reject_non_stackexchange(self):
        self.assertFalse(self.ch.can_handle("https://www.google.com"))

    def test_reject_quora(self):
        self.assertFalse(self.ch.can_handle("https://www.quora.com/question"))

    def test_reject_zhihu(self):
        self.assertFalse(self.ch.can_handle("https://www.zhihu.com/question/123"))

    # ---- check ----
    def test_check_returns_tuple(self):
        status, msg = self.ch.check()
        self.assertIn(status, ("ok", "warn"))
        self.assertIsInstance(msg, str)

    # ---- registration ----
    def test_registered(self):
        from agent_reach.channels import ALL_CHANNELS
        names = [c.name for c in ALL_CHANNELS]
        self.assertIn("stackexchange", names)


if __name__ == "__main__":
    unittest.main()
