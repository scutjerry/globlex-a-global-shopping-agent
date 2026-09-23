# -*- coding: utf-8 -*-
"""受控模拟订单的版本化静态费用规则。

这些规则仅用于 Globex 项目自建虚构数据的到手价演示，绝不是税务、报关、
物流或最终收费计算。规则在请求期间不访问搜索引擎、海关、物流或支付服务。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.domain.catalog.exchange_rate import ExchangeRateTable
from app.domain.catalog.money import Money

SIMULATED_FEE_RULE_SET_VERSION = "cross-border-fees-2026-01-v1"
ESTIMATE_DISCLAIMER = "费用为下单前估算，最终金额以结算结果为准。"


@dataclass(frozen=True)
class SimulatedFeeRule:
    destination_country: str
    import_tax_rate: float
    base_shipping_cny_minor: int
    additional_item_ratio: float
    tax_threshold_minor: Optional[int]
    threshold_currency: str
    source_id: str
    source_summary: str
    source_status: str
    assumption_note: str


# 费率是显式的演示建模假设。资料目录和核验限制见 docs/SIMULATED_ORDERS_V1_DESIGN.md。
_RULES: dict[str, SimulatedFeeRule] = {
    "US": SimulatedFeeRule(
        "US", 0.06, 6500, 0.60, 80000, "USD", "us-cbp-internet-purchases",
        "US CBP Internet Purchases（低值包裹与税费结构参考）", "official_verified",
        "参考税费率；未按 HS、原产地、配额或监管要求计算。",
    ),
    "EU": SimulatedFeeRule(
        "EU", 0.20, 7500, 0.60, None, "EUR", "eu-commission-online-imports",
        "European Commission 非欧盟在线购物进口说明（进口 VAT/€150 结构参考）", "official_verified",
        "EU 为区域结算代码，不按成员国 VAT、IOSS 或 TARIC 分别计算。",
    ),
    "GB": SimulatedFeeRule(
        "GB", 0.20, 7000, 0.60, None, "GBP", "gb-gov-tax-and-customs-abroad",
        "GOV.UK 境外寄送商品税费说明（VAT/£135 结构参考）", "official_verified",
        "不覆盖北爱尔兰、消费税货物或 UK Trade Tariff 的实际归类。",
    ),
    "JP": SimulatedFeeRule(
        "JP", 0.10, 4500, 0.60, 1000000, "JPY", "jp-customs-major-duty-rates",
        "Japan Customs 主要商品关税税率说明（按品类变化结构参考）", "official_verified",
        "统一演示税费率与阈值；不按材质、加工、用途或真实消费税结算。",
    ),
    "CN": SimulatedFeeRule(
        "CN", 0.091, 2500, 0.60, 500000, "CNY", "cn-cross-border-demo-assumption",
        "CN 跨境费用参考规则", "reference_rule",
        "参考规则未按商品税号逐项计算，不能解释为中国实际税率或免税额度。",
    ),
}


@dataclass(frozen=True)
class SimulatedFeeQuote:
    merchandise_subtotal: Money
    shipping_amount: Money
    import_tax_amount: Money
    destination_country: str
    rule_set_version: str
    source_id: str
    source_summary: str
    source_status: str
    estimate_disclaimer: str = ESTIMATE_DISCLAIMER

    def __post_init__(self) -> None:
        currencies = {
            self.merchandise_subtotal.currency,
            self.shipping_amount.currency,
            self.import_tax_amount.currency,
        }
        if len(currencies) != 1:
            raise ValueError("费用报价币种必须一致")

    @property
    def landed_total(self) -> Money:
        return self.merchandise_subtotal.add(self.shipping_amount).add(self.import_tax_amount)

    def to_dict(self) -> dict:
        return {
            "merchandise_subtotal_major": self.merchandise_subtotal.to_major_units(),
            "shipping_amount_major": self.shipping_amount.to_major_units(),
            "import_tax_amount_major": self.import_tax_amount.to_major_units(),
            "landed_total_major": self.landed_total.to_major_units(),
            "currency": self.landed_total.currency,
            "destination_country": self.destination_country,
            "rule_set_version": self.rule_set_version,
            "source_summary": self.source_summary,
            "source_status": self.source_status,
            "estimate_disclaimer": self.estimate_disclaimer,
        }


@dataclass(frozen=True)
class SimulatedFeeSchedule:
    rates: ExchangeRateTable

    def supported_destinations(self) -> list[str]:
        return sorted(_RULES)

    def rule_for(self, destination_country: str) -> SimulatedFeeRule:
        rule = _RULES.get(destination_country)
        if rule is None:
            raise ValueError(
                f"暂不支持该目的市场：{destination_country}（支持 {self.supported_destinations()}）",
            )
        return rule

    def quote(self, merchandise_subtotal: Money, quantity: int, destination_country: str, target_currency: str) -> SimulatedFeeQuote:
        if quantity < 1 or quantity > 10:
            raise ValueError("订单商品总数量必须在 1 到 10 之间")
        rule = self.rule_for(destination_country)
        subtotal = self.rates.convert(merchandise_subtotal, target_currency)
        freight_cny = round(rule.base_shipping_cny_minor * (1 + rule.additional_item_ratio * (quantity - 1)))
        shipping = self.rates.convert(Money.of(freight_cny, "CNY"), target_currency)
        taxable = subtotal.add(shipping)
        taxable_for_rate = taxable
        if rule.tax_threshold_minor is not None:
            threshold = self.rates.convert(Money.of(rule.tax_threshold_minor, rule.threshold_currency), target_currency)
            taxable_for_rate = Money.of(max(0, taxable.amount_in_minor_units - threshold.amount_in_minor_units), target_currency)
        import_tax = Money.of(round(taxable_for_rate.amount_in_minor_units * rule.import_tax_rate), target_currency)
        return SimulatedFeeQuote(
            merchandise_subtotal=subtotal,
            shipping_amount=shipping,
            import_tax_amount=import_tax,
            destination_country=destination_country,
            rule_set_version=SIMULATED_FEE_RULE_SET_VERSION,
            source_id=rule.source_id,
            source_summary=rule.source_summary,
            source_status=rule.source_status,
        )
