# -*- coding: utf-8 -*-
"""受控模拟订单用例。

所有运行时写操作仅记录项目自建虚构数据：不会扣减/预占/回补库存，也不会调用
支付、履约、物流、搜索或其他外部交易服务。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Optional

from app.domain.catalog.exchange_rate import ExchangeRateTable
from app.domain.catalog.ports.product_repository import ProductRepository
from app.domain.catalog.product import Product
from app.domain.order.order import Order, OrderPricingSnapshot
from app.domain.order.order_line import OrderLine
from app.domain.order.ports.order_repository import OrderRepository
from app.domain.shipping.simulated_fee_rules import SimulatedFeeQuote, SimulatedFeeSchedule


@dataclass(frozen=True)
class OrderItemInput:
    product_id: str
    sku_id: str
    quantity: int


@dataclass(frozen=True)
class SimulatedOrderQuote:
    lines: list[OrderLine]
    fee_quote: SimulatedFeeQuote

    def public_view(self) -> dict:
        return {
            **self.fee_quote.to_dict(),
            "items": [
                {
                    "product_id": line.product_id,
                    "sku_id": line.sku_id,
                    "title": line.title,
                    "unit_price_major": line.unit_price.to_major_units(),
                    "currency": line.unit_price.currency,
                    "quantity": line.quantity,
                }
                for line in self.lines
            ],
        }


@dataclass(frozen=True)
class CreatedSimulatedOrder:
    order: Order
    control_token: str
    reused: bool = False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class QuoteSimulatedOrderUseCase:
    def __init__(
        self,
        product_repo: ProductRepository,
        fee_schedule: Optional[SimulatedFeeSchedule] = None,
    ) -> None:
        self._product_repo = product_repo
        self._fees = fee_schedule or SimulatedFeeSchedule(ExchangeRateTable())

    async def execute(
        self,
        items: list[OrderItemInput],
        destination_country: str,
        currency: str,
    ) -> SimulatedOrderQuote:
        if not items:
            raise ValueError("订单 items 不能为空")
        if destination_country not in self._fees.supported_destinations():
            self._fees.rule_for(destination_country)  # raises a stable, explanatory validation error
        if len({(item.product_id, item.sku_id) for item in items}) != len(items):
            raise ValueError("订单不允许重复商品项，请合并数量后重试")
        total_quantity = 0
        lines: list[OrderLine] = []
        for item in items:
            if not item.product_id or not item.sku_id:
                raise ValueError("订单商品与 SKU 不能为空")
            if not isinstance(item.quantity, int) or isinstance(item.quantity, bool) or not 1 <= item.quantity <= 10:
                raise ValueError("每个模拟订单商品数量必须在 1 到 10 之间")
            product = await self._require_product(item.product_id)
            if destination_country not in product.ships_to:
                raise ValueError(f"商品不支持寄送至 {destination_country}：{product.product_id}")
            sku = product.find_sku(item.sku_id)
            if sku is None:
                raise ValueError(f"Sku 不存在：{item.product_id}/{item.sku_id}")
            # 运行时不检查或改变库存：目录库存只是演示字段，不构成可售承诺。
            target_price = self._fees.rates.convert(sku.price, currency)
            lines.append(OrderLine(
                product_id=product.product_id,
                sku_id=sku.sku_id,
                title=f"{product.title}（{sku.spec}）",
                unit_price=target_price,
                quantity=item.quantity,
            ))
            total_quantity += item.quantity
        if total_quantity > 10:
            raise ValueError("订单商品总数量必须在 1 到 10 之间")
        subtotal = lines[0].subtotal()
        for line in lines[1:]:
            subtotal = subtotal.add(line.subtotal())
        return SimulatedOrderQuote(
            lines=lines,
            fee_quote=self._fees.quote(subtotal, total_quantity, destination_country, currency),
        )

    async def _require_product(self, product_id: str) -> Product:
        product = await self._product_repo.find_by_id(product_id)
        if product is None:
            raise ValueError(f"商品不存在：{product_id}")
        return product


class CreateSimulatedOrderUseCase:
    def __init__(
        self,
        quote_order: QuoteSimulatedOrderUseCase,
        order_repo: OrderRepository,
    ) -> None:
        self._quote_order = quote_order
        self._order_repo = order_repo

    async def execute(
        self,
        buyer_id: str,
        items: list[OrderItemInput],
        destination_country: str,
        currency: str,
    ) -> CreatedSimulatedOrder:
        if not buyer_id:
            raise ValueError("订单 buyer_id 不能为空")
        quote = await self._quote_order.execute(items, destination_country, currency)
        control_token = secrets.token_urlsafe(32)
        pricing = OrderPricingSnapshot(
            merchandise_subtotal=quote.fee_quote.merchandise_subtotal,
            shipping_amount=quote.fee_quote.shipping_amount,
            import_tax_amount=quote.fee_quote.import_tax_amount,
            destination_country=quote.fee_quote.destination_country,
            rule_set_version=quote.fee_quote.rule_set_version,
            source_ids=(quote.fee_quote.source_id,),
            source_summary=quote.fee_quote.source_summary,
            source_status=quote.fee_quote.source_status,
            estimate_disclaimer=quote.fee_quote.estimate_disclaimer,
        )
        order = Order.place_simulation(
            order_id=await self._order_repo.next_order_id(),
            buyer_id=buyer_id,
            destination_country=destination_country,
            lines=quote.lines,
            pricing=pricing,
            control_token_hash=_token_hash(control_token),
        )
        await self._order_repo.save(order)
        return CreatedSimulatedOrder(order=order, control_token=control_token)

    async def execute_with_idempotency(
        self,
        buyer_id: str,
        items: list[OrderItemInput],
        destination_country: str,
        currency: str,
        request_key_hash: str,
        request_hash: str,
    ) -> CreatedSimulatedOrder:
        if not request_key_hash or not request_hash:
            raise ValueError("订单幂等键不能为空")
        if not buyer_id:
            raise ValueError("订单 buyer_id 不能为空")
        # Fast retry path: return the originally frozen order before re-quoting against mutable catalog/rules.
        existing = await self._order_repo.find_idempotency(request_key_hash)
        if existing is not None:
            existing_order_id, existing_request_hash = existing
            if existing_request_hash != request_hash:
                raise RuntimeError("Idempotency-Key 已用于不同的模拟订单请求")
            previous = await self._order_repo.find_by_id(existing_order_id)
            if previous is None:
                # Keep the idempotency record rather than silently recreating a logically deleted order.
                raise RuntimeError("该订单已删除，不能通过重试恢复")
            return CreatedSimulatedOrder(order=previous, control_token="", reused=True)
        quote = await self._quote_order.execute(items, destination_country, currency)
        control_token = secrets.token_urlsafe(32)
        pricing = OrderPricingSnapshot(
            merchandise_subtotal=quote.fee_quote.merchandise_subtotal,
            shipping_amount=quote.fee_quote.shipping_amount,
            import_tax_amount=quote.fee_quote.import_tax_amount,
            destination_country=quote.fee_quote.destination_country,
            rule_set_version=quote.fee_quote.rule_set_version,
            source_ids=(quote.fee_quote.source_id,),
            source_summary=quote.fee_quote.source_summary,
            source_status=quote.fee_quote.source_status,
            estimate_disclaimer=quote.fee_quote.estimate_disclaimer,
        )
        order = Order.place_simulation(
            order_id=await self._order_repo.next_order_id(), buyer_id=buyer_id,
            destination_country=destination_country, lines=quote.lines, pricing=pricing,
            control_token_hash=_token_hash(control_token),
        )
        existing_order_id = await self._order_repo.save_new_with_idempotency(order, request_key_hash, request_hash)
        if existing_order_id is None:
            return CreatedSimulatedOrder(order=order, control_token=control_token)
        existing = await self._order_repo.find_by_id(existing_order_id)
        if existing is None:
            raise RuntimeError("幂等模拟订单记录不完整")
        return CreatedSimulatedOrder(order=existing, control_token="", reused=True)


class DeleteSimulatedOrderUseCase:
    """控制令牌授权的逻辑删除；不物理删除任何订单行、审计或幂等记录。"""

    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def execute(self, order_id: str, control_token: str) -> None:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            raise LookupError("订单不存在")
        if not order.is_deletable:
            raise RuntimeError("该订单当前不可删除")
        token_hash = _token_hash(control_token) if control_token else ""
        if not token_hash or not order.control_token_hash or not hmac.compare_digest(token_hash, order.control_token_hash):
            # Do not disclose whether this order belongs to an actor or whether a supplied token was close.
            raise PermissionError("无法执行此订单删除")
        if not await self._order_repo.delete_if_allowed(order_id, token_hash):
            # Another delete/cancel may have won after the initial check; never resurrect on a retry.
            refreshed = await self._order_repo.find_by_id(order_id)
            if refreshed is None:
                raise LookupError("订单不存在")
            raise RuntimeError("该订单当前不可删除")


class QueryOrderUseCase:
    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def execute(self, order_id: str) -> dict:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            raise ValueError(f"订单不存在：{order_id}")
        return order.public_view()


class ListOrdersUseCase:
    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def execute(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("订单列表 limit 必须在 1 到 50 之间")
        return [
            {
                key: order.public_view()[key]
                for key in (
                    "order_id", "status", "total_amount_major", "currency", "destination_country",
                    "created_at", "order_kind",
                )
            } | {"item_count": sum(line.quantity for line in order.lines)}
            for order in await self._order_repo.list_orders(limit=limit)
        ]


class CancelSimulatedOrderUseCase:
    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def execute(self, order_id: str, control_token: str) -> dict:
        order = await self._order_repo.find_by_id(order_id)
        if order is None:
            raise LookupError(f"订单不存在：{order_id}")
        if not order.is_cancellable:
            raise RuntimeError("该订单当前不可取消")
        token_hash = _token_hash(control_token) if control_token else ""
        if not token_hash or not order.control_token_hash or not hmac.compare_digest(token_hash, order.control_token_hash):
            # Intentional generic message: do not reveal ownership or token validity detail.
            raise PermissionError("无法执行此订单取消")
        if not await self._order_repo.cancel_if_confirmed(order_id, token_hash):
            # A concurrent cancellation may have won after the initial read.
            refreshed = await self._order_repo.find_by_id(order_id)
            if refreshed is not None and refreshed.status.value == "CANCELLED":
                raise RuntimeError("该订单当前不可取消")
            raise PermissionError("无法执行此订单取消")
        cancelled = await self._order_repo.find_by_id(order_id)
        if cancelled is None:
            raise RuntimeError("订单取消后读取失败")
        return cancelled.public_view()

