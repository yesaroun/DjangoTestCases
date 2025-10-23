# api/v1/weather/views/weather_fetch_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from pydantic import ValidationError

from apps.weather.services.weather_api.api_helper import WeatherAPIHelperLegacy
from apps.weather.services.weather_api.schemas import WeatherForecastViewRequestSchema
from apps.weather.services.weather_service import IWeatherService, get_weather_service


# ============================================================
# Before: 레거시 버전 (나쁜 예시)
# ============================================================


class WeatherForecastViewLegacy(APIView):
    """
    날씨 예보 조회 View - 레거시 버전

    문제점:
    1. View 내부에서 직접 API Helper 인스턴스화 - DI 부재
    2. request.data.get()으로 데이터 추출 - 타입 검증 없음
    3. dict 응답 - 응답 타입 불명확
    4. View에 모든 로직이 집중 - 책임 과다
    5. 테스트 시 복잡한 패치 필요
    """

    def post(self, request):
        """
        날씨 예보 조회 - 레거시 방식
        사실 model serializer를 주로 사용하고 있습니다.

        문제점:
        - View 내부에서 직접 인스턴스화
        - 타입 검증 없음
        - 서비스 레이어 없음
        """
        # 문제 1: View 내부에서 직접 인스턴스화 - DI 부재
        api_helper = WeatherAPIHelperLegacy(api_key=settings.WEATHER_API_KEY)

        # 문제 2: request.data.get() - 타입 검증 없음, None 가능
        city = request.data.get("city")
        country_code = request.data.get("country_code")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        # 문제 3: View에서 직접 외부 API 호출 - 비즈니스 로직이 View에
        try:
            weather_data = api_helper.get_weather_forecast(
                city=city,
                country_code=country_code,
                start_date=start_date,
                end_date=end_date,
                include_hourly=True,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 문제 4: dict 응답 - 타입 불명확
        return Response(
            {"success": True, "data": weather_data}, status=status.HTTP_200_OK
        )


# ============================================================
# After: 개선된 버전 (서비스 레이어 사용)
# ============================================================


class WeatherForecastView(APIView):
    """
    개선된 날씨 예보 조회 View

    개선점:
    1. Pydantic으로 요청 데이터 검증 (View 진입 시점)
    2. 서비스 레이어를 통한 비즈니스 로직 분리
    3. View는 HTTP 요청/응답 처리만 담당 (얇은 레이어)
    4. DI를 통한 느슨한 결합 (메서드 레벨)

    Before vs After:
    - Before: request.data.get() → 타입 검증 없음
    - After: Pydantic 스키마 검증 → 타입 안전
    """

    service_factory = staticmethod(get_weather_service)

    def post(self, request, weather_service: IWeatherService = None):
        """
        날씨 예보 조회

        Args:
            request: HTTP 요청
            weather_service: 날씨 서비스 (테스트용, 기본값=None)

        """
        # 서비스 인스턴스 가져오기 (DI)
        service = weather_service or self.service_factory()

        try:
            validated_data = WeatherForecastViewRequestSchema(**request.data)
        except ValidationError as e:
            return Response(
                {"success": False, "errors": e.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            weather_data = service.get_weather_forecast(
                city=validated_data.city,
                country_code=validated_data.country_code,
                start_date=validated_data.start_date,
                end_date=validated_data.end_date,
                include_hourly=validated_data.include_hourly,
                units=validated_data.units,
            )
        except ValidationError as e:
            return Response(
                {"success": False, "errors": e.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"success": True, "data": weather_data.model_dump(exclude_none=True)},
            status=status.HTTP_200_OK,
        )
