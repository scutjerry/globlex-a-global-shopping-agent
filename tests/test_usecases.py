# -*- coding: utf-8 -*-
"""usecase 层单测：商品召回 + 受控模拟订单（不依赖 LLM）。"""
import pytest

from app.application.usecases.catalog_search import CatalogSearchUseCase
from app.application.usecases.order_usecases import (
    CancelSimulatedOrderUseCase,
    CreateSimulatedOrderUseCase,
    OrderItemInput,
    QueryOrderUseCase,
    QuoteSimulatedOrderUseCase,
)
from app.domain.catalog.product_search_spec import ProductSearchSpec
from app.infrastructure.persistence.in_memory_repositories import (
    InMemoryOrderRepository,
    InMemoryProductRepository,
)


@pytest.fixture()
def product_repo() -> InMemoryProductRepository:
    return InMemoryProductRepository()


@pytest.fixture()
def order_repo() -> InMemoryOrderRepository:
    return InMemoryOrderRepository()


class TestCatalogSearch:
    async def test_recall_travel_set(self, product_repo):
        usecase = CatalogSearchUseCase(product_repo)
        result = await usecase.execute(ProductSearchSpec(normalized_query="旅行三件套 抗造 轻便 无塑料"))
        assert result["hits"], "旅行三件套应能召回"
        assert result["hits"][0]["product_id"] == "P1001", "语义最相关的 SPU 应排第一"

    async def test_ship_to_filter(self, product_repo):
        usecase = CatalogSearchUseCase(product_repo)
        result = await usecase.execute(ProductSearchSpec(normalized_query="旅行茶具", ship_to="US"))
        assert all(hit["product_id"] != "P1006" for hit in result["hits"])

    async def test_top_k_limit(self, product_repo):
        result = await CatalogSearchUseCase(product_repo).execute(ProductSearchSpec(normalized_query="旅行", top_k=2))
        assert len(result["hits"]) <= 2

    async def test_no_hit_returns_empty(self, product_repo):
        result = await CatalogSearchUseCase(product_repo).execute(ProductSearchSpec(normalized_query="quantum flux capacitor"))
        assert result["hits"] == []


class TestSimulatedOrderLifecycle:
    async def test_place_query_cancel_roundtrip_without_inventory_side_effects(self, product_repo, order_repo):
        product = await product_repo.find_by_id("P1001")
        original_stock = product.find_sku("P1001-S1").stock
        quote = QuoteSimulatedOrderUseCase(product_repo)
        created = await CreateSimulatedOrderUseCase(quote, order_repo).execute(
            buyer_id="buyer-1",
            items=[OrderItemInput(product_id="P1001", sku_id="P1001-S1", quantity=2)],
            destination_country="US",
            currency="USD",
        )
        assert created.order.status.value == "CONFIRMED"
        assert created.order.total_amount().amount_in_minor_units > 0
        assert product.find_sku("P1001-S1").stock == original_stock

        queried = await QueryOrderUseCase(order_repo).execute(created.order.order_id)
        assert queried["order_id"] == created.order.order_id
        assert queried["shipping_amount_major"] > 0

        cancelled = await CancelSimulatedOrderUseCase(order_repo).execute(created.order.order_id, created.control_token)
        assert cancelled["status"] == "CANCELLED"
        assert product.find_sku("P1001-S1").stock == original_stock

    async def test_invalid_quantity_rejects_without_stock_write(self, product_repo, order_repo):
        product = await product_repo.find_by_id("P1006")
        original_stock = product.find_sku("P1006-S1").stock
        quote = QuoteSimulatedOrderUseCase(product_repo)
        with pytest.raises(ValueError, match="1 到 10"):
            await quote.execute(
                [OrderItemInput(product_id="P1006", sku_id="P1006-S1", quantity=11)], "JP", "JPY",
            )
        assert product.find_sku("P1006-S1").stock == original_stock

    async def test_query_unknown_order(self, order_repo):
        with pytest.raises(ValueError, match="订单不存在"):
            await QueryOrderUseCase(order_repo).execute("SIM-UNKNOWN")
