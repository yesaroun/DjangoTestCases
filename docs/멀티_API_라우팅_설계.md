# 멀티 API Provider 라우팅 시스템 설계

## 문제 정의

### 상황
동일한 기능을 제공하는 두 개의 서로 다른 API가 있습니다:

- **A API (스크래핑 기반)**
  - 직접 구현한 웹 스크래핑 로직
  - 비용: 무료
  - 안정성: 상대적으로 낮음 (웹사이트 구조 변경에 취약)

- **B API (외부 유료 서비스)**
  - 외부 업체에서 제공하는 안정적인 API
  - 비용: 사용량에 따른 과금
  - 안정성: 높음

### 해결하고자 하는 문제

1. **비용 최적화**: 가능한 한 무료 A API를 사용하되, 필요시 B API로 전환
2. **고가용성**: A API 장애 시 자동으로 B API로 폴백
3. **동적 부하 분산**: 사용자별로 동적으로 API 할당 (부하/비용 기준)
4. **자동 복구**: 장애가 해결되면 자동으로 원래 API로 복귀

### 요구사항

✅ **동적 할당**: 부하나 비용을 고려하여 실시간으로 API 선택
✅ **즉시 폴백**: API 호출 실패 시 즉시 다른 API로 재시도
✅ **Redis 캐싱**: 유저별 라우팅 정보를 캐시하여 성능 향상
✅ **자동 복구**: 헬스체크를 통해 API 상태 모니터링 및 자동 복귀

---

## 아키텍처 설계

### 전체 구조

```
┌─────────────┐
│   Request   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ WeatherService  │
└────────┬────────┘
         │
         ▼
┌──────────────────┐         ┌─────────────┐
│   API Router     │◄────────┤    Redis    │
│                  │         │ (Routing    │
│ - 유저별 할당    │         │  Cache)     │
│ - 폴백 로직      │         └─────────────┘
│ - 헬스체크 참조  │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│ A API  │ │ B API  │
│Provider│ │Provider│
└────────┘ └────────┘
    ▲         ▲
    │         │
    └────┬────┘
         │
┌────────────────┐
│ Health Checker │ (주기적 실행)
└────────────────┘
```

### 핵심 컴포넌트

#### 1. API Provider 인터페이스
각 API(A, B)를 추상화하는 공통 인터페이스

```python
class IWeatherAPIProvider(Protocol):
    """날씨 API Provider 인터페이스"""

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """날씨 예보 조회"""
        ...

    def health_check(self) -> bool:
        """헬스체크"""
        ...

    @property
    def provider_name(self) -> str:
        """Provider 이름"""
        ...

    @property
    def cost_per_request(self) -> float:
        """요청당 비용"""
        ...
```

#### 2. API Router
유저별 API 할당 및 폴백 처리

```python
class APIRouter:
    """
    API 라우팅 및 폴백 처리

    책임:
    1. 유저별 API 선택 (동적 할당)
    2. 실패 시 즉시 폴백
    3. Redis 캐싱
    """

    def route_request(
        self,
        user_id: int,
        request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        요청 라우팅

        1. Redis에서 유저 라우팅 캐시 조회
        2. 캐시 없으면 동적 할당
        3. Primary API 호출
        4. 실패 시 Fallback API 호출
        """
        ...
```

#### 3. Health Checker
주기적으로 각 API 상태 확인

```python
class HealthChecker:
    """
    API 헬스체크

    주기적으로 실행하여:
    1. 각 API 상태 확인
    2. Redis에 상태 저장
    3. 장애 복구 감지
    """

    def check_all_providers(self) -> Dict[str, bool]:
        """모든 Provider 헬스체크"""
        ...

    def update_routing_on_recovery(self, provider_name: str):
        """복구 감지 시 라우팅 업데이트"""
        ...
```

---

## Redis 설계

### 키 구조

```
# 유저별 라우팅 정보 (1시간 TTL)
weather:routing:{user_id} → "A" or "B"

# API 헬스 상태
weather:api:health:A → {"status": "healthy", "last_check": "2024-10-24T10:30:00", "last_error": null}
weather:api:health:B → {"status": "healthy", "last_check": "2024-10-24T10:30:00", "last_error": null}

# API 사용 메트릭 (선택적)
weather:api:metrics:A → {"success": 1000, "failure": 5, "last_hour_requests": 120}
weather:api:metrics:B → {"success": 950, "failure": 2, "last_hour_requests": 80}

# 전역 설정
weather:config:allocation_ratio → {"A": 0.8, "B": 0.2}  # A API 80%, B API 20%
```

### 캐싱 전략

1. **유저 라우팅 캐시**: 1시간 TTL
   - DB 조회 없이 빠른 라우팅 결정
   - 장애 복구 시 자동 만료로 재할당

2. **헬스 상태 캐시**: 무기한 (수동 업데이트)
   - Health Checker가 주기적으로 갱신
   - 장애 감지 시 즉시 업데이트

3. **메트릭 캐시**: 1시간 TTL
   - 부하 기반 동적 할당에 활용

---

## 동작 흐름

### 정상 케이스

```
1. 유저 요청 → WeatherService
2. APIRouter.route_request(user_id, request_data)
3. Redis 조회: weather:routing:{user_id}
   - 캐시 HIT → "A" 반환
   - 캐시 MISS → 동적 할당 (부하/비용 기준) → "A" 할당 → Redis 저장 (1시간 TTL)
4. A API Provider 호출
5. 성공 → 결과 반환
```

### 폴백 케이스

```
1. 유저 요청 → WeatherService
2. APIRouter.route_request(user_id, request_data)
3. Redis에서 "A" 할당 확인
4. A API Provider 호출
5. 실패 (타임아웃, 5xx 에러 등)
6. 즉시 B API Provider 호출 (폴백)
7. B API 성공 → 결과 반환
8. Redis 업데이트:
   - weather:api:health:A → "unhealthy"
   - weather:routing:{user_id} → "B" (다음 요청부터 B 사용)
```

### 헬스체크 및 자동 복구

```
[Background Job - 1분마다 실행]
1. HealthChecker.check_all_providers()
2. A API 헬스체크 → 성공
3. Redis 조회: weather:api:health:A → "unhealthy"
4. 복구 감지!
5. Redis 업데이트:
   - weather:api:health:A → "healthy"
   - weather:routing:* 캐시 삭제 (다음 요청 시 재할당)
6. 다음 요청부터 자동으로 A API 사용 (비용 절감)
```

---

## 구현 계획

### Phase 1: Provider 추상화 (기반 작업)

**파일 생성:**
- `apps/weather/services/api_providers/__init__.py`
- `apps/weather/services/api_providers/base.py` - IWeatherAPIProvider 인터페이스
- `apps/weather/services/api_providers/scraping_provider.py` - A API 구현
- `apps/weather/services/api_providers/external_provider.py` - B API 구현

**내용:**
- 기존 WeatherAPIHelper를 ScrapingProvider로 변환
- ExternalProvider는 Mock으로 구현 (실제 API 없으므로)
- health_check 메서드 추가

### Phase 2: Redis 설정

**파일 수정:**
- `pyproject.toml` - redis, django-redis 의존성 추가
- `config/settings.py` - Redis 캐시 설정

**Redis 설정:**
```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

### Phase 3: API Router 구현

**파일 생성:**
- `apps/weather/services/api_router.py`

**핵심 로직:**
1. `route_request()`: 메인 라우팅 로직
2. `_select_provider()`: 동적 할당 로직
3. `_call_with_fallback()`: 폴백 처리

### Phase 4: Health Checker 구현

**파일 생성:**
- `apps/weather/services/health_checker.py`
- `apps/weather/management/commands/check_api_health.py` - Django 관리 명령어

**실행 방법:**
```bash
# 수동 실행
python manage.py check_api_health

# Cron 등록 (1분마다)
* * * * * cd /path/to/project && python manage.py check_api_health
```

### Phase 5: WeatherService 통합

**파일 수정:**
- `apps/weather/services/weather_service.py`

**변경사항:**
- 기존 api_client 대신 api_router 사용
- 라우팅 로직을 Router에 위임

### Phase 6: 테스트 작성

**파일 생성:**
- `tests/weather/test_api_router.py`
- `tests/weather/test_health_checker.py`
- `tests/weather/test_providers.py`

**테스트 시나리오:**
1. 정상 라우팅 (A → 성공)
2. 폴백 (A → 실패 → B → 성공)
3. 헬스체크 및 복구
4. 동적 할당 로직
5. Redis 캐싱

---

## 확장 가능성

### 1. Provider 추가
새로운 C API 추가 시:
- `apps/weather/services/api_providers/c_provider.py` 생성
- IWeatherAPIProvider 인터페이스 구현
- APIRouter에 등록만 하면 자동 지원

### 2. 라우팅 전략 변경
- 현재: 부하/비용 기반 동적 할당
- 확장: 지역별, 시간대별, 데이터 타입별 라우팅 가능

### 3. Circuit Breaker 패턴 추가
- 연속 실패 시 일정 시간 동안 해당 API 차단
- 점진적 복구 (Half-Open 상태)

### 4. 모니터링 및 알림
- API 사용량, 에러율 대시보드
- 장애 발생 시 Slack/이메일 알림
- 비용 추적 및 예산 알림

---
