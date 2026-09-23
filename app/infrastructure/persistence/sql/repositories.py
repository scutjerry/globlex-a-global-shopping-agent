# -*- coding: utf-8 -*-
"""关系库持久化实现（SQLAlchemy 2.0 async）

当前只验证与交付 sqlite+aiosqlite（零外部依赖，开箱即用）。
要换 MySQL / PostgreSQL：装上对应异步驱动（aiomysql / asyncpg）并把 DATABASE_URL
改成该驱动即可，仓储代码不需要改；但本仓未验证过那些驱动的特有行为。

实现四个领域端口：SessionStore / ConversationStore / OrderRepository / PreferenceStore。
domain 与 application 不感知本模块的存在，替换存储只改组装根。

并发安全要点：
    - 订单保存用 merge 覆盖写（订单号唯一，状态机由 domain 保证合法迁移）
    - 偏好去重靠唯一约束，重复插入吞掉 IntegrityError（比先查后插更可靠）
    - turn_index 按会话取当前最大值 +1，同会话并发写有极小概率撞号，
      撞号只影响展示顺序不影响数据完整性，故不加分布式锁

SQLite 的边界（重要）：单写者模型。模块三的 worker 是独立进程，与 API 进程并发写
同一个 db 文件时可能碰到 "database is locked"；WAL 模式能缓解，高并发仍应换服务型数据库。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, event, func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.domain.buyer.preference import BuyerPreference, PreferenceStore
from app.domain.catalog.money import Money
from app.domain.catalog.ports.product_repository import ProductRepository
from app.domain.catalog.product import Product, ProductHighlight
from app.domain.catalog.sku import Sku
from app.domain.order.address import Address
from app.domain.order.order import Order, OrderKind, OrderPricingSnapshot, OrderStatus
from app.domain.order.order_line import OrderLine
from app.domain.order.ports.order_repository import OrderRepository
from app.domain.session.ports.conversation_store import (
    ConversationEventRecord,
    ConversationStore,
    ConversationTurn,
)
from app.domain.session.ports.session_store import SessionStore
from app.infrastructure.persistence.sql.tables import (
    AgentSessionStateRow,
    Base,
    BuyerPreferenceRow,
    CatalogComplianceReviewRow,
    CatalogHighlightRow,
    CatalogMarketRow,
    CatalogProductRow,
    CatalogSkuRow,
    CatalogSourceRow,
    ConversationEventRow,
    ConversationMessageRow,
    ConversationSessionRow,
    OrderIdempotencyRow,
    OrderLineRow,
    OrderRow,
)

logger = logging.getLogger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    """创建异步引擎。连接池参数必须按驱动分开给。

    SQLite：不能传 pool_size / max_overflow（对其默认池无意义），pool_recycle 也无处可用
    （本地文件连接不会被服务端回收）。开 WAL 让读写不互斥，缓解 worker 与 API
    双进程并发写时的 "database is locked"。
    服务型数据库：必需 pool_pre_ping，否则空闲连接被服务端回收后首次查询必报断连。
    """
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url, echo=False)

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_wal(dbapi_conn, _record):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")  # 锁竞争时等待而不是立即报错
            cursor.close()

        return engine
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


async def bootstrap_schema(engine: AsyncEngine) -> None:
    """幂等建表并补齐受控模拟订单字段。

    MVP 仍不引入 Alembic，但 ``create_all`` 不会修改已存在的 SQLite 表。这里仅为
    既有 Docker ``app-data`` volume 添加缺失列，绝不删除或重建订单表。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.url.get_backend_name() == "sqlite":
            columns = await conn.run_sync(lambda sync_conn: {
                column["name"] for column in inspect(sync_conn).get_columns("orders")
            })
            additions = {
                "order_kind": "VARCHAR(24) NOT NULL DEFAULT 'SEEDED_DEMO'",
                "pricing_json": "JSON",
                "control_token_hash": "VARCHAR(64)",
                "cancel_reason_code": "VARCHAR(32)",
                "deleted_at": "DATETIME",
            }
            for column, definition in additions.items():
                if column not in columns:
                    await conn.execute(text(f"ALTER TABLE orders ADD COLUMN {column} {definition}"))
    logger.info("数据库表结构已就绪（%s）", engine.url.get_backend_name())


class SqlProductRepository(ProductRepository):
    """商品目录 SQL 仓储。

    目录数据由数据底座的模拟来源导入；运行时只读取已发布条目。SKU 库存变更
    通过 ``save`` 回写，避免内存聚合在请求结束后丢失库存扣减。
    """

    _SOURCE_ID = "synthetic-catalog-v1"

    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed_if_empty(self, products: list[Product]) -> int:
        """首次启动时幂等导入自建模拟目录，返回本次新增 SPU 数。"""
        async with self._session_factory() as db:
            await db.merge(CatalogSourceRow(
                source_id=self._SOURCE_ID,
                name="Globex 自建合规模拟商品目录",
                source_type="synthetic_demo",
                license_note="项目自建虚构文本，仅用于开发、演示与检索评测；不可视为真实商品、认证或供货授权。",
            ))
            added = 0
            for product in products:
                if await db.get(CatalogProductRow, product.product_id):
                    continue
                added += 1
                db.add(CatalogProductRow(
                    product_id=product.product_id, title=product.title, brand=product.brand,
                    category=product.category, origin_country=product.origin_country,
                    description=product.description, source_id=self._SOURCE_ID,
                    lifecycle_status="published",
                ))
                db.add_all([
                    CatalogSkuRow(
                        sku_id=sku.sku_id, product_id=product.product_id, spec=sku.spec,
                        price_minor=sku.price.amount_in_minor_units, currency=sku.price.currency,
                        stock=sku.stock,
                    ) for sku in product.skus
                ])
                db.add_all([
                    CatalogHighlightRow(product_id=product.product_id, label=h.label, detail=h.detail)
                    for h in product.highlights
                ])
                db.add_all([
                    CatalogMarketRow(product_id=product.product_id, market_code=market)
                    for market in product.ships_to
                ])
                db.add(CatalogComplianceReviewRow(
                    product_id=product.product_id,
                    review_status="simulated_approved",
                    markets=",".join(product.ships_to),
                    rule_set_version="synthetic-demo-v1",
                    review_note=(
                        "自建虚构商品数据：字段完整性、市场代码与禁用真实品牌/认证宣称校验通过。"
                        "不构成 CN/US/EU 的真实监管准入、产品安全或税务结论。"
                    ),
                ))
            await db.commit()
        return added

    async def save(self, product: Product) -> None:
        async with self._session_factory() as db:
            for sku in product.skus:
                await db.execute(
                    update(CatalogSkuRow)
                    .where(CatalogSkuRow.sku_id == sku.sku_id)
                    .values(stock=sku.stock),
                )
            await db.commit()

    async def find_by_id(self, product_id: str) -> Optional[Product]:
        products = await self.find_by_ids([product_id])
        return products[0] if products else None

    async def find_by_ids(self, product_ids: list[str]) -> list[Product]:
        if not product_ids:
            return []
        async with self._session_factory() as db:
            rows = (await db.execute(
                select(CatalogProductRow).where(
                    CatalogProductRow.product_id.in_(product_ids),
                    CatalogProductRow.lifecycle_status == "published",
                ),
            )).scalars().all()
            products = await self._hydrate(db, rows)
        by_id = {product.product_id: product for product in products}
        return [by_id[product_id] for product_id in product_ids if product_id in by_id]

    async def list_all(self) -> list[Product]:
        async with self._session_factory() as db:
            rows = (await db.execute(
                select(CatalogProductRow).where(CatalogProductRow.lifecycle_status == "published"),
            )).scalars().all()
            return await self._hydrate(db, rows)

    @staticmethod
    async def _hydrate(db, product_rows: list[CatalogProductRow]) -> list[Product]:  # noqa: ANN001
        if not product_rows:
            return []
        ids = [row.product_id for row in product_rows]
        skus = (await db.execute(select(CatalogSkuRow).where(CatalogSkuRow.product_id.in_(ids)))).scalars().all()
        highlights = (await db.execute(select(CatalogHighlightRow).where(CatalogHighlightRow.product_id.in_(ids)))).scalars().all()
        markets = (await db.execute(select(CatalogMarketRow).where(CatalogMarketRow.product_id.in_(ids)))).scalars().all()
        sku_map: dict[str, list[Sku]] = {product_id: [] for product_id in ids}
        highlight_map: dict[str, list[ProductHighlight]] = {product_id: [] for product_id in ids}
        market_map: dict[str, list[str]] = {product_id: [] for product_id in ids}
        for sku in skus:
            sku_map[sku.product_id].append(Sku(
                sku_id=sku.sku_id, spec=sku.spec,
                price=Money(amount_in_minor_units=sku.price_minor, currency=sku.currency), stock=sku.stock,
            ))
        for highlight in highlights:
            highlight_map[highlight.product_id].append(ProductHighlight(highlight.label, highlight.detail))
        for market in markets:
            market_map[market.product_id].append(market.market_code)
        return [Product(
            product_id=row.product_id, title=row.title, brand=row.brand, category=row.category,
            origin_country=row.origin_country, description=row.description,
            highlights=highlight_map[row.product_id], ships_to=market_map[row.product_id],
            skus=sku_map[row.product_id],
        ) for row in product_rows]


class SqlSessionStore(SessionStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def save(self, session_id: str, state_json: str) -> None:
        async with self._session_factory() as db:
            await db.merge(AgentSessionStateRow(session_id=session_id, state_json=state_json))
            await db.commit()

    async def load(self, session_id: str) -> Optional[str]:
        async with self._session_factory() as db:
            row = await db.get(AgentSessionStateRow, session_id)
            return row.state_json if row else None


class SqlConversationStore(ConversationStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def touch_session(self, session_id: str, buyer_id: str, locale: str, currency: str) -> None:
        async with self._session_factory() as db:
            existing = await db.get(ConversationSessionRow, session_id)
            if existing is None:
                db.add(
                    ConversationSessionRow(
                        session_id=session_id, buyer_id=buyer_id, locale=locale, currency=currency,
                    ),
                )
            else:
                existing.last_active_at = datetime.now(timezone.utc)
            await db.commit()

    async def append_turn(self, turn: ConversationTurn) -> None:
        async with self._session_factory() as db:
            max_index = await db.scalar(
                select(func.max(ConversationMessageRow.turn_index)).where(
                    ConversationMessageRow.session_id == turn.session_id,
                ),
            )
            db.add(
                ConversationMessageRow(
                    session_id=turn.session_id,
                    turn_index=(max_index or 0) + 1,
                    buyer_id=turn.buyer_id,
                    role=turn.role,
                    content=turn.content,
                    model=turn.model,
                    latency_ms=turn.latency_ms,
                ),
            )
            await db.commit()

    async def append_events(self, events: list[ConversationEventRecord]) -> None:
        if not events:
            return
        async with self._session_factory() as db:
            db.add_all(
                [
                    ConversationEventRow(
                        session_id=event.session_id,
                        type=event.type,
                        payload=event.payload,
                        occurred_at=event.occurred_at,
                    )
                    for event in events
                ],
            )
            await db.commit()

    async def list_turns(self, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        async with self._session_factory() as db:
            rows = (
                await db.scalars(
                    select(ConversationMessageRow)
                    .where(ConversationMessageRow.session_id == session_id)
                    .order_by(ConversationMessageRow.turn_index)
                    .limit(limit),
                )
            ).all()
        return [
            ConversationTurn(
                session_id=row.session_id,
                buyer_id=row.buyer_id,
                role=row.role,
                content=row.content,
                model=row.model,
                latency_ms=row.latency_ms,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
            for row in rows
        ]

    async def find_session(self, session_id: str) -> Optional[dict]:
        async with self._session_factory() as db:
            row = await db.get(ConversationSessionRow, session_id)
            if row is None:
                return None
            return {
                "session_id": row.session_id,
                "buyer_id": row.buyer_id,
                "locale": row.locale,
                "currency": row.currency,
                "last_active_at": row.last_active_at.isoformat() if row.last_active_at else "",
            }


class SqlOrderRepository(OrderRepository):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def save(self, order: Order) -> None:
        total = order.total_amount()
        async with self._session_factory() as db:
            await db.merge(
                OrderRow(
                    order_id=order.order_id,
                    buyer_id=order.buyer_id,
                    status=order.status.value,
                    currency=total.currency,
                    total_amount_minor=total.amount_in_minor_units,
                    shipping_address_json=_address_to_dict(order.shipping_address),
                    created_at=order.created_at,
                    confirmed_at=order.confirmed_at,
                    cancelled_at=order.cancelled_at,
                    deleted_at=order.deleted_at,
                    cancel_reason=order.cancel_reason,
                    order_kind=order.order_kind.value,
                    pricing_json=_pricing_to_dict(order.pricing),
                    control_token_hash=order.control_token_hash,
                    cancel_reason_code=order.cancel_reason_code,
                ),
            )
            # 订单行整体重写：行数固定且量小，比逐行 diff 更简单可靠
            await db.execute(delete(OrderLineRow).where(OrderLineRow.order_id == order.order_id))
            db.add_all(
                [
                    OrderLineRow(
                        order_id=order.order_id,
                        product_id=line.product_id,
                        sku_id=line.sku_id,
                        title=line.title,
                        unit_price_minor=line.unit_price.amount_in_minor_units,
                        currency=line.unit_price.currency,
                        quantity=line.quantity,
                    )
                    for line in order.lines
                ],
            )
            await db.commit()

    async def find_by_id(self, order_id: str) -> Optional[Order]:
        """公开/应用读取不返回已逻辑删除的订单。"""
        async with self._session_factory() as db:
            row = await db.get(OrderRow, order_id)
            if row is None or row.deleted_at is not None:
                return None
            line_rows = (
                await db.scalars(select(OrderLineRow).where(OrderLineRow.order_id == order_id))
            ).all()
        return _row_to_order(row, line_rows)

    async def list_orders(self, buyer_id: Optional[str] = None, limit: int = 50) -> list[Order]:
        """按创建时间倒序返回订单聚合；受控模拟订单中心的脱敏读取使用。"""
        safe_limit = max(1, min(limit, 100))
        async with self._session_factory() as db:
            stmt = (
                select(OrderRow)
                .where(OrderRow.deleted_at.is_(None))
                .order_by(OrderRow.created_at.desc(), OrderRow.order_id.desc())
                .limit(safe_limit)
            )
            if buyer_id is not None:
                stmt = stmt.where(OrderRow.buyer_id == buyer_id)
            rows = (await db.scalars(stmt)).all()
            if not rows:
                return []
            order_ids = [row.order_id for row in rows]
            line_rows = (
                await db.scalars(select(OrderLineRow).where(OrderLineRow.order_id.in_(order_ids)))
            ).all()
        lines_by_order: dict[str, list[OrderLineRow]] = {order_id: [] for order_id in order_ids}
        for line in line_rows:
            lines_by_order.setdefault(line.order_id, []).append(line)
        return [_row_to_order(row, lines_by_order[row.order_id]) for row in rows]

    async def next_order_id(self) -> str:
        """随机模拟订单号，避免按总数并发生成重复 ID。"""
        import secrets
        return f"SIM-{secrets.token_hex(6).upper()}"

    async def find_idempotency(self, key_hash: str) -> Optional[tuple[str, str]]:
        async with self._session_factory() as db:
            row = await db.get(OrderIdempotencyRow, key_hash)
            return (row.order_id, row.request_hash) if row is not None else None

    async def save_idempotency(self, key_hash: str, request_hash: str, order_id: str) -> None:
        async with self._session_factory() as db:
            await db.merge(OrderIdempotencyRow(
                key_hash=key_hash, request_hash=request_hash, order_id=order_id,
            ))
            await db.commit()

    async def save_new_with_idempotency(self, order: Order, key_hash: str, request_hash: str) -> Optional[str]:
        """在一个 SQLite 事务中写订单和唯一幂等键。

        若另一请求已抢先写入相同 key，整个本事务（含订单行）会回滚，随后返回
        已有订单号；绝不留下没有幂等记录的重复订单。
        """
        total = order.total_amount()
        try:
            async with self._session_factory() as db:
                db.add(OrderRow(
                    order_id=order.order_id, buyer_id=order.buyer_id, status=order.status.value,
                    currency=total.currency, total_amount_minor=total.amount_in_minor_units,
                    shipping_address_json=_address_to_dict(order.shipping_address),
                    created_at=order.created_at, confirmed_at=order.confirmed_at,
                    cancelled_at=order.cancelled_at, cancel_reason=order.cancel_reason,
                    order_kind=order.order_kind.value, pricing_json=_pricing_to_dict(order.pricing),
                    control_token_hash=order.control_token_hash, cancel_reason_code=order.cancel_reason_code,
                ))
                db.add_all([
                    OrderLineRow(
                        order_id=order.order_id, product_id=line.product_id, sku_id=line.sku_id,
                        title=line.title, unit_price_minor=line.unit_price.amount_in_minor_units,
                        currency=line.unit_price.currency, quantity=line.quantity,
                    ) for line in order.lines
                ])
                db.add(OrderIdempotencyRow(key_hash=key_hash, request_hash=request_hash, order_id=order.order_id))
                await db.commit()
            return None
        except IntegrityError:
            # Unique key conflict is expected under a retry/concurrent request. Read after rollback.
            async with self._session_factory() as db:
                existing = await db.get(OrderIdempotencyRow, key_hash)
                if existing is None:
                    raise
                if existing.request_hash != request_hash:
                    raise RuntimeError("Idempotency-Key 已用于不同的模拟订单请求")
                return existing.order_id

    async def cancel_if_confirmed(self, order_id: str, control_token_hash: str) -> bool:
        """用单条条件更新保证 CONFIRMED → CANCELLED 至多成功一次。"""
        async with self._session_factory() as db:
            result = await db.execute(
                update(OrderRow)
                .where(
                    OrderRow.order_id == order_id,
                    OrderRow.order_kind == OrderKind.USER_SIMULATION.value,
                    OrderRow.status == OrderStatus.CONFIRMED.value,
                    OrderRow.deleted_at.is_(None),
                    OrderRow.control_token_hash == control_token_hash,
                )
                .values(
                    status=OrderStatus.CANCELLED.value,
                    cancelled_at=datetime.now(timezone.utc),
                    cancel_reason_code="buyer_requested",
                    cancel_reason=None,
                ),
            )
            await db.commit()
        return bool(result.rowcount)

    async def delete_if_allowed(self, order_id: str, control_token_hash: str) -> bool:
        """原子逻辑删除：可删除的运行时订单恰好成功一次，保留订单行和幂等记录。"""
        async with self._session_factory() as db:
            result = await db.execute(
                update(OrderRow)
                .where(
                    OrderRow.order_id == order_id,
                    OrderRow.order_kind == OrderKind.USER_SIMULATION.value,
                    OrderRow.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.CANCELLED.value]),
                    OrderRow.deleted_at.is_(None),
                    OrderRow.control_token_hash == control_token_hash,
                )
                .values(status=OrderStatus.DELETED.value, deleted_at=datetime.now(timezone.utc)),
            )
            await db.commit()
        return bool(result.rowcount)


class SqlPreferenceStore(PreferenceStore):
    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def append(self, preference: BuyerPreference) -> None:
        async with self._session_factory() as db:
            db.add(
                BuyerPreferenceRow(
                    buyer_id=preference.buyer_id,
                    kind=preference.kind,
                    statement=preference.statement,
                    created_at=preference.created_at,
                ),
            )
            try:
                await db.commit()
            except IntegrityError:
                # 唯一约束命中 = 该偏好已存在，幂等语义下静默跳过
                await db.rollback()

    async def list_by_buyer(self, buyer_id: str) -> list[BuyerPreference]:
        async with self._session_factory() as db:
            rows = (
                await db.scalars(
                    select(BuyerPreferenceRow)
                    .where(BuyerPreferenceRow.buyer_id == buyer_id)
                    .order_by(BuyerPreferenceRow.id),
                )
            ).all()
        return [
            BuyerPreference(
                buyer_id=row.buyer_id,
                kind=row.kind,
                statement=row.statement,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def delete(self, buyer_id: str, statement: str) -> bool:
        """精确匹配 statement 删除；返回是否真的删到了行。"""
        async with self._session_factory() as db:
            result = await db.execute(
                delete(BuyerPreferenceRow).where(
                    BuyerPreferenceRow.buyer_id == buyer_id,
                    BuyerPreferenceRow.statement == statement,
                ),
            )
            await db.commit()
        return bool(result.rowcount)


# ---- 领域对象 <-> 行记录转换 ----


def _address_to_dict(address: Address) -> dict:
    return {
        "recipient_name": address.recipient_name,
        "country": address.country,
        "state": address.state,
        "city": address.city,
        "address_line": address.address_line,
        "postal_code": address.postal_code,
        "phone": address.phone,
    }


def _pricing_to_dict(pricing: Optional[OrderPricingSnapshot]) -> Optional[dict]:
    if pricing is None:
        return None
    return {
        "merchandise_subtotal_minor": pricing.merchandise_subtotal.amount_in_minor_units,
        "shipping_amount_minor": pricing.shipping_amount.amount_in_minor_units,
        "import_tax_amount_minor": pricing.import_tax_amount.amount_in_minor_units,
        "currency": pricing.landed_total().currency,
        "destination_country": pricing.destination_country,
        "rule_set_version": pricing.rule_set_version,
        "source_ids": list(pricing.source_ids),
        "source_summary": pricing.source_summary,
        "source_status": pricing.source_status,
        "estimate_disclaimer": pricing.estimate_disclaimer,
    }


def _pricing_from_dict(payload: Optional[dict]) -> Optional[OrderPricingSnapshot]:
    if not payload:
        return None
    currency = payload["currency"]
    return OrderPricingSnapshot(
        merchandise_subtotal=Money.of(int(payload["merchandise_subtotal_minor"]), currency),
        shipping_amount=Money.of(int(payload["shipping_amount_minor"]), currency),
        import_tax_amount=Money.of(int(payload["import_tax_amount_minor"]), currency),
        destination_country=payload["destination_country"],
        rule_set_version=payload["rule_set_version"],
        source_ids=tuple(payload["source_ids"]),
        source_summary=payload.get("source_summary", "历史模拟费用规则快照"),
        source_status=payload.get("source_status", "legacy_pricing_snapshot"),
        estimate_disclaimer=payload["estimate_disclaimer"],
    )


def _row_to_order(row: OrderRow, line_rows: list[OrderLineRow]) -> Order:
    return Order(
        order_id=row.order_id,
        buyer_id=row.buyer_id,
        shipping_address=Address(**row.shipping_address_json),
        lines=[
            OrderLine(
                product_id=line.product_id,
                sku_id=line.sku_id,
                title=line.title,
                unit_price=Money(amount_in_minor_units=line.unit_price_minor, currency=line.currency),
                quantity=line.quantity,
            )
            for line in line_rows
        ],
        status=OrderStatus(row.status),
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        cancelled_at=row.cancelled_at,
        deleted_at=getattr(row, "deleted_at", None),
        cancel_reason=row.cancel_reason,
        order_kind=OrderKind(getattr(row, "order_kind", None) or OrderKind.SEEDED_DEMO.value),
        pricing=_pricing_from_dict(getattr(row, "pricing_json", None)),
        control_token_hash=getattr(row, "control_token_hash", None),
        cancel_reason_code=getattr(row, "cancel_reason_code", None),
    )
