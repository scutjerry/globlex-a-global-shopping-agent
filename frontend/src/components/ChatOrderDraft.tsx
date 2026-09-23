import { useEffect, useMemo, useState } from "react";
import type {
  CreatedSimulatedOrder,
  DestinationCountry,
  OrderQuote,
  ProductCard,
  SimulatedOrderItem,
} from "../types";

interface ChatOrderDraftProps {
  apiBase: string;
  product: ProductCard;
  onDismiss: () => void;
  onCreated: (created: CreatedSimulatedOrder) => void;
}

// V1 静态费用规则覆盖的市场。只有同时落在商品 ships_to 内的市场才可能创建模拟订单：
// 对不支持的市场发起报价会得到 422，因此这里从一开始就不提供该选项。
const feeMarkets: Array<{ value: DestinationCountry; label: string }> = [
  { value: "US", label: "美国 (US)" },
  { value: "EU", label: "欧盟区域 (EU)" },
  { value: "GB", label: "英国 (GB)" },
  { value: "JP", label: "日本 (JP)" },
  { value: "CN", label: "中国 (CN)" },
];

// 与后端 SUPPORTED_CURRENCIES（静态汇率表口径）保持一致，避免提交无法换算的币种。
const supportedCurrencies = [
  "USD", "EUR", "GBP", "JPY", "CNY", "HKD", "AUD", "CAD", "SGD",
  "KRW", "THB", "NZD", "INR", "BRL", "AED",
];

function formatAmount(amount: number, currency: string): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency", currency, currencyDisplay: "code", maximumFractionDigits: 2,
  }).format(amount);
}

/**
 * A chat-owned confirmation surface. It consumes only catalog IDs from the Agent's verified
 * product search event, requests a fresh server quote, and never gives the Agent a write tool
 * or a capability token. Closing this card is purely local and performs no write.
 */
export default function ChatOrderDraft({ apiBase, product, onDismiss, onCreated }: ChatOrderDraftProps) {
  // 商品若未声明 ships_to，则回退到全部费用市场，由服务端做最终校验。
  const availableDestinations = useMemo(() => {
    const shippable = product.ships_to?.length ? product.ships_to : feeMarkets.map((market) => market.value);
    return feeMarkets.filter((market) => shippable.includes(market.value));
  }, [product.ships_to]);

  const quotedShipTo = product.landed_price?.ship_to as DestinationCountry | undefined;
  const defaultDestination = useMemo(() => {
    // 优先沿用搜索时的目的市场（此时卡片已带该市场的到手价），否则取第一个可寄送市场。
    if (quotedShipTo && availableDestinations.some((market) => market.value === quotedShipTo)) return quotedShipTo;
    return availableDestinations[0]?.value ?? "US";
  }, [quotedShipTo, availableDestinations]);

  const defaultCurrency = product.landed_price?.currency ?? product.skus[0]?.currency ?? "USD";

  const [skuId, setSkuId] = useState(product.skus[0]?.sku_id ?? "");
  const [quantity, setQuantity] = useState(1);
  const [destination, setDestination] = useState<DestinationCountry>(defaultDestination);
  const [currency, setCurrency] = useState(defaultCurrency);
  const [quote, setQuote] = useState<OrderQuote | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const item = useMemo<SimulatedOrderItem>(() => ({ product_id: product.product_id, sku_id: skuId, quantity }), [product.product_id, skuId, quantity]);

  // 切换到另一张推荐卡时必须重新推导 SKU / 目的地 / 币种，否则会沿用上一件商品的组合。
  // App 侧同时以 key 强制重挂载，这里作为第二道保险。
  useEffect(() => {
    setSkuId(product.skus[0]?.sku_id ?? "");
    setQuantity(1);
    setDestination(defaultDestination);
    setCurrency(defaultCurrency);
  }, [product]);

  useEffect(() => {
    setQuote(null);
    setError("");
  }, [skuId, quantity, destination, currency]);

  const request = () => ({ items: [item], destination_country: destination, currency: currency.toUpperCase() });

  const getQuote = async () => {
    if (!availableDestinations.length) { setError("该推荐不支持任何 V1 模拟费用市场，无法创建模拟订单。"); return; }
    if (!skuId) { setError("该推荐没有可创建的目录 SKU。"); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/order-quotes`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request()),
      });
      const payload = await response.json() as OrderQuote | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail : `报价响应 ${response.status}`);
      setQuote(payload as OrderQuote);
    } catch (reason) {
      setQuote(null); setError(`无法生成模拟订单草案：${String(reason)}`);
    } finally { setBusy(false); }
  };

  const confirm = async () => {
    if (!quote) { setError("请先计算并核对模拟到手价。"); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch(`${apiBase}/commerce/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(request()),
      });
      const payload = await response.json() as CreatedSimulatedOrder | { detail?: string };
      if (!response.ok) throw new Error("detail" in payload ? payload.detail : `创建订单响应 ${response.status}`);
      onCreated(payload as CreatedSimulatedOrder);
    } catch (reason) {
      setError(`无法创建模拟订单：${String(reason)}`);
    } finally { setBusy(false); }
  };

  return <aside className="chat-order-draft" aria-label="待确认模拟订单">
    <p className="eyebrow">SIMULATED ORDER DRAFT · USER CONFIRMATION REQUIRED</p>
    <h3>为「{product.title}」创建模拟订单草案</h3>
    <p>Agent 仅提供目录推荐。服务端会重新校验 SKU 和静态费用；不会支付、发货、扣减库存或收集地址。</p>
    <p className="ship-to">可寄送市场：{product.ships_to?.length ? product.ships_to.join(" / ") : "目录未声明"} · V1 模拟费用规则覆盖：{feeMarkets.map((market) => market.value).join(" / ")}</p>
    {availableDestinations.length === 0 ? (
      <p className="draft-error">该推荐的可寄送市场不在 V1 模拟费用规则覆盖范围内，因此无法创建模拟订单。请换一个可寄送至 {feeMarkets.map((market) => market.value).join(" / ")} 的商品。</p>
    ) : (
      <>
        <div className="draft-controls">
          <label>SKU<select value={skuId} onChange={(event) => setSkuId(event.target.value)}>{product.skus.map((sku) => <option value={sku.sku_id} key={sku.sku_id}>{sku.spec} · {sku.price_major} {sku.currency}</option>)}</select></label>
          <label>数量<input type="number" min="1" max="10" value={quantity} onChange={(event) => setQuantity(Math.max(1, Math.min(10, Number(event.target.value) || 1)))} /></label>
          <label>目的市场<select value={destination} onChange={(event) => setDestination(event.target.value as DestinationCountry)}>{availableDestinations.map((entry) => <option value={entry.value} key={entry.value}>{entry.label}</option>)}</select></label>
          <label>显示币种<select value={currency} onChange={(event) => setCurrency(event.target.value)}>{supportedCurrencies.map((code) => <option value={code} key={code}>{code}</option>)}</select></label>
        </div>
        {!quote && <button type="button" onClick={() => void getQuote()} disabled={busy || !skuId}>{busy ? "正在核验…" : "计算模拟到手价"}</button>}
        {quote && <div className="draft-quote">
          <strong>模拟到手价：{formatAmount(quote.landed_total_major, quote.currency)}</strong>
          <span>商品小计：{formatAmount(quote.merchandise_subtotal_major, quote.currency)}</span>
          <span>模拟运费：{formatAmount(quote.shipping_amount_major, quote.currency)}</span>
          <span>模拟进口税费：{formatAmount(quote.import_tax_amount_major, quote.currency)}</span>
          <small>规则 {quote.rule_set_version} · {quote.source_summary} · {quote.source_status}</small>
          <small>{quote.estimate_disclaimer}</small>
          <div className="draft-actions"><button type="button" className="confirm-order" onClick={() => void confirm()} disabled={busy}>确认创建模拟订单</button><button type="button" onClick={onDismiss} disabled={busy}>取消草案</button></div>
        </div>}
      </>
    )}
    {error && <p className="draft-error">{error}</p>}
  </aside>;
}
