# tests/weather/test_providers.py
"""
API Provider 테스트
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.weather.services.api_providers.scraping_provider import ScrapingWeatherProvider
from apps.weather.services.api_providers.external_provider import ExternalWeatherProvider
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    LocationSchema,
    DateRangeSchema,
    ForecastOptionsSchema,
)


class TestScrapingProvider(TestCase):
    """스크래핑 Provider 테스트"""

    def setUp(self):
        self.provider = ScrapingWeatherProvider(api_key="test-key")

    def test_provider_metadata(self):
        """Provider 메타데이터 확인"""
        self.assertEqual(self.provider.provider_name, "scraping")
        self.assertEqual(self.provider.cost_per_request, 0.0)

    @patch("apps.weather.services.api_providers.scraping_provider.requests.post")
    def test_get_weather_forecast_success(self, mock_post):
        """날씨 예보 조회 성공 케이스"""
        # Mock 응답 설정
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "temperature": 20.5,
                "humidity": 60,
                "condition": "sunny",
                "forecast_date": "2024-01-15"
            },
            "error": None
        }
        mock_post.return_value = mock_response

        # 요청 데이터 생성
        request_data = WeatherForecastRequestSchema(
            api_key="test-key",
            location=LocationSchema(city="Seoul", country_code="KR"),
            date_range=DateRangeSchema(start="2024-01-01", end="2024-01-31"),
            options=ForecastOptionsSchema(include_hourly="N", units="metric"),
        )

        # 실행
        response = self.provider.get_weather_forecast(request_data)

        # 검증
        self.assertIsInstance(response, WeatherForecastResponseSchema)
        self.assertEqual(response.temperature, 20.5)
        mock_post.assert_called_once()

    @patch("apps.weather.services.api_providers.scraping_provider.requests.get")
    def test_health_check_success(self, mock_get):
        """헬스체크 성공 케이스"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.provider.health_check()

        self.assertTrue(result)

    @patch("apps.weather.services.api_providers.scraping_provider.requests.get")
    def test_health_check_failure(self, mock_get):
        """헬스체크 실패 케이스"""
        mock_get.side_effect = Exception("Connection error")

        result = self.provider.health_check()

        self.assertFalse(result)


class TestExternalProvider(TestCase):
    """외부 유료 Provider 테스트"""

    def setUp(self):
        self.provider = ExternalWeatherProvider(api_key="external-key")

    def test_provider_metadata(self):
        """Provider 메타데이터 확인"""
        self.assertEqual(self.provider.provider_name, "external")
        self.assertEqual(self.provider.cost_per_request, 0.01)

    @patch("apps.weather.services.api_providers.external_provider.requests.post")
    def test_get_weather_forecast_success(self, mock_post):
        """날씨 예보 조회 성공 케이스"""
        # Mock 응답 설정
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "temperature": 15.0,
                "humidity": 70,
                "condition": "cloudy",
                "forecast_date": "2024-01-20"
            },
            "error": None
        }
        mock_post.return_value = mock_response

        # 요청 데이터 생성
        request_data = WeatherForecastRequestSchema(
            api_key="external-key",
            location=LocationSchema(city="Busan", country_code="KR"),
            date_range=DateRangeSchema(start="2024-01-01", end="2024-01-31"),
            options=ForecastOptionsSchema(include_hourly="Y", units="metric"),
        )

        # 실행
        response = self.provider.get_weather_forecast(request_data)

        # 검증
        self.assertIsInstance(response, WeatherForecastResponseSchema)
        self.assertEqual(response.temperature, 15.0)
        mock_post.assert_called_once()
