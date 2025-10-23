"""
API Provider 패키지

동일한 기능을 제공하는 여러 API를 추상화하여 관리
"""

from .base import IWeatherAPIProvider
from .scraping_provider import ScrapingWeatherProvider
from .external_provider import ExternalWeatherProvider

__all__ = [
    "IWeatherAPIProvider",
    "ScrapingWeatherProvider",
    "ExternalWeatherProvider",
]
