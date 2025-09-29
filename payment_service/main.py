import asyncio, os, json
import aio_pika
from fastapi import FastAPI
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel, AbstractIncomingMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import SessionLocal
from .models import OrderStatus

# A utility function for logging, assuming it exists or will be created
def log_json(level="info", **kwargs):
    print(json.dumps({"level": level, **kwargs}), flush=True)

app = FastAPI(title="Payment Service")

rabbitmq_connection: AbstractRobustConnection | None = None
rabbitmq_channel: AbstractRobustChannel | None = None

async def connect_rabbitmq():
    global rabbitmq_connection, rabbitmq_channel
    
    for i in range(10):
        try:
            log_json(event="rabbitmq_connect", status="attempting", count=i)
            connection = await aio_pika.connect_robust(host=settings.rabbitmq_host, timeout=5)
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

async def on_message(message: AbstractIncomingMessage):
    # 확인용 로그
    # log_json(event="payment_service_on_message_triggered")
    async with message.process():
        try:
            data = json.loads(message.body.decode('utf-8'))
            order_id = data.get("order_id")
            event_id = data.get("event_id")
            qty = data.get("qty")

            if not all([order_id, event_id, qty]):
                log_json(level="error", msg="invalid_message_received", data=data)
                return

            log_json(event="payment_processing_start", order_id=order_id)

            async with SessionLocal() as session:
                async with session.begin():
                    # This is the core logic from the original /pay endpoint
                    await session.execute(text("UPDATE orders SET status=:status WHERE id=:oid"), {"status": OrderStatus.PAID.value, "oid": order_id})
                    await session.execute(text("UPDATE events SET sold_qty = sold_qty + :qty WHERE id=:eid"), {"qty": qty, "eid": event_id})
                    await session.execute(text("DELETE FROM holds WHERE event_id=:eid AND user_id='user_demo'"), {"eid": event_id})
            
            log_json(event="payment_processing_success", order_id=order_id)

            # Publish result back to the main app
            result_message = {
                "order_id": order_id,
                "status": "PAID",
                "event_id": event_id,
                "qty": qty
            }
            await rabbitmq_channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(result_message).encode('utf-8')),
                routing_key='payment_result_queue'
            )
            log_json(event="payment_result_published", order_id=order_id)

        except Exception as e:
            log_json(level="error", msg="payment_processing_failed", error=str(e))
            # Here you might want to publish a "FAILED" message back
            # For now, just logging the error

async def consume_payment_requests():
    if not rabbitmq_channel:
        log_json(level="error", msg="cannot_consume_no_channel")
        return
        
    queue = await rabbitmq_channel.get_queue('payment_request_queue')
    await queue.consume(on_message)
    log_json(event="consumer_started", queue="payment_request_queue")

@app.on_event("startup")
async def on_start():
    await connect_rabbitmq()
    asyncio.create_task(consume_payment_requests())

@app.on_event("shutdown")
async def on_shutdown():
    global rabbitmq_connection
    if rabbitmq_connection and not rabbitmq_connection.is_closed:
        await rabbitmq_connection.close()
        log_json(event="rabbitmq_shutdown", status="connection closed")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}