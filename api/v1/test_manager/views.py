from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model

from services.external_api import check_hometax_registration
from services.calculation import calculate_refund

User = get_user_model()


# ============================================================
# 레거시 버전: 이메일 하드코딩 방식 (문제가 있는 기존 코드)
# ============================================================
# 문제점:
# 1. 코드 수정 없이 테스트 케이스 변경 불가
# 2. 테스터와 시나리오 매핑 관리 어려움
# 3. 새로운 테스트 케이스 추가 시 코드 배포 필요
# ============================================================

# 하드코딩된 테스트 이메일 리스트
TEST_EMAILS = [
    "test1@company.com",
    "test2@company.com",
    "test_hometax@company.com",
    "test_refund@company.com",
]


@login_required
@require_http_methods(["GET"])
def process_refund_legacy(request):
    """환급 처리 - 레거시 버전 (이메일 하드코딩 방식)"""
    user = request.user
    user_id = user.id

    # 테스트 유저 체크 (이메일 기반)
    if user.email in TEST_EMAILS:
        # 특정 플로우 강제 실행 - Mock 데이터 반환
        return JsonResponse(
            {
                "success": True,
                "user": user.username,
                "hometax_status": {"registered": False, "is_test": True},
                "refund_amount": {"amount": 1_500_000, "is_test": True},
                "message": "테스트 유저 - Mock 데이터 반환",
            }
        )

    try:
        # 실제 유저인 경우 정상 플로우
        # 1. 홈택스 가입 확인
        hometax_status = check_hometax_registration(user_id)

        # 2. 환급액 계산
        refund_amount = calculate_refund(user_id)

        return JsonResponse(
            {
                "success": True,
                "user": user.username,
                "hometax_status": hometax_status,
                "refund_amount": refund_amount,
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "error": "UNKNOWN_ERROR", "message": str(e)}, status=500
        )


# ============================================================
# 개선된 버전: DB 기반 동적 관리 방식
# ============================================================
@login_required
@require_http_methods(["GET"])
def process_refund(request):
    """환급 처리 전체 플로우"""
    user_id = request.user.id

    try:
        # 1. 홈택스 가입 확인
        hometax_status = check_hometax_registration(user_id)

        # 2. 환급액 계산
        refund_amount = calculate_refund(user_id)

        return JsonResponse(
            {
                "success": True,
                "user": request.user.username,
                "hometax_status": hometax_status,
                "refund_amount": refund_amount,
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "error": "UNKNOWN_ERROR", "message": str(e)}, status=500
        )
