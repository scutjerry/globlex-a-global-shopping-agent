# -*- coding: utf-8 -*-
"""商品数据底座：结构化入库、来源/审核记录、库存回写。"""
from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.seed_products import build_seed_products
from app.infrastructure.rag.category_knowledge import KNOWLEDGE_DIR
from app.infrastructure.persistence.sql.repositories import (
    SqlProductRepository,
    bootstrap_schema,
    create_engine,
)
from app.infrastructure.persistence.sql.tables import (
    CatalogComplianceReviewRow,
    CatalogProductRow,
    CatalogSourceRow,
)


V1_FEE_MARKETS = {"US", "EU", "GB", "JP", "CN"}


def test_category_knowledge_covers_all_expanded_catalog_categories():
    """新增品类必须有可供 category_insight 灌库的知识文档。"""
    expected_documents = {
        "travel-gear.md", "digital-accessories.md", "home-living.md", "outdoor-sports.md",
        "cross-border-guide.md", "health-care.md", "parenting.md", "pet-travel.md",
        "office-stationery.md", "apparel-accessories.md",
    }
    assert {path.name for path in KNOWLEDGE_DIR.glob("*.md")} == expected_documents


def test_expanded_seed_catalog_has_retrieval_depth_and_preserves_anchor_products():
    """420 SPU 的模拟目录应具备规格、亮点和市场维度的排序区分度。

    P1001–P1010 是既有检索测试的顺序/内容锚点，扩容只能在其后追加新商品，
    不能改动这些固定商品的字段或排序。
    """
    products = build_seed_products()
    by_id = {product.product_id: product for product in products}

    assert len(products) == 420
    assert [product.product_id for product in products[:10]] == [f"P{number}" for number in range(1001, 1011)]
    assert by_id["P1001"].title == "Nomadica 旅行三件套（收纳袋+颈枕+眼罩）"
    assert by_id["P1001"].description == (
        "帆布加尼龙材质 结实耐磨 抗造 轻便 无塑料感 小众设计师品牌 适合长途飞行 旅行收纳"
    )
    assert by_id["P1008"].title == "LumenGo 便携露营灯 可充电"

    assert len({product.product_id for product in products}) == len(products)
    assert sum(len(product.skus) for product in products) >= 800
    assert sum(len(product.skus) > 1 for product in products) >= 250
    assert sum(len(product.highlights) for product in products) >= 1200
    assert len(Counter(product.category for product in products)) == 10

    new_products = [product for product in products if product.product_id >= "P1201"]
    assert len(new_products) == 312
    assert all(set(product.ships_to) & V1_FEE_MARKETS for product in new_products)
    forbidden_experience_terms = ("模拟", "虚构", "演示")
    assert all(
        not any(term in product.searchable_text() for term in forbidden_experience_terms)
        for product in products
    )


@pytest.mark.asyncio
async def test_sql_catalog_seed_is_structured_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}")
    try:
        await bootstrap_schema(engine)
        repo = SqlProductRepository(engine)
        products = build_seed_products()

        assert len(products) >= 100
        assert await repo.seed_if_empty(products) == len(products)
        assert await repo.seed_if_empty(products) == 0

        catalog = await repo.list_all()
        assert len(catalog) == len(products)
        # 目录必须覆盖多个产地与目的市场，且所有内容仍是自建虚构演示数据。
        assert {"CA", "GB", "JP", "KR", "SG", "AU", "TH", "BR", "AE"}.issubset(
            {item.origin_country for item in catalog},
        )
        product = await repo.find_by_id("P1061")
        assert product is not None
        assert set(product.ships_to) == {"CN", "US", "EU"}

        async with repo._session_factory() as db:  # 断言数据底座记录真实落库
            assert (await db.execute(select(func.count()).select_from(CatalogProductRow))).scalar_one() == len(products)
            assert (await db.execute(select(func.count()).select_from(CatalogSourceRow))).scalar_one() == 1
            review = (await db.execute(
                select(CatalogComplianceReviewRow).where(
                    CatalogComplianceReviewRow.product_id == "P1061",
                ),
            )).scalar_one()
            assert review.review_status == "simulated_approved"
            assert "不构成" in review.review_note
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_catalog_sku_stock_is_persisted(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}")
    try:
        await bootstrap_schema(engine)
        repo = SqlProductRepository(engine)
        await repo.seed_if_empty(build_seed_products())
        product = await repo.find_by_id("P1061")
        assert product is not None
        before = product.primary_sku().stock
        product.primary_sku().deduct_stock(2)
        await repo.save(product)
        reloaded = await repo.find_by_id("P1061")
        assert reloaded is not None
        assert reloaded.primary_sku().stock == before - 2
    finally:
        await engine.dispose()
