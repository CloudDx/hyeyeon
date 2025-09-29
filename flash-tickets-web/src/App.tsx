import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, CircleDot, CircleSlash, Coins, Send, Server, ShoppingCart, Webhook } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080";

function genIdem() { return "ui-" + Math.random().toString(36).slice(2, 12); }

type StockEvent = { type: string; remaining?: number; sold?: number; inHold?: number; orderId?: string; status?: string; ts?: number; };
type PurchaseResp = { orderId?: string; status: string; remaining: number; holdExpiresAt?: string | null; reason?: string | null; };

export default function App() {
  const [eventId, setEventId] = useState("E1");
  const [qty, setQty] = useState(1);
  const [idem, setIdem] = useState(genIdem());
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [stock, setStock] = useState<{ remaining: number; sold: number; inHold: number } | null>(null);
  const [timeline, setTimeline] = useState<StockEvent[]>([]);
  const [lastOrderId, setLastOrderId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const chartData = useMemo(() => {
    const pts: { name: string; remaining: number }[] = [];
    timeline.forEach((e) => {
      if (e.type === "stock.update" && typeof e.remaining === "number") {
        pts.push({ name: new Date(e.ts ?? Date.now()).toLocaleTimeString(), remaining: e.remaining });
      }
    });
    return pts.slice(-40);
  }, [timeline]);

  function push(e: StockEvent) { setTimeline((prev) => [...prev.slice(-199), { ...e, ts: Date.now() }]); }

  const connectWS = () => {
    try {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
      setConnecting(true);
      const wsURL = new URL((API_BASE.startsWith("/") ? window.location.origin + API_BASE : API_BASE).replace(/^http/, "ws"));
      wsURL.pathname = (wsURL.pathname.replace(/\/$/, "") || "") + "/ws";
      wsURL.searchParams.set("eventId", eventId);
      const ws = new WebSocket(wsURL.toString());
      wsRef.current = ws;

      ws.onopen = () => {
        setError(null);
        setConnected(true);
        setConnecting(false);
        push({ type: "ws.open" });
      };

      ws.onclose = () => {
        setConnected(false);
        setConnecting(false);
        // Automatically reconnect after a delay
        setTimeout(connectWS, 2000);
      };

      ws.onerror = (err) => {
        console.log("WebSocket connection failed, retrying...", err);
        // No need to set a visible error message here, as reconnection is automatic
        ws.close(); // This will trigger the onclose handler for reconnection
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          push(data);
          if (data.type === "stock.update") setStock({ remaining: data.remaining, sold: data.sold, inHold: data.inHold });
        } catch {}
      };
    } catch (e: any) {
      setError(e?.message || "connect failed");
      setConnecting(false);
    }
  };

  const disconnectWS = () => {
    if (wsRef.current) {
      wsRef.current.onclose = null; // Prevent automatic reconnection
      wsRef.current.close();
      wsRef.current = null;
      setConnected(false);
      setConnecting(false);
      push({ type: "ws.close" });
    }
  };

  useEffect(() => {
    connectWS();
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnection on component unmount
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const purchase = async () => {
    setError(null);
    try {
      const r = await fetch((API_BASE.replace(/\/$/, "")) + "/purchase", {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idem },
        body: JSON.stringify({ eventId, qty }),
      });
      const data: PurchaseResp = await r.json();
      if (!r.ok) throw new Error(data?.reason || (data as any)?.detail || r.statusText);
      setLastOrderId(data.orderId || null);
      if (data.status === "HOLD") setIdem(genIdem());
    } catch (e: any) { setError(e?.message || "purchase failed"); }
  };

  const pay = async () => {
    if (!lastOrderId) return setError("결제할 orderId가 없습니다 (먼저 구매)");
    setError(null);
    try {
      const r = await fetch((API_BASE.replace(/\/$/, "")) + "/pay/" + lastOrderId, { method: "POST" });
      const data = await r.json();
      if (!r.ok) throw new Error((data as any)?.detail || r.statusText);
    } catch (e: any) { setError(e?.message || "pay failed"); }
  };

  return (
    <div style={{ fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0 }}>Flash Tickets — Dashboard</h2>
            <small style={{ color: "#64748b" }}>FastAPI + WebSocket + PostgreSQL</small>
          </div>
          <div>
            <button onClick={connected ? disconnectWS : connectWS} style={{ padding: "8px 12px" }}>
              {connected ? <CircleSlash size={16} style={{ marginRight: 6 }} /> : <CircleDot size={16} style={{ marginRight: 6 }} />}
              {connected ? "Disconnect" : (connecting ? "Connecting..." : "Connect")}
            </button>
          </div>
        </header>

        <section style={{ marginTop: 16, display: "grid", gap: 12, gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
          <label>Event ID <input value={eventId} onChange={(e) => setEventId(e.target.value)} placeholder="E1" /></label>
          <label>Qty <input type="number" value={qty} min={1} max={10} onChange={(e) => setQty(parseInt(e.target.value || "1"))} /></label>
          <label>Idempotency-Key <input value={idem} onChange={(e) => setIdem(e.target.value)} /></label>
          <div style={{ display: "flex", alignItems: "end" }}>
            <button onClick={() => setIdem(genIdem())} style={{ width: "100%" }}>새 키</button>
          </div>
        </section>

        {error && <div style={{ marginTop: 12, padding: 12, background: "#fee2e2", border: "1px solid #fecaca" }}>
          <b>오류</b><div>{error}</div>
        </div>}

        <section style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={purchase}><Send size={16} style={{ marginRight: 6 }} /> 구매(HOLD)</button>
          <button onClick={pay}><CheckCircle2 size={16} style={{ marginRight: 6 }} /> 결제(PAID)</button>
          {lastOrderId && <span style={{ border: "1px solid #cbd5e1", padding: "6px 8px", borderRadius: 4, color: "#475569" }}>
            last order: {lastOrderId}
          </span>}
        </section>

        <section style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}>
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "#64748b", display: "flex", justifyContent: "space-between" }}>
              <span>남은 수량</span><ShoppingCart size={16} />
            </div>
            <div style={{ fontSize: 36, fontWeight: 700 }}>{stock?.remaining ?? "-"}</div>
            <small style={{ color: "#94a3b8" }}>실시간</small>
          </div>
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "#64748b", display: "flex", justifyContent: "space-between" }}>
              <span>판매 완료</span><Coins size={16} />
            </div>
            <div style={{ fontSize: 36, fontWeight: 700 }}>{stock?.sold ?? "-"}</div>
            <small style={{ color: "#94a3b8" }}>누적</small>
          </div>
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "#64748b", display: "flex", justifyContent: "space-between" }}>
              <span>홀드 중</span><Server size={16} />
            </div>
            <div style={{ fontSize: 36, fontWeight: 700 }}>{stock?.inHold ?? "-"}</div>
            <small style={{ color: "#94a3b8" }}>결제 대기</small>
          </div>
        </section>

        <section style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12, height: 300 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <b>남은 수량 추이</b>
            </div>
            <div style={{ height: 230 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="c1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="name" hide />
                  <YAxis width={30} stroke="#94a3b8" />
                  <Tooltip />
                  <Area type="monotone" dataKey="remaining" stroke="#3b82f6" fillOpacity={1} fill="url(#c1)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <b>실시간 이벤트</b>
              <span style={{ color: connected ? "#16a34a" : "#64748b", display: "inline-flex", alignItems: "center" }}>
                <Webhook size={14} style={{ marginRight: 6 }} /> {connected ? "connected" : "disconnected"}
              </span>
            </div>
            <pre style={{ maxHeight: 220, overflow: "auto", background: "#f8fafc", padding: 8 }}>
{timeline.slice().reverse().map((e) => {
  const ts = new Date(e.ts || Date.now()).toLocaleTimeString();
  const body =
    e.type === "stock.update" ? `remaining=${e.remaining} sold=${e.sold} hold=${e.inHold}` :
    e.type === "order.update" ? `order=${e.orderId} status=${e.status}` :
    e.type;
  return `${ts}  ${e.type}  ${body}\n`;
}).join("")}
            </pre>
          </div>
        </section>
      </div>
    </div>
  );
}
