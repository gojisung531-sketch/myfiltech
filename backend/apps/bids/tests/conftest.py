import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.bids.models import BidNotice
from apps.bids.services import add_attachment

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = "20230342721"


def extract_output() -> dict:
    return json.loads((FIXTURES / f"bid_{SAMPLE}.json").read_text(encoding="utf-8"))


def schema_responder(extract=None, fit=None):
    """Answer each LLM task by the shape of its output schema."""

    def respond(request):
        properties = (request.json_schema or {}).get("properties") or {}
        if "notice" in properties:
            return extract if extract is not None else extract_output()
        if "fit_score" in properties:
            return fit or {
                "fit_score": 60,
                "is_power_plant": True,
                "reason": "GT 흡기 필터",
                "matched": [],
            }
        if "code" in properties:  # document.classify: keep the rule result
            return {"code": "", "confidence": 0, "reason": ""}
        if "fields" in properties:  # document.extract_metadata
            return {"fields": [], "transcript": ""}
        raise AssertionError(f"unexpected schema: {list(properties)}")

    return respond


@pytest.fixture
def sample_bid(db):
    """Bid 20230342721 with its four real attachments (parsed, rule-classified)."""
    folder = Path(settings.INITIAL_DATA_DIR) / "bid_sample" / "won" / SAMPLE
    bid = BidNotice.objects.create(title=SAMPLE, source_ref=SAMPLE, outcome=BidNotice.Outcome.WON)
    for path in sorted(
        p for p in folder.iterdir() if p.is_file() and "Zone.Identifier" not in p.name
    ):
        with path.open("rb") as handle:
            add_attachment(bid, file=handle, filename=path.name)
    return bid
