# -*- coding: utf-8 -*-
"""MVP 受控模拟订单中心：读取、种子幂等、写接口与隐私边界。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.application.usecases.order_usecases import ListOrdersUseCase
from app.domain.catalog.money import Money
from app.domain.order.address import Address
from app.domain.order.order import Order, OrderStatus
from app.domain.order.order_line import OrderLine
from app.infrastructure.persistence.in_memory_repositories import InMemoryOrderRepository, InMemoryProductRepository
from app.infrastructure.persistence.seed_orders import build_demo_orders, seed_demo_orders_if_missing
from app.infrastructure.persistence.sql.repositories import SqlOrderRepository, bootstrap_schema, create_engine


def _order(order_id: str, buyer_id: str, created_at: datetime) -> Order:
    return Order(
        order_id=order_id,
        buyer_id=buyer_id,
        shipping_address=Address("演示用户", "CN", "上海", "上海", "模拟路 1 号", "200000", "00000000000"),
        lines=[OrderLine("P1001", "P1001-S1", "模拟旅行套装", Money.from_major_units(99, "CNY"), 1)],
        status=OrderStatus.CONFIRMED,
        created_at=created_at,
        confirmed_at=created_at,
    )


@pytest.mark.asyncio
async def test_in_memory_order_list_is_descending_and_capped():
    repo = InMemoryOrderRepository()
    now = datetime.now(timezone.utc)
    await repo.save(_order("D-1", "buyer-a", now - timedelta(days=2)))
    await repo.save(_order("D-2", "buyer-b", now - timedelta(days=1)))
    await repo.save(_order("D-3", "buyer-a", now))

    assert [order.order_id for order in await repo.list_orders(limit=2)] == ["D-3", "D-2"]
    assert [order.order_id for order in await repo.list_orders(buyer_id="buyer-a")] == ["D-3", "D-1"]


@pytest.mark.asyncio
async def test_sql_order_list_batches_lines_and_keeps_sorting(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'orders.db'}")
    try:
        await bootstrap_schema(engine)
        repo = SqlOrderRepository(engine)
        now = datetime.now(timezone.utc)
        await repo.save(_order("S-1", "buyer-a", now - timedelta(days=1)))
        await repo.save(_order("S-2", "buyer-b", now))

        orders = await repo.list_orders(limit=20)
        assert [order.order_id for order in orders] == ["S-2", "S-1"]
        assert orders[0].lines[0].sku_id == "P1001-S1"
        assert [order.order_id for order in await repo.list_orders(buyer_id="buyer-a")] == ["S-1"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_orders_usecase_enforces_small_read_limit():
    repo = InMemoryOrderRepository()
    await repo.save(_order("U-1", "buyer-a", datetime.now(timezone.utc)))
    usecase = ListOrdersUseCase(repo)

    summary = (await usecase.execute())[0]
    assert summary["order_id"] == "U-1"
    assert "buyer_id" not in summary
    with pytest.raises(ValueError, match="1 到 50"):
        await usecase.execute(limit=0)
    with pytest.raises(ValueError, match="1 到 50"):
        await usecase.execute(limit=51)


@pytest.mark.asyncio
async def test_query_order_usecase_is_sanitized_for_api_and_agent_tool_events():
    repo = InMemoryOrderRepository()
    await repo.save(_order("SAFE-1", "private-buyer", datetime.now(timezone.utc)))
    from app.application.usecases.order_usecases import QueryOrderUseCase

    view = await QueryOrderUseCase(repo).execute("SAFE-1")
    assert view["destination_country"] == "CN"
    for forbidden in ("buyer_id", "shipping_address", "recipient_name", "phone", "cancel_reason"):
        assert forbidden not in view


@pytest.mark.asyncio
async def test_demo_order_seed_is_idempotent_and_does_not_touch_catalog_stock():
    order_repo = InMemoryOrderRepository()
    product_repo = InMemoryProductRepository()
    before_stock = (await product_repo.find_by_id("P1001")).find_sku("P1001-S1").stock

    assert await seed_demo_orders_if_missing(order_repo) == len(build_demo_orders())
    assert await seed_demo_orders_if_missing(order_repo) == 0
    orders = await order_repo.list_orders(limit=20)

    assert len(orders) == len(build_demo_orders())
    assert {order.status for order in orders} == {OrderStatus.CONFIRMED, OrderStatus.CANCELLED}
    assert (await product_repo.find_by_id("P1001")).find_sku("P1001-S1").stock == before_stock


def test_order_routes_are_controlled_and_public_models_have_no_pii_fields():
    from app.presentation.dto import (
        CreatedSimulatedOrderResponse,
        OrderDetailResponse,
        OrderQuoteResponse,
        OrderSummaryResponse,
    )
    from app.presentation.server import build_app

    routes = {
        (route.path, tuple(sorted(route.methods)))
        for route in build_app().routes
        if hasattr(route, "methods")
    }
    assert ("/commerce/orders", ("GET",)) in routes
    assert ("/commerce/orders", ("POST",)) in routes
    assert ("/commerce/order-quotes", ("POST",)) in routes
    assert ("/commerce/orders/{order_id}", ("GET",)) in routes
    assert ("/commerce/orders/{order_id}/cancellations", ("POST",)) in routes
    assert ("/commerce/orders/{order_id}", ("DELETE",)) in routes
    public_fields = (
        set(OrderSummaryResponse.model_fields)
        | set(OrderDetailResponse.model_fields)
        | set(OrderQuoteResponse.model_fields)
    )
    forbidden = {
        "buyer_id", "shipping_address", "recipient_name", "phone", "postal_code", "state", "city",
        "address_line", "cancel_reason", "cancel_reason_code", "control_token_hash", "order_control_token",
    }
    assert not forbidden & public_fields
    # Token is intentionally isolated to the one-time create response only.
    assert "order_control_token" in CreatedSimulatedOrderResponse.model_fields


def test_order_control_tokens_stay_in_memory_and_agent_has_no_write_tool():
    from pathlib import Path

    app_source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    center_source = Path("frontend/src/components/OrderCenter.tsx").read_text(encoding="utf-8")
    draft_source = Path("frontend/src/components/ChatOrderDraft.tsx").read_text(encoding="utf-8")
    agent_tool_source = Path("app/application/tools/order_tools.py").read_text(encoding="utf-8")
    for source in (center_source, draft_source):
        assert "localStorage" not in source
        assert "sessionStorage" not in source
    # App has browser storage only for a synthetic session/buyer ID, never the control-token state.
    assert "const [controlTokens, setControlTokens] = useState" in app_source
    # The only persistent write is the generic synthetic session/buyer helper, never a token.
    assert app_source.count("localStorage.setItem(") == 1
    assert "localStorage.setItem(key, created)" in app_source
    assert "controlTokens" in center_source
    assert "{created.order_control_token}" not in center_source
    assert "method: \"DELETE\"" in center_source
    assert "window.confirm(" in center_source
    # An idempotent replay has an empty token and must not erase the first response's capability.
    assert "if (!created.order_control_token) return current;" in center_source
    # The chat draft first requests a quote; only an explicit user confirmation calls POST /orders.
    assert "/commerce/order-quotes" in draft_source
    assert "确认创建订单" in draft_source
    assert "取消草案" in draft_source
    assert "order_control_token" not in agent_tool_source
    assert "create" not in agent_tool_source.lower()
    assert "delete" not in agent_tool_source.lower()


def test_frontend_combines_shipping_and_import_tax_into_cross_border_fee():
    from pathlib import Path

    card_source = Path("frontend/src/components/ProductCards.tsx").read_text(encoding="utf-8")
    draft_source = Path("frontend/src/components/ChatOrderDraft.tsx").read_text(encoding="utf-8")
    center_source = Path("frontend/src/components/OrderCenter.tsx").read_text(encoding="utf-8")

    assert "freight_major + card.landed_price.tariff_major" in card_source
    assert "shipping_amount_major + quote.import_tax_amount_major" in draft_source
    assert "shipping_amount_major + order.import_tax_amount_major" in center_source
    for source in (card_source, draft_source, center_source):
        assert "跨境费用" in source
    for source in (draft_source, center_source):
        assert ">运费：" not in source
        assert ">进口税费：" not in source


def test_order_routes_do_not_return_raw_business_error_messages():
    from pathlib import Path

    source = Path("app/presentation/server.py").read_text(encoding="utf-8")
    assert "detail=str(err)" not in source
    assert 'detail="订单请求不符合规则"' in source
    assert 'detail="订单不存在"' in source


def test_customer_facing_copy_uses_standard_commerce_language():
    from pathlib import Path

    public_sources = [
        Path("app/application/prompts/globex.yml"),
        Path("frontend/src/App.tsx"),
        Path("frontend/src/components/ProductCards.tsx"),
        Path("frontend/src/components/ChatOrderDraft.tsx"),
        Path("frontend/src/components/OrderCenter.tsx"),
        Path("app/presentation/dto.py"),
        Path("app/presentation/server.py"),
        *Path("knowledge").glob("*.md"),
    ]
    forbidden = ("模拟", "虚构", "演示", "SIMULATED ORDER", "DEMO-")
    for path in public_sources:
        content = path.read_text(encoding="utf-8")
        assert not any(term in content for term in forbidden), path


def test_demo_orders_only_use_non_sensitive_fixture_data():
    for order in build_demo_orders():
        snapshot = order.snapshot()
        assert snapshot["order_id"].startswith("GBX-")
        assert snapshot["shipping_address"]
        assert "@" not in snapshot["shipping_address"]
