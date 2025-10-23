"""외부 API 연동 모듈"""

from django.conf import settings
from apps.test_manager.utils import is_test_user_for_scenario


def check_hometax_registration(user_id: int):
    """홈택스 가입 여부 확인"""
    # 프로덕션이 아닌 경우에만 테스트 유저 체크
    if not settings.IS_PRODUCTION:
        if is_test_user_for_scenario(user_id, "NOT_HOMETAX_MEMBER"):
            return {"registered": False}

    # 실제 외부 API 호출
    response = external_api_call(user_id)
    return response


def external_api_call(user_id: int):
    """실제 외부 API 호출 시뮬레이션"""
    # 실제로는 외부 API를 호출하지만 여기서는 예시
    return {"registered": True, "user_id": user_id, "registration_date": "2024-01-15"}
