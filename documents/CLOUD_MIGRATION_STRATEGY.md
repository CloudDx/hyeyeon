# Flash Tickets 클라우드 마이그레이션 전략

## 🎯 **최종 목표: 대기열 없는 플래시 세일 시스템**

현재 Flash Tickets을 **AWS 클라우드 기반의 무제한 확장 가능한 시스템**으로 전환하여, 100만명이 동시 접속해도 대기열 없이 즉시 처리 가능한 아키텍처 구축

---

## 🏆 **Target Architecture (최종 목표)**

### **완성된 아키텍처 (12-18개월 후)**
```
                    👥 사용자들 (무제한 동시 접속)
                           │
                           ▼
                 🌐 AWS Application Load Balancer
                    (Global Accelerator 연동)
                           │
                           ▼
                    ☸️ Amazon EKS Cluster
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   Pod Auto-Scale      Pod Auto-Scale     Pod Auto-Scale
   (1-100개 Pod)       (1-100개 Pod)      (1-100개 Pod)
   Multi-AZ 분산       Multi-AZ 분산      Multi-AZ 분산
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
  ⚡ ElastiCache     📨 Amazon MQ        🗄️ CNPG Cluster
   Redis Cluster     (관리형 RabbitMQ)    (PostgreSQL HA)
   (20+ 노드)         Multi-AZ HA         Primary + 2 Replica
   20M+ ops/sec      무제한 확장          자동 Failover
```

### **기술 스택 조합**
```yaml
Infrastructure:
  - Amazon EKS: Kubernetes 관리형 서비스
  - ElastiCache Redis: 고성능 캐시 클러스터
  - CNPG: Cloud Native PostgreSQL 운영자
  - Amazon MQ: 관리형 RabbitMQ

성능 목표:
  - 동시 사용자: 1,000,000+ 명
  - 응답 시간: 50ms 이하 유지
  - 처리량: 50,000+ TPS
  - 가용성: 99.99% SLA
```

### **예상 성능 향상**
```
현재 시스템 vs 목표 시스템:

동시 처리:     1,000명    →    1,000,000명 (1000배)
응답 시간:     34ms       →    50ms (유지)
처리량:        1,000 TPS  →    50,000+ TPS (50배)
가용성:        99.9%      →    99.99% (10배 향상)
확장성:        수동       →    자동 무제한 확장
운영 복잡도:   수동       →    완전 자동화
```

---

## ⚠️ **위험 요소 분석**

### **한 번에 전환할 경우 위험성**
```
복잡성 폭증:
  현재 관리 항목: 5개
  ├── Docker Compose
  ├── PostgreSQL 
  ├── Redis
  ├── RabbitMQ
  └── Nginx

  목표 관리 항목: 20+ 개
  ├── EKS 클러스터 관리
  ├── kubectl 명령어 숙지
  ├── Helm 차트 관리  
  ├── YAML 매니페스트 작성
  ├── ElastiCache 클러스터 설정
  ├── CNPG Operator 설치/관리
  ├── IAM 권한 관리
  ├── VPC 네트워킹
  ├── 보안 그룹 설정
  ├── 로드 밸런서 구성
  ├── Auto Scaling 정책
  ├── 모니터링 설정 (Prometheus, Grafana)
  ├── 로깅 (ELK Stack)
  ├── 백업/복구 전략
  ├── 비용 최적화
  ├── 장애 대응 프로세스
  └── ... 등등

비용 폭증:
  현재: $100/월 → 목표: $2,000+/월 (20배 증가)
  
학습 곡선:
  현재: Docker 기본 지식
  목표: Kubernetes, AWS 전문 지식 필요 (6-12개월 학습)
```

---

## 🚀 **단계적 마이그레이션 전략**

### **Phase 1: ElastiCache 우선 전환** ⭐ **즉시 실행 권장**

#### **목표**
```
현재 Redis → AWS ElastiCache 전환
- 코드 변경 최소화
- 즉시 200배 성능 향상
- 대기열 없는 시스템 90% 달성
```

#### **기술적 구현**
```python
# Before (현재 Docker Redis)
redis_client = redis.Redis(
    host='redis',
    port=6379,
    decode_responses=True
)

# After (ElastiCache)
elasticache_client = RedisCluster(
    startup_nodes=[
        {"host": "flash-tickets.xxx.cache.amazonaws.com", "port": 6379}
    ],
    decode_responses=True,
    skip_full_coverage_check=True
)

# 나머지 모든 코드는 동일!
# - stock_cache.py 로직 그대로
# - redis_lock.py 분산 락 그대로  
# - Lua 스크립트 그대로
```

#### **ElastiCache 클러스터 설정**
```bash
# AWS CLI로 클러스터 생성
aws elasticache create-replication-group \
    --replication-group-id flash-tickets-cluster \
    --description "Flash Tickets Redis Cluster" \
    --num-cache-clusters 3 \
    --cache-node-type cache.r6g.large \
    --engine redis \
    --engine-version 7.0 \
    --multi-az-enabled \
    --automatic-failover-enabled \
    --at-rest-encryption-enabled \
    --transit-encryption-enabled \
    --auth-token "your-secure-token"
```

#### **성능 예상 효과**
```
현재 Docker Redis:
- 처리량: 100,000 ops/sec
- 응답시간: 2ms
- 동시 연결: 10,000개
- 메모리: 256MB

ElastiCache 클러스터:
- 처리량: 20,000,000 ops/sec (200배 ↑)
- 응답시간: 3-5ms (약간 증가)
- 동시 연결: 65,000개 (6배 ↑)
- 메모리: 수백 GB (1000배 ↑)

플래시 세일 대응력:
- 현재: 10만명 동시 처리 한계
- 개선: 100만명+ 동시 처리 가능
```

#### **비용 및 일정**
```
비용: $600/월 추가 (현재 $100 → $700)
ROI: 즉시 회수 (서버 다운 방지 효과)
일정: 1주일 (테스트 + 전환)
위험도: 낮음 ⭐⭐

Week 1: ElastiCache 클러스터 생성 + 연결 테스트
Week 2: 프로덕션 환경 전환
Week 3: 성능 튜닝 + 모니터링 설정
Week 4: 부하 테스트로 100만 동시 접속 검증
```

### **Phase 2: Amazon RDS PostgreSQL 전환** (3개월 후)

#### **목표**
```
Docker PostgreSQL → Amazon RDS
- 고가용성 확보 (Multi-AZ)
- 자동 백업/패치
- 운영 부담 제거
```

#### **RDS 설정 예시**
```yaml
# Terraform 구성
resource "aws_db_instance" "flash_tickets" {
  identifier = "flash-tickets-postgres"
  
  # 엔진 설정
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.r6g.xlarge"
  
  # 스토리지 설정
  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true
  
  # 고가용성 설정
  multi_az               = true
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  
  # 보안 설정
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.flash_tickets.name
  
  # 성능 설정
  monitoring_interval = 60
  performance_insights_enabled = true
  
  # 연결 설정
  db_name  = "tickets"
  username = "app"
  password = var.db_password
}
```

#### **성능 및 비용**
```
현재 Docker PostgreSQL:
- 가용성: 95% (단일 장애점)
- 백업: 수동
- 패치: 수동
- 모니터링: 기본

Amazon RDS:
- 가용성: 99.95% (Multi-AZ)
- 백업: 자동 (PITR 지원)
- 패치: 자동 (유지보수 창구)
- 모니터링: CloudWatch + Performance Insights

비용: $400/월 추가
일정: 1개월
위험도: 낮음 ⭐⭐
```

### **Phase 3: Amazon EKS 전환** (6-9개월 후)

#### **전환 조건**
```
✅ Kubernetes 전문 지식 확보 (팀 교육 완료)
✅ 월 활성 사용자 100만명+ 달성
✅ 24/7 운영팀 구성 (최소 3명)
✅ 월 예산 $2000+ 확보
✅ ElastiCache + RDS 운영 경험 6개월+
```

#### **EKS 클러스터 구성**
```yaml
# EKS 클러스터 설정
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig

metadata:
  name: flash-tickets-cluster
  region: ap-northeast-2
  version: "1.29"

managedNodeGroups:
  - name: flash-tickets-workers
    instanceTypes: ["m5.large", "m5.xlarge"]
    minSize: 3
    maxSize: 100
    desiredCapacity: 6
    
    # Auto Scaling 설정
    iam:
      withAddonPolicies:
        autoScaler: true
        albIngress: true
        cloudWatch: true
    
    # 다중 AZ 배포
    availabilityZones: ["ap-northeast-2a", "ap-northeast-2b", "ap-northeast-2c"]

# Pod Auto Scaling 설정
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: flash-tickets-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: flash-tickets-api
  minReplicas: 5
  maxReplicas: 200
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

#### **애플리케이션 배포 구성**
```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flash-tickets-api
spec:
  replicas: 5
  selector:
    matchLabels:
      app: flash-tickets-api
  template:
    metadata:
      labels:
        app: flash-tickets-api
    spec:
      containers:
      - name: api
        image: flash-tickets:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: flash-tickets-secrets
              key: database-url
        - name: REDIS_URL
          value: "redis://flash-tickets.xxx.cache.amazonaws.com:6379"
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        
        # Health Checks
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5

---
# Service
apiVersion: v1
kind: Service
metadata:
  name: flash-tickets-api-service
spec:
  selector:
    app: flash-tickets-api
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

#### **비용 및 효과**
```
추가 비용: $1,000/월
- EKS 클러스터: $500/월
- EC2 인스턴스: $400/월
- ALB, VPC 등: $100/월

효과:
- 무제한 자동 확장 (1→200 Pod)
- 무중단 배포 (Rolling Update)
- 자동 장애 복구
- 멀티 리전 배포 가능
- 마이크로서비스 아키텍처 지원

일정: 3개월
위험도: 높음 ⭐⭐⭐⭐
```

### **Phase 4: CNPG 도입** (12-18개월 후)

#### **전환 조건**
```
✅ EKS 운영 경험 6개월+
✅ PostgreSQL DBA 전문 인력 확보
✅ 고도화된 DB 요구사항 발생
✅ RDS 비용 최적화 필요성 대두
```

#### **CNPG 클러스터 구성**
```yaml
# CloudNativePG Cluster
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: flash-tickets-postgres
spec:
  instances: 3  # Primary + 2 Standby
  
  postgresql:
    parameters:
      # 성능 튜닝
      max_connections: "500"
      shared_buffers: "256MB"
      effective_cache_size: "1GB"
      maintenance_work_mem: "64MB"
      checkpoint_completion_target: "0.9"
      wal_buffers: "16MB"
      default_statistics_target: "100"
      random_page_cost: "1.1"  # SSD 최적화
      
      # 복제 설정
      hot_standby: "on"
      max_wal_senders: "10"
      max_replication_slots: "10"
      
  bootstrap:
    initdb:
      database: tickets
      owner: app
      secret:
        name: postgres-credentials
        
  storage:
    storageClass: "fast-ssd"
    size: "100Gi"
    
  monitoring:
    enabled: true
    
  backup:
    retentionPolicy: "30d"
    barmanObjectStore:
      destinationPath: "s3://flash-tickets-backups"
      s3Credentials:
        accessKeyId:
          name: backup-credentials
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: backup-credentials  
          key: SECRET_ACCESS_KEY
      wal:
        retention: "7d"
      data:
        retention: "30d"
```

#### **고급 기능 활용**
```yaml
# Connection Pooling
apiVersion: postgresql.cnpg.io/v1
kind: Pooler
metadata:
  name: flash-tickets-pooler
spec:
  cluster:
    name: flash-tickets-postgres
  instances: 3
  type: rw  # read-write
  pgbouncer:
    poolMode: transaction
    parameters:
      max_client_conn: "200"
      default_pool_size: "25"
      max_db_connections: "100"

---
# Read-only Pooler for Analytics
apiVersion: postgresql.cnpg.io/v1
kind: Pooler
metadata:
  name: flash-tickets-pooler-ro
spec:
  cluster:
    name: flash-tickets-postgres
  instances: 2
  type: ro  # read-only
  pgbouncer:
    poolMode: transaction
    parameters:
      max_client_conn: "500"
      default_pool_size: "50"
```

#### **비용 효과**
```
RDS → CNPG 비용 비교:
- RDS Multi-AZ: $800/월
- CNPG (EC2 3대): $300/월
- 비용 절감: $500/월

추가 장점:
- 세밀한 PostgreSQL 설정 제어
- Kubernetes 네이티브 통합
- 자동 백업/복구 (WAL-G)
- Connection Pooling 내장
- 읽기 전용 복제본 자동 관리

일정: 2개월
위험도: 매우 높음 ⭐⭐⭐⭐⭐
```

---

## 📊 **각 단계별 ROI 분석**

### **Phase 1: ElastiCache (즉시 실행)**
```
투자: $600/월 (7배 비용 증가)
효과: 200배 성능 향상, 대기열 없는 플래시 세일 90% 달성
ROI: 즉시 회수 (서버 다운 방지, 비즈니스 기회 확대)
리스크: 매우 낮음
추천도: ⭐⭐⭐⭐⭐ (즉시 실행 강력 권장)
```

### **Phase 2: RDS PostgreSQL (3개월 후)**
```
투자: $400/월 추가
효과: 고가용성 99.95%, 운영 자동화, 백업/복구 자동화
ROI: 6개월 후 회수 (운영 비용 절감, 장애 시간 단축)
리스크: 낮음
추천도: ⭐⭐⭐⭐
```

### **Phase 3: EKS (9개월 후)**
```
투자: $1,000/월 추가 + 인력 비용 $3,000/월
효과: 무제한 확장성, 고급 배포 전략, 마이크로서비스 지원
ROI: 12개월 후 회수 (대규모 사용자 대응, 개발 생산성 향상)
리스크: 높음 (Kubernetes 학습 곡선, 운영 복잡도)
추천도: ⭐⭐⭐ (신중한 검토 필요)
```

### **Phase 4: CNPG (15개월 후)**
```
투자: -$500/월 (비용 절감)
효과: 세밀한 DB 제어, 비용 최적화, Kubernetes 네이티브
ROI: 즉시 (비용 절감 효과)
리스크: 매우 높음 (PostgreSQL 전문 지식 필요)
추천도: ⭐⭐ (전문 팀 구성 후 고려)
```

---

## 🎯 **즉시 실행 권장사항**

### **Phase 1: ElastiCache 전환 (이번 주 실행)**

#### **실행 체크리스트**
```bash
□ 1. AWS 계정 및 VPC 설정
□ 2. ElastiCache 서브넷 그룹 생성
□ 3. 보안 그룹 설정 (6379 포트)
□ 4. ElastiCache Redis 클러스터 생성
□ 5. 연결 테스트 (개발 환경)
□ 6. 애플리케이션 설정 변경
□ 7. 프로덕션 환경 전환
□ 8. 성능 모니터링 설정
□ 9. 부하 테스트 실행
□ 10. 100만 동시 접속 검증
```

#### **예상 결과**
```
전환 전:
- 동시 처리: 1만명
- 플래시 세일: 대기열 필수
- 서버 부하: 위험 수준

전환 후:
- 동시 처리: 100만명+
- 플래시 세일: 대기열 없음
- 서버 부하: 안정적
- 목표 달성: 90% 완료! 🎉
```

---

## ⚡ **긴급 실행 가이드 (ElastiCache)**

### **1. 인프라 생성 (AWS CLI)**
```bash
# 1. VPC 보안 그룹 생성
aws ec2 create-security-group \
    --group-name flash-tickets-elasticache \
    --description "ElastiCache security group"

# 2. Redis 포트 허용
aws ec2 authorize-security-group-ingress \
    --group-name flash-tickets-elasticache \
    --protocol tcp \
    --port 6379 \
    --source-group flash-tickets-api

# 3. 서브넷 그룹 생성
aws elasticache create-cache-subnet-group \
    --cache-subnet-group-name flash-tickets-subnets \
    --cache-subnet-group-description "Flash Tickets subnets" \
    --subnet-ids subnet-xxx subnet-yyy subnet-zzz

# 4. Redis 클러스터 생성
aws elasticache create-replication-group \
    --replication-group-id flash-tickets-prod \
    --description "Flash Tickets Production Redis" \
    --num-cache-clusters 3 \
    --cache-node-type cache.r6g.large \
    --engine redis \
    --engine-version 7.0 \
    --multi-az-enabled \
    --automatic-failover-enabled \
    --cache-subnet-group-name flash-tickets-subnets \
    --security-group-ids sg-xxx \
    --at-rest-encryption-enabled \
    --transit-encryption-enabled \
    --auth-token "$(openssl rand -base64 32)"
```

### **2. 애플리케이션 코드 수정**
```python
# app/config.py
class Settings(BaseSettings):
    # Before
    # redis_url: str = "redis://redis:6379/0"
    
    # After
    redis_url: str = "rediss://flash-tickets-prod.xxx.cache.amazonaws.com:6379"
    redis_cluster_mode: bool = True
    redis_ssl: bool = True
    redis_auth_token: str = "your-auth-token"

# app/redis_client.py  
class RedisClient:
    def __init__(self):
        if settings.redis_cluster_mode:
            # ElastiCache 클러스터 모드
            self.pool = RedisCluster(
                startup_nodes=[
                    {"host": settings.redis_url.split("://")[1].split(":")[0], "port": 6379}
                ],
                decode_responses=True,
                ssl=settings.redis_ssl,
                password=settings.redis_auth_token,
                skip_full_coverage_check=True
            )
        else:
            # 기존 단일 Redis 모드
            self.pool = redis.from_url(settings.redis_url)
```

### **3. Docker Compose 수정**
```yaml
# docker-compose.yaml
services:
  api1:
    environment:
      REDIS_URL: "rediss://flash-tickets-prod.xxx.cache.amazonaws.com:6379"
      REDIS_CLUSTER_MODE: "true"
      REDIS_SSL: "true"
      REDIS_AUTH_TOKEN: "${REDIS_AUTH_TOKEN}"
  
  # Redis 컨테이너 제거!
  # redis:
  #   image: redis:7-alpine
  #   ports:
  #     - "6379:6379"
```

### **4. 검증 스크립트**
```python
# test_elasticache.py
import asyncio
import time
from app.redis_client import redis_client

async def test_performance():
    # 연결 테스트
    await redis_client.connect()
    
    # 성능 테스트
    start_time = time.time()
    
    tasks = []
    for i in range(10000):
        task = redis_client.set(f"test_key_{i}", f"test_value_{i}")
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    end_time = time.time()
    
    print(f"10,000 operations completed in {end_time - start_time:.2f} seconds")
    print(f"Operations per second: {10000 / (end_time - start_time):.0f}")

if __name__ == "__main__":
    asyncio.run(test_performance())
```

---

## 🎯 **최종 요약**

### **즉시 실행 (이번 주)**
**ElastiCache 전환으로 "대기열 없는 플래시 세일" 90% 달성**
- 비용: $600/월 추가
- 효과: 200배 성능 향상  
- 위험: 매우 낮음
- ROI: 즉시

### **중기 계획 (6개월 내)**  
**RDS 전환으로 운영 안정성 확보**
- 비용: $400/월 추가
- 효과: 고가용성, 자동화
- 위험: 낮음

### **장기 계획 (12개월 후)**
**EKS + CNPG로 완전한 클라우드 네이티브 달성**
- 비용: 총 $2,000/월 수준
- 효과: 무제한 확장성
- 위험: 높음 (전문 지식 필요)

### **성공 지표**
```
✅ 100만명 동시 접속 처리
✅ 응답 시간 50ms 이하 유지
✅ 99.99% 가용성 달성
✅ 대기열 완전 제거
✅ 플래시 세일 성공률 100%
```

**"한 번에 하나씩, 확실하게 성공하는 마이그레이션!"**

Flash Tickets을 세계 최고 수준의 플래시 세일 시스템으로 발전시키는 여정이 시작됩니다! 🚀