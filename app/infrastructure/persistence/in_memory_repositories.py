# -*- coding: utf-8 -*-
"""InMemoryProductRepository / InMemoryOrderRepository

开发态内存仓储实现。ProductRepository 由种子数据初始化；
OrderRepository 提供自增单号（GBX-XXXX 前缀，便于日志排查）。
"""
from __future__ import annotations

import itertools
import secrets
from typing import Optional

from app.domain.catalog.ports.product_repository import ProductRepository
from app.domain.catalog.product import Product
from app.domain.order.order import Order
from app.domain.order.ports.order_repository import OrderRepository
from app.infrastructure.persistence.seed_products import build_seed_products


class InMemoryProductRepository(ProductRepository):
    def __init__(self, products: Optional[list[Product]] = None) -> None:
        seed = products if products is not None else build_seed_products()
        self._products: dict[str, Product] = {p.product_id: p for p in seed}

    async def save(self, product: Product) -> None:
        self._products[product.product_id] = product

    async def find_by_id(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)

    async def find_by_ids(self, product_ids: list[str]) -> list[Product]:
        return [self._products[pid] for pid in product_ids if pid in self._products]

    async def list_all(self) -> list[Product]:
        return list(self._products.values())


class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._counter = itertools.count(1)
        self._idempotency: dict[str, tuple[str, str]] = {}

    async def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    async def find_by_id(self, order_id: str) -> Optional[Order]:
        order = self._orders.get(order_id)
        return order if order is not None and order.status.value != "DELETED" else None

    async def list_orders(self, buyer_id: Optional[str] = None, limit: int = 50) -> list[Order]:
        orders = (order for order in self._orders.values() if order.status.value != "DELETED")
        if buyer_id is not None:
            orders = (order for order in orders if order.buyer_id == buyer_id)
        return sorted(orders, key=lambda order: (order.created_at, order.order_id), reverse=True)[:limit]

    async def next_order_id(self) -> str:
        return f"GBX-{secrets.token_hex(6).upper()}"

    async def find_idempotency(self, key_hash: str) -> Optional[tuple[str, str]]:
        return self._idempotency.get(key_hash)

    async def save_idempotency(self, key_hash: str, request_hash: str, order_id: str) -> None:
        self._idempotency[key_hash] = (order_id, request_hash)

    async def save_new_with_idempotency(self, order: Order, key_hash: str, request_hash: str) -> Optional[str]:
        existing = self._idempotency.get(key_hash)
        if existing is not None:
            existing_order_id, existing_request_hash = existing
            if existing_request_hash != request_hash:
                raise RuntimeError("Idempotency-Key 已用于不同的模拟订单请求")
            return existing_order_id
        self._orders[order.order_id] = order
        self._idempotency[key_hash] = (order.order_id, request_hash)
        return None

    async def cancel_if_confirmed(self, order_id: str, control_token_hash: str) -> bool:
        order = self._orders.get(order_id)
        if order is None or not order.is_cancellable or order.control_token_hash != control_token_hash:
            return False
        order.cancel()
        return True

    async def delete_if_allowed(self, order_id: str, control_token_hash: str) -> bool:
        order = self._orders.get(order_id)
        if order is None or not order.is_deletable or order.control_token_hash != control_token_hash:
            return False
        order.delete()
        return True
