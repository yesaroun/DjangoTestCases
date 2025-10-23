# tests/weather/test_api_router.py
"""
API Router 테스트
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.core.cache import cache

from apps.weather.services.api_router import APIRouter
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
    LocationSchema,
    DateRangeSchema,
    ForecastOptionsSchema,
)


class TestAPIRouter(TestCase):
    """API Router 테스트"""

    def setUp(self):
        # 각 테스트마다 캐시 초기화
        cache.clear()

        # Mock Provider 생성
        self.mock_provider_a = MagicMock()
        self.mock_provider_a.provider_name = "scraping"
        self.mock_provider_a.cost_per_request = 0.0

        self.mock_provider_b = MagicMock()
        self.mock_provider_b.provider_name = "external"
        self.mock_provider_b.cost_per_request = 0.01

        # Router 생성
        self.router = APIRouter(providers=[self.mock_provider_a, self.mock_provider_b])

        # 테스트용 요청 데이터
        self.request_data = WeatherForecastRequestSchema(
            api_key="test-key",
            location=LocationSchema(city="Seoul", country_code="KR"),
            date_range=DateRangeSchema(start="2024-01-01", end="2024-01-31"),
            options=ForecastOptionsSchema(include_hourly="N", units="metric"),
        )

    def tearDown(self):
        cache.clear()

    def test_route_request_cache_miss_success(self):
        """캐시 미스 시 동적 할당 및 성공"""
        # Mock 응답 설정
        mock_response = WeatherForecastResponseSchema(
            temperature=20.0,
            humidity=60,
            condition="sunny",
            forecast_date="2024-01-15"
        )
        self.mock_provider_a.get_weather_forecast.return_value = mock_response

        # 실행
        response = self.router.route_request(user_id=1, request_data=self.request_data)

        # 검증
        self.assertEqual(response.temperature, 20.0)
        self.mock_provider_a.get_weather_forecast.assert_called_once()

        # 캐시 확인
        cached_provider = cache.get("routing:1")
        self.assertEqual(cached_provider, "scraping")

    def test_route_request_cache_hit(self):
        """캐시 히트 시 캐시된 Provider 사용"""
        # 캐시에 미리 저장
        cache.set("routing:1", "external", timeout=3600)

        # Mock 응답 설정
        mock_response = WeatherForecastResponseSchema(
            temperature=15.0,
            humidity=70,
            condition="cloudy",
            forecast_date="2024-01-20"
        )
        self.mock_provider_b.get_weather_forecast.return_value = mock_response

        # 실행
        response = self.router.route_request(user_id=1, request_data=self.request_data)

        # 검증: external Provider가 호출되어야 함
        self.assertEqual(response.temperature, 15.0)
        self.mock_provider_b.get_weather_forecast.assert_called_once()
        self.mock_provider_a.get_weather_forecast.assert_not_called()

    def test_fallback_on_primary_failure(self):
        """Primary Provider 실패 시 Fallback"""
        # Primary 실패, Fallback 성공
        self.mock_provider_a.get_weather_forecast.side_effect = Exception("API Error")

        mock_fallback_response = WeatherForecastResponseSchema(
            temperature=18.0,
            humidity=65,
            condition="rainy",
            forecast_date="2024-01-25"
        )
        self.mock_provider_b.get_weather_forecast.return_value = mock_fallback_response

        # 실행
        response = self.router.route_request(user_id=2, request_data=self.request_data)

        # 검증
        self.assertEqual(response.temperature, 18.0)
        self.mock_provider_a.get_weather_forecast.assert_called_once()
        self.mock_provider_b.get_weather_forecast.assert_called_once()

        # 캐시가 fallback Provider로 업데이트되어야 함
        cached_provider = cache.get("routing:2")
        self.assertEqual(cached_provider, "external")

    def test_all_providers_fail(self):
        """모든 Provider 실패 시 예외 발생"""
        # 모든 Provider 실패
        self.mock_provider_a.get_weather_forecast.side_effect = Exception("A failed")
        self.mock_provider_b.get_weather_forecast.side_effect = Exception("B failed")

        # 실행 및 검증
        with self.assertRaises(Exception) as context:
            self.router.route_request(user_id=3, request_data=self.request_data)

        self.assertIn("All providers failed", str(context.exception))

    def test_select_provider_prefers_free(self):
        """동적 할당 시 무료 Provider 우선"""
        # 모두 healthy 상태로 설정
        import json
        cache.set("api:health:scraping", json.dumps({"status": "healthy"}))
        cache.set("api:health:external", json.dumps({"status": "healthy"}))

        selected = self.router._select_provider(user_id=4)

        # 무료인 scraping을 선택해야 함
        self.assertEqual(selected, "scraping")

    def test_select_provider_fallback_when_primary_unhealthy(self):
        """Primary가 unhealthy면 Fallback 선택"""
        # scraping을 unhealthy로 설정
        import json
        cache.set("api:health:scraping", json.dumps({"status": "unhealthy"}))
        cache.set("api:health:external", json.dumps({"status": "healthy"}))

        selected = self.router._select_provider(user_id=5)

        # external을 선택해야 함
        self.assertEqual(selected, "external")
