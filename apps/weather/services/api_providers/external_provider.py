# apps/weather/services/api_providers/external_provider.py
"""
외부 유료 날씨 API Provider (B API)

특징:
- 외부 업체에서 제공하는 안정적인 API
- 비용: 사용량에 따른 과금
- 안정성: 높음
"""

import requests
import logging
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    WeatherAPIResponseSchema,
)

logger = logging.getLogger(__name__)


class ExternalWeatherProvider:
    """
    외부 유료 날씨 API Provider

    실제 외부 API가 없으므로 Mock으로 구현
    실제 사용 시 외부 API 스펙에 맞춰 수정 필요
    """

    def __init__(self, api_key: str, timeout: int = 10):
        """
        Args:
            api_key: 외부 API 키
            timeout: 요청 타임아웃 (초)
        """
        self.api_key = api_key
        self.base_url = "https://api.external-weather-service.com"
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "external"

    @property
    def cost_per_request(self) -> float:
        return 0.01  # $0.01 per request

    def get_weather_forecast(
        self, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        외부 API로 날씨 예보 조회

        Args:
            request_data: 날씨 예보 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            requests.RequestException: 네트워크 오류
            Exception: API 오류
        """
        endpoint = f"{self.base_url}/api/v2/forecast"

        try:
            # 외부 API는 다른 바디 구조를 사용할 수 있음
            body_data = self._convert_to_external_format(request_data)

            logger.info(
                f"[ExternalProvider] Calling API: {endpoint} for city={request_data.location.city}"
            )

            response = requests.post(
                endpoint,
                json=body_data,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()

            # 외부 API 응답을 내부 스키마로 변환
            api_response = self._convert_from_external_format(response.json())

            # 에러 응답 처리
            if api_response.is_error:
                logger.error(
                    f"[ExternalProvider] API Error: {api_response.error_message}"
                )
                raise Exception(f"API Error: {api_response.error_message}")

            # 성공 시 데이터만 반환
            if api_response.data is None:
                raise Exception("API returned success but no data")

            logger.info("[ExternalProvider] API call successful")
            return api_response.data

        except requests.Timeout:
            logger.error("[ExternalProvider] Request timeout")
            raise Exception("External API timeout")
        except requests.RequestException as e:
            logger.error(f"[ExternalProvider] Network error: {e}")
            raise Exception(f"External API network error: {e}")
        except Exception as e:
            logger.error(f"[ExternalProvider] Unexpected error: {e}")
            raise

    def health_check(self) -> bool:
        """
        헬스체크: 실제 API 엔드포인트에 ping 요청

        Returns:
            bool: True=정상, False=장애
        """
        try:
            health_endpoint = f"{self.base_url}/health"
            response = requests.get(
                health_endpoint,
                headers={"X-API-Key": self.api_key},
                timeout=5,
            )
            is_healthy = response.status_code == 200

            logger.info(
                f"[ExternalProvider] Health check: {'OK' if is_healthy else 'FAIL'}"
            )
            return is_healthy

        except Exception as e:
            logger.warning(f"[ExternalProvider] Health check failed: {e}")
            return False

    def _convert_to_external_format(
        self, request_data: WeatherForecastRequestSchema
    ) -> dict:
        """
        내부 스키마를 외부 API 형식으로 변환

        실제 외부 API 스펙에 맞춰 수정 필요
        """
        return {
            "query": {
                "city": request_data.location.city,
                "country": request_data.location.country_code,
            },
            "period": {
                "from": request_data.date_range.start,
                "to": request_data.date_range.end,
            },
            "settings": {
                "hourly": request_data.options.include_hourly == "Y",
                "unit_system": request_data.options.units,
            },
        }

    def _convert_from_external_format(self, external_response: dict) -> WeatherAPIResponseSchema:
        """
        외부 API 응답을 내부 스키마로 변환

        실제 외부 API 스펙에 맞춰 수정 필요
        """
        # 외부 API 응답 형식을 내부 형식으로 변환
        # 여기서는 동일한 형식이라고 가정
        return WeatherAPIResponseSchema(**external_response)
