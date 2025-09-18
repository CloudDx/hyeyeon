# Flash Tickets — FastAPI (Phase 1: PostgreSQL only)

## Features
- FastAPI + Uvicorn
- WebSocket: `/ws?eventId=E1` (stock/order/queue updates)
- HTTP: `POST /purchase`, `POST /pay/:orderId`, `GET /healthz`, `GET /metrics`
- PostgreSQL (async SQLAlchemy + asyncpg), transactional stock decrement with `FOR UPDATE`
- Idempotency via unique `(event_id, idempotency_key)`
- Simple HOLD with TTL (expires in background task)
- Prometheus metrics: success/latency/WS connections
- JSON logs (one line)

## Quickstart (local)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# update .env (DB connection), or start a dev postgres:
docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=tickets postgres:15

# env
cp .env.example .env

# init sample data
python -m app.init_db

# run
uvicorn app.main:app --reload --port 8080
```

## Env
See `.env.example`.

## API
- `POST /purchase`  (Idempotency-Key header required)
- `POST /pay/:orderId`
- `GET /healthz` (use `?db=ping` for DB check)
- `GET /metrics`
- `GET /ws?eventId=E1`

## Docker
```bash
docker build -t flash-tickets:local .
docker run --rm -dit -p 8080:8080 --env-file .env --name flash-ticket flash-tickets:local
```

1) .env 준비 (없으면 기본값 사용)
예시:
DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/appdb
POSTGRES_USER=app
POSTGRES_PASSWORD=app
POSTGRES_DB=appdb

2) 빌드 & 실행
docker compose up -d --build

3) 확인
docker compose ps
curl -s http://localhost:8080/healthz?db=ping