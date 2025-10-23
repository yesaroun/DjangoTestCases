# tests/weather/test_health_checker.py
"""
Health Checker 테스트
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.core.cache import cache
import json

from apps.weather.services.health_checker import HealthChecker


class TestHealthChecker(TestCase):
    """Health Checker 테스트"""

    def setUp(self):
        cache.clear()

        # Mock Provider 생성
        self.mock_provider_a = MagicMock()
        self.mock_provider_a.provider_name = "scraping"
        self.mock_provider_a.health_check.return_value = True

        self.mock_provider_b = MagicMock()
        self.mock_provider_b.provider_name = "external"
        self.mock_provider_b.health_check.return_value = True

        # Health Checker 생성
        self.checker = HealthChecker(providers=[self.mock_provider_a, self.mock_provider_b])

    def tearDown(self):
        cache.clear()

    def test_check_all_providers_all_healthy(self):
        """모든 Provider가 정상인 경우"""
        results = self.checker.check_all_providers()

        self.assertEqual(results, {
            "scraping": True,
            "external": True
        })

        # Redis에 저장되었는지 확인
        scraping_status = json.loads(cache.get("api:health:scraping"))
        self.assertEqual(scraping_status["status"], "healthy")

        external_status = json.loads(cache.get("api:health:external"))
        self.assertEqual(external_status["status"], "healthy")

    def test_check_all_providers_one_unhealthy(self):
        """하나의 Provider가 비정상인 경우"""
        self.mock_provider_a.health_check.return_value = False

        results = self.checker.check_all_providers()

        self.assertEqual(results, {
            "scraping": False,
            "external": True
        })

        # Redis 확인
        scraping_status = json.loads(cache.get("api:health:scraping"))
        self.assertEqual(scraping_status["status"], "unhealthy")

    def test_check_provider_exception_handling(self):
        """헬스체크 중 예외 발생 시 처리"""
        self.mock_provider_a.health_check.side_effect = Exception("Connection timeout")

        results = self.checker.check_all_providers()

        self.assertFalse(results["scraping"])

        # Redis에 에러 정보가 저장되어야 함
        scraping_status = json.loads(cache.get("api:health:scraping"))
        self.assertEqual(scraping_status["status"], "unhealthy")
        self.assertIn("Connection timeout", scraping_status["last_error"])

    @patch.object(HealthChecker, "_clear_routing_cache_pattern")
    def test_recovery_detection(self, mock_clear_cache):
        """장애 복구 감지 테스트"""
        # 초기 상태: scraping이 unhealthy
        cache.set("api:health:scraping", json.dumps({
            "status": "unhealthy",
            "last_check": "2024-01-01T10:00:00",
            "last_error": "Previous error"
        }))

        # 이번 체크에서는 healthy
        self.mock_provider_a.health_check.return_value = True

        # 실행
        self.checker.check_all_providers()

        # 복구 감지로 캐시 삭제가 호출되어야 함
        mock_clear_cache.assert_called_once()

    def test_no_recovery_if_already_healthy(self):
        """이미 healthy면 복구 처리 안 함"""
        # 초기 상태: 이미 healthy
        cache.set("api:health:scraping", json.dumps({
            "status": "healthy",
            "last_check": "2024-01-01T10:00:00",
            "last_error": None
        }))

        with patch.object(HealthChecker, "_clear_routing_cache_pattern") as mock_clear:
            self.checker.check_all_providers()

            # 캐시 삭제가 호출되지 않아야 함
            mock_clear.assert_not_called()

    def test_update_health_status(self):
        """헬스 상태 업데이트 테스트"""
        self.checker._update_health_status("test_provider", "unhealthy", "Test error")

        # Redis 확인
        health_data = json.loads(cache.get("api:health:test_provider"))
        self.assertEqual(health_data["status"], "unhealthy")
        self.assertEqual(health_data["last_error"], "Test error")
        self.assertIsNotNone(health_data["last_check"])
