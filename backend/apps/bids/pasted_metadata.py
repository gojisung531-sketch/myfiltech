"""Conservative, local-only pasted notice metadata. Never extracts requirements."""

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from rest_framework.exceptions import ValidationError

from .models import BidNotice

MAX_SOURCE_LENGTH = 200_000
KST = ZoneInfo("Asia/Seoul")
DATETIMES = {"bid_open_at", "bid_close_at", "opening_at", "qualification_deadline_at"}
MONEY = {"budget_krw", "estimated_price_krw"}
FIELDS = (
    "title",
    "notice_no",
    "buyer_org",
    "contracting_org",
    "plant_name",
    "bid_method",
    "procurement_type",
    "item_category_code",
    "item_category_name",
    "budget_krw",
    "estimated_price_krw",
    "bid_open_at",
    "bid_close_at",
    "opening_at",
    "qualification_deadline_at",
    "delivery_terms",
    "delivery_place",
    "warranty_terms",
    "summary",
)
ALIASES = {
    "title": ["공고명", "입찰공고명", "건명", "입찰건명", "공사명", "구매건명"],
    "notice_no": ["공고번호", "입찰공고번호"],
    "buyer_org": ["수요기관", "수요기관명"],
    "contracting_org": ["공고기관", "공고기관명", "발주기관", "발주기관명", "계약기관"],
    "plant_name": ["발전소명", "사업장명"],
    "bid_method": ["계약방법", "입찰방법"],
    "procurement_type": ["조달구분"],
    "item_category_code": ["물품분류번호", "세부품명번호"],
    "item_category_name": ["물품분류명", "세부품명"],
    "budget_krw": ["예산", "예산금액", "사업예산"],
    "estimated_price_krw": ["추정가격"],
    "bid_open_at": ["입찰시작일시", "입찰개시일시", "입찰서제출시작일시", "투찰시작일시"],
    "bid_close_at": [
        "입찰마감일시",
        "입찰신청및입찰마감일시",
        "입찰서제출마감일시",
        "투찰마감일시",
    ],
    "opening_at": ["개찰일시"],
    "qualification_deadline_at": [
        "참가자격등록마감일시",
        "입찰참가자격등록마감일시",
        "입찰참가신청마감일시",
    ],
    "delivery_terms": ["납품조건", "인도조건"],
    "delivery_place": ["납품장소", "납품장소명", "인도장소"],
    "warranty_terms": ["하자보증", "하자보증조건", "하자보증기간", "하자담보책임기간"],
    "summary": ["공고요약"],
}
UNSUPPORTED = [
    "공고일시",
    "공고일자",
    "게시일시",
    "부가세",
    "부가가치세",
    "합계금액",
    "합계",
    "기초금액",
    "예비가기초금액",
    "예비가격기초금액",
    "추정금액",
]
LABELS = {label: field for field, labels in ALIASES.items() for label in labels}
LABELS.update(dict.fromkeys(UNSUPPORTED))
LABEL_PATTERN = "|".join(
    r"\s*".join(map(re.escape, label)) for label in sorted(LABELS, key=len, reverse=True)
)
PREFIX = re.compile(
    r"^\s*(?P<label>" + LABEL_PATTERN + r")(?:(?:\s*[:：]\s*|\s+)(?P<value>.+)|\s*[:：]?\s*)$"
)
INLINE = re.compile(r"(?<!\S)(?P<label>" + LABEL_PATTERN + r")\s*[:：]\s*")
DATE = re.compile(
    r"(?P<y>\d{4})\s*[.\-/년]\s*(?P<m>\d{1,2})\s*[.\-/월]\s*(?P<d>\d{1,2})"
    r"\s*[.일]?\s*(?:\((?P<weekday>[월화수목금토일])(?:요일)?\)\s*)?"
    r"[T\s](?P<h>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
    r"\s*(?P<tz>Z|[+-]\d{2}:\d{2})?"
)


def source_text(value, *, allow_blank=False):
    if not isinstance(value, str) or len(value) > MAX_SOURCE_LENGTH:
        raise ValidationError({"source_text": [f"{MAX_SOURCE_LENGTH}자 이하 문자열이어야 합니다."]})
    if not allow_blank and not value.strip():
        raise ValidationError({"source_text": ["공고 본문을 입력하세요."]})
    return value  # Hash and storage always use the unmodified input.


def source_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(text):
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    return re.sub(
        r"\s+", " ", text.replace("&nbsp;", " ").replace("\xa0", " ").replace("**", "")
    ).strip()


def _label(text):
    return re.sub(r"\s", "", text)


def _horizontal_tables(text):
    """Explicit metadata headers + Markdown separator + equally sized value rows."""
    lines = list(re.finditer(r"[^\r\n]+", text))
    pairs, covered = [], []
    index = 0
    while index + 2 < len(lines):
        header, separator = lines[index : index + 2]
        cells = list(re.finditer(r"[^|]+", header.group().strip().strip("|")))
        labels = [_label(_clean(c.group())) for c in cells]
        separators = [_clean(v) for v in separator.group().strip().strip("|").split("|")]
        if (
            "|" not in header.group()
            or len(separators) != len(labels)
            or sum(label in LABELS for label in labels) < 2
            or not all(re.fullmatch(r":?-{3,}:?", v) for v in separators)
        ):
            index += 1
            continue
        last = index + 2
        while last < len(lines) and "|" in lines[last].group():
            data = lines[last]
            values = data.group().strip().strip("|").split("|")
            if len(values) != len(labels):
                break
            for label, value in zip(labels, values, strict=True):
                if label in LABELS:
                    pairs.append((label, _clean(value), header.start(), data.end()))
            last += 1
        if last > index + 2:
            covered.append((header.start(), lines[last - 1].end()))
            index = last
        else:
            index += 1
    return pairs, covered


def _pairs(text):
    """Keep raw spans; normalize only a working copy, never a returned quote."""
    horizontal, covered = _horizontal_tables(text)
    yield from horizontal
    pending = None
    for segment in re.finditer(r"[^\r\n|\t]+", text):
        if any(start <= segment.start() < end for start, end in covered):
            if pending:
                yield pending[0], "", pending[1], pending[2]
                pending = None
            continue
        if pending and pending[3] and re.search(r"[\r\n]", text[pending[2] : segment.start()]):
            yield pending[0], "", pending[1], pending[2]
            pending = None
        raw = segment.group()
        line_start = text.rfind("\n", 0, segment.start()) + 1
        line_end = text.find("\n", segment.end())
        table_row = "|" in text[line_start : line_end if line_end >= 0 else len(text)]
        value = _clean(raw)
        if not value or re.fullmatch(r"[:\- ]+", value):
            continue
        matches = list(INLINE.finditer(value))
        if matches:
            if pending:
                yield pending[0], "", pending[1], pending[2]
            pending = None
            for i, match in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(value)
                label = _label(match["label"])
                content = value[match.end() : end].strip()
                if content:
                    yield label, content, segment.start(), segment.end()
                else:
                    pending = (label, segment.start(), segment.end(), table_row)
            continue
        match = PREFIX.fullmatch(value)
        if match:
            if pending:
                yield pending[0], "", pending[1], pending[2]
            label = _label(match["label"])
            if match["value"]:
                yield label, match["value"], segment.start(), segment.end()
                pending = None
            else:
                pending = (label, segment.start(), segment.end(), table_row)
        elif pending:
            # Another explicit key/heading is not the value of a missing field.
            if re.search(r"[:：]", value) and not re.fullmatch(r"[\d\s.\-/():+TZ]+", value):
                yield pending[0], "", pending[1], pending[2]
            else:
                yield pending[0], value, pending[1], segment.end()
            pending = None
    if pending:
        yield pending[0], "", pending[1], pending[2]


def _datetime(value):
    match = DATE.fullmatch(value)
    if not match:
        raise ValueError("날짜와 시각을 모두 명시해야 합니다.")
    parts = match.groupdict()
    value = datetime(
        int(parts["y"]),
        int(parts["m"]),
        int(parts["d"]),
        int(parts["h"]),
        int(parts["minute"]),
        int(parts["second"] or 0),
    )
    if parts["weekday"] and "월화수목금토일"[value.weekday()] != parts["weekday"]:
        raise ValueError("날짜와 요일이 다릅니다.")
    if parts["tz"]:
        value = datetime.fromisoformat(value.isoformat() + parts["tz"].replace("Z", "+00:00"))
    else:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST).isoformat()


def _parse(field, value):
    if not value:
        raise ValueError("항목 값이 비어 있습니다.")
    if field in DATETIMES:
        return _datetime(value)
    if field in MONEY:
        match = re.fullmatch(r"(?:₩\s*|KRW\s*)?(\d+|\d{1,3}(?:,\d{3})+)\s*원?", value)
        if not match:
            raise ValueError("금액의 원 단위 정수를 확인하세요.")
        number = int(match[1].replace(",", ""))
        if number > 2**63 - 1:
            raise ValueError("저장 가능한 금액 범위를 초과했습니다.")
        return number
    maximum = BidNotice._meta.get_field(field).max_length
    if maximum and len(value) > maximum:
        raise ValueError(f"{maximum}자 제한을 초과했습니다.")
    return value


def preview(text):
    text = source_text(text)
    candidates = defaultdict(list)
    warnings = []
    invalid = set()
    for label, raw, start, end in _pairs(text):
        field = LABELS[label]
        if field is None:
            warnings.append(
                {
                    "field": None,
                    "code": "UNSUPPORTED_FIELD",
                    "message": f"{label}: 대응 저장 필드가 없어 원문에만 보존합니다.",
                }
            )
            continue
        try:
            value = _parse(field, raw)
        except (ValueError, OverflowError) as exc:
            invalid.add(field)
            warnings.append({"field": field, "code": "INVALID_VALUE", "message": str(exc)})
            continue
        candidates[field].append((value, {"quote": text[start:end]}))
    values, evidence = {}, {}
    for field, options in candidates.items():
        if len({v for v, _ in options}) > 1:
            warnings.append(
                {
                    "field": field,
                    "code": "CONFLICTING_VALUES",
                    "message": "서로 다른 값이 있어 자동 입력하지 않았습니다.",
                }
            )
        elif field not in invalid:
            values[field], evidence[field] = options[0]
            if len(options) > 1:
                warnings.append(
                    {
                        "field": field,
                        "code": "DUPLICATE_VALUE",
                        "message": "같은 값이 반복되어 한 값으로 제시합니다.",
                    }
                )
    for earlier, later in [("bid_open_at", "bid_close_at"), ("bid_close_at", "opening_at")]:
        if earlier in values and later in values and values[earlier] > values[later]:
            for field in (earlier, later):
                values.pop(field)
                evidence.pop(field)
                warnings.append(
                    {
                        "field": field,
                        "code": "DATE_ORDER_CONFLICT",
                        "message": "시작·마감·개찰 시각의 순서를 확인하세요. 자동 입력하지 않았습니다.",
                    }
                )
    if not values:
        warnings.append(
            {
                "field": None,
                "code": "NO_FIELDS_FOUND",
                "message": "확실한 기본 정보를 찾지 못했습니다. 항목명과 값을 확인하세요.",
            }
        )
    return {
        "source_sha256": source_hash(text),
        "values": values,
        "evidence": evidence,
        "warnings": warnings,
    }


def _validated_values(values):
    from .serializers import BidUpdateSerializer

    if not isinstance(values, dict) or set(values) - set(FIELDS):
        raise ValidationError(
            {"notice_metadata": ["values는 허용된 기본 정보 필드의 객체여야 합니다."]}
        )
    normalized = {}
    for field, value in values.items():
        if field in MONEY:
            if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
                raise ValidationError(
                    {"notice_metadata": [f"{field}: 원 단위 정수 또는 null이어야 합니다."]}
                )
            normalized[field] = value
        elif field in DATETIMES:
            try:
                normalized[field] = _datetime(value) if isinstance(value, str) else None
                if value is not None and not isinstance(value, str):
                    raise ValueError("문자열 또는 null이어야 합니다.")
            except (ValueError, OverflowError) as exc:
                raise ValidationError({"notice_metadata": [f"{field}: {exc}"]}) from exc
        elif not isinstance(value, str):
            raise ValidationError({"notice_metadata": [f"{field}: 문자열이어야 합니다."]})
        else:
            normalized[field] = value
    serializer = BidUpdateSerializer(data=normalized, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _json_values(values):
    return {
        key: value.astimezone(KST).isoformat() if isinstance(value, datetime) else value
        for key, value in values.items()
    }


def registration(text, metadata=None, explicit_title=""):
    """Recompute auto evidence; edited fields are manual, including explicit clears."""
    result = (
        preview(text)
        if text.strip()
        else {"source_sha256": source_hash(text), "values": {}, "evidence": {}, "warnings": []}
    )
    values = _validated_values(result["values"])
    origins = dict.fromkeys(values, "SOURCE_TEXT_RULE")
    evidence = dict(result["evidence"])
    edited = set()
    if metadata is not None:
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (ValueError, TypeError) as exc:
                raise ValidationError(
                    {"notice_metadata": ["유효한 JSON 객체 문자열이어야 합니다."]}
                ) from exc
        if not isinstance(metadata, dict) or set(metadata) != {
            "source_sha256",
            "values",
            "edited_fields",
        }:
            raise ValidationError(
                {"notice_metadata": ["source_sha256, values, edited_fields 세 필드가 필요합니다."]}
            )
        if metadata["source_sha256"] != result["source_sha256"]:
            raise ValidationError(
                {
                    "notice_metadata": [
                        "본문 해시가 다릅니다. 현재 본문으로 미리보기를 다시 확인하세요."
                    ]
                }
            )
        fields = metadata["edited_fields"]
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            raise ValidationError(
                {"notice_metadata": ["edited_fields는 필드명 배열이어야 합니다."]}
            )
        supplied = _validated_values(metadata["values"])
        edited = set(fields)
        if len(edited) != len(fields) or not edited <= set(supplied):
            raise ValidationError(
                {
                    "notice_metadata": [
                        "edited_fields는 중복 없이 values에 포함된 필드만 지정하세요."
                    ]
                }
            )
        for field, value in supplied.items():
            if field not in edited and (field not in values or value != values[field]):
                raise ValidationError(
                    {
                        "notice_metadata": [
                            f"{field}: 자동 값이 원문 재검증 결과와 다릅니다. 수정값은 edited_fields로 지정하세요."
                        ]
                    }
                )
            values[field] = value
            if field in edited:
                origins[field] = "MANUAL"
                evidence.pop(field, None)
    if explicit_title:
        title = _validated_values({"title": explicit_title})["title"]
        # A UI may send the verified auto title through the legacy title field too.
        verified_auto = (
            metadata is not None
            and origins.get("title") == "SOURCE_TEXT_RULE"
            and values.get("title") == title
        )
        values["title"] = title
        if not verified_auto:
            origins["title"] = "EXPLICIT_INPUT"
            evidence.pop("title", None)
            edited.add("title")
    saved = {
        "schema": "pasted-notice-metadata.v1",
        "scope": "REGISTRATION_SNAPSHOT",
        "source_sha256": result["source_sha256"],
        "values": _json_values(values),
        "field_sources": origins,
        "evidence": evidence,
        "edited_fields": sorted(edited),
        "warnings": result["warnings"],
    }
    return values, {"locked_fields": sorted(edited), "pasted_notice_metadata": saved}
