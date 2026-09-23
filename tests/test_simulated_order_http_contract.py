# -*- coding: utf-8 -*-
"""HTTP 契约的静态回归：受控写路径、错误脱敏和私有字段隔离。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.presentation.dto import (
    CancelSimulatedOrderRequest,
    CreatedSimulatedOrderResponse,
    OrderDetailResponse,
    OrderQuoteResponse,
    SimulatedOrderRequest,
)


_PRIVATE_INPUTS = {
    "buyer_id",
    "shipping_address",
    "recipient_name",
    "phone",
    "postal_code",
    "state",
    "city",
    "address_line",
    "cancel_reason",
    "cancel_reason_code",
    "order_control_token",
}


def _valid_order_body() -> dict:
    return {
        "items": [{"product_id": "P1001", "sku_id": "P1001-S1", "quantity": 1}],
        "destination_country": "US",
        "currency": "USD",
    }


def test_create_request_does_not_accept_real_address_or_cancel_reason():
    for field in _PRIVATE_INPUTS:
        assert field not in SimulatedOrderRequest.model_fields
    assert "cancel_reason" not in CancelSimulatedOrderRequest.model_fields
    assert set(CancelSimulatedOrderRequest.model_fields) == {"order_control_token"}


@pytest.mark.parametrize("field", sorted(_PRIVATE_INPUTS))
def test_simulated_order_request_rejects_every_private_extra_field(field):
    body = _valid_order_body()
    body[field] = "PRIVATE-VALUE"
    with pytest.raises(ValidationError) as error:
        SimulatedOrderRequest.model_validate(body)
    assert field in str(error.value)


def test_simulated_order_item_rejects_embedded_pii_extra_fields():
    body = _valid_order_body()
    body["items"][0].update({"recipient_name": "PRIVATE-NAME", "phone": "PRIVATE-PHONE"})
    with pytest.raises(ValidationError) as error:
        SimulatedOrderRequest.model_validate(body)
    assert "recipient_name" in str(error.value)


def test_cancel_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CancelSimulatedOrderRequest.model_validate({
            "order_control_token": "x" * 32,
            "cancel_reason": "PRIVATE-REASON",
        })


def test_control_token_is_only_in_create_response():
    assert "order_control_token" in CreatedSimulatedOrderResponse.model_fields
    assert "order_control_token" not in OrderDetailResponse.model_fields
    assert "order_control_token" not in OrderQuoteResponse.model_fields


def test_public_order_models_exclude_all_private_order_fields_and_keep_audit_status():
    fields = set(OrderDetailResponse.model_fields) | set(OrderQuoteResponse.model_fields)
    assert "source_status" in fields
    assert not fields.intersection({
        "buyer_id", "recipient_name", "phone", "postal_code", "state", "city", "address_line",
        "shipping_address", "cancel_reason", "cancel_reason_code", "control_token_hash",
    })


def test_order_validation_handler_uses_fixed_error_without_raw_input_echo():
    from app.presentation.server import build_app

    app = build_app()
    handler = app.exception_handlers.get(__import__("fastapi").exceptions.RequestValidationError)
    assert handler is not None
    # The source-level assertion guards against returning Pydantic exc.errors(), which carries `input`.
    import inspect
    source = inspect.getsource(handler)
    assert '"detail": "请求格式无效"' in source
    assert ".errors()" not in source
