# -*- coding: utf-8 -*-

import json

from agent_reach.channels import get_channel
from agent_reach.channels.shopify import ShopifyChannel, main


def test_health_mock(monkeypatch):
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_TOKEN", raising=False)

    assert get_channel("shopify") is not None
    assert ShopifyChannel().health() == {"status": "ok"}


def test_products_list_mock(monkeypatch):
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_TOKEN", raising=False)

    result = ShopifyChannel().products_list()
    assert "products" in result
    assert len(result["products"]) >= 1
    assert result["products"][0]["id"] == 1001
    assert result["products"][0]["variants"][0]["inventory_quantity"] == 42


def test_products_get_mock(monkeypatch):
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_TOKEN", raising=False)

    result = ShopifyChannel().products_get("1002")
    assert result["product"]["id"] == 1002
    assert result["product"]["handle"] == "mock-mug"


def test_missing_product_id(capsys, monkeypatch):
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_TOKEN", raising=False)

    code = main(["products", "get"])
    captured = capsys.readouterr()

    assert code == 1
    assert json.loads(captured.out) == {"error": "missing required argument: --id"}


def test_invalid_command(capsys):
    code = main(["not-a-command"])
    captured = capsys.readouterr()

    assert code == 2
    payload = json.loads(captured.out)
    assert "error" in payload


def test_api_error_handling(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "demo.myshopify.com")
    monkeypatch.setenv("SHOPIFY_TOKEN", "token")

    class FakeResponse:
        status_code = 500

        @staticmethod
        def json():
            return {"errors": "internal"}

    monkeypatch.setattr("agent_reach.channels.shopify.requests.get", lambda *args, **kwargs: FakeResponse())

    result = ShopifyChannel().products_list()
    assert result == {"error": "shopify api error: 500"}
