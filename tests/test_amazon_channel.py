# -*- coding: utf-8 -*-
"""Tests for the Amazon channel."""

import unittest
from agent_reach.channels.amazon import AmazonChannel


class TestAmazonChannel(unittest.TestCase):
    def setUp(self):
        self.ch = AmazonChannel()

    # ---- metadata ----
    def test_name(self):
        self.assertEqual(self.ch.name, "amazon")

    def test_tier(self):
        self.assertEqual(self.ch.tier, 0)

    def test_backends(self):
        self.assertIn("Jina Reader", self.ch.backends)

    # ---- can_handle ----
    def test_handle_product_page(self):
        self.assertTrue(self.ch.can_handle("https://www.amazon.com/dp/B0D1XD1ZV3"))

    def test_handle_search(self):
        self.assertTrue(self.ch.can_handle("https://www.amazon.com/s?k=mechanical+keyboard"))

    def test_handle_co_jp(self):
        self.assertTrue(self.ch.can_handle("https://www.amazon.co.jp/dp/B0D1XD1ZV3"))

    def test_handle_de(self):
        self.assertTrue(self.ch.can_handle("https://www.amazon.de/dp/B0D1XD1ZV3"))

    def test_handle_co_uk(self):
        self.assertTrue(self.ch.can_handle("https://www.amazon.co.uk/dp/B0D1XD1ZV3"))

    def test_reject_non_amazon(self):
        self.assertFalse(self.ch.can_handle("https://www.google.com"))

    def test_reject_ebay(self):
        self.assertFalse(self.ch.can_handle("https://www.ebay.com/itm/12345"))

    # ---- check ----
    def test_check_returns_tuple(self):
        status, msg = self.ch.check()
        self.assertIn(status, ("ok", "warn"))
        self.assertIsInstance(msg, str)

    # ---- registration ----
    def test_registered(self):
        from agent_reach.channels import ALL_CHANNELS
        names = [c.name for c in ALL_CHANNELS]
        self.assertIn("amazon", names)


if __name__ == "__main__":
    unittest.main()
