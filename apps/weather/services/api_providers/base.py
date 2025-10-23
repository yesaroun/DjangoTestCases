# apps/weather/services/api_providers/base.py
"""
API Provider 기본 인터페이스

모든 날씨 API Provider가 구현해야 하는 공통 인터페이스 정의
"""

from typing import Protocol
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
)


class IWeatherAPIProvider(Protocol):
    """
    날씨 API Provider 인터페이스

    동일한 기능을 제공하는 여러 API를 추상화하기 위한 인터페이스
    각 Provider는 다음을 구현해야 합니다:
    - 날씨 예보 조회
    - 헬스체크
    - Provider 메타데이터 (이름, 비용)
    """

    @property
    def provider_name(self) -> str:
        """
        Provider 이름

        Returns:
            str: Provider 식별자 (예: "scraping", "external")
        """
        ...

    @property
    def cost_per_request(self) -> float:
        """
        요청당 비용 (USD)

        Returns:
            float: 요청 1회당 비용 (0.0 = 무료)
        """
        ...

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        날씨 예보 조회

        Args:
            request_data: 날씨 예보 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            Exception: API 호출 실패
        """
        ...

    def health_check(self) -> bool:
        """
        API 헬스체크

        실제 API를 호출하여 현재 정상 작동 여부 확인

        Returns:
            bool: True=정상, False=장애
        """
        ...
