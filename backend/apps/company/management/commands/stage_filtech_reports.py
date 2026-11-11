import json

from django.core.management.base import BaseCommand, CommandError

from apps.company.report_staging import StagingError, stage_filtech_reports


class Command(BaseCommand):
    help = "관리대장을 검토 대기로 적재합니다. 기본은 dry-run이며 정식 자료로 전환하지 않습니다."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path")
        parser.add_argument("--apply", action="store_true", help="검토 대기 저장 실행")
        parser.add_argument("--expected-sha256", help="쓰기 전 확인한 원본 SHA256(필수)")

    def handle(self, *args, **options):
        try:
            result = stage_filtech_reports(
                options["xlsx_path"],
                apply=options["apply"],
                expected_sha256=options["expected_sha256"],
            )
        except StagingError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
