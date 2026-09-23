# -*- coding: utf-8 -*-
"""订单 Agent 工具：只允许脱敏查询。

受控模拟订单的创建和取消刻意只通过显式 HTTP 页面流程处理：该流程有前端确认、
一次性控制令牌和不进入 Agent/事件流的隐私边界。这里不能重新加入写工具。

注意：本模块不能用 ``from __future__ import annotations``（AgentScope schema 生成依赖运行时注解）。
"""
import json

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool import ToolChunk

from app.application.usecases.order_usecases import QueryOrderUseCase
from app.infrastructure.context import ShoppingContext
from app.infrastructure.eventbus import TradeEventBus


def _ok(payload: dict) -> ToolChunk:
    return ToolChunk(
        content=[TextBlock(type="text", text=json.dumps(payload, ensure_ascii=False))],
        state=ToolResultState.SUCCESS,
    )


def _fail(message: str) -> ToolChunk:
    return ToolChunk(
        content=[TextBlock(type="text", text=f"[error] {message}")],
        state=ToolResultState.ERROR,
    )


def build_query_order_tool(usecase: QueryOrderUseCase, bus: TradeEventBus):
    async def query_order_tool(order_id: str) -> ToolChunk:
        """查询脱敏的模拟订单详情；不能创建、取消或读取地址/令牌。

        Args:
            order_id (`str`):
                订单号，如 ``DEMO-CN-24001`` 或 ``SIM-ABC123``。
        """
        session_id = ShoppingContext.current_session_id()
        bus.publish(session_id, "tool.invoke", {"tool": "query_order_tool", "args": {"order_id": order_id}})
        try:
            snapshot = await usecase.execute(order_id)
        except ValueError as err:
            bus.publish(session_id, "tool.result", {"tool": "query_order_tool", "error": str(err)})
            return _fail(str(err))
        bus.publish(session_id, "tool.result", {"tool": "query_order_tool", "order": snapshot})
        return _ok(snapshot)

    return query_order_tool
