# syntax=docker/dockerfile:1

# 1. Builder stage: 의존성 빌드
FROM python:3.11-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# 2. Final stage: 실제 실행 환경
FROM python:3.11-slim AS final
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Builder stage에서 빌드한 패키지 복사 및 설치
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 소스 코드 복사
COPY . ./payment_service/

CMD ["uvicorn", "payment_service.main:app", "--host", "0.0.0.0", "--port", "8081"]