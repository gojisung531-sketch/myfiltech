"""Creating bids and attachments (specs/04 §3.1)."""

from pathlib import Path

from django.core.files import File
from django.db import transaction

from apps.documents.classify import classify
from apps.documents.models import Document
from apps.documents.parsers import detect_format
from apps.documents.pipeline import parse_step

from .models import BidAttachment, BidNotice

NOTICE_ROLE = "bid_notice"


def _quick_process(document: Document) -> None:
    """Parse and rule-classify right away (no LLM); LLM steps run in EXTRACT_BID."""
    parse_step(document)
    if document.category_source == Document.CategorySource.MANUAL and document.category_id:
        return
    result = classify(
        filename=document.original_filename or document.title,
        text=document.extracted_text,
        owner_type="BID",
    )
    document.category = result.schema
    document.category_confidence = result.confidence
    document.save(update_fields=["category", "category_confidence"])


def add_attachment(
    bid: BidNotice,
    *,
    file=None,
    filename: str = "",
    text: str = "",
    title: str = "",
    sha256: str = "",
    user=None,
) -> BidAttachment:
    """Attach a file (any object with .read/.size/.name) or pasted text to a bid."""
    if file is not None:
        filename = filename or Path(file.name).name
        document = Document(
            owner_type="BID",
            original_filename=filename,
            file_format=detect_format(filename) or "TXT",
            file_size=getattr(file, "size", 0) or 0,
            sha256=sha256,
            created_by=user,
        )
        document.file.save(filename, file if hasattr(file, "chunks") else File(file), save=True)
    else:
        document = Document.objects.create(
            owner_type="BID",
            title=title or "공고 본문",
            source_text=text,
            file_format="TXT",
            created_by=user,
        )
    _quick_process(document)
    order = bid.attachments.count()
    attachment = BidAttachment.objects.create(
        bid=bid,
        document=document,
        role=document.category.code if document.category else "",
        order=order,
    )
    ensure_primary(bid)
    attachment.refresh_from_db()
    return attachment


@transaction.atomic
def ensure_primary(bid: BidNotice) -> None:
    """Keep exactly one primary attachment, preferring the notice document."""
    attachments = list(bid.attachments.select_related("document").order_by("order", "id"))
    if not attachments or any(a.is_primary for a in attachments):
        return
    primary = next((a for a in attachments if a.role == NOTICE_ROLE), attachments[0])
    primary.is_primary = True
    primary.save(update_fields=["is_primary"])


@transaction.atomic
def set_primary(attachment: BidAttachment) -> None:
    BidAttachment.objects.filter(bid=attachment.bid, is_primary=True).exclude(
        pk=attachment.pk
    ).update(is_primary=False)
    attachment.is_primary = True
    attachment.save(update_fields=["is_primary"])
