# apps/weather/services/api_router.py
"""
API 라우터

유저별 API 선택 및 폴백 처리를 담당
"""

import logging
import json
from typing import Dict, List, Optional
from django.core.cache import cache
from django.conf import settings

from apps.weather.services.api_providers.base import IWeatherAPIProvider
from apps.weather.services.api_providers.scraping_provider import ScrapingWeatherProvider
from apps.weather.services.api_providers.external_provider import ExternalWeatherProvider
from apps.weather.services.weather_api.schemas import (
    WeatherForecastRequestSchema,
    WeatherForecastResponseSchema,
)

logger = logging.getLogger(__name__)


class APIRouter:
    """
    API 라우터

    책임:
    1. 유저별 API 선택 (동적 할당)
    2. 실패 시 즉시 폴백
    3. Redis 캐싱
    4. 헬스 상태 업데이트
    """

    # Redis 키 프리픽스
    ROUTING_KEY_PREFIX = "routing"
    HEALTH_KEY_PREFIX = "api:health"
    METRICS_KEY_PREFIX = "api:metrics"

    # 캐시 TTL
    ROUTING_CACHE_TTL = 3600  # 1시간

    def __init__(self, providers: Optional[List[IWeatherAPIProvider]] = None):
        """
        Args:
            providers: API Provider 리스트 (기본값: 자동 생성)
        """
        if providers is None:
            # 기본 Provider 생성
            api_key = getattr(settings, "WEATHER_API_KEY", "default-api-key")
            self.providers = [
                ScrapingWeatherProvider(api_key=api_key),
                ExternalWeatherProvider(api_key=api_key),
            ]
        else:
            self.providers = providers

        # Provider를 이름으로 매핑
        self.provider_map: Dict[str, IWeatherAPIProvider] = {
            provider.provider_name: provider for provider in self.providers
        }

        logger.info(
            f"[APIRouter] Initialized with providers: {list(self.provider_map.keys())}"
        )

    def route_request(
        self, user_id: int, request_data: WeatherForecastRequestSchema
    ) -> WeatherForecastResponseSchema:
        """
        요청 라우팅 및 폴백 처리

        1. Redis에서 유저 라우팅 캐시 조회
        2. 캐시 없으면 동적 할당
        3. Primary API 호출
        4. 실패 시 Fallback API 호출
        5. Redis에 결과 캐싱

        Args:
            user_id: 사용자 ID
            request_data: 날씨 예보 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            Exception: 모든 API 실패 시
        """
        logger.info(f"[APIRouter] Routing request for user_id={user_id}")

        # 1. 캐시에서 할당된 Provider 조회
        cached_provider_name = self._get_cached_routing(user_id)

        # 2. 캐시 없으면 동적 할당
        if cached_provider_name is None:
            primary_provider_name = self._select_provider(user_id)
            logger.info(
                f"[APIRouter] No cache, dynamically selected: {primary_provider_name}"
            )
        else:
            primary_provider_name = cached_provider_name
            logger.info(
                f"[APIRouter] Cache hit: {primary_provider_name}"
            )

        # 3. Primary API 호출 및 폴백 처리
        response = self._call_with_fallback(
            user_id, primary_provider_name, request_data
        )

        return response

    def _get_cached_routing(self, user_id: int) -> Optional[str]:
        """
        Redis에서 유저 라우팅 캐시 조회

        Args:
            user_id: 사용자 ID

        Returns:
            Optional[str]: Provider 이름 (없으면 None)
        """
        cache_key = f"{self.ROUTING_KEY_PREFIX}:{user_id}"
        cached_value = cache.get(cache_key)

        if cached_value:
            logger.debug(f"[APIRouter] Cache hit for user_id={user_id}: {cached_value}")
        else:
            logger.debug(f"[APIRouter] Cache miss for user_id={user_id}")

        return cached_value

    def _set_cached_routing(self, user_id: int, provider_name: str):
        """
        Redis에 유저 라우팅 캐시 저장

        Args:
            user_id: 사용자 ID
            provider_name: Provider 이름
        """
        cache_key = f"{self.ROUTING_KEY_PREFIX}:{user_id}"
        cache.set(cache_key, provider_name, self.ROUTING_CACHE_TTL)
        logger.debug(
            f"[APIRouter] Cached routing for user_id={user_id}: {provider_name}"
        )

    def _select_provider(self, user_id: int) -> str:
        """
        동적 Provider 선택

        부하/비용/헬스 상태를 고려하여 최적의 Provider 선택

        Args:
            user_id: 사용자 ID

        Returns:
            str: 선택된 Provider 이름
        """
        # 각 Provider의 헬스 상태 확인
        healthy_providers = []
        for provider_name, provider in self.provider_map.items():
            health_status = self._get_health_status(provider_name)
            if health_status.get("status") == "healthy":
                healthy_providers.append(provider_name)

        if not healthy_providers:
            # 모두 unhealthy면 기본값 사용 (scraping)
            logger.warning("[APIRouter] No healthy providers, using default: scraping")
            return "scraping"

        # 비용 기반 선택: 무료 Provider 우선 (scraping)
        # 실제로는 더 복잡한 로직 (부하, 메트릭 등) 고려 가능
        if "scraping" in healthy_providers:
            logger.info("[APIRouter] Selected scraping provider (free)")
            return "scraping"
        else:
            # scraping이 unhealthy면 external 사용
            logger.info("[APIRouter] Scraping unhealthy, selected external provider")
            return healthy_providers[0]

    def _call_with_fallback(
        self,
        user_id: int,
        primary_provider_name: str,
        request_data: WeatherForecastRequestSchema,
    ) -> WeatherForecastResponseSchema:
        """
        Primary API 호출 및 실패 시 폴백 처리

        Args:
            user_id: 사용자 ID
            primary_provider_name: Primary Provider 이름
            request_data: 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 응답

        Raises:
            Exception: 모든 API 실패 시
        """
        # Primary Provider 시도
        primary_provider = self.provider_map.get(primary_provider_name)
        if primary_provider is None:
            raise Exception(f"Provider not found: {primary_provider_name}")

        try:
            logger.info(f"[APIRouter] Calling primary provider: {primary_provider_name}")
            response = primary_provider.get_weather_forecast(request_data)

            # 성공 시 캐시 저장
            self._set_cached_routing(user_id, primary_provider_name)
            self._increment_success_metric(primary_provider_name)

            return response

        except Exception as e:
            logger.error(
                f"[APIRouter] Primary provider failed: {primary_provider_name}, error: {e}"
            )
            self._increment_failure_metric(primary_provider_name)
            self._update_health_status(primary_provider_name, "unhealthy", str(e))

            # Fallback Provider 선택 (primary가 아닌 다른 Provider)
            fallback_providers = [
                name for name in self.provider_map.keys() if name != primary_provider_name
            ]

            if not fallback_providers:
                raise Exception(f"No fallback provider available, primary failed: {e}")

            # Fallback Provider 시도
            for fallback_name in fallback_providers:
                try:
                    logger.info(f"[APIRouter] Trying fallback provider: {fallback_name}")
                    fallback_provider = self.provider_map[fallback_name]
                    response = fallback_provider.get_weather_forecast(request_data)

                    # Fallback 성공 시 캐시 업데이트 (다음부터 이 Provider 사용)
                    self._set_cached_routing(user_id, fallback_name)
                    self._increment_success_metric(fallback_name)

                    logger.info(
                        f"[APIRouter] Fallback successful: {fallback_name}"
                    )
                    return response

                except Exception as fallback_error:
                    logger.error(
                        f"[APIRouter] Fallback provider failed: {fallback_name}, error: {fallback_error}"
                    )
                    self._increment_failure_metric(fallback_name)
                    self._update_health_status(fallback_name, "unhealthy", str(fallback_error))
                    continue

            # 모든 Provider 실패
            raise Exception("All providers failed")

    def _get_health_status(self, provider_name: str) -> dict:
        """
        Redis에서 Provider 헬스 상태 조회

        Args:
            provider_name: Provider 이름

        Returns:
            dict: 헬스 상태 (없으면 기본값: healthy)
        """
        cache_key = f"{self.HEALTH_KEY_PREFIX}:{provider_name}"
        cached_status = cache.get(cache_key)

        if cached_status:
            return json.loads(cached_status)
        else:
            # 캐시 없으면 healthy로 가정
            return {"status": "healthy", "last_check": None, "last_error": None}

    def _update_health_status(self, provider_name: str, status: str, error: Optional[str] = None):
        """
        Redis에 Provider 헬스 상태 저장

        Args:
            provider_name: Provider 이름
            status: 상태 ("healthy" or "unhealthy")
            error: 에러 메시지 (선택)
        """
        from datetime import datetime

        cache_key = f"{self.HEALTH_KEY_PREFIX}:{provider_name}"
        health_data = {
            "status": status,
            "last_check": datetime.now().isoformat(),
            "last_error": error,
        }
        cache.set(cache_key, json.dumps(health_data), timeout=None)  # 무기한 저장
        logger.info(f"[APIRouter] Updated health status for {provider_name}: {status}")

    def _increment_success_metric(self, provider_name: str):
        """성공 메트릭 증가"""
        cache_key = f"{self.METRICS_KEY_PREFIX}:{provider_name}:success"
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=3600)  # 1시간 TTL

    def _increment_failure_metric(self, provider_name: str):
        """실패 메트릭 증가"""
        cache_key = f"{self.METRICS_KEY_PREFIX}:{provider_name}:failure"
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=3600)  # 1시간 TTL


# 전역 인스턴스 (싱글톤 패턴)
_api_router_instance = None


def get_api_router(providers: Optional[List[IWeatherAPIProvider]] = None) -> APIRouter:
    """
    API Router 인스턴스 반환 (팩토리 함수)

    Args:
        providers: API Provider 리스트 (테스트용)

    Returns:
        APIRouter 인스턴스
    """
    global _api_router_instance

    # 테스트나 특수한 경우에만 새 인스턴스 생성
    if providers is not None:
        return APIRouter(providers=providers)

    # 싱글톤 사용
    if _api_router_instance is None:
        _api_router_instance = APIRouter()

    return _api_router_instance
