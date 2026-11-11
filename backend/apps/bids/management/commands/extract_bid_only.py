"""Run one existing bid's extraction without draining jobs or calculating downstream results."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.bids.extraction import BidExtractionError, extract_bid
from apps.bids.models import BidNotice


class Command(BaseCommand):
    help = "지정 공고 하나만 문서 읽기·요구조건 추출합니다. 실제 LLM 호출이 발생합니다."

    def add_arguments(self, parser):
        parser.add_argument("--bid-id", type=int, required=True)

    def handle(self, *args, **options):
        bid = BidNotice.objects.filter(pk=options["bid_id"]).first()
        if bid is None:
            raise CommandError("지정 공고가 없습니다.")
        try:
            result = extract_bid(bid, extraction_only=True)
        except BidExtractionError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
