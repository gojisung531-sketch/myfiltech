import json

from django.core.management.base import BaseCommand, CommandError

from apps.bids.loader import load_bids
from apps.documents.loader import COMPANY_SEED_BLOCKED_MESSAGE


class Command(BaseCommand):
    help = "Load initial-data/ into the database (specs/12-initial-data.md)."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["skip", "update"], default="skip")
        parser.add_argument("--only", choices=["company", "bids"], default=None)
        parser.add_argument(
            "--no-llm", action="store_true", help="Rules only; bids stay DRAFT (no LLM calls)."
        )

    def handle(self, *args, mode, only, no_llm, **options):
        def report(progress, message=""):
            self.stdout.write(f"[{progress:3d}%] {message}")

        summary = {}
        try:
            if only in (None, "company"):
                # Personal build: virtual company seed is blocked.
                if only == "company":
                    raise CommandError(COMPANY_SEED_BLOCKED_MESSAGE)
                self.stdout.write(COMPANY_SEED_BLOCKED_MESSAGE)
            if only in (None, "bids"):
                summary["bids"] = load_bids(mode=mode, use_llm=not no_llm, report=report)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
        failed = sum(len(part.get("failed", [])) for part in summary.values())
        if failed:
            raise CommandError(f"{failed}건 처리 실패")
