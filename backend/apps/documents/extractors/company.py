"""Rule extractors for company documents (specs/06 §5.1).

The initial-data company PDFs have a fixed layout, so these must extract every field
without the LLM. Each extractor returns {field_key: MetaValue}.
"""

import re

from apps.core.units import parse_airflow, parse_dimension, parse_number, parse_pressure

from .common import (
    MetaValue,
    blank_if_dash,
    find_table,
    glued,
    key_values,
    lookup,
    notes_from_text,
    one_line,
    parse_date,
    table_dict,
)

FILTER_TYPE_KEYWORDS = [
    (r"카트리지|펄스|cartridge|pulse", "CARTRIDGE_PULSE"),
    (r"V-?bank", "V_BANK"),
    (r"미니\s*플리트|HEPA|ULPA|mini-?pleat", "MINI_PLEAT_HEPA"),
    (r"포켓|백\s*필터|bag|pocket", "POCKET_BAG"),
    (r"패널|panel", "PANEL"),
    (r"데미스터|demister", "DEMISTER"),
    (r"카본|활성탄|carbon|chemical", "CARBON"),
]


def classify_filter_type(text: str) -> str:
    for pattern, code in FILTER_TYPE_KEYWORDS:
        if re.search(pattern, text or "", re.I):
            return code
    return "OTHER"


def _kv(kv, *labels, transform=None, unit=""):
    found = lookup(kv, *labels)
    if found is None:
        return None
    raw, page = found
    raw = one_line(raw)
    if raw in ("", "-"):
        return MetaValue(None, raw, unit, page=page, quote=f"{labels[0]}: {raw}")
    value = transform(raw) if transform else raw
    return MetaValue(value, raw, unit, page=page, quote=f"{labels[0]}: {raw}")


def _put(result: dict, key: str, item: MetaValue | None) -> None:
    if item is not None:
        result[key] = item


def extract_datasheet(text: str, tables: list[dict]) -> dict[str, MetaValue]:
    kv = key_values(tables)
    result: dict[str, MetaValue] = {}

    model = _kv(kv, "모델명")
    _put(result, "model_no", model)
    model_no = model.value if model else ""

    kind = _kv(kv, "형식")
    if kind:
        result["filter_type"] = MetaValue(classify_filter_type(kind.raw), kind.raw, page=kind.page)
    title = re.search(rf"^{re.escape(model_no)}\s+(.+)$", text, re.M) if model_no else None
    if title:
        result["product_name"] = MetaValue(title.group(1).strip(), title.group(0), page=1)
    elif kind:
        result["product_name"] = MetaValue(kind.raw, kind.raw, page=kind.page)

    usage = re.search(r"주 용도는\s*(.+?)입니다", text.replace("\n", " "))
    if usage:
        result["application"] = MetaValue(usage.group(1).strip(), usage.group(0), page=1)

    _put(result, "dimension", _kv(kv, "외형 치수", transform=parse_dimension, unit="mm"))
    _put(result, "media", _kv(kv, "여재"))
    frame = _kv(kv, "프레임")
    if frame and frame.value:
        option = re.search(r"\(옵션:\s*(.+?)\)", frame.raw)
        material = frame.raw[: option.start()].strip() if option else frame.raw
        result["frame_material"] = MetaValue(material, frame.raw, page=frame.page)
        options = []
        if option:
            parts = re.match(r"(\S+)\s*프레임\s*(\S+?)\s*,\s*(.+)", option.group(1))
            if parts:
                options.append({"material": parts[1], "model": parts[2], "note": parts[3].strip()})
            else:
                options.append({"material": option.group(1), "model": "", "note": ""})
        result["frame_options"] = MetaValue(options, frame.raw, page=frame.page)
    _put(result, "gasket", _kv(kv, "개스킷"))
    _put(result, "rated_airflow_m3h", _kv(kv, "정격 풍량", transform=parse_airflow, unit="m3/h"))
    _put(result, "initial_dp_pa", _kv(kv, "초기 차압", transform=parse_pressure, unit="Pa"))
    _put(result, "final_dp_pa", _kv(kv, "권장 최종 차압", transform=parse_pressure, unit="Pa"))
    _put(result, "iso16890_class", _kv(kv, "ISO 16890"))
    _put(result, "iso29461_class", _kv(kv, "ISO 29461"))
    _put(result, "en1822_class", _kv(kv, "EN 1822"))
    _put(result, "max_temp_c", _kv(kv, "사용 온도", transform=parse_number, unit="°C"))
    _put(result, "max_rh", _kv(kv, "사용 습도", transform=parse_number, unit="%RH"))
    _put(result, "fire_rating", _kv(kv, "난연"))

    curve_table = find_table(tables, "풍량")
    if curve_table and len(curve_table["rows"]) >= 2:
        flows, drops = curve_table["rows"][0][1:], curve_table["rows"][1][1:]
        curve = [
            {"airflow_m3h": parse_number(f), "dp_pa": parse_number(d)}
            for f, d in zip(flows, drops, strict=False)
            if parse_number(f) is not None and parse_number(d) is not None
        ]
        result["airflow_dp_curve"] = MetaValue(curve, page=curve_table["page"])

    reports_table = find_table(tables, "성적서 번호")
    if reports_table:
        reports = [
            {
                "report_no": one_line(r[0]),
                "standard": one_line(r[1]),
                "issue_date": parse_date(r[2]),
                "result": one_line(r[3]),
            }
            for r in reports_table["rows"][1:]
            if len(r) >= 4
        ]
        result["related_test_reports"] = MetaValue(reports, page=reports_table["page"])
        en779 = next((r for r in reports if "EN 779" in r["standard"]), None)
        if en779:
            result["en779_class"] = MetaValue(
                en779["result"], f"{en779['report_no']} {en779['standard']}"
            )

    revision = re.search(r"Rev\.\s*\d+\s*·\s*\d{4}-\d{2}", text)
    if revision:
        result["revision"] = MetaValue(revision.group(0), revision.group(0), page=1)
    return result


STANDARD_FAMILIES = [
    (r"ISO\s*16890", "ISO16890"),
    (r"ISO\s*29461", "ISO29461"),
    (r"EN\s*1822", "EN1822"),
    (r"EN\s*779", "EN779"),
    (r"ASHRAE\s*52\.1", "ASHRAE52_1"),
    (r"ASHRAE\s*52\.2", "ASHRAE52_2"),
    (r"UL\s*900", "UL900"),
    (r"\bKS\b", "KS"),
]


def standard_family(standard: str) -> str:
    for pattern, code in STANDARD_FAMILIES:
        if re.search(pattern, standard or "", re.I):
            return code
    return "OTHER"


def extract_test_report(text: str, tables: list[dict]) -> dict[str, MetaValue]:
    kv = key_values([t for t in tables if t.get("page") == 1] or tables[:1])
    result: dict[str, MetaValue] = {}
    for key, label in [
        ("report_no", "성적서 번호"),
        ("client", "의뢰자"),
        ("sample_name", "시료명"),
        ("model_no", "모델명"),
        ("standard", "시험 규격"),
        ("lab_name", "시험 기관"),
        ("lab_accreditation", "인정 현황"),
        ("result_class", "판정 결과"),
    ]:
        _put(result, key, _kv(kv, label))
    _put(result, "sample_dimension", _kv(kv, "시료 치수", transform=parse_dimension, unit="mm"))
    _put(result, "test_date", _kv(kv, "시험 일자", transform=parse_date))
    _put(result, "issue_date", _kv(kv, "발행 일자", transform=parse_date))

    conditions_table = next(
        (t for t in tables if t["rows"] and t["rows"][0][:2] == ["항목", "조건"]), None
    )
    results_table = next(
        (t for t in tables if t["rows"] and t["rows"][0][:2] == ["항목", "결과"]), None
    )
    conditions = table_dict(conditions_table)
    results = table_dict(results_table)
    page = (results_table or conditions_table or {}).get("page")

    efficiency = []
    for table in tables:
        rows = table["rows"]
        if rows and one_line(rows[0][0]).startswith("입경 범위") and len(rows) >= 2:
            for size, eff in zip(rows[0][1:], rows[1][1:], strict=False):
                efficiency.append({"size_um": one_line(size), "efficiency_pct": parse_number(eff)})
    if efficiency:
        result["efficiency_by_size"] = MetaValue(efficiency, page=page)
        results["입경별 초기 분진포집효율"] = efficiency
    if conditions:
        result["conditions"] = MetaValue(conditions, page=conditions_table["page"])
    if results:
        result["results"] = MetaValue(results, page=page)

    def from_results(key, label, transform=parse_number, unit=""):
        raw = results.get(label)
        if raw is None or isinstance(raw, list):
            return
        value = None if raw in ("", "-") else transform(raw)
        result[key] = MetaValue(value, raw, unit, page=page, quote=f"{label}: {raw}")

    airflow = conditions.get("시험 풍량")
    if airflow:
        result["test_airflow_m3h"] = MetaValue(
            parse_airflow(airflow), airflow, "m3/h", page=conditions_table["page"]
        )
    for key, label in [("test_aerosol", "시험 에어로졸"), ("conditioning", "컨디셔닝")]:
        if conditions.get(label):
            result[key] = MetaValue(conditions[label], conditions[label], page=page)

    initial = next((v for k, v in results.items() if k.startswith("초기 차압")), None)
    if initial:
        result["initial_dp_pa"] = MetaValue(parse_pressure(initial), initial, "Pa", page=page)
    from_results("epm1", "ePM1 (min/평균)", unit="%")
    from_results("epm2_5", "ePM2.5", unit="%")
    from_results("epm10", "ePM10", unit="%")
    from_results("coarse", "ISO Coarse (초기 중량법)", unit="%")
    from_results("mpps_um", "MPPS", unit="µm")
    from_results("integral_eff", "MPPS 전체(integral) 효율", unit="%")
    from_results("local_eff", "국부(local) 효율", transform=blank_if_dash)
    from_results("leak_test", "누설 시험", transform=blank_if_dash)
    from_results("dust_holding_g", "분진 보유량", unit="g")
    from_results("eff_0_4um_initial", "0.4 µm 초기 효율", unit="%")
    from_results("eff_0_4um_conditioned", "0.4 µm 컨디셔닝 후 효율", unit="%")

    notes = notes_from_text(text)
    if conditions.get("비고"):
        notes.insert(0, conditions["비고"])
    if notes:
        result["notes"] = MetaValue("\n".join(notes), "\n".join(notes), page=page)
    return result


def extract_certificate(text: str, tables: list[dict]) -> dict[str, MetaValue]:
    kv = key_values(tables)
    result: dict[str, MetaValue] = {}
    cert_no = _kv(kv, "인증 번호")
    _put(result, "cert_no", cert_no)
    _put(result, "holder", _kv(kv, "인증 대상"))
    _put(result, "scope", _kv(kv, "인증 범위"))
    _put(result, "issuer", _kv(kv, "발급 기관"))
    _put(result, "issue_date", _kv(kv, "최초/갱신 인증일", "인증일", transform=parse_date))

    validity = _kv(kv, "유효 기간")
    if validity and validity.raw:
        dates = re.findall(r"\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2}", validity.raw)
        if dates:
            result["valid_from"] = MetaValue(parse_date(dates[0]), validity.raw, page=validity.page)
            result["valid_until"] = MetaValue(
                parse_date(dates[-1]), validity.raw, page=validity.page
            )

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if cert_no and cert_no.value:
        header = next((i for i, line in enumerate(lines) if cert_no.value in line), None)
        if header is not None and header + 2 < len(lines):
            result["cert_name"] = MetaValue(lines[header + 1], lines[header + 1], page=1)
            result["standard"] = MetaValue(lines[header + 2], lines[header + 2], page=1)

    scope = result.get("scope")
    if scope and scope.value:
        codes = re.findall(r"세부품명번호\s*[:：]?\s*([0-9]{4,10}x*)", scope.value)
        result["product_codes"] = MetaValue(codes, scope.raw, page=scope.page)
    return result


def extract_delivery_record(text: str, tables: list[dict]) -> dict[str, MetaValue]:
    result: dict[str, MetaValue] = {}
    as_of = re.search(r"(\d{4}-\d{2})\s*기준", text)
    if as_of:
        result["as_of"] = MetaValue(as_of.group(1), as_of.group(0), page=1)

    table = find_table(tables, "납품 시기")
    if not table:
        return result
    header = [one_line(c) for c in table["rows"][0]]
    default_unit = "EA" if "EA" in "".join(header) else ""
    records = []
    for row in table["rows"][1:]:
        if len(row) < 6:
            continue
        cells = dict(zip(header, row, strict=False))
        models = [m.strip() for m in one_line(cells.get("모델")).split("/") if m.strip()]
        quantities = []
        for index, qty_text in enumerate(one_line(cells.get("수량(EA)")).split("/")):
            qty = parse_number(qty_text)
            if qty is None:
                continue
            unit_match = re.search(r"\d\s*([^\d\s,]+)\s*$", qty_text.strip())
            quantities.append(
                {
                    "model": models[index]
                    if index < len(models)
                    else (models[0] if models else ""),
                    "qty": int(qty) if qty.is_integer() else qty,
                    "unit": unit_match.group(1) if unit_match else default_unit,
                }
            )
        records.append(
            {
                "delivered_ym": one_line(cells.get("납품 시기")),
                "client": glued(cells.get("발주처")),
                "project_name": one_line(cells.get("사업명")),
                "item_desc": one_line(cells.get("품목")),
                "models": models,
                "quantities": quantities,
                "notes": blank_if_dash(cells.get("비고")),
            }
        )
    result["records"] = MetaValue(records, page=table["page"])
    return result


EXTRACTORS = {
    "datasheet": extract_datasheet,
    "test_report": extract_test_report,
    "certificate": extract_certificate,
    "delivery_record": extract_delivery_record,
}
