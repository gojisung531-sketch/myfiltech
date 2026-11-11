import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.company.report_preview import PreviewError, preview_filtech_reports


class Command(BaseCommand):
    help = "실제 시험성적서 관리대장을 읽기 전용으로 미리 봅니다. DB·LLM을 사용하지 않습니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path")
        parser.add_argument(
            "--output", help="상세 JSON 경로. .venv/b1-preview/ 등 Git 제외 위치 권장"
        )

    def handle(self, *args, **options):
        source = Path(options["xlsx_path"]).resolve()
        output = Path(options["output"]).resolve() if options["output"] else None
        if output and (output == source or output.suffix.lower() != ".json"):
            raise CommandError("출력은 원본과 다른 .json 파일이어야 합니다.")
        try:
            preview = preview_filtech_reports(source)
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("x", encoding="utf-8") as stream:
                    json.dump(preview, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.write("\n")
        except (PreviewError, OSError, ValueError) as exc:
            raise CommandError(
                "미리보기에 실패했습니다. 파일·헤더·출력 경로를 확인하세요. 기존 출력은 덮어쓰지 않습니다."
            ) from exc
        summary = {
            "mode": preview["mode"],
            "file_sha256": preview["file"]["sha256"],
            "sheets": [
                {
                    **{
                        k: sheet[k]
                        for k in (
                            "name",
                            "record_count",
                            "report_number_anchor_count",
                            "model_present_count",
                            "missing",
                            "warnings",
                            "sheet_warnings",
                        )
                    },
                    "merged_range_count": len(sheet["merged_ranges"]),
                    "duplicate_entry_number_groups": len(sheet["duplicate_entry_numbers"]),
                }
                for sheet in preview["sheets"]
            ],
            "duplicate_report_number_groups": len(preview["duplicate_report_numbers"]),
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
