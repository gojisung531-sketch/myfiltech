"""Rule-based document classification (specs/06 §3). LLM fallback is added in Phase 4."""

import re
from dataclasses import dataclass
from pathlib import PurePath

from .models import MetadataSchema

# Folder names used by initial-data/company (highest priority, specs/06 §3.1).
FOLDER_HINTS = {
    "certificates": "certificate",
    "datasheets": "datasheet",
    "records": "delivery_record",
    "test_reports": "test_report",
}

# Body keywords in the first 2,000 characters (specs/06 §3.2).
CONTENT_KEYWORDS = [
    (r"시\s*험\s*성\s*적\s*서|Test Report No\.", "test_report"),
    (r"제품 기술사양서|Technical Data Sheet", "datasheet"),
    (r"납품\s*실적", "delivery_record"),
    (r"인증서|증명서", "certificate"),
    (r"제한\s*경쟁\s*사유", "bid_restriction_reason"),
    (r"물자\s*규격서|구매\s*규격서|시\s*방\s*서", "bid_spec"),
    (r"입찰\s*공고|조달물자.*입찰 공고", "bid_notice"),
]

CONFIDENCE = {"folder": 1.0, "filename": 0.9, "content": 0.85}


@dataclass
class Classification:
    schema: MetadataSchema | None
    confidence: float | None
    method: str  # folder / filename / content / none


def classify(
    *, filename: str, text: str, owner_type: str, path_hint: str | None = None
) -> Classification:
    schemas = list(MetadataSchema.objects.filter(is_active=True, owner_type=owner_type))
    by_code = {s.code: s for s in schemas}

    if path_hint:
        for part in PurePath(path_hint).parts:
            code = FOLDER_HINTS.get(part)
            if code in by_code:
                return Classification(by_code[code], CONFIDENCE["folder"], "folder")

    stem = PurePath(filename).stem
    for schema in sorted(schemas, key=lambda s: (s.priority, s.code)):
        if any(re.search(p, stem, re.I) for p in schema.filename_patterns):
            return Classification(schema, CONFIDENCE["filename"], "filename")

    head = (text or "")[:2000]
    for pattern, code in CONTENT_KEYWORDS:
        if code in by_code and re.search(pattern, head, re.I):
            return Classification(by_code[code], CONFIDENCE["content"], "content")

    return Classification(None, None, "none")
