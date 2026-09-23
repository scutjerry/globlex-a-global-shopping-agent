# -*- coding: utf-8 -*-
"""受控模拟交易：费用冻结、无库存副作用、令牌取消和公开脱敏。"""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from app.application.usecases.order_usecases import (
    CancelSimulatedOrderUseCase,
    CreateSimulatedOrderUseCase,
    DeleteSimulatedOrderUseCase,
    OrderItemInput,
    QueryOrderUseCase,
    QuoteSimulatedOrderUseCase,
)
from app.infrastructure.persistence.in_memory_repositories import InMemoryOrderRepository, InMemoryProductRepository


@pytest.fixture()
def product_repo() -> InMemoryProductRepository:
    return InMemoryProductRepository()


@pytest.fixture()
def order_repo() -> InMemoryOrderRepository:
    return InMemoryOrderRepository()


@pytest.fixture()
def quote(product_repo: InMemoryProductRepository) -> QuoteSimulatedOrderUseCase:
    return QuoteSimulatedOrderUseCase(product_repo)


@pytest.mark.asyncio
async def test_quote_uses_three_part_landed_price_and_versions_rules(quote):
    result = await quote.execute(
        [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD",
    )
    view = result.public_view()
    assert view["landed_total_major"] == pytest.approx(
        view["merchandise_subtotal_major"] + view["shipping_amount_major"] + view["import_tax_amount_major"],
    )
    assert view["rule_set_version"].startswith("simulated-fees-")
    assert "模拟估算" in view["estimate_disclaimer"]
    assert view["source_status"] == "official_verified"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "destination,currency,product_id,sku_id",
    [
        ("US", "USD", "P1001", "P1001-S1"),
        ("EU", "EUR", "P1005", "P1005-S1"),
        ("GB", "GBP", "P1103", "P1103-S1"),
        ("JP", "JPY", "P1005", "P1005-S1"),
        ("CN", "CNY", "P1001", "P1001-S1"),
    ],
)
async def test_all_v1_destinations_have_quotes(quote, destination, currency, product_id, sku_id):
    result = await quote.execute([OrderItemInput(product_id, sku_id, 1)], destination, currency)
    assert result.fee_quote.destination_country == destination
    assert result.fee_quote.landed_total.amount_in_minor_units >= result.fee_quote.merchandise_subtotal.amount_in_minor_units


@pytest.mark.asyncio
async def test_quote_rejects_a_market_the_product_does_not_ship_to(quote):
    """回归：聊天草案卡曾把目的地硬编码为 US，导致只寄 CN/JP 的商品（如 P1006）必然返回
    「模拟订单请求不符合规则」422。前端现依商品卡的 ships_to 限定选项，服务端必须继续拒绝非法组合。"""
    product = await InMemoryProductRepository().find_by_id("P1006")
    assert product is not None
    assert "US" not in product.ships_to, "该回归用例需要一个不寄送 US 的种子商品"
    sku_id = product.skus[0].sku_id

    with pytest.raises(ValueError, match="不支持寄送"):
        await quote.execute([OrderItemInput("P1006", sku_id, 1)], "US", "USD")

    # 商品真正声明的可寄送市场必须都能正常报价，否则前端限定后的选项仍会失败。
    for market in product.ships_to:
        result = await quote.execute([OrderItemInput("P1006", sku_id, 1)], market, "CNY")
        assert result.fee_quote.destination_country == market
        assert result.fee_quote.landed_total.amount_in_minor_units > 0


@pytest.mark.asyncio
async def test_create_and_cancel_never_change_catalog_stock(product_repo, order_repo, quote):
    sku = (await product_repo.find_by_id("P1001")).find_sku("P1001-S1")
    before = sku.stock
    create = CreateSimulatedOrderUseCase(quote, order_repo)
    created = await create.execute("buyer-private", [OrderItemInput("P1001", "P1001-S1", 2)], "US", "USD")
    assert created.order.status.value == "CONFIRMED"
    assert created.order.order_id.startswith("SIM-")
    assert (await product_repo.find_by_id("P1001")).find_sku("P1001-S1").stock == before

    cancelled = await CancelSimulatedOrderUseCase(order_repo).execute(created.order.order_id, created.control_token)
    assert cancelled["status"] == "CANCELLED"
    assert (await product_repo.find_by_id("P1001")).find_sku("P1001-S1").stock == before


@pytest.mark.asyncio
async def test_order_freezes_quote_and_hides_private_fields(product_repo, order_repo, quote):
    created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
        "buyer-private", [OrderItemInput("P1001", "P1001-S1", 1)], "CN", "CNY",
    )
    view = await QueryOrderUseCase(order_repo).execute(created.order.order_id)
    assert view["total_amount_major"] == pytest.approx(
        view["merchandise_subtotal_major"] + view["shipping_amount_major"] + view["import_tax_amount_major"],
    )
    assert view["source_status"] == "assumption_pending_official_revalidation"
    assert "待官方资料复核" in view["source_summary"]
    for forbidden in (
        "buyer_id", "shipping_address", "recipient_name", "phone", "postal_code", "address_line",
        "cancel_reason", "cancel_reason_code", "control_token_hash", "order_control_token",
    ):
        assert forbidden not in view


@pytest.mark.asyncio
async def test_cancel_requires_the_one_time_control_token(order_repo, quote):
    created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
        "buyer-private", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD",
    )
    cancel = CancelSimulatedOrderUseCase(order_repo)
    with pytest.raises(PermissionError, match="无法执行"):
        await cancel.execute(created.order.order_id, "not-the-token")
    with pytest.raises(PermissionError, match="无法执行"):
        await cancel.execute(created.order.order_id, "")
    await cancel.execute(created.order.order_id, created.control_token)
    with pytest.raises(RuntimeError, match="不可取消"):
        await cancel.execute(created.order.order_id, created.control_token)


@pytest.mark.asyncio
async def test_idempotent_create_returns_one_order_and_does_not_reissue_token(order_repo, quote):
    create = CreateSimulatedOrderUseCase(quote, order_repo)
    key_hash = hashlib.sha256(b"test-idempotency-key").hexdigest()
    request_hash = hashlib.sha256(b"stable-body").hexdigest()
    first, second = await asyncio.gather(
        create.execute_with_idempotency("buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD", key_hash, request_hash),
        create.execute_with_idempotency("buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD", key_hash, request_hash),
    )
    assert first.order.order_id == second.order.order_id
    assert sum(bool(result.control_token) for result in (first, second)) == 1
    assert len(await order_repo.list_orders()) == 1
    # A later retry returns the original frozen order without reissuing the capability token.
    retried = await create.execute_with_idempotency(
        "buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD", key_hash, request_hash,
    )
    assert retried.reused is True
    assert retried.order.order_id == first.order.order_id
    assert retried.control_token == ""


@pytest.mark.asyncio
async def test_logical_delete_requires_token_hides_order_and_never_changes_stock(product_repo, order_repo, quote):
    sku = (await product_repo.find_by_id("P1001")).find_sku("P1001-S1")
    before = sku.stock
    created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
        "buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD",
    )
    delete = DeleteSimulatedOrderUseCase(order_repo)
    with pytest.raises(PermissionError, match="无法执行"):
        await delete.execute(created.order.order_id, "wrong-token")
    await delete.execute(created.order.order_id, created.control_token)
    with pytest.raises(ValueError, match="不存在"):
        await QueryOrderUseCase(order_repo).execute(created.order.order_id)
    assert await order_repo.find_by_id(created.order.order_id) is None
    assert created.order.order_id not in [order.order_id for order in await order_repo.list_orders()]
    assert (await product_repo.find_by_id("P1001")).find_sku("P1001-S1").stock == before
    with pytest.raises(LookupError, match="不存在"):
        await delete.execute(created.order.order_id, created.control_token)


@pytest.mark.asyncio
async def test_delete_rejects_seeded_demo_order(order_repo, quote):
    from app.domain.order.address import Address
    from app.domain.order.order import Order
    from app.domain.order.order_line import OrderLine
    from app.domain.catalog.money import Money

    seeded = Order.place(
        "DEMO-DELETE-LOCKED", "seed-buyer",
        Address("演示", "US", "", "演示城市", "演示地址", "", ""),
        [OrderLine("P1", "P1-S1", "演示 SKU", Money.of(100, "USD"), 1)],
    )
    await order_repo.save(seeded)
    with pytest.raises(RuntimeError, match="不可删除"):
        await DeleteSimulatedOrderUseCase(order_repo).execute(seeded.order_id, "x" * 32)
    assert await order_repo.find_by_id(seeded.order_id) is not None


@pytest.mark.asyncio
async def test_concurrent_delete_succeeds_exactly_once(order_repo, quote):
    created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
        "buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD",
    )
    delete = DeleteSimulatedOrderUseCase(order_repo)
    results = await asyncio.gather(
        delete.execute(created.order.order_id, created.control_token),
        delete.execute(created.order.order_id, created.control_token),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, LookupError) for result in results) == 1


@pytest.mark.asyncio
async def test_concurrent_cancel_succeeds_exactly_once(order_repo, quote):
    created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
        "buyer", [OrderItemInput("P1001", "P1001-S1", 1)], "US", "USD",
    )
    cancel = CancelSimulatedOrderUseCase(order_repo)
    results = await asyncio.gather(
        cancel.execute(created.order.order_id, created.control_token),
        cancel.execute(created.order.order_id, created.control_token),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) and result["status"] == "CANCELLED" for result in results) == 1
    assert sum(isinstance(result, RuntimeError) for result in results) == 1
