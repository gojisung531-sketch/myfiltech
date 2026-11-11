"""Load a local, human-reviewed company/source manifest; no extraction or jobs."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.company.manual_registration import register_reviewed


class Command(BaseCommand):
    help = "Plan/apply reviewed company facts and typed certificates without downstream work"

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup", type=Path)

    def handle(self, *args, **options):
        try:
            manifest = json.loads(options["manifest"].read_text(encoding="utf-8-sig"))
            result = register_reviewed(manifest, apply=options["apply"], backup=options["backup"])
        except (ValueError, KeyError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps({k: v for k, v in result.items() if k != "inventory"}, ensure_ascii=False)
        )
