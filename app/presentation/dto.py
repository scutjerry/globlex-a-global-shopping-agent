# -*- coding: utf-8 -*-
"""REST 请求/响应 DTO；订单公共响应始终脱敏。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubmitIntentRequest(BaseModel):
    shopping_session_id: Optional[str] = Field(default=None, description="会话 ID，缺省则新建会话")
    buyer_id: str = Field(min_length=1, description="买家 ID")
    locale: str = Field(default="zh-CN")
    currency: str = Field(default="CNY")
    raw_query: str = Field(min_length=1, description="买家自然语言购物意图")


class SubmitIntentResponse(BaseModel):
    shopping_session_id: str
    final_text: str


class SimulatedOrderItemRequest(BaseModel):
    # Item objects are also strict: do not silently accept PII embedded under an order line.
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=32)
    sku_id: str = Field(min_length=1, max_length=32)
    quantity: int = Field(ge=1, le=10)


class SimulatedOrderRequest(BaseModel):
    """新模拟订单只接收商品、目的市场与显示币种，绝不收集真实地址。"""

    model_config = ConfigDict(extra="forbid")

    items: list[SimulatedOrderItemRequest] = Field(min_length=1, max_length=10)
    destination_country: Literal["US", "EU", "GB", "JP", "CN"]
    currency: str = Field(default="CNY", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class OrderSummaryResponse(BaseModel):
    """订单中心列表行；刻意不包含买家、地址、控制令牌或取消原因。"""

    order_id: str
    status: str
    total_amount_major: float
    currency: str
    item_count: int
    destination_country: str
    created_at: str
    order_kind: str


class OrderListResponse(BaseModel):
    items: list[OrderSummaryResponse]
    demo_data: bool = True


class OrderLineResponse(BaseModel):
    product_id: str
    sku_id: str
    title: str
    unit_price_major: float
    currency: str
    quantity: int


class OrderPricingResponse(BaseModel):
    merchandise_subtotal_major: float
    shipping_amount_major: float
    import_tax_amount_major: float
    rule_set_version: str
    source_summary: str
    source_status: str
    estimate_disclaimer: str


class OrderDetailResponse(OrderSummaryResponse, OrderPricingResponse):
    lines: list[OrderLineResponse]
    demo_data: bool = True


class OrderQuoteResponse(OrderPricingResponse):
    landed_total_major: float
    currency: str
    destination_country: str
    source_status: str
    items: list[OrderLineResponse]


class CreatedSimulatedOrderResponse(OrderDetailResponse):
    order_control_token: str
    control_token_warning: str = "仅此一次返回；请仅在当前页面临时保存以取消模拟订单。"


class CancelSimulatedOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_control_token: str = Field(min_length=32, max_length=256)
