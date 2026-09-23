# -*- coding: utf-8 -*-
"""FastAPI 服务入口

路由：
    POST /commerce/intents                 提交买家意图（同步返回最终回复；启用队列时内部入队后等结果）
    POST /commerce/intents/async           提交买家意图（立即返回 task_id，结果走 WS 或轮询）
    GET  /commerce/tasks/{task_id}         查任务状态（queued / running / done / failed）
    WS   /commerce/events                  订阅会话事件流
    POST /commerce/order-quotes            无副作用到手价
    POST /commerce/orders                  受控创建订单（幂等）
    POST /commerce/orders/{id}/cancellations  持控制令牌取消订单
    GET  /commerce/orders                  脱敏订单列表
    GET  /commerce/orders/{order_id}       脱敏订单详情
    GET  /health                           健康检查（含依赖连通性与队列深度）

启动：
    uv run uvicorn app.presentation.server:app --port 8000
    uv run python -m app.worker          # 启用队列时另起消费进程

同步接口为什么保留：13 case 评测脚本与前端都依赖它直接返回 final_text，
改成纯异步会一次性搞挂回归与前端。削峰由 worker 并发度保证，与接口形态无关。
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.application.agents.orchestrator import SubmitIntentInput
from app.application.usecases.order_usecases import OrderItemInput
from app.composition import Container, build_container
from app.domain.queue.ports.task_queue import IntentTask, TaskStatus
from app.presentation.connection import ConnectionManager
from app.presentation.dto import (
    CancelSimulatedOrderRequest,
    CreatedSimulatedOrderResponse,
    OrderDetailResponse,
    OrderLineResponse,
    OrderListResponse,
    OrderQuoteResponse,
    OrderSummaryResponse,
    SimulatedOrderRequest,
    SubmitIntentRequest,
    SubmitIntentResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

logger = logging.getLogger(__name__)

# 幂等键有效期：同一会话同一句话在此窗口内重复提交视为重复请求
_IDEMPOTENCY_TTL_SECONDS = 600
# 轮数计数器存活时长：比幂等窗口长得多，让一整段会话都能被正确分类
_TURN_COUNTER_TTL_SECONDS = 86400


def build_app() -> FastAPI:
    state: dict = {}

    async def _forward_remote_events(c: Container) -> None:
        """把其他进程（worker）广播的事件转发给本进程的 WS 订阅者。"""
        if c.backplane is None:
            return
        try:
            async for event in c.backplane.listen():
                c.bus.deliver_local(event)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            logger.warning("事件背板监听中断：%s", err)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        c = await build_container()
        state["c"] = c
        state["connections"] = ConnectionManager(c.bus)
        await c.startup()
        if c.backplane is not None:
            # 跨进程事件转发：不开这个任务，worker 产生的流式事件到不了前端
            state["forwarder"] = asyncio.create_task(_forward_remote_events(c))
        try:
            yield
        finally:
            forwarder = state.pop("forwarder", None)
            if forwarder is not None:
                forwarder.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await forwarder
            state.pop("c", None)
            await c.shutdown()

    api = FastAPI(title="Globex 跨境电商 Agent", version="0.4.0", lifespan=lifespan)

    @api.exception_handler(RequestValidationError)
    async def safe_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        """绝不回显 Pydantic 的原始 input，避免 token 或拒绝的 PII 出现在响应中。"""
        return JSONResponse(status_code=422, content={"detail": "请求格式无效"})

    def container() -> Container:
        if "c" not in state:
            raise HTTPException(status_code=503, detail="服务尚未就绪")
        return state["c"]

    settings_origins = build_container_origins()
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/health")
    async def health() -> dict:
        """依赖连通性一并报出，避免"进程活着但存储已挂"被当成健康。"""
        c = container()
        database = "disabled"
        if c.db_engine is not None:
            try:
                async with c.db_engine.connect() as conn:
                    await conn.execute(text("select 1"))
                database = c.db_engine.url.get_backend_name()
            except Exception as err:  # noqa: BLE001
                database = f"error: {err}"
        redis_state = "disabled"
        if c.cache.enabled:
            redis_state = "ok" if await c.cache.ping() else "error"
        return {
            "status": "ok",
            "model": c.settings.llm_model,
            "database": database,
            "redis": redis_state,
            "semantic_cache": c.semantic_cache.enabled,
            "queue": "enabled" if c.task_queue is not None else "disabled",
            "queue_depth": await c.task_queue.depth() if c.task_queue is not None else 0,
        }

    @api.post("/commerce/intents", response_model=SubmitIntentResponse)
    async def submit_intent(body: SubmitIntentRequest) -> SubmitIntentResponse:
        c = container()
        session_id = body.shopping_session_id or f"session-{uuid.uuid4().hex[:8]}"
        intent = SubmitIntentInput(
            shopping_session_id=session_id,
            buyer_id=body.buyer_id,
            locale=body.locale,
            currency=body.currency,
            raw_query=body.raw_query,
        )
        if c.task_queue is None:
            result = await c.orchestrator.handle_intent(intent)
            return SubmitIntentResponse(
                shopping_session_id=result.shopping_session_id, final_text=result.final_text,
            )

        task_id = await _enqueue(c, intent)
        final_text = await _await_result(c, task_id, session_id)
        return SubmitIntentResponse(shopping_session_id=session_id, final_text=final_text)

    @api.post("/commerce/intents/async")
    async def submit_intent_async(body: SubmitIntentRequest) -> dict:
        c = container()
        session_id = body.shopping_session_id or f"session-{uuid.uuid4().hex[:8]}"
        intent = SubmitIntentInput(
            shopping_session_id=session_id,
            buyer_id=body.buyer_id,
            locale=body.locale,
            currency=body.currency,
            raw_query=body.raw_query,
        )
        if c.task_queue is None:
            raise HTTPException(status_code=503, detail="队列未启用，请使用 /commerce/intents")
        task_id = await _enqueue(c, intent)
        return {"shopping_session_id": session_id, "task_id": task_id, "state": "queued"}

    @api.get("/commerce/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        c = container()
        if c.task_queue is None:
            raise HTTPException(status_code=503, detail="队列未启用")
        status = await c.task_queue.get_status(task_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"任务不存在或已过期：{task_id}")
        return {
            "task_id": status.task_id,
            "state": status.state,
            "final_text": status.final_text,
            "error": status.error,
            "queue_position": status.queue_position,
        }

    @api.websocket("/commerce/events")
    async def commerce_events(websocket: WebSocket) -> None:
        await state["connections"].serve(websocket)

    def _items(body: SimulatedOrderRequest) -> list[OrderItemInput]:
        return [OrderItemInput(product_id=item.product_id, sku_id=item.sku_id, quantity=item.quantity) for item in body.items]

    def _line_responses(lines: list[dict]) -> list[OrderLineResponse]:
        return [OrderLineResponse(**line) for line in lines]

    def _detail_response(order: dict) -> OrderDetailResponse:
        return OrderDetailResponse(
            order_id=order["order_id"], status=order["status"],
            total_amount_major=order["total_amount_major"], currency=order["currency"],
            item_count=sum(line["quantity"] for line in order["lines"]),
            destination_country=order["destination_country"], created_at=order["created_at"],
            manageable=order["order_kind"] == "USER_SIMULATION", lines=_line_responses(order["lines"]),
            merchandise_subtotal_major=order["merchandise_subtotal_major"],
            shipping_amount_major=order["shipping_amount_major"],
            import_tax_amount_major=order["import_tax_amount_major"],
            rule_set_version=order["rule_set_version"], source_summary=order["source_summary"],
            source_status=order["source_status"], estimate_disclaimer=order["estimate_disclaimer"],
        )

    @api.post("/commerce/order-quotes", response_model=OrderQuoteResponse)
    async def quote_simulated_order(body: SimulatedOrderRequest) -> OrderQuoteResponse:
        """按目录 SKU 计算到手价；不写订单、库存或外部系统。"""
        try:
            quote = await container().quote_simulated_order.execute(
                _items(body), body.destination_country, body.currency,
            )
        except ValueError as err:
            logger.info("订单报价被拒绝：%s", type(err).__name__)
            raise HTTPException(status_code=422, detail="订单请求不符合规则") from err
        view = quote.public_view()
        return OrderQuoteResponse(
            **{key: view[key] for key in (
                "merchandise_subtotal_major", "shipping_amount_major", "import_tax_amount_major",
                "landed_total_major", "currency", "destination_country", "rule_set_version",
                "source_summary", "source_status", "estimate_disclaimer",
            )},
            items=_line_responses(view["items"]),
        )

    @api.post("/commerce/orders", response_model=CreatedSimulatedOrderResponse, status_code=201)
    async def create_simulated_order(
        body: SimulatedOrderRequest,
        response: Response,
        idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=128),
    ) -> CreatedSimulatedOrderResponse:
        """明确创建一笔无库存、无支付副作用的订单。"""
        c = container()
        normalized = {"items": [item.model_dump() for item in body.items], "destination_country": body.destination_country, "currency": body.currency}
        request_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        try:
            created = await c.create_simulated_order.execute_with_idempotency(
                buyer_id="web-simulation", items=_items(body),
                destination_country=body.destination_country, currency=body.currency,
                request_key_hash=key_hash, request_hash=request_hash,
            )
        except ValueError as err:
            logger.info("订单创建被拒绝：%s", type(err).__name__)
            raise HTTPException(status_code=422, detail="订单请求不符合规则") from err
        except RuntimeError as err:
            logger.info("订单创建冲突：%s", type(err).__name__)
            raise HTTPException(status_code=409, detail="订单创建请求冲突") from err
        if created.reused:
            # Token is deliberately not reissued on a retry or concurrent duplicate request.
            response.status_code = 200
            return CreatedSimulatedOrderResponse(
                **_detail_response(created.order.public_view()).model_dump(),
                order_control_token="", control_token_warning="重复请求未重新返回控制令牌；请使用首次创建响应中的令牌。",
            )
        return CreatedSimulatedOrderResponse(
            **_detail_response(created.order.public_view()).model_dump(),
            order_control_token=created.control_token,
        )

    @api.delete("/commerce/orders/{order_id}", status_code=204)
    async def delete_simulated_order(order_id: str, body: CancelSimulatedOrderRequest) -> Response:
        """逻辑删除当前页面持令牌的运行时订单；不物理删除审计记录。"""
        try:
            await container().delete_simulated_order.execute(order_id, body.order_control_token)
        except LookupError as err:
            logger.info("订单删除对象不存在：%s", type(err).__name__)
            raise HTTPException(status_code=404, detail="订单不存在") from err
        except PermissionError as err:
            logger.info("订单删除授权失败：%s", type(err).__name__)
            raise HTTPException(status_code=403, detail="无法删除此订单") from err
        except RuntimeError as err:
            logger.info("订单删除冲突：%s", type(err).__name__)
            raise HTTPException(status_code=409, detail="该订单当前不可删除") from err
        return Response(status_code=204)

    @api.get("/commerce/orders", response_model=OrderListResponse)
    async def list_orders(limit: int = 20) -> OrderListResponse:
        try:
            items = await container().list_orders.execute(limit=limit)
        except ValueError as err:
            logger.info("订单列表请求被拒绝：%s", type(err).__name__)
            raise HTTPException(status_code=422, detail="订单列表请求不符合规则") from err
        return OrderListResponse(items=[OrderSummaryResponse(
            **{key: value for key, value in item.items() if key != "order_kind"},
            manageable=item["order_kind"] == "USER_SIMULATION",
        ) for item in items])

    @api.get("/commerce/orders/{order_id}", response_model=OrderDetailResponse)
    async def get_order(order_id: str) -> OrderDetailResponse:
        try:
            return _detail_response(await container().query_order.execute(order_id))
        except ValueError as err:
            logger.info("订单详情不存在：%s", type(err).__name__)
            raise HTTPException(status_code=404, detail="订单不存在") from err

    @api.post("/commerce/orders/{order_id}/cancellations", response_model=OrderDetailResponse)
    async def cancel_simulated_order(order_id: str, body: CancelSimulatedOrderRequest) -> OrderDetailResponse:
        try:
            return _detail_response(await container().cancel_simulated_order.execute(order_id, body.order_control_token))
        except LookupError as err:
            logger.info("订单取消对象不存在：%s", type(err).__name__)
            raise HTTPException(status_code=404, detail="订单不存在") from err
        except PermissionError as err:
            logger.info("订单取消授权失败：%s", type(err).__name__)
            raise HTTPException(status_code=403, detail="无法取消此订单") from err
        except RuntimeError as err:
            logger.info("订单取消冲突：%s", type(err).__name__)
            raise HTTPException(status_code=409, detail="该订单当前不可取消") from err

    return api


async def _queue_priority(c: Container, session_id: str) -> int:
    """按对话轮数定队列优先级（0 = 正常，1 = 大请求）。

    长会话上下文大、单次耗时长，分到低优先流，避免堵住新会话。
    轮数计数存 Redis（计数不原子，但优先级本身是启发式，差一两次无影响）；
    Redis 不可用或开关关闭时一律返回 0，退化为单队列。
    """
    if not c.settings.queue_priority_enabled or not c.cache.enabled:
        return 0
    key = f"globex:turns:{session_id}"
    try:
        current = int(await c.cache.get_raw(key) or 0) + 1
        await c.cache.set_json(key, current, _TURN_COUNTER_TTL_SECONDS)
    except Exception:  # noqa: BLE001 —— 计数失败不能影响入队
        return 0
    return 1 if current >= c.settings.queue_large_request_turns else 0


async def _enqueue(c: Container, intent: SubmitIntentInput) -> str:
    """入队并做幂等保护。

    队列是 at-least-once，且买家/前端可能重复提交。用「会话 + 问句」指纹做幂等键，
    命中说明短时间内已提交过同样内容，直接复用原 task_id，不再入队一次。
    这一步对写操作（下单）尤其关键：重复消费等于重复下单。
    """
    fingerprint = hashlib.sha256(
        f"{intent.shopping_session_id}\n{intent.raw_query}".encode(),
    ).hexdigest()[:32]
    idem_key = f"idem:{fingerprint}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"

    acquired = await c.cache.set_if_absent(idem_key, task_id, _IDEMPOTENCY_TTL_SECONDS)
    if not acquired:
        previous = await c.cache.get_raw(idem_key)
        if previous:
            logger.info("幂等命中，复用已有任务：%s", previous)
            return previous

    await c.task_queue.enqueue(  # type: ignore[union-attr]
        IntentTask(
            task_id=task_id,
            shopping_session_id=intent.shopping_session_id,
            buyer_id=intent.buyer_id,
            locale=intent.locale,
            currency=intent.currency,
            raw_query=intent.raw_query,
            priority=await _queue_priority(c, intent.shopping_session_id),
        ),
    )
    await c.task_queue.set_status(TaskStatus(task_id=task_id, state="queued"))  # type: ignore[union-attr]
    c.bus.publish(intent.shopping_session_id, "task.queued", {"task_id": task_id})
    return task_id


async def _await_result(c: Container, task_id: str, session_id: str) -> str:
    """等 worker 跑完。

    优先等 final.result 事件（实时）；同时定期查任务状态兜底——
    worker 崩溃或任务进死信时事件永远不会来，只靠等事件会把请求挂死。
    """
    queue = c.bus.subscribe(session_id)
    deadline = time.monotonic() + c.settings.queue_wait_seconds
    try:
        while time.monotonic() < deadline:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                status = await c.task_queue.get_status(task_id)  # type: ignore[union-attr]
                if status is not None and status.state == "done":
                    return status.final_text
                if status is not None and status.state == "failed":
                    return f"[error] {status.error}"
                continue
            if event.type == "final.result":
                return str(event.payload.get("text", ""))
        return "[error] 处理超时，请稍后重试或改用异步接口查询任务状态"
    finally:
        c.bus.unsubscribe(session_id, queue)


def build_container_origins() -> list[str]:
    """CORS 需要在 app 构造期就确定，此处单独读一次配置。"""
    from app.infrastructure.settings import load_settings

    return load_settings().cors_origins


app = build_app()


if __name__ == "__main__":
    import uvicorn

    from app.infrastructure.settings import load_settings

    uvicorn.run(app, host="0.0.0.0", port=load_settings().port)
