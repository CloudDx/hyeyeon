import asyncio
import os
import aio_pika

async def main():
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
    connection = None

    # 10번 재시도
    for i in range(10):
        try:
            print(f"Attempting to connect to RabbitMQ... ({i+1}/10)")
            connection = await aio_pika.connect_robust(host=rabbitmq_host, timeout=5)
            print("Successfully connected to RabbitMQ.")
            break  # 성공 시 루프 탈출
        except Exception as e:
            print(f"RabbitMQ not ready, retrying in 5 seconds... Error: {e}")
            await asyncio.sleep(5)

    if not connection:
        print("Failed to connect to RabbitMQ after several retries.")
        exit(1)

    async with connection:
        # 채널 생성
        channel = await connection.channel()

        # 큐 선언 (생산자와 동일한 큐)
        queue = await channel.declare_queue('hello')

        print(' [*] Waiting for messages. To exit press CTRL+C')

        # 큐를 비동기적으로 순회하며 메시지 처리
        async for message in queue:
            async with message.process():
                print(f" [x] Received {message.body.decode()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
