# -*- coding: utf-8 -*-
"""TradeAgent

MVP 脱敏订单查询专家。工具集仅包含 query_order_tool；受控模拟订单的创建和取消
只能由显式 HTTP 页面流程触发，因此 Agent 对话入口不能改变订单或库存。

同 SearchAgent 一样，通过 task_dispatch 工具被 MainAgent 调度，每次调度新建独立实例；
`build_tools()` 同时供 MainAgent 复用。
"""
from __future__ import annotations

from agentscope.agent import Agent, ReActConfig
from agentscope.tool import FunctionTool, Toolkit

from app.application.agents.context_policy import build_context_config
from app.application.agents.permissions import allow_business_tools
from app.application.prompts.loader import load_prompts
from app.application.tools.order_tools import build_query_order_tool
from app.application.usecases.order_usecases import QueryOrderUseCase
from app.infrastructure.eventbus import TradeEventBus
from app.infrastructure.llm import create_chat_model
from app.infrastructure.throttle import GatewayThrottle
from app.infrastructure.resilience import (
    CircuitBreakerRegistry,
    ToolResilienceMiddleware,
)
from app.infrastructure.settings import Settings
from app.infrastructure.tracing import build_agent_middlewares


class TradeAgentFactory:
    def __init__(
        self,
        settings: Settings,
        query_order: QueryOrderUseCase,
        bus: TradeEventBus,
        circuit_registry: CircuitBreakerRegistry,
        throttle: GatewayThrottle,
    ) -> None:
        self._settings = settings
        self._query_order = query_order
        self._bus = bus
        self._circuit_registry = circuit_registry
        self._throttle = throttle

    def _resilience(self) -> list:
        return [ToolResilienceMiddleware(self._circuit_registry, self._bus)]

    def build_tools(self) -> list[FunctionTool]:
        """TradeAgent 的业务工具集，MainAgent 单干时持有同一批（均带超时+熔断保护）。"""
        return [
            FunctionTool(
                build_query_order_tool(self._query_order, self._bus),
                is_read_only=True,
                middlewares=self._resilience(),
            ),
        ]

    def build(self) -> Agent:
        prompts = load_prompts()["sub_agents"]["trade"]
        return allow_business_tools(
            Agent(
                name=prompts["name"],
                system_prompt=prompts["system_prompt"],
                model=create_chat_model(self._settings, throttle=self._throttle, bus=self._bus),
                toolkit=Toolkit(tools=list(self.build_tools())),
                middlewares=build_agent_middlewares(self._settings),
                context_config=build_context_config(
                    self._settings.context_size,
                    self._settings.tool_result_limit,
                ),
                react_config=ReActConfig(max_iters=6),
            ),
        )
