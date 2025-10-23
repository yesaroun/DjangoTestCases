# apps/weather/services/health_checker.py
"""
API Health Checker

주기적으로 각 API Provider의 상태를 확인하고
장애 복구 시 자동으로 라우팅을 업데이트
"""

import logging
import json
from typing import Dict, List
from datetime import datetime
from django.core.cache import cache
from django.conf import settings

from apps.weather.services.api_providers.base import IWeatherAPIProvider
from apps.weather.services.api_providers.scraping_provider import ScrapingWeatherProvider
from apps.weather.services.api_providers.external_provider import ExternalWeatherProvider

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    API Health Checker

    주기적으로 실행하여:
    1. 각 API Provider 상태 확인
    2. Redis에 헬스 상태 저장
    3. 장애 복구 감지 시 라우팅 캐시 초기화
    """

    HEALTH_KEY_PREFIX = "api:health"
    ROUTING_KEY_PREFIX = "routing"

    def __init__(self, providers: List[IWeatherAPIProvider] = None):
        """
        Args:
            providers: 체크할 Provider 리스트 (기본값: 자동 생성)
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

        logger.info(
            f"[HealthChecker] Initialized with {len(self.providers)} providers"
        )

    def check_all_providers(self) -> Dict[str, bool]:
        """
        모든 Provider 헬스체크

        Returns:
            Dict[str, bool]: {provider_name: is_healthy}
        """
        logger.info("[HealthChecker] Starting health check for all providers")

        results = {}
        for provider in self.providers:
            provider_name = provider.provider_name
            is_healthy = self._check_provider(provider)
            results[provider_name] = is_healthy

            # 복구 감지
            if is_healthy:
                self._check_and_handle_recovery(provider_name)

        logger.info(f"[HealthChecker] Health check completed: {results}")
        return results

    def _check_provider(self, provider: IWeatherAPIProvider) -> bool:
        """
        개별 Provider 헬스체크

        Args:
            provider: Provider 인스턴스

        Returns:
            bool: True=정상, False=장애
        """
        provider_name = provider.provider_name

        try:
            is_healthy = provider.health_check()

            if is_healthy:
                self._update_health_status(provider_name, "healthy")
                logger.info(f"[HealthChecker] {provider_name}: HEALTHY")
            else:
                self._update_health_status(
                    provider_name, "unhealthy", "Health check returned False"
                )
                logger.warning(f"[HealthChecker] {provider_name}: UNHEALTHY")

            return is_healthy

        except Exception as e:
            self._update_health_status(
                provider_name, "unhealthy", f"Health check exception: {str(e)}"
            )
            logger.error(f"[HealthChecker] {provider_name}: ERROR - {e}")
            return False

    def _check_and_handle_recovery(self, provider_name: str):
        """
        장애 복구 감지 및 처리

        이전에 unhealthy였던 Provider가 healthy로 복구되면
        해당 Provider로 할당된 유저 라우팅 캐시를 삭제하여
        다음 요청 시 재할당되도록 함

        Args:
            provider_name: Provider 이름
        """
        # 이전 상태 조회
        previous_status = self._get_previous_health_status(provider_name)

        if previous_status == "unhealthy":
            logger.info(
                f"[HealthChecker] Recovery detected for {provider_name}! "
                "Clearing routing cache for affected users."
            )
            # 실제로는 영향받은 유저들의 캐시만 삭제해야 하지만,
            # 간단하게 패턴 매칭으로 모든 라우팅 캐시 삭제
            self._clear_routing_cache_pattern(f"{self.ROUTING_KEY_PREFIX}:*")

    def _get_previous_health_status(self, provider_name: str) -> str:
        """
        이전 헬스 상태 조회

        Args:
            provider_name: Provider 이름

        Returns:
            str: "healthy" or "unhealthy" (기본값: "healthy")
        """
        cache_key = f"{self.HEALTH_KEY_PREFIX}:{provider_name}"
        cached_status = cache.get(cache_key)

        if cached_status:
            health_data = json.loads(cached_status)
            return health_data.get("status", "healthy")
        else:
            return "healthy"

    def _update_health_status(
        self, provider_name: str, status: str, error: str = None
    ):
        """
        Redis에 헬스 상태 저장

        Args:
            provider_name: Provider 이름
            status: "healthy" or "unhealthy"
            error: 에러 메시지 (선택)
        """
        cache_key = f"{self.HEALTH_KEY_PREFIX}:{provider_name}"
        health_data = {
            "status": status,
            "last_check": datetime.now().isoformat(),
            "last_error": error,
        }
        cache.set(cache_key, json.dumps(health_data), timeout=None)  # 무기한 저장

    def _clear_routing_cache_pattern(self, pattern: str):
        """
        패턴 매칭으로 라우팅 캐시 삭제

        Args:
            pattern: Redis 키 패턴 (예: "routing:*")
        """
        try:
            # django-redis는 delete_pattern 지원
            cache.delete_pattern(pattern)
            logger.info(f"[HealthChecker] Cleared routing cache: {pattern}")
        except AttributeError:
            # delete_pattern이 없는 경우 (일반 캐시 백엔드)
            logger.warning(
                "[HealthChecker] delete_pattern not supported, "
                "skipping cache clear"
            )
        except Exception as e:
            logger.error(f"[HealthChecker] Failed to clear cache: {e}")


def run_health_check() -> Dict[str, bool]:
    """
    헬스체크 실행 (편의 함수)

    Returns:
        Dict[str, bool]: {provider_name: is_healthy}
    """
    checker = HealthChecker()
    return checker.check_all_providers()
