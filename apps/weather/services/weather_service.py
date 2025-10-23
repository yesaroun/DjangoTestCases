# apps/weather/services/weather_service.py
"""
날씨 서비스 레이어

책임:
- 비즈니스 로직 처리
- API Helper 조율
- 요청/응답 변환
"""
from typing import Protocol
from django.conf import settings

from .weather_api.api_helper import WeatherAPIHelper, IWeatherAPIClient
from .weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    LocationSchema,
    DateRangeSchema,
    ForecastOptionsSchema,
)


# ============================================================
# Before: 서비스 레이어 없음 (나쁜 예시)
# ============================================================
# 레거시 버전에서는 서비스 레이어가 없고,
# View가 직접 API Helper를 호출함


# ============================================================
# After: 서비스 레이어 추가 (좋은 예시)
# ============================================================


class IWeatherService(Protocol):
    """
    날씨 서비스 인터페이스

    장점:
    - View가 구체 구현이 아닌 인터페이스에 의존
    - 테스트 시 Mock 서비스 주입 용이
    """

    def get_weather_forecast(
        self,
        city: str,
        country_code: str,
        start_date: str,
        end_date: str,
        include_hourly: bool = False,
        units: str = "metric",
    ) -> WeatherForecastResponseSchema: ...


class WeatherService:
    """
    날씨 서비스 구현체

    책임:
    1. View로부터 받은 단순 파라미터를 Pydantic 스키마로 변환
    2. API Helper를 통해 외부 API 호출
    3. 비즈니스 로직 처리 (필요시)
    4. 응답 반환

    장점:
    - View는 얇게 유지 (HTTP 요청/응답 처리만)
    - 비즈니스 로직이 서비스 레이어에 집중
    - DI를 통해 테스트 용이
    """

    def __init__(self, api_client: IWeatherAPIClient = None):
        """
        생성자 주입 (Dependency Injection)

        Args:
            api_client: API 클라이언트 (기본값: WeatherAPIHelper)
        """
        self.api_client = api_client or WeatherAPIHelper(
            api_key=getattr(settings, "WEATHER_API_KEY", "default-api-key")
        )

    def get_weather_forecast(
        self,
        city: str,
        country_code: str,
        start_date: str,
        end_date: str,
        include_hourly: bool = False,
        units: str = "metric",
    ) -> WeatherForecastResponseSchema:
        """
        날씨 예보 조회

        Args:
            city: 도시명
            country_code: 국가 코드 (2자)
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            include_hourly: 시간별 예보 포함 여부
            units: 단위 (metric/imperial)

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            ValidationError: 요청 데이터 검증 실패
            Exception: API 호출 실패
        """
        request_schema = WeatherForecastRequestSchema(
            api_key=getattr(settings, "WEATHER_API_KEY", "default-api-key"),
            location=LocationSchema(
                city=city,
                country_code=country_code,
            ),
            date_range=DateRangeSchema(
                start=start_date,
                end=end_date,
            ),
            options=ForecastOptionsSchema(
                include_hourly="Y" if include_hourly else "N",
                units=units,
            ),
        )

        response = self.api_client.get_weather_forecast(request_data=request_schema)

        # 비즈니스 로직 생략

        return response


# ============================================================
# Multi-Provider Router 버전 (NEW)
# ============================================================


class WeatherServiceWithRouter:
    """
    멀티 API Provider 라우팅을 지원하는 날씨 서비스

    기존 WeatherService를 확장하여:
    - 여러 API Provider 중 동적으로 선택
    - 장애 발생 시 자동 폴백
    - Redis 캐싱을 통한 성능 향상
    - 자동 복구 지원

    차이점:
    - user_id 파라미터 필수 (라우팅에 사용)
    - api_router를 통한 Provider 선택
    """

    def __init__(self, api_router=None):
        """
        생성자 주입 (Dependency Injection)

        Args:
            api_router: API Router 인스턴스 (기본값: 자동 생성)
        """
        if api_router is None:
            from .api_router import get_api_router
            self.api_router = get_api_router()
        else:
            self.api_router = api_router

    def get_weather_forecast(
        self,
        user_id: int,
        city: str,
        country_code: str,
        start_date: str,
        end_date: str,
        include_hourly: bool = False,
        units: str = "metric",
    ) -> WeatherForecastResponseSchema:
        """
        날씨 예보 조회 (멀티 Provider 지원)

        Args:
            user_id: 사용자 ID (라우팅에 사용)
            city: 도시명
            country_code: 국가 코드 (2자)
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            include_hourly: 시간별 예보 포함 여부
            units: 단위 (metric/imperial)

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            ValidationError: 요청 데이터 검증 실패
            Exception: 모든 API 실패
        """
        # 요청 스키마 생성
        request_schema = WeatherForecastRequestSchema(
            api_key=getattr(settings, "WEATHER_API_KEY", "default-api-key"),
            location=LocationSchema(
                city=city,
                country_code=country_code,
            ),
            date_range=DateRangeSchema(
                start=start_date,
                end=end_date,
            ),
            options=ForecastOptionsSchema(
                include_hourly="Y" if include_hourly else "N",
                units=units,
            ),
        )

        # API Router를 통해 호출 (자동 라우팅 및 폴백)
        response = self.api_router.route_request(user_id, request_schema)

        # 비즈니스 로직 생략

        return response


# 전역 인스턴스 (싱글톤 패턴)
_weather_service_instance = None
_weather_service_with_router_instance = None


def get_weather_service(api_client: IWeatherAPIClient = None) -> WeatherService:
    """
    날씨 서비스 인스턴스 반환 (팩토리 함수)

    장점:
    - View에서 직접 인스턴스화하지 않아도 됨
    - 테스트 시 Mock 서비스 주입 가능
    - 필요시 싱글톤 패턴 적용 가능

    Args:
        api_client: API 클라이언트 (테스트용)

    Returns:
        WeatherService 인스턴스
    """
    global _weather_service_instance

    # 테스트나 특수한 경우에만 새 인스턴스 생성
    if api_client is not None:
        return WeatherService(api_client=api_client)

    # 싱글톤 사용
    if _weather_service_instance is None:
        _weather_service_instance = WeatherService()

    return _weather_service_instance


def get_weather_service_with_router(api_router=None) -> WeatherServiceWithRouter:
    """
    멀티 Provider 라우팅을 지원하는 날씨 서비스 인스턴스 반환

    Args:
        api_router: API Router 인스턴스 (테스트용)

    Returns:
        WeatherServiceWithRouter 인스턴스
    """
    global _weather_service_with_router_instance

    # 테스트나 특수한 경우에만 새 인스턴스 생성
    if api_router is not None:
        return WeatherServiceWithRouter(api_router=api_router)

    # 싱글톤 사용
    if _weather_service_with_router_instance is None:
        _weather_service_with_router_instance = WeatherServiceWithRouter()

    return _weather_service_with_router_instance
