/// <reference types="vite/client" />

export type TradeEventType =
  | "agent.dispatch"
  | "tool.invoke"
  | "tool.result"
  | "token.delta"
  | "plan.update"
  | "context.compressed"
  | "model.fallback"
  | "final.result"
  | "error";

export interface TradeEvent {
  type: TradeEventType;
  payload: Record<string, any>;
  occurred_at: string;
}

export interface LandedPrice {
  ship_to: string;
  subtotal_major: number;
  freight_major: number;
  tariff_major: number;
  tariff_rate: number;
  de_minimis_applied: boolean;
  landed_total_major: number;
  currency: string;
  unavailable_reason?: string;
}

export interface ProductCard {
  product_id: string;
  title: string;
  brand: string;
  category: string;
  origin_country: string;
  price_major: number;
  currency: string;
  highlights: string[];
  // 目录公开数据，非隐私字段。用于把模拟订单草案的目的地限制在商品真正可寄送的市场内。
  ships_to?: string[];
  skus: { sku_id: string; spec: string; price_major: number; currency: string; stock: number }[];
  score: number;
  landed_price?: LandedPrice;
}

export type DestinationCountry = "US" | "EU" | "GB" | "JP" | "CN";

export interface SimulatedOrderItem {
  product_id: string;
  sku_id: string;
  quantity: number;
}

export interface OrderLine {
  product_id: string;
  sku_id: string;
  title: string;
  unit_price_major: number;
  currency: string;
  quantity: number;
}

export interface PricingBreakdown {
  merchandise_subtotal_major: number;
  shipping_amount_major: number;
  import_tax_amount_major: number;
  rule_set_version: string;
  source_summary: string;
  source_status: string;
  estimate_disclaimer: string;
}

export interface OrderSummary {
  order_id: string;
  status: "DRAFT" | "CONFIRMED" | "CANCELLED";
  total_amount_major: number;
  currency: string;
  item_count: number;
  destination_country: string;
  created_at: string;
  order_kind: "SEEDED_DEMO" | "USER_SIMULATION";
}

export interface OrderDetail extends OrderSummary, PricingBreakdown {
  lines: OrderLine[];
}

export interface OrderQuote extends PricingBreakdown {
  landed_total_major: number;
  currency: string;
  destination_country: DestinationCountry;
  items: OrderLine[];
}

export interface CreatedSimulatedOrder extends OrderDetail {
  // This token deliberately only lives in the OrderCenter component state. Never persist or display it.
  order_control_token: string;
  control_token_warning: string;
}

export interface OrderListResponse {
  items: OrderSummary[];
  demo_data: boolean;
}
