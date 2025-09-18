from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

ws_connections = Gauge("ws_connections","Active WebSocket connections")
ws_messages_total = Counter("ws_messages_total","WebSocket messages", ["direction","type"])
purchase_attempts_total = Counter("purchase_attempts_total","Purchase attempts", ["result"])
purchase_duration_seconds = Histogram("purchase_duration_seconds","Purchase latency seconds", buckets=(0.01,0.05,0.1,0.2,0.3,0.5,1,2,5))
pg_locks_wait_seconds = Histogram("pg_locks_wait_seconds","DB lock wait seconds", buckets=(0.001,0.005,0.01,0.02,0.05,0.1,0.2,0.5,1))

def metrics_response():
    data = generate_latest()
    return CONTENT_TYPE_LATEST, data
