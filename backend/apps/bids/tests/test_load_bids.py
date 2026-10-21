"""initial-data/bid_sample loading without LLM (specs/12 §3)."""

import pytest

from apps.bids.loader import load_bids
from apps.bids.models import BidAttachment, BidNotice

pytestmark = pytest.mark.django_db


def test_load_bids_without_llm():
    summary = load_bids()
    assert summary["created"] == 8
    assert summary["extracted"] == 0
    assert BidAttachment.objects.count() == 32
    assert set(BidNotice.objects.values_list("outcome", flat=True)) == {"WON"}
    assert set(BidNotice.objects.values_list("processing_status", flat=True)) == {"DRAFT"}
    for bid in BidNotice.objects.all():
        assert bid.attachments.filter(is_primary=True).count() == 1

    sample = BidNotice.objects.get(source_ref="20230342721")
    primary = sample.attachments.get(is_primary=True)
    assert primary.role == "bid_notice"
    assert not BidAttachment.objects.filter(
        document__original_filename__contains="Zone.Identifier"
    ).exists()

    again = load_bids()
    assert (again["created"], again["skipped"]) == (0, 8)
