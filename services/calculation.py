"""환급 계산 비즈니스 로직"""

from django.conf import settings
from apps.test_manager.utils import is_test_user_for_scenario


def get_user_income(user_id: int) -> int:
    """사용자 소득 조회 (예시)"""
    # 실제로는 DB나 외부 API에서 조회
    return 50_000_000  # 5천만원


def calculate_actual_refund(user_id: int) -> dict:
    """실제 환급액 계산"""
    income = get_user_income(user_id)

    # 소득 기준에 따른 환급액 계산
    if income > 70_000_000:
        return {"amount": 0, "reason": "소득 초과"}
    elif income > 50_000_000:
        return {"amount": 500_000, "reason": "부분 환급"}
    else:
        return {"amount": 1_000_000, "reason": "전액 환급"}


def calculate_refund(user_id: int):
    """환급액 계산 - 테스트 시나리오 포함"""
    # 프로덕션이 아닌 경우에만 테스트 유저 체크
    if not settings.IS_PRODUCTION:
        # 테스트 유저용 특별 처리
        if is_test_user_for_scenario(user_id, "MONTHLY_RENT_REFUND"):
            # 항상 환급액이 있는 시나리오
            return {"amount": 1_500_000, "reason": "월세 환급 테스트"}

    # 실제 계산 로직
    income = get_user_income(user_id)
    if income > 70_000_000:
        return {"amount": 0, "reason": "소득 초과"}

    return calculate_actual_refund(user_id)
