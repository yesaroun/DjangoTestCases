# apps/weather/services/api_router.py
"""
API 라우터 (Lazy 헬스체크 버전)

유저별 API 선택 및 폴백 처리를 담당
실패한 Provider는 일정 시간 후 요청 시점에 복구 시도
"""

import logging
import time
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
    API 라우터 (Lazy 헬스체크)

    책임:
    1. 글로벌 API 선택 (동적 할당)
    2. 실패 시 즉시 폴백
    3. Redis 캐싱
    4. 실패 시점 기록 및 Lazy 복구
    """

    # Redis 키
    ROUTING_KEY = "routing:current"  # 현재 선택된 Provider (글로벌)
    FAILED_KEY_PREFIX = "api:failed"  # 마지막 실패 타임스탬프
    METRICS_KEY_PREFIX = "api:metrics"

    # 캐시 TTL
    ROUTING_CACHE_TTL = 3600  # 1시간
    FAILED_CACHE_TTL = 3600  # 1시간

    # 재시도 간격 (초)
    RETRY_INTERVAL_SECONDS = 60  # 1분

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
        요청 라우팅 및 폴백 처리 (Lazy 헬스체크)

        1. Redis에서 글로벌 라우팅 캐시 조회
        2. 캐시 없으면 동적 할당 (lazy 복구 시도 포함)
        3. Primary API 호출
        4. 실패 시 Fallback API 호출
        5. Redis에 결과 캐싱

        Args:
            user_id: 사용자 ID (메트릭/로깅용)
            request_data: 날씨 예보 요청 데이터

        Returns:
            WeatherForecastResponseSchema: 날씨 예보 응답

        Raises:
            Exception: 모든 API 실패 시
        """
        logger.info(f"[APIRouter] Routing request for user_id={user_id}")

        # 1. 캐시에서 할당된 Provider 조회
        cached_provider_name = self._get_cached_routing()

        # 2. 캐시 없으면 동적 할당 (lazy 복구 시도 포함)
        if cached_provider_name is None:
            primary_provider_name = self._select_provider(request_data)
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
            primary_provider_name, request_data
        )

        return response

    def _get_cached_routing(self) -> Optional[str]:
        """
        Redis에서 글로벌 라우팅 캐시 조회

        Returns:
            Optional[str]: Provider 이름 (없으면 None)
        """
        cached_value = cache.get(self.ROUTING_KEY)

        if cached_value:
            logger.debug(f"[APIRouter] Cache hit: {cached_value}")
        else:
            logger.debug(f"[APIRouter] Cache miss")

        return cached_value

    def _set_cached_routing(self, provider_name: str):
        """
        Redis에 글로벌 라우팅 캐시 저장

        Args:
            provider_name: Provider 이름
        """
        cache.set(self.ROUTING_KEY, provider_name, self.ROUTING_CACHE_TTL)
        logger.debug(
            f"[APIRouter] Cached routing: {provider_name}"
        )

    def _select_provider(self, request_data: WeatherForecastRequestSchema) -> str:
        """
        동적 Provider 선택 (Lazy 헬스체크 포함)

        실패한 Provider는 재시도 간격이 지났으면 복구 시도

        Args:
            request_data: 요청 데이터 (복구 시도용)

        Returns:
            str: 선택된 Provider 이름
        """
        available_providers = []

        for provider_name in self.provider_map.keys():
            # 재시도 가능한지 확인
            if self._should_retry_provider(provider_name):
                # Lazy 복구 시도
                logger.info(f"[APIRouter] Attempting lazy recovery for {provider_name}")
                recovered = self._try_recovery(provider_name, request_data)

                if recovered:
                    logger.info(f"[APIRouter] {provider_name} recovered!")
                    available_providers.append(provider_name)
                else:
                    logger.warning(f"[APIRouter] {provider_name} still unhealthy")
            elif not self._is_provider_failed(provider_name):
                # 실패 기록이 없으면 사용 가능
                available_providers.append(provider_name)

        if not available_providers:
            # 모두 실패 상태면 기본값 사용 (scraping)
            logger.warning("[APIRouter] No available providers, using default: scraping")
            return "scraping"

        # 비용 기반 선택: 무료 Provider 우선 (scraping)
        if "scraping" in available_providers:
            logger.info("[APIRouter] Selected scraping provider (free)")
            return "scraping"
        else:
            # scraping이 없으면 다른 Provider 사용
            selected = available_providers[0]
            logger.info(f"[APIRouter] Selected {selected} provider")
            return selected

    def _should_retry_provider(self, provider_name: str) -> bool:
        """
        Provider가 재시도 가능한지 확인

        실패한 지 RETRY_INTERVAL_SECONDS 이상 경과했는지 확인

        Args:
            provider_name: Provider 이름

        Returns:
            bool: True=재시도 가능, False=아직 대기 중
        """
        last_failed_at = self._get_last_failed_timestamp(provider_name)

        if last_failed_at is None:
            # 실패 기록 없음
            return False

        elapsed = time.time() - last_failed_at

        if elapsed >= self.RETRY_INTERVAL_SECONDS:
            logger.debug(
                f"[APIRouter] {provider_name} retry interval elapsed ({elapsed:.1f}s)"
            )
            return True
        else:
            logger.debug(
                f"[APIRouter] {provider_name} still in cooldown ({elapsed:.1f}s / {self.RETRY_INTERVAL_SECONDS}s)"
            )
            return False

    def _try_recovery(self, provider_name: str, request_data: WeatherForecastRequestSchema) -> bool:
        """
        Provider 복구 시도 (헬스체크)

        Args:
            provider_name: Provider 이름
            request_data: 요청 데이터 (실제 호출 대신 헬스체크)

        Returns:
            bool: True=복구 성공, False=여전히 실패
        """
        provider = self.provider_map.get(provider_name)
        if provider is None:
            return False

        try:
            # 헬스체크 시도
            is_healthy = provider.health_check()

            if is_healthy:
                # 복구 성공: 실패 기록 삭제
                self._clear_failed_timestamp(provider_name)
                logger.info(f"[APIRouter] {provider_name} recovery successful")
                return True
            else:
                # 여전히 실패: 타임스탬프 갱신
                self._mark_provider_failed(provider_name)
                logger.warning(f"[APIRouter] {provider_name} recovery failed")
                return False

        except Exception as e:
            # 헬스체크 실패: 타임스탬프 갱신
            self._mark_provider_failed(provider_name)
            logger.error(f"[APIRouter] {provider_name} recovery exception: {e}")
            return False

    def _is_provider_failed(self, provider_name: str) -> bool:
        """
        Provider가 실패 상태인지 확인

        Args:
            provider_name: Provider 이름

        Returns:
            bool: True=실패 상태, False=정상
        """
        return self._get_last_failed_timestamp(provider_name) is not None

    def _get_last_failed_timestamp(self, provider_name: str) -> Optional[float]:
        """
        마지막 실패 타임스탬프 조회

        Args:
            provider_name: Provider 이름

        Returns:
            Optional[float]: Unix timestamp (없으면 None)
        """
        cache_key = f"{self.FAILED_KEY_PREFIX}:{provider_name}"
        timestamp = cache.get(cache_key)
        return float(timestamp) if timestamp is not None else None

    def _mark_provider_failed(self, provider_name: str):
        """
        Provider를 실패 상태로 마킹 (타임스탬프 저장)

        Args:
            provider_name: Provider 이름
        """
        cache_key = f"{self.FAILED_KEY_PREFIX}:{provider_name}"
        cache.set(cache_key, time.time(), timeout=self.FAILED_CACHE_TTL)
        logger.info(f"[APIRouter] Marked {provider_name} as failed")

    def _clear_failed_timestamp(self, provider_name: str):
        """
        Provider 실패 기록 삭제 (복구 완료)

        Args:
            provider_name: Provider 이름
        """
        cache_key = f"{self.FAILED_KEY_PREFIX}:{provider_name}"
        cache.delete(cache_key)
        logger.info(f"[APIRouter] Cleared failed status for {provider_name}")

    def _call_with_fallback(
        self,
        primary_provider_name: str,
        request_data: WeatherForecastRequestSchema,
    ) -> WeatherForecastResponseSchema:
        """
        Primary API 호출 및 실패 시 폴백 처리

        Args:
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

            # 성공 시: 캐시 저장 & 실패 기록 삭제 (복구)
            self._set_cached_routing(primary_provider_name)
            self._increment_success_metric(primary_provider_name)
            self._clear_failed_timestamp(primary_provider_name)

            return response

        except Exception as e:
            logger.error(
                f"[APIRouter] Primary provider failed: {primary_provider_name}, error: {e}"
            )
            self._increment_failure_metric(primary_provider_name)
            self._mark_provider_failed(primary_provider_name)

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

                    # Fallback 성공 시: 캐시 업데이트 & 실패 기록 삭제
                    self._set_cached_routing(fallback_name)
                    self._increment_success_metric(fallback_name)
                    self._clear_failed_timestamp(fallback_name)

                    logger.info(
                        f"[APIRouter] Fallback successful: {fallback_name}"
                    )
                    return response

                except Exception as fallback_error:
                    logger.error(
                        f"[APIRouter] Fallback provider failed: {fallback_name}, error: {fallback_error}"
                    )
                    self._increment_failure_metric(fallback_name)
                    self._mark_provider_failed(fallback_name)
                    continue

            # 모든 Provider 실패
            raise Exception("All providers failed")

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
