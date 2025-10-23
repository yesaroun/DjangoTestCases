# apps/weather/management/commands/check_api_health.py
"""
API 헬스체크 Django 관리 명령어

사용법:
    python manage.py check_api_health

Cron 등록 예시 (1분마다):
    * * * * * cd /path/to/project && python manage.py check_api_health
"""

from django.core.management.base import BaseCommand
from apps.weather.services.health_checker import run_health_check


class Command(BaseCommand):
    help = "Check health of all weather API providers"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Starting API health check...")
        )

        try:
            results = run_health_check()

            self.stdout.write("\nHealth Check Results:")
            self.stdout.write("-" * 40)

            for provider_name, is_healthy in results.items():
                status_style = self.style.SUCCESS if is_healthy else self.style.ERROR
                status_text = "HEALTHY" if is_healthy else "UNHEALTHY"
                self.stdout.write(
                    f"  {provider_name}: {status_style(status_text)}"
                )

            self.stdout.write("-" * 40)

            # 전체 요약
            healthy_count = sum(1 for v in results.values() if v)
            total_count = len(results)

            if healthy_count == total_count:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✓ All {total_count} providers are healthy"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠ {healthy_count}/{total_count} providers are healthy"
                    )
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"\n✗ Health check failed: {e}")
            )
            raise
