from django.conf import settings

from apps.test_manager.models import UserTestCaseAssignment


def is_test_user_for_scenario(user_id: int, scenario: str) -> bool:
    """
    특정 유저가 특정 테스트 시나리오에 할당되었는지 확인
    개발 서버에서만 동작

    Args:
        user_id: 확인할 유저 ID
        scenario: 테스트 시나리오 이름 (예: "NOT_HOMETAX_MEMBER")

    Returns:
        bool: 테스트 유저 여부
    """
    # 프로덕션에서는 항상 False 반환
    if settings.IS_PRODUCTION:
        return False

    try:
        return UserTestCaseAssignment.objects.filter(
            user_id=user_id, test_case__name=scenario
        ).exists()
    except Exception:
        return False
