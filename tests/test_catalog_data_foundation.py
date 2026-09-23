# -*- coding: utf-8 -*-
"""商品数据底座：结构化入库、来源/审核记录、库存回写。"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.seed_products import build_seed_products
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
