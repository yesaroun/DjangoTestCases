# tests/weather/test_api_router.py
"""
API Router 테스트 (Lazy 헬스체크 버전)
"""

from unittest.mock import MagicMock, patch
import time
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
    """API Router 테스트 (Lazy 헬스체크)"""

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

        # 실패 타임스탬프가 저장되어야 함
        failed_timestamp = cache.get("api:failed:scraping")
        self.assertIsNotNone(failed_timestamp)

    def test_all_providers_fail(self):
        """모든 Provider 실패 시 예외 발생"""
        # 모든 Provider 실패
        self.mock_provider_a.get_weather_forecast.side_effect = Exception("A failed")
        self.mock_provider_b.get_weather_forecast.side_effect = Exception("B failed")

        # 실행 및 검증
        with self.assertRaises(Exception) as context:
            self.router.route_request(user_id=3, request_data=self.request_data)

        self.assertIn("All providers failed", str(context.exception))

        # 모든 Provider가 실패 마킹되어야 함
        self.assertIsNotNone(cache.get("api:failed:scraping"))
        self.assertIsNotNone(cache.get("api:failed:external"))

    def test_select_provider_prefers_free(self):
        """동적 할당 시 무료 Provider 우선"""
        # 모두 정상 상태 (실패 기록 없음)
        selected = self.router._select_provider(user_id=4, request_data=self.request_data)

        # 무료인 scraping을 선택해야 함
        self.assertEqual(selected, "scraping")

    def test_select_provider_skips_failed(self):
        """실패한 Provider는 재시도 간격 전에는 스킵"""
        # scraping을 실패 상태로 마킹
        self.router._mark_provider_failed("scraping")

        selected = self.router._select_provider(user_id=5, request_data=self.request_data)

        # external을 선택해야 함
        self.assertEqual(selected, "external")

    def test_lazy_recovery_after_interval(self):
        """재시도 간격 후 Lazy 복구 시도"""
        # scraping을 실패 상태로 마킹 (과거 시점)
        past_timestamp = time.time() - 120  # 2분 전
        cache.set("api:failed:scraping", past_timestamp, timeout=3600)

        # 헬스체크 성공으로 설정
        self.mock_provider_a.health_check.return_value = True

        # Provider 선택
        selected = self.router._select_provider(user_id=6, request_data=self.request_data)

        # 복구되어 scraping 선택되어야 함
        self.assertEqual(selected, "scraping")
        self.mock_provider_a.health_check.assert_called_once()

        # 실패 기록이 삭제되어야 함
        failed_timestamp = cache.get("api:failed:scraping")
        self.assertIsNone(failed_timestamp)

    def test_lazy_recovery_fails(self):
        """Lazy 복구 시도 실패 시"""
        # scraping을 실패 상태로 마킹 (과거 시점)
        past_timestamp = time.time() - 120  # 2분 전
        cache.set("api:failed:scraping", past_timestamp, timeout=3600)

        # 헬스체크 실패로 설정
        self.mock_provider_a.health_check.return_value = False

        # Provider 선택
        selected = self.router._select_provider(user_id=7, request_data=self.request_data)

        # 여전히 external 선택
        self.assertEqual(selected, "external")
        self.mock_provider_a.health_check.assert_called_once()

        # 실패 기록이 여전히 존재 (갱신됨)
        failed_timestamp = cache.get("api:failed:scraping")
        self.assertIsNotNone(failed_timestamp)

    def test_should_retry_provider_within_interval(self):
        """재시도 간격 내에는 재시도 불가"""
        # 30초 전 실패
        recent_timestamp = time.time() - 30
        cache.set("api:failed:scraping", recent_timestamp, timeout=3600)

        should_retry = self.router._should_retry_provider("scraping")

        # 아직 1분이 안 지났으므로 False
        self.assertFalse(should_retry)

    def test_should_retry_provider_after_interval(self):
        """재시도 간격 후에는 재시도 가능"""
        # 2분 전 실패
        old_timestamp = time.time() - 120
        cache.set("api:failed:scraping", old_timestamp, timeout=3600)

        should_retry = self.router._should_retry_provider("scraping")

        # 1분이 지났으므로 True
        self.assertTrue(should_retry)

    def test_success_clears_failed_status(self):
        """성공 시 실패 상태 자동 삭제"""
        # 실패 상태로 시작
        self.router._mark_provider_failed("scraping")
        self.assertIsNotNone(cache.get("api:failed:scraping"))

        # 성공 응답 설정
        mock_response = WeatherForecastResponseSchema(
            temperature=20.0,
            humidity=60,
            condition="sunny",
            forecast_date="2024-01-15"
        )
        self.mock_provider_a.get_weather_forecast.return_value = mock_response

        # 캐시에 scraping 할당
        cache.set("routing:8", "scraping", timeout=3600)

        # 실행
        self.router.route_request(user_id=8, request_data=self.request_data)

        # 실패 기록이 삭제되어야 함
        failed_timestamp = cache.get("api:failed:scraping")
        self.assertIsNone(failed_timestamp)

    def test_metrics_increment(self):
        """메트릭 증가 테스트"""
        # 성공 메트릭 증가
        self.router._increment_success_metric("scraping")
        self.router._increment_success_metric("scraping")

        # 실패 메트릭 증가
        self.router._increment_failure_metric("scraping")

        # Redis에서 직접 확인
        success_count = cache.get("api:metrics:scraping:success")
        failure_count = cache.get("api:metrics:scraping:failure")

        self.assertEqual(success_count, 2)
        self.assertEqual(failure_count, 1)
