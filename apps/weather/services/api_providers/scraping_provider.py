# apps/weather/services/api_providers/scraping_provider.py
"""
스크래핑 기반 날씨 API Provider (A API)

특징:
- 직접 구현한 웹 스크래핑 로직
- 비용: 무료
- 안정성: 상대적으로 낮음
"""

import requests
import logging
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    WeatherAPIResponseSchema,
)

logger = logging.getLogger(__name__)


class ScrapingWeatherProvider:
    """
    스크래핑 기반 날씨 API Provider

    기존 WeatherAPIHelper를 Provider 인터페이스로 래핑
    """

    def __init__(self, api_key: str, timeout: int = 10):
        """
        Args:
            api_key: API 키
            timeout: 요청 타임아웃 (초)
        """
        self.api_key = api_key
        self.base_url = "https://api.weather-service.com"
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "scraping"

    @property
    def cost_per_request(self) -> float:
        return 0.0  # 무료

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        스크래핑 방식으로 날씨 예보 조회

        Args:
            request_data: 날씨 예보 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            requests.RequestException: 네트워크 오류
            Exception: API 오류
        """
        endpoint = f"{self.base_url}/v1/forecast"

        try:
            # Pydantic 스키마를 API 바디로 변환
            body_data = request_data.to_api_body()

            logger.info(
                f"[ScrapingProvider] Calling API: {endpoint} for city={request_data.location.city}"
            )

            response = requests.post(
                endpoint, json=body_data, timeout=self.timeout
            )
            response.raise_for_status()

            # 전체 응답을 스키마로 검증
            api_response = WeatherAPIResponseSchema(**response.json())

            # 에러 응답 처리
            if api_response.is_error:
                logger.error(
                    f"[ScrapingProvider] API Error: {api_response.error_message}"
                )
                raise Exception(f"API Error: {api_response.error_message}")

            # 성공 시 데이터만 반환
            if api_response.data is None:
                raise Exception("API returned success but no data")

            logger.info("[ScrapingProvider] API call successful")
            return api_response.data

        except requests.Timeout:
            logger.error("[ScrapingProvider] Request timeout")
            raise Exception("Scraping API timeout")
        except requests.RequestException as e:
            logger.error(f"[ScrapingProvider] Network error: {e}")
            raise Exception(f"Scraping API network error: {e}")
        except Exception as e:
            logger.error(f"[ScrapingProvider] Unexpected error: {e}")
            raise

    def health_check(self) -> bool:
        """
        헬스체크: 실제 API 엔드포인트에 ping 요청

        Returns:
            bool: True=정상, False=장애
        """
        try:
            health_endpoint = f"{self.base_url}/health"
            response = requests.get(health_endpoint, timeout=5)
            is_healthy = response.status_code == 200

            logger.info(
                f"[ScrapingProvider] Health check: {'OK' if is_healthy else 'FAIL'}"
            )
            return is_healthy

        except Exception as e:
            logger.warning(f"[ScrapingProvider] Health check failed: {e}")
            return False
