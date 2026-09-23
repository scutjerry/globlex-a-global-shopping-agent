import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type {
  CreatedSimulatedOrder,
  DestinationCountry,
  OrderDetail,
  OrderListResponse,
  OrderQuote,
  OrderSummary,
  SimulatedOrderItem,
} from "../types";

interface OrderCenterProps {
  apiBase: string;
  controlTokens: Record<string, string>;
  setControlTokens: Dispatch<SetStateAction<Record<string, string>>>;
  initialOrderId?: string;
}

const statusText: Record<OrderSummary["status"], string> = {
  DRAFT: "待确认",
  CONFIRMED: "已记录",
  CANCELLED: "已取消",
};

const destinationOptions: Array<{ value: DestinationCountry; label: string }> = [
  { value: "US", label: "US · 美国" },
  { value: "EU", label: "EU · 欧盟区域" },
  { value: "GB", label: "GB · 英国" },
  { value: "JP", label: "JP · 日本" },
  { value: "CN", label: "CN · 中国" },
];

function formatAmount(amount: number, currency: string): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function pricingRows(order: OrderDetail | OrderQuote) {
  return [
    ["商品小计", order.merchandise_subtotal_major],
    ["模拟运费", order.shipping_amount_major],
    ["模拟进口税费", order.import_tax_amount_major],
  ] as const;
}

export default function OrderCenter({ apiBase, controlTokens, setControlTokens, initialOrderId }: OrderCenterProps) {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [itemsText, setItemsText] = useState('[{"product_id":"P1001","sku_id":"P1001-S1","quantity":1}]');
  const [destination, setDestination] = useState<DestinationCountry>("US");
  const [currency, setCurrency] = useState("USD");
  const [quote, setQuote] = useState<OrderQuote | null>(null);
  // Reused only while retrying the same confirmed quote; never persisted across a page reload.
  const [createIdempotencyKey, setCreateIdempotencyKey] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const parsedItems = useMemo((): SimulatedOrderItem[] | null => {
    try {
      const parsed: unknown = JSON.parse(itemsText);
      if (!Array.isArray(parsed)) return null;
      return parsed as SimulatedOrderItem[];
    } catch {
      return null;
    }
  }, [itemsText]);

  const loadOrders = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/orders?limit=20`);
      if (!response.ok) throw new Error(`订单目录响应 ${response.status}`);
      const payload = (await response.json()) as OrderListResponse;
      setOrders(payload.items);
      setSelectedId((current) => current || payload.items[0]?.order_id || "");
    } catch (loadError) {
      setError(`无法读取模拟订单：${String(loadError)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOrders();
  }, [apiBase]);

  useEffect(() => {
    if (initialOrderId) setSelectedId(initialOrderId);
  }, [initialOrderId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setDetail(null);
      return () => { cancelled = true; };
    }
    const loadDetail = async () => {
      try {
        const response = await fetch(`${apiBase}/commerce/orders/${encodeURIComponent(selectedId)}`);
        if (!response.ok) throw new Error(`订单详情响应 ${response.status}`);
        const payload = (await response.json()) as OrderDetail;
        if (!cancelled) setDetail(payload);
      } catch (loadError) {
        if (!cancelled) setError(`无法读取订单详情：${String(loadError)}`);
      }
    };
    void loadDetail();
    return () => { cancelled = true; };
  }, [apiBase, selectedId]);

  const body = (): { items: SimulatedOrderItem[]; destination_country: DestinationCountry; currency: string } | null => {
    if (!parsedItems?.length) return null;
    return { items: parsedItems, destination_country: destination, currency: currency.toUpperCase() };
  };

  const invalidateQuote = () => {
    setQuote(null);
    setCreateIdempotencyKey("");
  };

  const requestQuote = async () => {
    const request = body();
    if (!request) {
      setError("订单项必须是非空 JSON 数组，例如 [{\"product_id\":\"P1001\",\"sku_id\":\"P1001-S1\",\"quantity\":1}]。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/order-quotes`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
      });
      const payload = await response.json() as OrderQuote | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail : `报价响应 ${response.status}`);
      setQuote(payload as OrderQuote);
      setCreateIdempotencyKey(crypto.randomUUID());
    } catch (quoteError) {
      setQuote(null);
      setError(`无法计算模拟到手价：${String(quoteError)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const createOrder = async () => {
    const request = body();
    if (!request || !quote) {
      setError("请先成功计算模拟到手价，再创建模拟订单。");
      return;
    }
    if (!createIdempotencyKey) {
      setError("报价已失效，请重新计算模拟到手价后再创建。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": createIdempotencyKey },
        body: JSON.stringify(request),
      });
      const payload = await response.json() as CreatedSimulatedOrder | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail : `创建订单响应 ${response.status}`);
      const created = payload as CreatedSimulatedOrder;
      // Keep the first non-empty capability token in memory only. An idempotent replay deliberately
      // returns an empty token and must never erase the original cancellation capability.
      setControlTokens((current) => {
        if (!created.order_control_token) return current;
        return { ...current, [created.order_id]: created.order_control_token };
      });
      setSelectedId(created.order_id);
      setDetail(created);
      setQuote(null);
      setCreateIdempotencyKey("");
      await loadOrders();
    } catch (createError) {
      setError(`无法创建模拟订单：${String(createError)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const deleteOrder = async () => {
    if (!detail) return;
    const token = controlTokens[detail.order_id];
    if (!token) { setError("此页面未持有该模拟订单的删除控制令牌；不能删除。"); return; }
    if (!window.confirm("删除后该模拟订单将从订单中心隐藏且不可恢复；这不会退款、发货或改变库存。确定删除吗？")) return;
    setSubmitting(true); setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/orders/${encodeURIComponent(detail.order_id)}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ order_control_token: token }),
      });
      if (!response.ok) {
        const payload = await response.json() as { detail?: string };
        throw new Error(payload.detail ?? `删除订单响应 ${response.status}`);
      }
      setControlTokens((current) => { const next = { ...current }; delete next[detail.order_id]; return next; });
      setDetail(null); setSelectedId("");
      await loadOrders();
    } catch (deleteError) {
      setError(`无法删除模拟订单：${String(deleteError)}`);
    } finally { setSubmitting(false); }
  };

  const cancelOrder = async () => {
    if (!detail) return;
    const token = controlTokens[detail.order_id];
    if (!token) {
      setError("此页面未持有该模拟订单的取消控制令牌；为保护演示订单，不能取消。\n");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/orders/${encodeURIComponent(detail.order_id)}/cancellations`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ order_control_token: token }),
      });
      const payload = await response.json() as OrderDetail | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail : `取消订单响应 ${response.status}`);
      setDetail(payload as OrderDetail);
      // A CANCELLED user simulation remains logically deletable. Retain the in-memory-only
      // capability until deletion or page refresh; never persist or render it.
      await loadOrders();
    } catch (cancelError) {
      setError(`无法取消模拟订单：${String(cancelError)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="order-center" aria-label="受控模拟订单中心">
      <div className="order-heading">
        <div>
          <p className="eyebrow">SIMULATED ORDER LAB · NO REAL TRANSACTION</p>
          <h2>受控模拟订单中心</h2>
          <p>可为项目自建虚构商品创建、取消模拟订单；不会支付、发货、扣减库存或收集真实地址。价格是静态规则估算，绝非最终税费。</p>
        </div>
        <span className="demo-stamp">受控演示</span>
      </div>

      <section className="order-creator" aria-label="创建模拟订单">
        <h3>1. 计算模拟到手价</h3>
        <p>订单项使用项目目录 SKU；不输入姓名、电话、邮编或地址。覆盖市场：US、EU、GB、JP、CN。</p>
        <label>订单项 JSON
          <textarea value={itemsText} onChange={(event) => { setItemsText(event.target.value); invalidateQuote(); }} aria-label="模拟订单商品项" />
        </label>
        <div className="creator-controls">
          <label>目的市场
            <select value={destination} onChange={(event) => { setDestination(event.target.value as DestinationCountry); invalidateQuote(); }}>
              {destinationOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>显示币种
            <input value={currency} maxLength={3} onChange={(event) => { setCurrency(event.target.value.toUpperCase()); invalidateQuote(); }} />
          </label>
          <button type="button" onClick={() => void requestQuote()} disabled={submitting}>计算估算</button>
        </div>
        {quote && (
          <div className="quote-panel">
            <strong>模拟到手价：{formatAmount(quote.landed_total_major, quote.currency)}</strong>
            {pricingRows(quote).map(([label, amount]) => <span key={label}>{label}：{formatAmount(amount, quote.currency)}</span>)}
            <small>规则 {quote.rule_set_version} · {quote.source_summary} · {quote.source_status}</small>
            <small>{quote.estimate_disclaimer}</small>
            <button type="button" onClick={() => void createOrder()} disabled={submitting}>2. 明确创建模拟订单</button>
          </div>
        )}
      </section>

      {loading && <div className="order-feedback">正在载入模拟订单…</div>}
      {error && <div className="order-feedback error">{error}</div>}
      {!loading && !error && !orders.length && <div className="order-feedback">暂时没有可展示的模拟订单。</div>}

      {!loading && orders.length > 0 && (
        <div className="order-grid">
          <div className="order-list" role="list">
            {orders.map((order) => (
              <button className={`order-ticket ${order.order_id === selectedId ? "selected" : ""}`} key={order.order_id} onClick={() => setSelectedId(order.order_id)} type="button">
                <span className="ticket-route">{order.order_id}</span>
                <span className={`status status-${order.status.toLowerCase()}`}>{statusText[order.status]}</span>
                <strong>{formatAmount(order.total_amount_major, order.currency)}</strong>
                <small>{order.destination_country} · {order.item_count} 件商品 · {formatTime(order.created_at)}</small>
              </button>
            ))}
          </div>

          {detail && (
            <article className="order-detail">
              <div className="detail-topline">
                <div><p className="eyebrow">DESTINATION</p><h3>{detail.destination_country}</h3></div>
                <span className={`status status-${detail.status.toLowerCase()}`}>{statusText[detail.status]}</span>
              </div>
              <p className="detail-id">{detail.order_id} · {formatTime(detail.created_at)}</p>
              <div className="order-lines">
                {detail.lines.map((line) => (
                  <div className="order-line" key={`${line.sku_id}-${line.product_id}`}>
                    <div><strong>{line.title}</strong><span>{line.sku_id} · × {line.quantity}</span></div>
                    <span>{formatAmount(line.unit_price_major * line.quantity, line.currency)}</span>
                  </div>
                ))}
              </div>
              <div className="pricing-breakdown">
                {pricingRows(detail).map(([label, amount]) => <div key={label}><span>{label}</span><strong>{formatAmount(amount, detail.currency)}</strong></div>)}
              </div>
              <div className="order-total"><span>模拟到手价合计</span><strong>{formatAmount(detail.total_amount_major, detail.currency)}</strong></div>
              <p className="rule-note">规则 {detail.rule_set_version} · {detail.source_summary} · {detail.source_status}<br />{detail.estimate_disclaimer}</p>
              {detail.order_kind === "USER_SIMULATION" && detail.status === "CONFIRMED" && (
                <button className="cancel-order" type="button" onClick={() => void cancelOrder()} disabled={submitting || !controlTokens[detail.order_id]}>
                  {controlTokens[detail.order_id] ? "取消此模拟订单" : "仅创建页面可取消"}
                </button>
              )}
              {detail.order_kind === "USER_SIMULATION" && (detail.status === "CONFIRMED" || detail.status === "CANCELLED") && (
                <button className="delete-order" type="button" onClick={() => void deleteOrder()} disabled={submitting || !controlTokens[detail.order_id]}>
                  {controlTokens[detail.order_id] ? "删除此模拟订单" : "仅创建页面可删除"}
                </button>
              )}
              <p className="privacy-note">不展示或收集买家身份、电话、邮编、详细收货地址或取消原因；取消和删除不会退款、发货或改变库存。</p>
            </article>
          )}
        </div>
      )}
    </section>
  );
}
