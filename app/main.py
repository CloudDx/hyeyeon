import asyncio, os, uuid, time, json
import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage
from datetime import datetime, timedelta, timezone

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Response, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aws_xray_sdk.core import xray_recorder
from starlette.middleware.base import BaseHTTPMiddleware
from xraysink.asgi.middleware import xray_middleware
from aws_xray_sdk.core.async_context import AsyncContext

from .config import settings
from .db import get_session, SessionLocal
from .models import Event, Order, Hold, OrderStatus
from .schemas import PurchaseIn, PurchaseOut, PayOut
from .metrics import ws_connections, ws_messages_total, purchase_attempts_total, purchase_duration_seconds, pg_locks_wait_seconds, metrics_response
from .utils import log_json

app = FastAPI(title="Flash Tickets (FastAPI)")

xray_recorder.configure(service='flash-ticket-backend', context=AsyncContext())
app.add_middleware(BaseHTTPMiddleware, dispatch=xray_middleware)

rabbitmq_connection: AbstractRobustConnection | None = None
rabbitmq_channel: AbstractRobustChannel | None = None

# 프로덕션 배포 시 실제 프론트엔드 도메인으로 교체
PROD_ORIGINS = ["https://gpdus4605.site", "https://www.gpdus4605.site"]

app.add_middleware(
    CORSMiddleware,
    # 로컬 개발 환경과 프로덕션 환경의 Origin을 모두 허용
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"] + PROD_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Idempotency-Key", "Content-Type"],
)

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

@app.get("/metrics", response_model=None)
async def metrics():
    ct, data = metrics_response()
    return Response(content=data, media_type=ct)

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

    async with session.begin():
        q = select(Order).where(
            Order.event_id == event_id,
            Order.idempotency_key == Idempotency_Key,
        )
        res = await session.execute(q)
        ex = res.scalars().first()
        if ex:
            purchase_attempts_total.labels(result="idempotent").inc()
            remaining, _, _ = await current_remaining(session, event_id)
            return PurchaseOut(orderId=ex.id, status=ex.status, remaining=remaining, holdExpiresAt=None)

        wait_start = time.perf_counter()
        await session.execute(text("SELECT 1 FROM events WHERE id=:eid FOR UPDATE"), {"eid": event_id})
        pg_locks_wait_seconds.observe(time.perf_counter() - wait_start)

        remaining, sold, in_hold = await current_remaining(session, event_id)
        if remaining < qty:
            purchase_attempts_total.labels(result="out_of_stock").inc()
            raise HTTPException(status_code=409, detail="OUT_OF_STOCK")

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

    purchase_attempts_total.labels(result="hold").inc()
    purchase_duration_seconds.observe(time.perf_counter() - start)

    remaining2, sold2, in_hold2 = await current_remaining(session, event_id)
    await manager.broadcast({"type": "stock.update", "remaining": remaining2, "sold": sold2, "inHold": in_hold2})
    await manager.broadcast({"type": "order.update", "orderId": order_id, "status": "HOLD"})

    return PurchaseOut(orderId=order_id, status="HOLD", remaining=remaining2, holdExpiresAt=expires.isoformat())

@app.post("/pay/{order_id}", response_model=PayOut)
async def pay(order_id: str, session: AsyncSession = Depends(get_session)):
    # 확인용 로그
    # log_json(event="pay_endpoint_triggered", order_id=order_id)
    # 1. Get order details
    r = await session.execute(text("SELECT event_id, qty, status FROM orders WHERE id=:oid"), {"oid": order_id})
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="order not found")
    event_id, qty, status = row

    if status == OrderStatus.PAID.value:
        return PayOut(ok=True, status="PAID")
    if status not in (OrderStatus.HOLD.value, OrderStatus.INIT.value):
        raise HTTPException(status_code=409, detail=f"invalid status {status}")

    # 2. Publish payment request message
    if not rabbitmq_channel:
        raise HTTPException(status_code=503, detail="RabbitMQ service not available")

    message_body = {
        "order_id": order_id,
        "event_id": event_id,
        "qty": qty
    }
    try:
        await rabbitmq_channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message_body).encode('utf-8')),
            routing_key='payment_request_queue'
        )
        log_json(event="payment_request_published", order_id=order_id)
        return PayOut(ok=True, status="PAYMENT_PROCESSING")
    except Exception as e:
        log_json(level="error", msg="payment_request_publish_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to publish payment request: {e}")

@app.websocket("/ws")
async def ws(ws: WebSocket, eventId: str):
    await manager.connect(ws)
    try:
        async with SessionLocal() as session:
            rem, sold, in_hold = await current_remaining(session, eventId)
        await ws.send_json({"type":"stock.update","remaining":rem,"sold":sold,"inHold":in_hold})
        ws_messages_total.labels(direction="send", type="stock.update").inc()

        while True:
            await ws.receive_text()
            ws_messages_total.labels(direction="recv", type="client").inc()
            await ws.send_json({"type":"ack"})
            ws_messages_total.labels(direction="send", type="ack").inc()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)

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

async def on_payment_result(message: AbstractIncomingMessage):
    # 확인용 로그
    # log_json(event="on_payment_result_triggered")
    async with message.process():
        try:
            data = json.loads(message.body.decode('utf-8'))
            order_id = data.get("order_id")
            status = data.get("status")
            event_id = data.get("event_id")

            if status == "PAID":
                log_json(event="payment_result_received", order_id=order_id, result="PAID")
                async with SessionLocal() as session:
                    rem, sold, in_hold = await current_remaining(session, event_id)
                await manager.broadcast({"type":"stock.update","remaining":rem,"sold":sold,"inHold":in_hold})
                await manager.broadcast({"type":"order.update","orderId":order_id,"status":"PAID"})
            else:
                log_json(event="payment_result_received", order_id=order_id, result="FAILED")
                # Optionally, handle failed payments (e.g., notify user)

        except Exception as e:
            log_json(level="error", msg="payment_result_processing_failed", error=str(e))

async def consume_payment_results():
    if not rabbitmq_channel:
        log_json(level="error", msg="cannot_consume_results_no_channel")
        return
    queue = await rabbitmq_channel.get_queue('payment_result_queue')
    await queue.consume(on_payment_result)
    log_json(event="consumer_started", queue="payment_result_queue")

async def connect_rabbitmq():
    global rabbitmq_connection, rabbitmq_channel
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
    
    for i in range(10):
        try:
            log_json(event="rabbitmq_connect", status="attempting", count=i)
            connection = await aio_pika.connect_robust(host=rabbitmq_host, timeout=5)
            rabbitmq_connection = connection
            log_json(event="rabbitmq_connect", status="success")
            
            rabbitmq_channel = await rabbitmq_connection.channel()
            log_json(event="rabbitmq_channel_get", status="success")

            await rabbitmq_channel.declare_queue('payment_request_queue', durable=True)
            log_json(event="rabbitmq_queue_declare", status="success", queue='payment_request_queue')
            
            await rabbitmq_channel.declare_queue('payment_result_queue', durable=True)
            log_json(event="rabbitmq_queue_declare", status="success", queue='payment_result_queue')

            break
        except Exception as e:
            log_json(level="warning", msg="rabbitmq_connect_failed_retrying", error=str(e), attempt=i)
            await asyncio.sleep(5)
    else:
        log_json(level="error", msg="rabbitmq_connect_failed_gave_up")
        raise RuntimeError("Failed to connect to RabbitMQ after several retries.")

async def consume_payment_results():
    if not rabbitmq_channel:
        log_json(level="error", msg="cannot_consume_results_no_channel")
        return
    queue = await rabbitmq_channel.get_queue('payment_result_queue')
    await queue.consume(on_payment_result)
    log_json(event="consumer_started", queue="payment_result_queue")

@app.on_event("startup")
async def on_start():
    asyncio.create_task(expire_task())
    await connect_rabbitmq()
    asyncio.create_task(consume_payment_results())

@app.on_event("shutdown")
async def on_shutdown():
    global rabbitmq_connection
    if rabbitmq_connection and not rabbitmq_connection.is_closed:
        await rabbitmq_connection.close()
        log_json(event="rabbitmq_shutdown", status="connection closed")
