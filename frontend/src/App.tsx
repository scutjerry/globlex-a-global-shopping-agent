import { useEffect, useRef, useState } from "react";
import EventTimeline from "./components/EventTimeline";
import ProductCards from "./components/ProductCards";
import ChatOrderDraft from "./components/ChatOrderDraft";
import OrderCenter from "./components/OrderCenter";
import type { CreatedSimulatedOrder, ProductCard, TradeEvent } from "./types";

// 生产容器使用 Nginx 同源代理；本地独立 Vite 仍可通过 VITE_API_BASE / VITE_WS_BASE 覆盖。
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;

function loadOrCreate(key: string, prefix: string): string {
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const created = `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
  localStorage.setItem(key, created);
  return created;
}

interface Turn {
  role: "buyer" | "agent";
  text: string;
}

export default function App() {
  const [sessionId] = useState(() => loadOrCreate("globex.session", "web"));
  const [buyerId] = useState(() => loadOrCreate("globex.buyer", "buyer"));
  const [events, setEvents] = useState<TradeEvent[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [streaming, setStreaming] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "orders">("chat");
  // Capability tokens are intentionally memory-only. They are never passed to the Agent,
  // persisted in browser storage, rendered into text, or sent through the websocket.
  const [controlTokens, setControlTokens] = useState<Record<string, string>>({});
  const [draftProduct, setDraftProduct] = useState<ProductCard | null>(null);
  const [createdFromChat, setCreatedFromChat] = useState<CreatedSimulatedOrder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // WS 订阅：按会话接收 Agent 过程事件（StrictMode 下会双次挂载，用 closed 标记避免早关告警）
  useEffect(() => {
    let closed = false;
    let retryTimer: number | undefined;

    const connect = () => {
      if (closed) return;
      const ws = new WebSocket(`${WS_BASE}/commerce/events`);
      wsRef.current = ws;
      ws.onopen = () => {
        if (closed) {
          ws.close();
          return;
        }
        ws.send(JSON.stringify({ shopping_session_id: sessionId }));
        setConnected(true);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          // 断线重连，避免长任务期间丢事件
          retryTimer = window.setTimeout(connect, 1500);
        }
      };
      ws.onmessage = (message) => {
        const event: TradeEvent = JSON.parse(message.data);
        if (event.type === "token.delta") {
          setStreaming((prev) => prev + (event.payload.token ?? ""));
          return;
        }
        setEvents((prev) => [...prev, event]);
        if (event.type === "final.result") {
          setStreaming("");
          setTurns((prev) => [...prev, { role: "agent", text: event.payload.text ?? "" }]);
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [sessionId]);

  const handleCreatedFromChat = (created: CreatedSimulatedOrder) => {
    // Preserve only the first non-empty token from the create response; idempotent replays never erase it.
    if (created.order_control_token) {
      setControlTokens((current) => ({ ...current, [created.order_id]: created.order_control_token }));
    }
    setCreatedFromChat(created);
    setDraftProduct(null);
    // Deliberately stays on the chat view: switching away here previously unmounted the chat and
    // made the recommended product cards and the draft entry point disappear. The user decides
    // when to open the order center, via the receipt rendered below.
  };

  const handleCreateDraft = (product: ProductCard) => {
    // A new draft supersedes the previous creation receipt.
    setCreatedFromChat(null);
    setDraftProduct(product);
  };

  const submit = async () => {
    const query = input.trim();
    if (!query || busy) return;
    setInput("");
    setBusy(true);
    setTurns((prev) => [...prev, { role: "buyer", text: query }]);
    try {
      await fetch(`${API_BASE}/commerce/intents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shopping_session_id: sessionId,
          buyer_id: buyerId,
          locale: "zh-CN",
          currency: "CNY",
          raw_query: query,
        }),
      });
    } catch (error) {
      setTurns((prev) => [...prev, { role: "agent", text: `[error] 请求失败：${error}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="layout">
      <header>
        <h1>Globex 跨境购物助手</h1>
        <div className="meta">
          <span>会话 {sessionId}</span>
          <span>买家 {buyerId}</span>
          <span className={connected ? "dot on" : "dot off"}>{connected ? "事件流已连接" : "事件流断开"}</span>
        </div>
        <nav className="view-tabs" aria-label="工作区切换">
          <button className={activeView === "chat" ? "active" : ""} onClick={() => setActiveView("chat")} type="button">Agent 对话</button>
          <button className={activeView === "orders" ? "active" : ""} onClick={() => setActiveView("orders")} type="button">模拟订单</button>
        </nav>
      </header>

      {activeView === "chat" ? <main>
        <section className="chat">
          <div className="turns">
            {turns.map((turn, index) => (
              <div key={index} className={`turn ${turn.role}`}>
                <div className="who">{turn.role === "buyer" ? "我" : "Globex"}</div>
                <div className="text">{turn.text}</div>
              </div>
            ))}
            {streaming && (
              <div className="turn agent streaming">
                <div className="who">Globex</div>
                <div className="text">{streaming}</div>
              </div>
            )}
            {busy && !streaming && <div className="hint">Agent 正在处理……</div>}
          </div>

          <ProductCards events={events} onCreateDraft={handleCreateDraft} />
          {draftProduct && <ChatOrderDraft key={draftProduct.product_id} apiBase={API_BASE} product={draftProduct} onDismiss={() => setDraftProduct(null)} onCreated={handleCreatedFromChat} />}

          {createdFromChat && (
            <div className="creation-notice" role="status">
              <strong>已创建模拟订单 {createdFromChat.order_id}</strong>
              <span>{createdFromChat.status} · 目的市场 {createdFromChat.destination_country} · {createdFromChat.total_amount_major} {createdFromChat.currency} · {createdFromChat.item_count} 件</span>
              <small>此订单不会支付、发货或扣减库存。控制令牌只保存在本次会话内存中，取消或删除都需在订单中心完成。</small>
              <div className="creation-actions">
                <button type="button" className="primary" onClick={() => setActiveView("orders")}>前往订单中心</button>
                <button type="button" onClick={() => setCreatedFromChat(null)}>继续挑选商品</button>
              </div>
            </div>
          )}

          <div className="composer">
            <textarea
              value={input}
              placeholder="例如：我人在美国，250 美元预算买个降噪耳机寄美国，到手价多少？"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit();
                }
              }}
            />
            <button onClick={() => void submit()} disabled={busy || !input.trim()}>
              {busy ? "处理中" : "发送"}
            </button>
          </div>
        </section>

        <EventTimeline events={events} />
      </main> : <OrderCenter apiBase={API_BASE} controlTokens={controlTokens} setControlTokens={setControlTokens} initialOrderId={createdFromChat?.order_id} />}
    </div>
  );
}
