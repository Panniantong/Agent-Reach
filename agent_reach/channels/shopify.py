# -*- coding: utf-8 -*-
"""Shopify channel and JSON CLI for product access."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests

from .base import Channel

_API_VERSION = "2024-01"
_MOCK_PRODUCTS = [
    {
        "id": 1001,
        "title": "Mock T-Shirt",
        "handle": "mock-t-shirt",
        "status": "active",
        "vendor": "Agent Reach",
        "product_type": "Apparel",
        "tags": "mock,test",
        "variants": [
            {
                "id": 2001,
                "title": "Default Title",
                "sku": "MOCK-TSHIRT",
                "price": "19.99",
                "inventory_quantity": 42,
            }
        ],
    },
    {
        "id": 1002,
        "title": "Mock Mug",
        "handle": "mock-mug",
        "status": "draft",
        "vendor": "Agent Reach",
        "product_type": "Home",
        "tags": "mock,test",
        "variants": [
            {
                "id": 2002,
                "title": "Default Title",
                "sku": "MOCK-MUG",
                "price": "12.50",
                "inventory_quantity": 8,
            }
        ],
    },
]


class ShopifyChannel(Channel):
    name = "shopify"
    description = "Shopify structured store data"
    backends = ["shopify-rest-api"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse

        return "myshopify.com" in urlparse(url).netloc.lower()

    def check(self, config=None):
        result = self.health()
        if "error" in result:
            return "warn", result["error"]
        if self._is_mock_mode():
            return "ok", "Shopify mock mode available"
        return "ok", "Shopify REST API available"

    def health(self) -> Dict[str, Any]:
        if self._is_mock_mode():
            return {"status": "ok"}
        payload = self._request("products.json", params={"limit": 1})
        if "error" in payload:
            return payload
        return {"status": "ok"}

    def products_list(self) -> Dict[str, Any]:
        if self._is_mock_mode():
            return {"products": [self._normalize_product(item) for item in _MOCK_PRODUCTS]}
        payload = self._request("products.json")
        if "error" in payload:
            return payload
        products = payload.get("products", [])
        return {"products": [self._normalize_product(item) for item in products]}

    def products_get(self, product_id: Optional[str]) -> Dict[str, Any]:
        if not product_id:
            return {"error": "missing required argument: --id"}

        if self._is_mock_mode():
            for item in _MOCK_PRODUCTS:
                if str(item.get("id")) == str(product_id):
                    return {"product": self._normalize_product(item)}
            return {"product": self._normalize_product(_MOCK_PRODUCTS[0])}

        payload = self._request(f"products/{product_id}.json")
        if "error" in payload:
            return payload
        product = payload.get("product")
        if not product:
            return {"error": f"product not found: {product_id}"}
        return {"product": self._normalize_product(product)}

    def _is_mock_mode(self) -> bool:
        return not (os.getenv("SHOPIFY_SHOP") and os.getenv("SHOPIFY_TOKEN"))

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        shop = os.getenv("SHOPIFY_SHOP")
        token = os.getenv("SHOPIFY_TOKEN")
        if not shop or not token:
            return {"error": "missing Shopify credentials"}

        url = f"https://{shop}/admin/api/{_API_VERSION}/{path}"
        response = requests.get(
            url,
            headers={
                "X-Shopify-Access-Token": token,
                "Accept": "application/json",
            },
            params=params,
            timeout=10,
        )

        if response.status_code >= 400:
            return {"error": f"shopify api error: {response.status_code}"}

        try:
            return response.json()
        except ValueError:
            return {"error": "invalid shopify response"}

    @staticmethod
    def _normalize_product(product: Dict[str, Any]) -> Dict[str, Any]:
        variants = []
        for variant in product.get("variants", []):
            variants.append(
                {
                    "id": variant.get("id"),
                    "title": variant.get("title"),
                    "sku": variant.get("sku"),
                    "price": variant.get("price"),
                    "inventory_quantity": variant.get("inventory_quantity"),
                }
            )

        return {
            "id": product.get("id"),
            "title": product.get("title"),
            "handle": product.get("handle"),
            "status": product.get("status"),
            "vendor": product.get("vendor"),
            "product_type": product.get("product_type"),
            "tags": product.get("tags"),
            "variants": variants,
        }


class _ShopifyArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ShopifyArgumentParser(prog="mcp-shopify")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("health")

    products = sub.add_parser("products")
    products_sub = products.add_subparsers(dest="products_command")
    products_sub.add_parser("list")
    get_parser = products_sub.add_parser("get")
    get_parser.add_argument("--id")

    return parser


def _handle_args(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    parser = _build_parser()
    args = parser.parse_args(argv)
    channel = ShopifyChannel()

    if args.command == "health":
        return channel.health()
    if args.command == "products" and args.products_command == "list":
        return channel.products_list()
    if args.command == "products" and args.products_command == "get":
        return channel.products_get(args.id)
    raise ValueError("invalid command")


def main(argv: Optional[List[str]] = None) -> int:
    try:
        result = _handle_args(argv)
        exit_code = 0 if "error" not in result else 1
    except ValueError as exc:
        result = {"error": str(exc)}
        exit_code = 2

    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
