# 외부 API 문제

## 문제점 분석

현재 외부 API Helper 구조에는 세 가지 주요 문제가 있습니다

### 하드코딩된 API 요청 데이터

```python
class APIHelper:
    def get_tax_report_detail(self, auth_method: str, name: str, ...):
        body_data = {
            "loginMethod": login_method,
            "resNm": name,
            "resNo": birth_date,
            # ... 20개 이상의 하드코딩된 필드
            "inqrDtStrt": "20230101",  # 하드코딩된 값
            "inqrDtEnd": "20231231",  # 하드코딩된 값
        }
```

**문제점:**

- 데이터 구조가 메서드 내부에 숨겨져 있음
- 타입 검증이 런타임에만 가능
- 테스트 시 데이터 구조 파악이 어려움

### Dependency Injection 부재

```python
class HomeTaxDataFetchView(APIView):
    def perform_post_logic(self, request, *args, **kwargs) -> Response:
        # View 내부에서 직접 인스턴스화
        api_helper: WorkerAPIHelper = WorkerAPIHelper(
            EXTERNAL_API_USER_ID, EXTERNAL_API_KEY
        )

        # ... 비즈니스 로직
        api_helper.get_tax_report_data(...)
```

**문제점:**

- 테스트 시 실제 API를 호출하거나 복잡한 패치 필요
- Mock 객체 주입이 어려움
- 위 문제들이 가장 큰 문제로 느껴지는 부분입니다.

### 응답 데이터 검증 부재

```python
async def download_year_end_reconciliation_pdf(self, ...):
    response_json = await self.async_api_call(...)

    # 타입 검증 없이 딕셔너리 접근
    common = response_json["common"]  # KeyError 가능
    err_yn = common["errYn"]  # 타입 불명확
    err_msg = common["errMsg"]  # 필드 누락 시 에러

    if err_yn == "Y":  # 문자열 비교로 에러 처리
        logger.error(f"{err_msg}")
        return None
```

**문제점:**

- 응답 데이터 구조 파악이 어려움
- 타입 검증 없어 잘못된 데이터 타입 처리 불가
- 에러 응답 처리 로직이 분산됨 (if문 반복)

---

## 개선 방향

### Pydantic 스키마 도입 (요청 + 응답)

- **요청 데이터**: API 요청 바디를 Pydantic 모델로 정의
- **응답 데이터**: API 응답 전체를 Pydantic 모델로 검증
- 타입 안정성과 런타임 검증 확보
- 명시적인 데이터 구조 문서화

### Dependency Injection 패턴 적용

- 테스트 시 Mock 객체 주입 용이

---

## 추상화된 예시 프로젝트 구조

실제 프로젝트의 세금 환급 API를 **날씨 정보 조회 API**로 추상화합니다.

```
demo_project/
├── apps/
│   └── weather/                           # 실제: apps/refund/
│       ├── services/
│       │   └── weather_api/               # 실제: external_api/
│       │       ├── api_helper.py          # 외부 API 호출 클래스
│       │       └── schemas.py             # Pydantic 스키마 (NEW)
│       └── schemas/
│           └── weather.py                 # 비즈니스 로직용 스키마
├── api/
│   └── v1/
│       └── weather/
│           └── views/
│               └── weather_fetch_views.py
└── tests/
    └── weather/
        └── test_weather_fetch_views.py
```

---

## Before/After 비교

### 실제 구현 파일 위치

이 프로젝트에는 Before/After 버전이 모두 실제로 구현되어 있습니다:

```
apps/weather/services/weather_api/
├── api_helper.py              # WeatherAPIHelperLegacy (Before)
│                              # WeatherAPIHelper (After)
├── schemas.py                 # Pydantic 스키마 정의
└── __init__.py

api/v1/weather/views/
└── weather_fetch_views.py     # WeatherForecastViewLegacy (Before)
                               # WeatherForecastView (After)
```

### 핵심 개선 사항

#### 1. 요청 데이터 처리

**Before (하드코딩)**

- 요청 바디가 메서드 내부에 숨겨져 있음
- 매개변수로만 데이터 전달 (`city`, `country_code`, ...)
- 타입 검증 없음, 런타임 에러 위험

**After (Pydantic 스키마)**

- 명시적인 스키마로 데이터 구조 정의 (`WeatherForecastRequestSchema`)
- 자동 타입 검증 및 변환
- IDE 자동완성 지원

참조: `apps/weather/services/weather_api/schemas.py`

#### 2. 응답 데이터 처리

**Before (dict)**

```python
weather_data = api_helper.get_weather_forecast(...)
temperature = weather_data["temperature"]  # KeyError 위험
```

**After (Pydantic 스키마)**

```python
weather_data: WeatherForecastResponseSchema = helper.get_weather_forecast(...)
temperature = weather_data.temperature  # 타입 안전, IDE 지원
```

참조: `apps/weather/services/weather_api/schemas.py:62-68`

#### 3. 에러 처리

**Before (분산된 if문)**

```python
if response_json.get("error"):
    error_message = response_json["error"]["message"]  # 구조 불명확
```

**After (스키마 속성)**

```python
if api_response.is_error:
    raise Exception(f"API Error: {api_response.error_message}")
```

참조: `apps/weather/services/weather_api/schemas.py:80-94`

#### 4. Dependency Injection

**Before (직접 인스턴스화)**

```python
class WeatherForecastView(APIView):
    def post(self, request):
        api_helper = WeatherAPIHelper(api_key=settings.KEY)  # 강결합
        weather_data = api_helper.get_weather_forecast(...)
```

**After (생성자 주입)**

```python
class WeatherForecastView(APIView):
    def __init__(self, weather_api_client: IWeatherAPIClient = None, **kwargs):
        self.weather_api_client = weather_api_client or WeatherAPIHelper(...)

    def post(self, request):
        weather_data = self.weather_api_client.get_weather_forecast(...)
```

참조: `api/v1/weather/views/weather_fetch_views.py:74-134`

### 테스트 코드 차이

**Before: 복잡한 패치**

- Mock 클래스와 인스턴스를 모두 설정

**After: 간단한 생성자 주입**

```python
mock_client = MagicMock()
view = WeatherForecastView(weather_api_client=mock_client)
```

- Mock 객체를 직접 주입
- View 내부 구현 변경에 영향 없음

참조: `tests/weather/test_weather_fetch_views.py`

---

## 현재 상황

현재 외부 API를 사용하는 코드가 너무 방대하다보니 업데이트가 진행되는 경우에 위에 케이스처럼 전체적으로 도입을 하고 있습니다.

그리고 별개로 전체적인 프로젝트는 시리얼라이저를 지양하고 Pydantic을 도입하고 있습니다.

