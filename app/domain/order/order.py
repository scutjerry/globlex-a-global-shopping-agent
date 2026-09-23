# -*- coding: utf-8 -*-
"""Globex 模拟订单聚合根。

运行时创建的订单只代表项目自建虚构数据的模拟记录：不支付、不履约、不处理
真实地址，且绝不改变 SKU 库存。固定种子订单保留为可读演示数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.domain.catalog.money import Money
from app.domain.order.address import Address
from app.domain.order.order_line import OrderLine


class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    # A logical-deletion terminal state. It is never exposed through public reads.
    DELETED = "DELETED"


class OrderKind(str, Enum):
    SEEDED_DEMO = "SEEDED_DEMO"
    USER_SIMULATION = "USER_SIMULATION"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OrderPricingSnapshot:
    """创建时冻结的模拟到手价；所有金额必须同币种且合计精确一致。"""

    merchandise_subtotal: Money
    shipping_amount: Money
    import_tax_amount: Money
    destination_country: str
    rule_set_version: str
    source_ids: tuple[str, ...]
    source_summary: str
    source_status: str
    estimate_disclaimer: str

    def __post_init__(self) -> None:
        currencies = {
            self.merchandise_subtotal.currency,
            self.shipping_amount.currency,
            self.import_tax_amount.currency,
        }
        if len(currencies) != 1:
            raise ValueError("订单费用快照币种必须一致")
        if (
            not self.destination_country or not self.rule_set_version or not self.source_ids
            or not self.source_summary or not self.source_status or not self.estimate_disclaimer
        ):
            raise ValueError("订单费用快照的目的市场、规则版本、来源、状态和免责声明不能为空")

    def landed_total(self) -> Money:
        return self.merchandise_subtotal.add(self.shipping_amount).add(self.import_tax_amount)


@dataclass
class Order:
    order_id: str
    buyer_id: str
    shipping_address: Address
    lines: list[OrderLine]
    status: OrderStatus = OrderStatus.DRAFT
    created_at: datetime = field(default_factory=_now)
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    order_kind: OrderKind = OrderKind.SEEDED_DEMO
    pricing: Optional[OrderPricingSnapshot] = None
    control_token_hash: Optional[str] = None
    cancel_reason_code: Optional[str] = None
    # Minimal internal audit metadata for logical deletion; never included in public DTOs.
    deleted_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("Order.order_id required")
        if not self.buyer_id:
            raise ValueError("Order.buyer_id required")
        if not self.lines:
            raise ValueError(f"Order 至少要有一条订单行：{self.order_id}")
        currencies = {line.unit_price.currency for line in self.lines}
        if len(currencies) > 1:
            raise ValueError(f"Order 订单行币种不一致：{currencies}")
        if self.pricing is not None and self.pricing.destination_country != self.shipping_address.country:
            raise ValueError("订单费用快照目的市场必须与订单目的市场一致")
        if self.order_kind is OrderKind.USER_SIMULATION:
            if self.pricing is None or not self.control_token_hash:
                raise ValueError("运行时订单必须有费用快照和控制令牌摘要")
            if self.status not in {OrderStatus.CONFIRMED, OrderStatus.CANCELLED, OrderStatus.DELETED}:
                raise ValueError("运行时订单状态必须为 CONFIRMED、CANCELLED 或 DELETED")
        if self.status is OrderStatus.DELETED and self.deleted_at is None:
            raise ValueError("逻辑删除的订单必须记录 deleted_at")

    @staticmethod
    def place(order_id: str, buyer_id: str, shipping_address: Address, lines: list[OrderLine]) -> "Order":
        """遗留兼容构造器：只供固定种子/历史单测，运行时 HTTP 不使用。"""
        order = Order(order_id=order_id, buyer_id=buyer_id, shipping_address=shipping_address, lines=lines)
        order.confirm()
        return order

    @staticmethod
    def place_simulation(
        order_id: str,
        buyer_id: str,
        destination_country: str,
        lines: list[OrderLine],
        pricing: OrderPricingSnapshot,
        control_token_hash: str,
    ) -> "Order":
        # 新订单不收集真实地址；仅保存目的市场与非个人化占位符，公开 DTO 不会返回它。
        destination = Address(
            recipient_name="未收集收件人",
            country=destination_country,
            state="",
            city="目的市场",
            address_line="未收集详细地址",
            postal_code="",
            phone="",
        )
        now = _now()
        return Order(
            order_id=order_id,
            buyer_id=buyer_id,
            shipping_address=destination,
            lines=lines,
            status=OrderStatus.CONFIRMED,
            created_at=now,
            confirmed_at=now,
            order_kind=OrderKind.USER_SIMULATION,
            pricing=pricing,
            control_token_hash=control_token_hash,
        )

    def confirm(self) -> None:
        if self.status is not OrderStatus.DRAFT:
            raise ValueError(f"仅 DRAFT 态可确认，当前={self.status.value}：{self.order_id}")
        self.status = OrderStatus.CONFIRMED
        self.confirmed_at = _now()

    @property
    def is_cancellable(self) -> bool:
        return self.order_kind is OrderKind.USER_SIMULATION and self.status is OrderStatus.CONFIRMED

    def cancel(self, reason: str = "buyer_requested") -> None:
        """仅模拟订单可取消；不会退款、回补库存或调用外部服务。"""
        if self.order_kind is not OrderKind.USER_SIMULATION:
            raise ValueError("历史订单不可取消")
        if self.status is not OrderStatus.CONFIRMED:
            raise ValueError(f"仅 CONFIRMED 态可取消，当前={self.status.value}：{self.order_id}")
        if not reason or not reason.strip():
            raise ValueError("Order.cancel 必须提供 reason")
        self.status = OrderStatus.CANCELLED
        self.cancelled_at = _now()
        self.cancel_reason_code = "buyer_requested"
        # 兼容旧持久化/内部对象；公开 DTO、日志、Agent 绝不能返回这个字段。
        self.cancel_reason = reason

    @property
    def is_deletable(self) -> bool:
        """删除仅是运行时模拟记录的不可逆逻辑隐藏，不影响固定种子或真实世界。"""
        return self.order_kind is OrderKind.USER_SIMULATION and self.status in {
            OrderStatus.CONFIRMED, OrderStatus.CANCELLED,
        }

    def delete(self) -> None:
        """逻辑删除模拟订单；保留最小审计记录和幂等键，不执行外部或库存副作用。"""
        if self.order_kind is not OrderKind.USER_SIMULATION:
            raise ValueError("历史订单不可删除")
        if not self.is_deletable:
            raise ValueError(f"该订单当前不可删除：{self.order_id}")
        self.status = OrderStatus.DELETED
        self.deleted_at = _now()

    def merchandise_subtotal(self) -> Money:
        total = self.lines[0].subtotal()
        for line in self.lines[1:]:
            total = total.add(line.subtotal())
        return total

    def total_amount(self) -> Money:
        return self.pricing.landed_total() if self.pricing is not None else self.merchandise_subtotal()

    def public_view(self) -> dict:
        """唯一可供 HTTP/Agent/UI 使用的脱敏订单视图。"""
        total = self.total_amount()
        payload = {
            "order_id": self.order_id,
            "status": self.status.value,
            "total_amount_major": total.to_major_units(),
            "currency": total.currency,
            "destination_country": self.shipping_address.country,
            "lines": [
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
            "created_at": self.created_at.isoformat(),
            "order_kind": self.order_kind.value,
        }
        if self.pricing is not None:
            payload.update({
                "merchandise_subtotal_major": self.pricing.merchandise_subtotal.to_major_units(),
                "shipping_amount_major": self.pricing.shipping_amount.to_major_units(),
                "import_tax_amount_major": self.pricing.import_tax_amount.to_major_units(),
                "rule_set_version": self.pricing.rule_set_version,
                "source_summary": self.pricing.source_summary,
                "source_status": self.pricing.source_status,
                "estimate_disclaimer": self.pricing.estimate_disclaimer,
            })
        else:
            payload.update({
                "merchandise_subtotal_major": self.merchandise_subtotal().to_major_units(),
                "shipping_amount_major": 0.0,
                "import_tax_amount_major": 0.0,
                "rule_set_version": "legacy-seed-v1",
                "source_summary": "历史订单费用快照",
                "source_status": "legacy_seed_snapshot",
                "estimate_disclaimer": "历史费用记录仅供订单明细展示。",
            })
        return payload

    def snapshot(self) -> dict:
        """遗留内部快照。新 HTTP/Agent 路径必须使用 public_view()。"""
        return {
            **self.public_view(),
            "buyer_id": self.buyer_id,
            "shipping_address": self.shipping_address.one_line(),
            "cancel_reason": self.cancel_reason,
        }
