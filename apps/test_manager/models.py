from django.db import models
from django.db.models import TextChoices


class UserTestCaseNames(TextChoices):
    """
    데이터베이스 'test_cases' 테이블의 'name' 컬럼에 있는 값들을
    코드에서 안전하게 사용하기 위해 정의하는 상수 목록입니다.

    이 목록을 바꾼다고 해서 마이그레이션이 필요하지는 않지만,
    DB와 항상 일치하도록 개발자가 직접 관리해야 합니다.
    """

    NOT_HOMETAX_MEMBER = ("NotHomeTaxMember", "홈택스 미가입자")
    MONTHLY_RENT_REFUND_AMOUNT = ("MonthlyRentRefundAmount", "월세 환급액 존재")


class TestCase(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="테스트 케이스 이름",
        help_text="코드에서 사용할 테스트 케이스 키 (예: additional_large_amount)",
    )
    users = models.ManyToManyField(
        "user.User",
        through="UserTestCaseAssignment",
        related_name="test_cases",
        blank=True,
        verbose_name="테스트 유저들",
    )

    class Meta:
        db_table = "test_cases"


class UserTestCaseAssignment(models.Model):
    """유저-테스트케이스 매핑"""

    user = models.ForeignKey("user.User", on_delete=models.CASCADE)
    test_case = models.ForeignKey("TestCase", on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_test_case_assignments"
        unique_together = ["user", "test_case"]
