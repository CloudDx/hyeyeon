import pika
import os
import time

# Docker Compose에서 설정한 RabbitMQ 서비스 이름(rabbitmq)을 호스트로 사용
rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
connection = None
retry_count = 0
max_retries = 10
retry_delay = 5

while retry_count < max_retries:
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
        print("Successfully connected to RabbitMQ.")
        break
    except pika.exceptions.AMQPConnectionError:
        print(f"RabbitMQ not ready, retrying in {retry_delay} seconds... ({retry_count + 1}/{max_retries})")
        time.sleep(retry_delay)
        retry_count += 1

if not connection:
    print("Failed to connect to RabbitMQ after several retries.")
    exit(1)

channel = connection.channel()

# 'hello'라는 이름의 큐를 생성
channel.queue_declare(queue='hello')

# 'hello' 큐에 "Hello World!" 메시지를 전송
channel.basic_publish(exchange='',
                      routing_key='hello',
                      body='Hello World!')
print(" [x] Sent 'Hello World!'")
connection.close()
