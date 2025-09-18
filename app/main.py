import asyncio, os, uuid, time
from datetime import datetime, timedelta, timezone

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Response, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session, SessionLocal
from .models import Event, Order, Hold, OrderStatus
from .schemas import PurchaseIn, PurchaseOut, PayOut
from .metrics import ws_connections, ws_messages_total, purchase_attempts_total, purchase_duration_seconds, pg_locks_wait_seconds, metrics_response
from .utils import log_json

app = FastAPI(title="Flash Tickets (FastAPI)")

# ▼ 추가: Vite(5173)에서 오는 프리플라이트/본요청 모두 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,   # 쿠키/인증 필요 없으면 False로 바꿔도 됨
    allow_methods=["*"],      # 프리플라이트에서 확인하는 메서드 전부 허용
    allow_headers=["Idempotency-Key"],      # 커스텀 헤더(Idempotency-Key 등) 허용
)

# --- simple in-memory WS broadcast manager ---
class WSManager:
    def __init__(self):
        self.active: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active.add(ws)
            ws_connections.inc()

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.active:
                self.active.remove(ws)
                ws_connections.dec()

    async def broadcast(self, msg: dict):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(msg)
                ws_messages_total.labels(direction="send", type=msg.get("type","unknown")).inc()
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

manager = WSManager()

async def current_remaining(sess: AsyncSession, event_id: str) -> tuple[int,int,int]:
    # get total/sold and inHold (non-expired)
    q = text("""
        WITH hold AS (
            SELECT COALESCE(SUM(qty),0) AS in_hold
            FROM holds WHERE event_id = :eid AND expires_at > now()
        )
        SELECT total_qty, sold_qty, hold.in_hold
        FROM events, hold
        WHERE events.id = :eid
    """)
    r = await sess.execute(q, {"eid": event_id})
    total, sold, in_hold = r.fetchone()
    remaining = total - sold - in_hold
    return remaining, sold, in_hold

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz(db: bool | None = Query(default=False), session: AsyncSession = Depends(get_session)):
    if db:
        await session.execute(text("SELECT 1"))
    return "ok"

@app.get("/metrics")
async def metrics():
    ct, data = metrics_response()
    return Response(content=data, media_type=ct)

# --- PURCHASE ---
@app.post("/purchase", response_model=PurchaseOut)
async def purchase(
    payload: PurchaseIn,
    session: AsyncSession = Depends(get_session),
    Idempotency_Key: str | None = Header(default=None),
):
    start = time.perf_counter()
    if not Idempotency_Key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    event_id = payload.eventId
    qty = payload.qty
    order_id = "ord_" + uuid.uuid4().hex[:10]
    hold_id = "hold_" + uuid.uuid4().hex[:10]

    # ✅ 트랜잭션을 딱 한 번만 연다 (이 안에 멱등체크/락/INSERT 모두)
    async with session.begin():
        # 1) 멱등체크 (이미 존재하면 그대로 반환)
        q = select(Order).where(
            Order.event_id == event_id,
            Order.idempotency_key == Idempotency_Key,
        )
        res = await session.execute(q)
        ex = res.scalars().first()
        if ex:
            purchase_attempts_total.labels(result="idempotent").inc()
            # remaining 계산은 별도 함수 사용 (SELECT만 수행)
            remaining, _, _ = await current_remaining(session, event_id)
            return PurchaseOut(orderId=ex.id, status=ex.status, remaining=remaining, holdExpiresAt=None)

        # 2) 이벤트 행 잠금 (원자적 차감 준비)
        wait_start = time.perf_counter()
        await session.execute(text("SELECT 1 FROM events WHERE id=:eid FOR UPDATE"), {"eid": event_id})
        pg_locks_wait_seconds.observe(time.perf_counter() - wait_start)

        # 3) 잔여 수량 확인
        remaining, sold, in_hold = await current_remaining(session, event_id)
        if remaining < qty:
            purchase_attempts_total.labels(result="out_of_stock").inc()
            raise HTTPException(status_code=409, detail="OUT_OF_STOCK")

        # 4) 주문 + 홀드 INSERT
        await session.execute(
            text("""
                INSERT INTO orders(id, user_id, event_id, status, qty, idempotency_key)
                VALUES (:oid, :uid, :eid, :status, :qty, :idem)
            """),
            {
                "oid": order_id,
                "uid": "user_demo",
                "eid": event_id,
                "status": OrderStatus.HOLD.value,
                "qty": qty,
                "idem": Idempotency_Key,
            },
        )
        expires = datetime.now(timezone.utc) + timedelta(seconds=settings.hold_ttl_sec)
        await session.execute(
            text("""
                INSERT INTO holds(id, event_id, user_id, qty, expires_at)
                VALUES (:hid, :eid, :uid, :qty, :exp)
            """),
            {"hid": hold_id, "eid": event_id, "uid": "user_demo", "qty": qty, "exp": expires},
        )

    # 트랜잭션 COMMIT 이후 브로드캐스트
    purchase_attempts_total.labels(result="hold").inc()
    purchase_duration_seconds.observe(time.perf_counter() - start)

    remaining2, sold2, in_hold2 = await current_remaining(session, event_id)
    await manager.broadcast({"type": "stock.update", "remaining": remaining2, "sold": sold2, "inHold": in_hold2})
    await manager.broadcast({"type": "order.update", "orderId": order_id, "status": "HOLD"})

    return PurchaseOut(orderId=order_id, status="HOLD", remaining=remaining2, holdExpiresAt=expires.isoformat())

@app.post("/pay/{order_id}", response_model=PayOut)
async def pay(order_id: str, session: AsyncSession = Depends(get_session)):
    async with session.begin():
        # get order
        r = await session.execute(text("SELECT event_id, qty, status FROM orders WHERE id=:oid FOR UPDATE"), {"oid": order_id})
        row = r.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="order not found")
        event_id, qty, status = row
        if status == OrderStatus.PAID.value:
            return PayOut(ok=True, status="PAID")
        if status not in (OrderStatus.HOLD.value, OrderStatus.INIT.value):
            raise HTTPException(status_code=409, detail=f"invalid status {status}")

        # set PAID and increase sold_qty
        await session.execute(text("UPDATE orders SET status='PAID' WHERE id=:oid"), {"oid": order_id})
        await session.execute(text("UPDATE events SET sold_qty = sold_qty + :qty WHERE id=:eid"), {"qty": qty, "eid": event_id})
        # remove corresponding holds
        await session.execute(text("DELETE FROM holds WHERE event_id=:eid AND user_id='user_demo'"), {"eid": event_id})

    # broadcast
    rem, sold, in_hold = await current_remaining(session, event_id)
    await manager.broadcast({"type":"stock.update","remaining":rem,"sold":sold,"inHold":in_hold})
    await manager.broadcast({"type":"order.update","orderId":order_id,"status":"PAID"})
    log_json(event="pay", orderId=order_id, result="PAID", remaining=rem)
    return PayOut(ok=True, status="PAID")

@app.websocket("/ws")
async def ws(ws: WebSocket, eventId: str):
    await manager.connect(ws)
    try:
        # send initial snapshot
        async with SessionLocal() as session:
            rem, sold, in_hold = await current_remaining(session, eventId)
        await ws.send_json({"type":"stock.update","remaining":rem,"sold":sold,"inHold":in_hold})
        ws_messages_total.labels(direction="send", type="stock.update").inc()

        while True:
            msg = await ws.receive_text()
            ws_messages_total.labels(direction="recv", type="client").inc()
            # simple echo ack
            await ws.send_json({"type":"ack"})
            ws_messages_total.labels(direction="send", type="ack").inc()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)

# --- background task: expire holds periodically ---
async def expire_task():
    while True:
        try:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(text("""
                        UPDATE orders SET status='EXPIRED'
                        WHERE id IN (
                          SELECT o.id FROM orders o
                          JOIN holds h ON h.event_id = o.event_id AND h.user_id = o.user_id
                          WHERE o.status='HOLD' AND h.expires_at <= now()
                        )
                    """))
                    await session.execute(text("DELETE FROM holds WHERE expires_at <= now()"))
            await asyncio.sleep(5)
        except Exception as e:
            log_json(level="error", msg="expire_task_error", error=str(e))
            await asyncio.sleep(5)

@app.on_event("startup")
async def on_start():
    asyncio.create_task(expire_task())
