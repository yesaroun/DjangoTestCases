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
3. **일관성**: 모든 사용자가 동일한 Provider 사용 (실패 상태는 글로벌)
4. **자동 복구**: 장애가 해결되면 자동으로 원래 API로 복귀

### 요구사항

✅ **동적 할당**: 비용을 고려하여 실시간으로 API 선택 (무료 우선)
✅ **즉시 폴백**: API 호출 실패 시 즉시 다른 API로 재시도
✅ **Redis 캐싱**: 글로벌 라우팅 정보를 캐시하여 성능 향상
✅ **자동 복구**: Lazy 헬스체크를 통해 API 상태 모니터링 및 자동 복귀

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
│ - 글로벌 할당    │         │  Cache)     │
│ - 폴백 로직      │         └─────────────┘
│ - Lazy 헬스체크  │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│ A API  │ │ B API  │
│Provider│ │Provider│
└────────┘ └────────┘
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
글로벌 API 할당, 폴백 처리 및 Lazy Health Check

```python
class APIRouter:
    """
    API 라우팅 및 폴백 처리

    책임:
    1. 글로벌 API 선택 (동적 할당)
    2. 실패 시 즉시 폴백
    3. Redis 캐싱
    4. Lazy Health Check (요청 시 복구 시도)
    """

    def route_request(
        self,
        user_id: int,
        request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        요청 라우팅

        1. Redis에서 글로벌 라우팅 캐시 조회
        2. 캐시 없으면 동적 할당
        3. 실패한 Provider가 있으면 Lazy 헬스체크 시도 (1분 경과 시)
        4. Primary API 호출
        5. 실패 시 Fallback API 호출

        Note: user_id는 로깅/메트릭용으로만 사용
        """
        ...

    def _try_recovery(self, provider: IWeatherAPIProvider) -> bool:
        """
        Lazy 헬스체크 - 요청 시점에 복구 시도

        1. 실패 타임스탬프 확인
        2. 1분 경과했으면 health_check() 호출
        3. 성공 시 실패 기록 삭제 및 즉시 복구
        """
        ...
```

---

## Redis 설계

### 키 구조

```
# 글로벌 라우팅 정보 (1시간 TTL)
routing:current → "scraping" or "external"

# API 실패 타임스탬프 (1시간 TTL)
api:failed:scraping → 1729732800.123  # Unix timestamp
api:failed:external → 1729732850.456

# API 사용 메트릭 (1시간 TTL)
api:metrics:scraping:success → 1000
api:metrics:scraping:failure → 5
api:metrics:external:success → 950
api:metrics:external:failure → 2
```

### 캐싱 전략

1. **글로벌 라우팅 캐시**: 1시간 TTL
   - 현재 선택된 Provider 저장 (모든 유저 공유)
   - 성공 시 캐시 저장
   - Redis 키 개수: O(1) - 유저 수와 무관

2. **실패 타임스탬프 캐시**: 1시간 TTL
   - 실패 시 현재 타임스탬프 저장
   - 재시도 간격 확인용 (1분)
   - 복구 성공 시 즉시 삭제

3. **메트릭 캐시**: 1시간 TTL
   - 성공/실패 카운트 추적
   - 모니터링 및 분석용

---

## 동작 흐름

### 정상 케이스

```
1. 유저 요청 → WeatherService
2. APIRouter.route_request(user_id, request_data)
3. Redis 조회: routing:current
   - 캐시 HIT → "scraping" 반환
   - 캐시 MISS → 동적 할당 (비용 기준) → "scraping" 할당 → Redis 저장 (1시간 TTL)
4. scraping API Provider 호출
5. 성공 → 결과 반환
```

### 폴백 케이스

```
1. 유저 요청 → WeatherService
2. APIRouter.route_request(user_id, request_data)
3. Redis에서 "scraping" 할당 확인
4. scraping API Provider 호출
5. 실패 (타임아웃, 5xx 에러 등)
6. 즉시 external API Provider 호출 (폴백)
7. external API 성공 → 결과 반환
8. Redis 업데이트:
   - api:failed:scraping → timestamp (실패 시점 기록)
   - routing:current → "external" (다음 요청부터 external 사용)
```

### Lazy 헬스체크 및 자동 복구

```
[요청 시점에 복구 시도]
1. 유저 요청 → WeatherService
2. APIRouter에서 Provider 선택 시:
   - scraping API 실패 기록 확인
   - 1분 경과 여부 확인
3. 1분 경과했으면 Lazy 헬스체크 시도
   - scraping API health_check() 호출
4. 헬스체크 성공 → 복구!
   - 실패 기록 삭제
   - scraping API 선택 (무료)
   - routing:current → "scraping" 업데이트
5. 헬스체크 실패 → 여전히 실패 상태
   - 타임스탬프 갱신
   - external API 선택 (폴백)
   - routing:current → "external" 유지
```

**장점:**
- Cron 불필요 (인프라 간소화)
- 실제 트래픽이 있을 때만 복구 시도
- 즉각적인 복구 (요청이 있을 때)

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

### Phase 4: Lazy 헬스체크 로직 (APIRouter에 통합)

**APIRouter에 추가된 메서드:**
- `_should_retry_provider()` - 재시도 가능 여부 확인 (1분 경과?)
- `_try_recovery()` - Lazy 헬스체크 시도
- `_mark_provider_failed()` - 실패 타임스탬프 저장
- `_clear_failed_timestamp()` - 복구 시 실패 기록 삭제
- `_is_provider_failed()` - 실패 상태 확인
- `_get_last_failed_timestamp()` - 마지막 실패 시간 조회

**동작 방식:**
- 요청이 올 때마다 실패한 Provider 확인
- 1분 경과했으면 자동으로 헬스체크 시도
- 1회 성공 시 즉시 복구

### Phase 5: WeatherService 통합

**파일 수정:**
- `apps/weather/services/weather_service.py`

**변경사항:**
- 기존 api_client 대신 api_router 사용
- 라우팅 로직을 Router에 위임
