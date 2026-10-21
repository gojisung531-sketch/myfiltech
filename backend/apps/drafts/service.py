"""Generate / save draft versions (specs/09, specs/05 §3 ④⑤)."""

from django.db import transaction

from .generators import GENERATORS
from .models import DraftDocument, DraftType


class DraftContentError(ValueError):
    """Content does not match the structure of its draft type."""


def draft_title(bid, doc_type: str) -> str:
    return f"{DraftType(doc_type).label} — {bid.title}"[:300]


@transaction.atomic
def generate_draft(bid, doc_type: str, *, new_version: bool = False, user=None, job=None):
    """Create a draft. Overwrites the latest version unless asked for a new one; a version
    the user has edited is never overwritten (a new version is created instead)."""
    content, used_llm = GENERATORS[doc_type](bid, user=user, job=job)
    latest = DraftDocument.latest(bid, doc_type)
    if latest is None or new_version or latest.is_modified:
        return DraftDocument.objects.create(
            bid=bid,
            doc_type=doc_type,
            title=draft_title(bid, doc_type),
            content=content,
            version=(latest.version + 1) if latest else 1,
            used_llm=used_llm,
            created_by=user,
            updated_by=user,
        )
    latest.title = draft_title(bid, doc_type)
    latest.content = content
    latest.used_llm = used_llm
    latest.generated_by = DraftDocument.GeneratedBy.AUTO
    latest.status = DraftDocument.Status.DRAFT
    latest.updated_by = user
    latest.save()
    return latest


def build_content(bid, doc_type: str, user=None) -> dict:
    """Latest saved content, or a rule-based draft (no LLM call) when none exists yet —
    used by the integrated report PDF."""
    latest = DraftDocument.latest(bid, doc_type)
    if latest is not None:
        return latest.content
    content, _ = GENERATORS[doc_type](bid, user=user, allow_llm=False)
    return content


def _require(condition: bool, message: str):
    if not condition:
        raise DraftContentError(message)


def validate_content(doc_type: str, content) -> dict:
    _require(isinstance(content, dict), "초안 내용은 JSON 객체여야 합니다.")
    if doc_type == DraftType.COMPLIANCE_MATRIX:
        _require(isinstance(content.get("header"), dict), "header가 필요합니다.")
        rows = content.get("rows")
        _require(
            isinstance(rows, list) and all(isinstance(r, dict) for r in rows),
            "rows는 행 목록이어야 합니다.",
        )
    elif doc_type == DraftType.BID_CHECKLIST:
        sections = content.get("sections")
        _require(isinstance(sections, list), "sections는 목록이어야 합니다.")
        for section in sections:
            _require(
                isinstance(section, dict) and isinstance(section.get("items"), list),
                "각 섹션에는 title과 items 목록이 필요합니다.",
            )
            for item in section["items"]:
                _require(isinstance(item, dict), "체크리스트 항목은 객체여야 합니다.")
                _require(
                    item.get("status", "TODO") in ("TODO", "DONE", "NA"),
                    "상태는 TODO/DONE/NA 중 하나입니다.",
                )
    elif doc_type == DraftType.TECHNICAL_QUERY:
        _require(isinstance(content.get("header"), dict), "header가 필요합니다.")
        _require(isinstance(content.get("questions"), list), "questions는 목록이어야 합니다.")
    elif doc_type == DraftType.REVIEW_REPORT:
        _require(
            content.get("recommendation") in ("BID", "CONDITIONAL", "NO_BID"),
            "recommendation은 BID / CONDITIONAL / NO_BID 중 하나입니다.",
        )
        _require(isinstance(content.get("key_risks", []), list), "key_risks는 목록이어야 합니다.")
        _require(
            isinstance(content.get("next_actions", []), list), "next_actions는 목록이어야 합니다."
        )
    return content


def save_draft(draft: DraftDocument, *, content=None, status=None, title=None, user=None):
    """Overwrite this version (specs/05 §3 ⑤)."""
    if content is not None:
        draft.content = validate_content(draft.doc_type, content)
        draft.is_modified = True
    if status is not None:
        draft.status = status
    if title:
        draft.title = title[:300]
    draft.updated_by = user
    draft.save()
    return draft
