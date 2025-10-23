# api/v1/weather/urls.py
from django.urls import path
from .views.weather_fetch_views import (
    WeatherForecastViewLegacy,
    WeatherForecastView
)

urlpatterns = [
    # Legacy endpoint (Before - 나쁜 예시)
    path('forecast/legacy/', WeatherForecastViewLegacy.as_view(), name='weather_forecast_legacy'),

    # Improved endpoint (After - 좋은 예시)
    path('forecast/', WeatherForecastView.as_view(), name='weather_forecast'),
]
