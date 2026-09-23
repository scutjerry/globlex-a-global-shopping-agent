# -*- coding: utf-8 -*-
"""OrderRepository 端口

Domain 不关心实现，Infrastructure 提供基于内存（后续可换 PG）的具体仓储。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.order.order import Order


class OrderRepository(ABC):
    @abstractmethod
    async def save(self, order: Order) -> None:
        ...

    @abstractmethod
    async def find_by_id(self, order_id: str) -> Optional[Order]:
        ...

    @abstractmethod
    async def list_orders(self, buyer_id: Optional[str] = None, limit: int = 50) -> list[Order]:
        """按创建时间倒序读取订单；MVP 订单中心只读使用。"""
        ...

    @abstractmethod
    async def next_order_id(self) -> str:
        ...

    @abstractmethod
    async def find_idempotency(self, key_hash: str) -> Optional[tuple[str, str]]:
        """返回 (order_id, request_hash)，仅用于受控模拟订单的写请求去重。"""
        ...

    @abstractmethod
    async def save_idempotency(self, key_hash: str, request_hash: str, order_id: str) -> None:
        ...

    @abstractmethod
    async def save_new_with_idempotency(self, order: Order, key_hash: str, request_hash: str) -> Optional[str]:
        """原子保存新订单及幂等键；返回既有 order_id，成功创建时返回 None。"""
        ...

    @abstractmethod
    async def cancel_if_confirmed(self, order_id: str, control_token_hash: str) -> bool:
        """仅当订单仍可取消且令牌摘要匹配时原子取消。"""
        ...

    @abstractmethod
    async def delete_if_allowed(self, order_id: str, control_token_hash: str) -> bool:
        """仅当运行时模拟订单仍可逻辑删除且令牌摘要匹配时原子删除。"""
        ...
