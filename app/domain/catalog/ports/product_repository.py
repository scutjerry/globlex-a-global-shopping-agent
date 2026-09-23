# -*- coding: utf-8 -*-
"""ProductRepository 端口

Domain 不关心实现，Infrastructure 提供基于内存（后续可换 PG / 向量库）的具体仓储。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.catalog.product import Product


class ProductRepository(ABC):
    @abstractmethod
    async def save(self, product: Product) -> None:
        """保存商品聚合（主要用于 SKU 库存变更）。"""
        ...

    @abstractmethod
    async def find_by_id(self, product_id: str) -> Optional[Product]:
        ...

    @abstractmethod
    async def find_by_ids(self, product_ids: list[str]) -> list[Product]:
        ...

    @abstractmethod
    async def list_all(self) -> list[Product]:
        ...
