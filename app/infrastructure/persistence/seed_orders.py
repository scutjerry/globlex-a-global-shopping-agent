# -*- coding: utf-8 -*-
"""只读订单中心的演示订单。

全部记录均为项目自建虚构数据，只用于 UI、API 和部署演示：
- 不代表真实买家、支付、物流、税务或履约；
- 不经过运行时受控模拟订单用例，因此不会影响任何模拟商品库存；
- 用固定订单号幂等写入，已有记录不会覆盖。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.catalog.money import Money
from app.domain.order.address import Address
from app.domain.order.order import Order, OrderStatus
from app.domain.order.order_line import OrderLine
from app.domain.order.ports.order_repository import OrderRepository


def _utc(days_ago: int, hour: int) -> datetime:
    """生成稳定且清晰的演示时间线。"""
    return datetime.now(timezone.utc).replace(hour=hour, minute=30, second=0, microsecond=0) - timedelta(days=days_ago)


def _address(
    recipient_name: str,
    country: str,
    state: str,
    city: str,
    address_line: str,
    postal_code: str,
    phone: str,
) -> Address:
    return Address(
        recipient_name=recipient_name,
        country=country,
        state=state,
        city=city,
        address_line=address_line,
        postal_code=postal_code,
        phone=phone,
    )


def build_demo_orders() -> list[Order]:
    """返回多个目的市场的模拟订单快照，供 MVP 只读展示。"""
    cn_created = _utc(2, 10)
    us_created = _utc(5, 14)
    eu_created = _utc(9, 16)
    jp_created = _utc(14, 9)
    sg_created = _utc(18, 11)

    return [
        Order(
            order_id="DEMO-CN-24001",
            buyer_id="buyer-demo",
            shipping_address=_address("林静", "CN", "上海", "上海", "静安区南京西路 218 号", "200040", "13800001234"),
            lines=[
                OrderLine("P1001", "P1001-S1", "Nomadica 旅行三件套（收纳袋+颈枕+眼罩）", Money.from_major_units(189, "CNY"), 1),
                OrderLine("P1005", "P1005-S1", "VoltTrek 65W 氮化镓旅行充电器（全球插脚）", Money.from_major_units(159, "CNY"), 1),
            ],
            status=OrderStatus.CONFIRMED,
            created_at=cn_created,
            confirmed_at=cn_created + timedelta(minutes=3),
        ),
        Order(
            order_id="DEMO-US-24002",
            buyer_id="buyer-demo",
            shipping_address=_address("Maya Chen", "US", "California", "San Francisco", "88 Townsend Street", "94107", "+1-415-555-0186"),
            lines=[
                OrderLine("P1004", "P1004-S1", "AeroHush 主动降噪蓝牙耳机 Pro", Money.from_major_units(219, "USD"), 1),
            ],
            status=OrderStatus.CONFIRMED,
            created_at=us_created,
            confirmed_at=us_created + timedelta(minutes=6),
        ),
        Order(
            order_id="DEMO-EU-24003",
            buyer_id="buyer-demo",
            shipping_address=_address("Noah Keller", "DE", "Berlin", "Berlin", "Friedrichstraße 120", "10117", "+49-30-555-0187"),
            lines=[
                OrderLine("P1002", "P1002-S1", "GlobeAdapt 全球通用转换插头", Money.from_major_units(99, "CNY"), 1),
                OrderLine("P1009", "P1009-S1", "LinenFold 亚麻旅行衣物收纳套", Money.from_major_units(329, "CNY"), 1),
            ],
            status=OrderStatus.CONFIRMED,
            created_at=eu_created,
            confirmed_at=eu_created + timedelta(minutes=4),
        ),
        Order(
            order_id="DEMO-JP-24004",
            buyer_id="buyer-demo",
            shipping_address=_address("佐藤 葵", "JP", "東京都", "渋谷区", "神南 1-19-11", "150-0041", "+81-3-5550-0188"),
            lines=[
                OrderLine("P1006", "P1006-S1", "TerraCotta 手工粗陶马克杯", Money.from_major_units(128, "CNY"), 2),
                OrderLine("P1008", "P1008-S1", "LumenGo 便携露营灯 可充电", Money.from_major_units(89, "CNY"), 1),
            ],
            status=OrderStatus.CANCELLED,
            created_at=jp_created,
            confirmed_at=jp_created + timedelta(minutes=5),
            cancelled_at=jp_created + timedelta(hours=2),
            cancel_reason="模拟订单：买家调整旅行计划",
        ),
        Order(
            order_id="DEMO-SG-24005",
            buyer_id="buyer-demo",
            shipping_address=_address("Amira Tan", "SG", "Singapore", "Singapore", "21 Beach Road", "189677", "+65-6555-0189"),
            lines=[
                OrderLine("P1007", "P1007-S1", "Wanderlite 轻量旅行腰包", Money.from_major_units(79, "CNY"), 1),
                OrderLine("P1003", "P1003-S1", "BreezeNeck 便携挂颈风扇", Money.from_major_units(119, "CNY"), 1),
            ],
            status=OrderStatus.CONFIRMED,
            created_at=sg_created,
            confirmed_at=sg_created + timedelta(minutes=2),
        ),
    ]


async def seed_demo_orders_if_missing(repository: OrderRepository) -> int:
    """幂等导入模拟订单，返回本次新增数。"""
    added = 0
    for order in build_demo_orders():
        if await repository.find_by_id(order.order_id) is not None:
            continue
        await repository.save(order)
        added += 1
    return added
