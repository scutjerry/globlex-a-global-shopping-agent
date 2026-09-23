# -*- coding: utf-8 -*-
"""domain 层单测：Money 与受控模拟订单状态机。"""
import pytest

from app.domain.catalog.money import Money
from app.domain.order.address import Address
from app.domain.order.order import Order, OrderKind, OrderPricingSnapshot, OrderStatus
from app.domain.order.order_line import OrderLine


def _address() -> Address:
    return Address("张三", "CN", "浙江", "杭州", "西湖区某路 1 号", "310000", "13800000000")


def _line(currency: str = "CNY", major: float = 189.0, quantity: int = 2) -> OrderLine:
    return OrderLine("P1001", "P1001-S1", "Nomadica 旅行三件套（军绿色）", Money.from_major_units(major, currency), quantity)


def _simulated_order() -> Order:
    lines = [_line()]
    pricing = OrderPricingSnapshot(
        merchandise_subtotal=Money.from_major_units(378, "CNY"),
        shipping_amount=Money.from_major_units(25, "CNY"),
        import_tax_amount=Money.from_major_units(10, "CNY"),
        destination_country="CN", rule_set_version="test-v1", source_ids=("test",),
        source_summary="测试来源", source_status="test_verified", estimate_disclaimer="仅为模拟估算。",
    )
    return Order.place_simulation("SIM-TEST", "buyer-1", "CN", lines, pricing, "a" * 64)


class TestMoney:
    def test_minor_units_storage(self):
        money = Money.from_major_units(189.0, "CNY")
        assert money.amount_in_minor_units == 18900
        assert money.to_major_units() == 189.0

    def test_add_and_multiply(self):
        total = Money.from_major_units(10.5, "USD").add(Money.from_major_units(0.5, "USD"))
        assert total.amount_in_minor_units == 1100
        assert total.multiply(3).amount_in_minor_units == 3300

    def test_reject_negative_amount(self):
        with pytest.raises(ValueError):
            Money.of(-1, "CNY")

    def test_reject_currency_mismatch(self):
        with pytest.raises(ValueError, match="币种不一致"):
            Money.of(100, "CNY").add(Money.of(100, "USD"))

    def test_reject_unsupported_currency(self):
        with pytest.raises(ValueError):
            Money.of(100, "XXX")


class TestOrderStateMachine:
    def test_place_simulation_enters_confirmed_and_freezes_landed_total(self):
        order = _simulated_order()
        assert order.status is OrderStatus.CONFIRMED
        assert order.order_kind is OrderKind.USER_SIMULATION
        assert order.confirmed_at is not None
        assert order.total_amount().to_major_units() == 413.0

    def test_cancel_confirmed_simulated_order(self):
        order = _simulated_order()
        order.cancel()
        assert order.status is OrderStatus.CANCELLED
        assert order.cancel_reason_code == "buyer_requested"

    def test_rehydrate_cancelled_simulated_order_is_valid(self):
        order = _simulated_order()
        order.cancel()
        restored = Order(
            order_id=order.order_id,
            buyer_id=order.buyer_id,
            shipping_address=order.shipping_address,
            lines=order.lines,
            status=order.status,
            created_at=order.created_at,
            confirmed_at=order.confirmed_at,
            cancelled_at=order.cancelled_at,
            order_kind=order.order_kind,
            pricing=order.pricing,
            control_token_hash=order.control_token_hash,
            cancel_reason_code=order.cancel_reason_code,
        )
        assert restored.status is OrderStatus.CANCELLED

    def test_seeded_order_cannot_cancel(self):
        seed = Order.place("DEMO-1", "buyer-1", _address(), [_line()])
        with pytest.raises(ValueError, match="历史订单不可取消"):
            seed.cancel("不再需要")

    def test_cancel_twice_rejected(self):
        order = _simulated_order()
        order.cancel()
        with pytest.raises(ValueError, match="仅 CONFIRMED"):
            order.cancel()

    def test_reject_mixed_currency_lines(self):
        with pytest.raises(ValueError, match="币种不一致"):
            Order.place("GBX-000001", "buyer-1", _address(), [_line("CNY"), _line("USD")])

    def test_reject_empty_lines(self):
        with pytest.raises(ValueError, match="订单行"):
            Order.place("GBX-000001", "buyer-1", _address(), [])
