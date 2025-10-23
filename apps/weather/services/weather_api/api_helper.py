# apps/weather/services/weather_api/api_helper.py
import requests
from typing import Optional, Protocol
from .schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    WeatherAPIResponseSchema,
    LocationSchema,
    DateRangeSchema,
    ForecastOptionsSchema,
)


# ============================================================
# Before: 하드코딩 방식 (나쁜 예시)
# ============================================================


class WeatherAPIHelperLegacy:
    """
    외부 날씨 API를 호출하는 헬퍼 클래스 - 레거시 버전

    문제점:
    1. 요청 바디가 메서드 내부에 하드코딩
    2. 필수/선택 필드가 매개변수로만 표현됨
    3. 데이터 검증이 API 호출 후에야 가능
    4. 응답을 dict로 반환 - 타입 검증 없음
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.weather-service.com"

    def get_weather_forecast(
        self,
        city: str,
        country_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_hourly: bool = False,
        units: str = "metric",
    ) -> dict:
        """
        날씨 예보 조회

        문제점:
        1. 요청 바디가 메서드 내부에 하드코딩
        2. 필수/선택 필드가 매개변수로만 표현됨
        3. 데이터 검증이 API 호출 후에야 가능
        """
        endpoint = f"{self.base_url}/v1/forecast"

        # 하드코딩된 요청 바디
        body_data = {
            "apiKey": self.api_key,
            "location": {
                "city": city,
                "countryCode": country_code,
            },
            "dateRange": {
                "start": start_date or "2023-01-01",  # 기본값 하드코딩
                "end": end_date or "2023-12-31",
            },
            "options": {
                "includeHourly": "Y" if include_hourly else "N",
                "units": units,
                "language": "ko",  # 하드코딩
                "timezone": "Asia/Seoul",  # 하드코딩
            },
            "format": "json",  # 하드코딩
        }

        response = requests.post(endpoint, json=body_data)
        # 응답을 dict로 반환 - 타입 검증 없음
        return response.json()


# ============================================================
# After: 개선된 방식 (좋은 예시)
# ============================================================


class IWeatherAPIClient(Protocol):
    """날씨 API 클라이언트 인터페이스"""

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema: ...


class WeatherAPIHelper:
    """
    개선된 날씨 API 헬퍼

    장점:
    1. Pydantic 스키마를 통한 타입 안정성
    2. 명시적인 데이터 구조
    3. 자동 검증
    4. 응답 데이터도 스키마로 검증
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.weather-service.com"

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        날씨 예보 조회 - Pydantic 스키마 사용

        개선점:
        1. 요청 데이터가 스키마로 명시적 정의
        2. 응답 데이터도 스키마로 검증
        3. 런타임 검증 자동화
        4. 타입 힌팅으로 IDE 지원
        """
        endpoint = f"{self.base_url}/v1/forecast"

        # Pydantic 스키마를 API 바디로 변환
        body_data = request_data.to_api_body()

        response = requests.post(endpoint, json=body_data)
        response.raise_for_status()

        # 전체 응답을 스키마로 검증
        api_response = WeatherAPIResponseSchema(**response.json())

        # 에러 응답 처리
        if api_response.is_error:
            raise Exception(f"API Error: {api_response.error_message}")

        # 성공 시 데이터만 반환
        if api_response.data is None:
            raise Exception("API returned success but no data")

        return api_response.data

    @classmethod
    def create_request(
        cls,
        api_key: str,
        city: str,
        country_code: str,
        start_date: str,
        end_date: str,
        include_hourly: bool = False,
        units: str = "metric",
    ) -> WeatherForecastRequestSchema:
        """
        편의 메서드: 요청 스키마 생성

        장점: View에서 스키마 생성 로직 재사용 가능
        """
        return WeatherForecastRequestSchema(
            api_key=api_key,
            location=LocationSchema(city=city, country_code=country_code),
            date_range=DateRangeSchema(start=start_date, end=end_date),
            options=ForecastOptionsSchema(
                include_hourly="Y" if include_hourly else "N", units=units
            ),
        )
