# tests/weather/test_weather_fetch_views.py
from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory
from pydantic import ValidationError

from api.v1.weather.views.weather_fetch_views import (
    WeatherForecastViewLegacy,
    WeatherForecastView
)
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
)
from apps.weather.services.weather_service import WeatherService


# ============================================================
# Before: 레거시 테스트 (복잡한 패치 방식)
# ============================================================

class TestWeatherForecastViewLegacy(TestCase):
    """
    레거시 View 테스트

    문제점:
    1. View 내부의 인스턴스화를 패치해야 함
    2. 패치 경로가 복잡함
    3. Mock 설정이 번거로움
    4. Mock 클래스와 인스턴스를 모두 다뤄야 함
    """

    def setUp(self):
        self.client = APIClient()

    @patch('api.v1.weather.views.weather_fetch_views.WeatherAPIHelperLegacy')
    def test_get_weather_forecast_success(self, mock_helper_class):
        """성공 케이스 테스트 - 복잡한 패치 필요"""

        # Mock 인스턴스 생성
        mock_helper = MagicMock()
        mock_helper.get_weather_forecast.return_value = {
            "temperature": 20,
            "condition": "sunny"
        }
        mock_helper_class.return_value = mock_helper

        # API 호출
        response = self.client.post('/api/v1/weather/forecast/legacy/', {
            "city": "Seoul",
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        # 검증
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        mock_helper.get_weather_forecast.assert_called_once()

    @patch('api.v1.weather.views.weather_fetch_views.WeatherAPIHelperLegacy')
    def test_get_weather_forecast_api_error(self, mock_helper_class):
        """API 에러 케이스 - 복잡한 패치"""

        # Mock이 예외 발생하도록 설정
        mock_helper = MagicMock()
        mock_helper.get_weather_forecast.side_effect = Exception("API connection failed")
        mock_helper_class.return_value = mock_helper

        # API 호출
        response = self.client.post('/api/v1/weather/forecast/legacy/', {
            "city": "Seoul",
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        # 검증
        self.assertEqual(response.status_code, 500)


# ============================================================
# After: 개선된 테스트 (서비스 레이어 Mock)
# ============================================================

class TestWeatherForecastView(TestCase):
    """
    개선된 View 테스트 - 서비스 레이어 사용

    개선점:
    1. 서비스 레이어를 Mock으로 주입
    2. View는 얇은 레이어이므로 테스트 간단
    3. 복잡한 패치 불필요
    4. 메서드 레벨 DI로 안전
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        # Mock 서비스 생성
        self.mock_service = MagicMock(spec=WeatherService)

    def test_get_weather_forecast_success(self):
        """성공 케이스 테스트 - 서비스 레이어 Mock 주입"""

        # Mock 응답 설정 (Pydantic 스키마 사용)
        mock_response = WeatherForecastResponseSchema(
            temperature=20.5,
            humidity=60,
            condition="sunny",
            forecast_date="2024-01-15"
        )
        self.mock_service.get_weather_forecast.return_value = mock_response

        # View 인스턴스 생성
        view = WeatherForecastView()

        # 요청 생성
        request = self.factory.post('/api/v1/weather/forecast/', {
            "city": "Seoul",
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        # View 실행 (서비스 주입)
        response = view.post(request, weather_service=self.mock_service)

        # 검증
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["temperature"], 20.5)

        # Mock 호출 검증
        self.mock_service.get_weather_forecast.assert_called_once_with(
            city="Seoul",
            country_code="KR",
            start_date="2024-01-01",
            end_date="2024-01-31",
            include_hourly=False,
            units="metric",
        )

    def test_get_weather_forecast_missing_fields(self):
        """필수 필드 누락 케이스"""

        view = WeatherForecastView()

        # 필수 필드 누락 (city 없음)
        request = self.factory.post('/api/v1/weather/forecast/', {
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        response = view.post(request, weather_service=self.mock_service)

        # 검증
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("error", response.data)

    def test_get_weather_forecast_validation_error(self):
        """Pydantic 검증 실패 케이스"""

        # Mock이 ValidationError 발생하도록 설정
        self.mock_service.get_weather_forecast.side_effect = ValidationError.from_exception_data(
            "validation_error",
            [{"loc": ("country_code",), "msg": "String should have at most 2 characters", "type": "string_too_long"}]
        )

        view = WeatherForecastView()

        request = self.factory.post('/api/v1/weather/forecast/', {
            "city": "Seoul",
            "country_code": "KOREA",  # 2자여야 하는데 5자
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        response = view.post(request, weather_service=self.mock_service)

        # 검증
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("errors", response.data)

    def test_get_weather_forecast_api_error(self):
        """API 에러 케이스"""

        # Mock이 예외 발생하도록 설정
        self.mock_service.get_weather_forecast.side_effect = Exception(
            "API connection failed"
        )

        view = WeatherForecastView()

        request = self.factory.post('/api/v1/weather/forecast/', {
            "city": "Seoul",
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        response = view.post(request, weather_service=self.mock_service)

        # 검증
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.data["success"])

    def test_service_injection_is_simple(self):
        """
        서비스 레이어 DI 패턴의 장점:
        - __init__ 문제 없음 (메서드 파라미터 사용)
        - 패치 경로 걱정 없음
        - Mock 주입이 직관적
        - View는 얇게 유지
        """
        mock_service = MagicMock()
        mock_service.get_weather_forecast.return_value = WeatherForecastResponseSchema(
            temperature=15.0,
            humidity=70,
            condition="cloudy",
            forecast_date="2024-01-20"
        )

        view = WeatherForecastView()
        request = self.factory.post('/api/v1/weather/forecast/', {
            "city": "Busan",
            "country_code": "KR",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })

        response = view.post(request, weather_service=mock_service)

        # 검증: 주입된 서비스가 호출되었는지
        self.assertEqual(response.status_code, 200)
        mock_service.get_weather_forecast.assert_called_once()
