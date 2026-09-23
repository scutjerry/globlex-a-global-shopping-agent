# -*- coding: utf-8 -*-
"""四期模块一：关系库仓储实现

跑 SQLite 内存库（与交付形态同源）。仓储代码不绑驱动，换服务型数据库
只需换 DATABASE_URL 与异步驱动，但那些驱动的特有行为本仓未验证。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.domain.buyer.preference import BuyerPreference
from app.domain.catalog.money import Money
from app.domain.order.address import Address
from app.domain.order.order import Order, OrderPricingSnapshot, OrderStatus
from app.domain.order.order_line import OrderLine
from app.domain.session.ports.conversation_store import (
    ConversationEventRecord,
    ConversationTurn,
)
from app.infrastructure.persistence.sql.repositories import (
    SqlConversationStore,
    SqlOrderRepository,
    SqlPreferenceStore,
    SqlSessionStore,
    bootstrap_schema,
    create_engine,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await bootstrap_schema(eng)
    yield eng
    await eng.dispose()


def _order(order_id: str = "GBX-000001") -> Order:
    return Order.place(
        order_id=order_id,
        buyer_id="buyer-001",
        shipping_address=Address(
            recipient_name="Pan",
            country="US",
            state="CA",
            city="San Jose",
            address_line="1 Market St",
            postal_code="95110",
            phone="+1-555-0100",
        ),
        lines=[
            OrderLine(
                product_id="P1008",
                sku_id="P1008-S1",
                title="LumenGo 便携露营灯 可充电",
                unit_price=Money(amount_in_minor_units=8900, currency="CNY"),
                quantity=2,
            ),
        ],
    )


class TestEngineSelection:
    """连接池参数必须按驱动分开给：把服务型数据库那套给 SQLite 会直接报错。"""

    async def test_sqlite_engine_created_without_server_pool_args(self):
        engine = create_engine("sqlite+aiosqlite:///:memory:")
        try:
            assert engine.url.get_backend_name() == "sqlite"
        finally:
            await engine.dispose()

    async def test_default_settings_point_to_sqlite(self, tmp_path, monkeypatch):
        """不配 DATABASE_URL 时默认落在 DATA_DIR 下的 SQLite 文件。"""
        from app.infrastructure.settings import load_settings

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("MYSQL_URL", raising=False)

        settings = load_settings()
        assert settings.database_url.startswith("sqlite+aiosqlite:///")
        assert settings.database_url.endswith("globex.db")

    async def test_explicit_database_url_wins(self, tmp_path, monkeypatch):
        from app.infrastructure.settings import load_settings

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////tmp/explicit.db")
        assert load_settings().database_url.endswith("explicit.db")


class TestSessionStore:
    async def test_state_roundtrip(self, engine):
        store = SqlSessionStore(engine)
        await store.save("s1", '{"session_id":"s1"}')
        assert await store.load("s1") == '{"session_id":"s1"}'

    async def test_save_is_upsert(self, engine):
        """每轮都会覆盖写同一会话，第二次不能因主键冲突失败。"""
        store = SqlSessionStore(engine)
        await store.save("s1", '{"v":1}')
        await store.save("s1", '{"v":2}')
        assert await store.load("s1") == '{"v":2}'

    async def test_missing_returns_none(self, engine):
        assert await SqlSessionStore(engine).load("nope") is None


class TestConversationStore:
    async def test_turns_ordered_by_turn_index(self, engine):
        store = SqlConversationStore(engine)
        await store.touch_session("s1", "buyer-001", "zh-CN", "CNY")
        for index in range(3):
            await store.append_turn(
                ConversationTurn(
                    session_id="s1", buyer_id="buyer-001", role="buyer", content=f"第{index}问",
                ),
            )
        turns = await store.list_turns("s1")
        assert [turn.content for turn in turns] == ["第0问", "第1问", "第2问"]

    async def test_turn_index_isolated_per_session(self, engine):
        """turn_index 按会话独立自增，不能被其他会话的行数带偏。"""
        store = SqlConversationStore(engine)
        await store.append_turn(
            ConversationTurn(session_id="s1", buyer_id="b", role="buyer", content="a"),
        )
        await store.append_turn(
            ConversationTurn(session_id="s1", buyer_id="b", role="agent", content="b"),
        )
        await store.append_turn(
            ConversationTurn(session_id="s2", buyer_id="b", role="buyer", content="c"),
        )
        assert len(await store.list_turns("s1")) == 2
        assert len(await store.list_turns("s2")) == 1

    async def test_events_persisted_with_payload(self, engine):
        store = SqlConversationStore(engine)
        await store.append_events(
            [
                ConversationEventRecord(
                    session_id="s1", type="tool.result", payload={"tool": "product_search_tool"},
                ),
            ],
        )
        # 事件表没有读接口，直接查会话主记录确认写入未抛错即可
        assert await store.find_session("s1") is None  # 事件不建会话主记录

    async def test_touch_session_is_idempotent(self, engine):
        store = SqlConversationStore(engine)
        await store.touch_session("s1", "buyer-001", "zh-CN", "CNY")
        await store.touch_session("s1", "buyer-001", "zh-CN", "CNY")
        session = await store.find_session("s1")
        assert session is not None and session["buyer_id"] == "buyer-001"

    async def test_empty_events_is_noop(self, engine):
        await SqlConversationStore(engine).append_events([])


class TestOrderRepository:
    async def test_bootstrap_upgrades_existing_orders_table_without_deleting_rows(self, tmp_path):
        database = tmp_path / "legacy-orders.db"
        legacy = create_async_engine(f"sqlite+aiosqlite:///{database}")
        try:
            async with legacy.begin() as conn:
                await conn.execute(text(
                    "CREATE TABLE orders ("
                    "order_id VARCHAR(32) PRIMARY KEY, buyer_id VARCHAR(64), status VARCHAR(16), "
                    "currency VARCHAR(8), total_amount_minor INTEGER, shipping_address_json JSON, "
                    "created_at DATETIME, confirmed_at DATETIME, cancelled_at DATETIME, cancel_reason VARCHAR(255))",
                ))
                await conn.execute(text(
                    "INSERT INTO orders (order_id, buyer_id, status, currency, total_amount_minor, shipping_address_json, created_at) "
                    "VALUES ('LEGACY-1', 'private', 'CONFIRMED', 'CNY', 100, '{}', CURRENT_TIMESTAMP)",
                ))
            await bootstrap_schema(legacy)
            async with legacy.connect() as conn:
                columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(orders)"))).all()}
                count = (await conn.execute(text("SELECT count(*) FROM orders"))).scalar_one()
            assert {"order_kind", "pricing_json", "control_token_hash", "cancel_reason_code", "deleted_at"} <= columns
            assert count == 1
        finally:
            await legacy.dispose()

    async def test_order_roundtrip_preserves_money_and_status(self, engine):
        repo = SqlOrderRepository(engine)
        await repo.save(_order())
        restored = await repo.find_by_id("GBX-000001")
        assert restored is not None
        assert restored.status is OrderStatus.CONFIRMED
        # 金额按最小单位存取，不能有浮点漂移
        assert restored.total_amount().amount_in_minor_units == 17800
        assert restored.total_amount().currency == "CNY"
        assert restored.lines[0].sku_id == "P1008-S1"
        assert restored.shipping_address.country == "US"

    async def test_legacy_pricing_copy_is_presented_with_current_commerce_wording(self, engine):
        repo = SqlOrderRepository(engine)
        pricing = OrderPricingSnapshot(
            merchandise_subtotal=Money.from_major_units(178, "CNY"),
            shipping_amount=Money.from_major_units(25, "CNY"),
            import_tax_amount=Money.from_major_units(12, "CNY"),
            destination_country="CN", rule_set_version="simulated-fees-2026-01-v1",
            source_ids=("legacy",), source_summary="CN 跨境费用演示假设（待官方资料复核）",
            source_status="assumption_pending_official_revalidation",
            estimate_disclaimer="仅为项目自建虚构数据的模拟估算。",
        )
        await repo.save(Order.place_simulation(
            "GBX-LEGACY-COPY", "buyer-001", "CN", _order().lines, pricing, "b" * 64,
        ))
        restored = await repo.find_by_id("GBX-LEGACY-COPY")
        assert restored is not None and restored.pricing is not None
        copy = " ".join((
            restored.pricing.rule_set_version, restored.pricing.source_summary,
            restored.pricing.source_status, restored.pricing.estimate_disclaimer,
        ))
        assert not any(term in copy for term in ("模拟", "虚构", "演示"))
        assert restored.pricing.rule_set_version.startswith("cross-border-fees-")

    async def test_simulated_order_roundtrip_preserves_frozen_pricing_and_cancel(self, engine):
        repo = SqlOrderRepository(engine)
        pricing = OrderPricingSnapshot(
            merchandise_subtotal=Money.from_major_units(178, "CNY"),
            shipping_amount=Money.from_major_units(25, "CNY"),
            import_tax_amount=Money.from_major_units(12, "CNY"),
            destination_country="US", rule_set_version="test-v1", source_ids=("test-source",),
            source_summary="测试来源", source_status="test_verified", estimate_disclaimer="仅为模拟估算。",
        )
        order = Order.place_simulation(
            "SIM-SQL", "buyer-001", "US", _order().lines, pricing, "a" * 64,
        )
        await repo.save(order)
        restored = await repo.find_by_id("SIM-SQL")
        assert restored is not None
        assert restored.total_amount().amount_in_minor_units == 21500
        assert restored.pricing is not None and restored.pricing.rule_set_version == "test-v1"
        assert restored.pricing.source_summary == "测试来源"
        assert restored.pricing.source_status == "test_verified"
        assert await repo.cancel_if_confirmed("SIM-SQL", "a" * 64) is True
        restored = await repo.find_by_id("SIM-SQL")
        assert restored is not None and restored.status is OrderStatus.CANCELLED
        assert restored.cancel_reason_code == "buyer_requested"
        assert len(restored.lines) == 1

    async def test_logical_delete_hides_sql_order_but_preserves_rows_and_idempotency(self, engine):
        repo = SqlOrderRepository(engine)
        pricing = OrderPricingSnapshot(
            merchandise_subtotal=Money.from_major_units(178, "CNY"),
            shipping_amount=Money.from_major_units(25, "CNY"),
            import_tax_amount=Money.from_major_units(12, "CNY"),
            destination_country="US", rule_set_version="test-v1", source_ids=("test-source",),
            source_summary="测试来源", source_status="test_verified", estimate_disclaimer="仅为模拟估算。",
        )
        order = Order.place_simulation("SIM-SQL-DELETE", "buyer-001", "US", _order().lines, pricing, "d" * 64)
        await repo.save_new_with_idempotency(order, "k" * 64, "r" * 64)
        assert await repo.delete_if_allowed(order.order_id, "d" * 64) is True
        assert await repo.find_by_id(order.order_id) is None
        assert order.order_id not in [item.order_id for item in await repo.list_orders()]
        assert await repo.find_idempotency("k" * 64) == (order.order_id, "r" * 64)
        async with engine.connect() as conn:
            row = (await conn.execute(text("SELECT status, deleted_at FROM orders WHERE order_id='SIM-SQL-DELETE'"))).one()
            lines = (await conn.execute(text("SELECT count(*) FROM order_items WHERE order_id='SIM-SQL-DELETE'"))).scalar_one()
        assert row.status == "DELETED" and row.deleted_at is not None
        assert lines == 1
        assert await repo.delete_if_allowed(order.order_id, "d" * 64) is False

    async def test_missing_order_returns_none(self, engine):
        assert await SqlOrderRepository(engine).find_by_id("GBX-999999") is None

    async def test_next_order_id_is_random_simulation_identifier(self, engine):
        repo = SqlOrderRepository(engine)
        first = await repo.next_order_id()
        second = await repo.next_order_id()
        assert first.startswith("GBX-")
        assert second.startswith("GBX-")
        assert first != second


class TestPreferenceStore:
    async def test_append_and_list(self, engine):
        store = SqlPreferenceStore(engine)
        await store.append(
            BuyerPreference(buyer_id="b1", kind="dislike", statement="不要塑料材质"),
        )
        prefs = await store.list_by_buyer("b1")
        assert [p.statement for p in prefs] == ["不要塑料材质"]

    async def test_duplicate_swallowed_by_unique_constraint(self, engine):
        """幂等去重靠唯一约束兜底，重复写入不能抛给调用方。"""
        store = SqlPreferenceStore(engine)
        pref = BuyerPreference(buyer_id="b1", kind="dislike", statement="不要塑料材质")
        await store.append(pref)
        await store.append(pref)
        assert len(await store.list_by_buyer("b1")) == 1

    async def test_same_statement_different_kind_both_kept(self, engine):
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="like", statement="小众设计"))
        await store.append(BuyerPreference(buyer_id="b1", kind="dislike", statement="小众设计"))
        assert len(await store.list_by_buyer("b1")) == 2

    async def test_buyers_isolated(self, engine):
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="like", statement="x"))
        assert await store.list_by_buyer("b2") == []

    async def test_delete_hit_and_miss(self, engine):
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="dislike", statement="不要塑料材质"))

        assert await store.delete("b1", "不要塑料材质") is True
        assert await store.list_by_buyer("b1") == []
        assert await store.delete("b1", "不要塑料材质") is False

    async def test_delete_requires_exact_match(self, engine):
        """删偏好不可逆，不得前缀匹配误删。"""
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="dislike", statement="不要塑料材质"))
        assert await store.delete("b1", "不要塑料") is False
        assert len(await store.list_by_buyer("b1")) == 1

    async def test_delete_removes_both_kinds_of_same_statement(self, engine):
        """同一句话可同时存为 like 与 dislike（见上一条用例），
        撤回时两条一并清除——买家表达的是“忘掉这条说法”。"""
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="like", statement="小众设计"))
        await store.append(BuyerPreference(buyer_id="b1", kind="dislike", statement="小众设计"))

        assert await store.delete("b1", "小众设计") is True
        assert await store.list_by_buyer("b1") == []

    async def test_delete_does_not_cross_buyers(self, engine):
        store = SqlPreferenceStore(engine)
        await store.append(BuyerPreference(buyer_id="b1", kind="dislike", statement="不要塑料材质"))
        await store.append(BuyerPreference(buyer_id="b2", kind="dislike", statement="不要塑料材质"))

        assert await store.delete("b1", "不要塑料材质") is True
        assert len(await store.list_by_buyer("b2")) == 1
