"""Unit normalization for filter specs (specs/06-document-processing.md §5).

Canonical units: pressure Pa, airflow m³/h, length mm.
"""

import re

PRESSURE_TO_PA = {
    "pa": 1.0,
    "kpa": 1000.0,
    "mmaq": 9.80665,
    "mmh2o": 9.80665,
    "inh2o": 249.089,
    "in.wg": 249.089,
    "inwg": 249.089,
    "inwc": 249.089,
}

AIRFLOW_TO_M3H = {
    "m3/h": 1.0,
    "cmh": 1.0,
    "m3/min": 60.0,
    "cmm": 60.0,
    "m3/s": 3600.0,
    "cfm": 1.699011,
}

LENGTH_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4, "in": 25.4, '"': 25.4}

_NUMBER = r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?"

_UNIT_ALIASES = {
    "㎜": "mm",
    "㎝": "cm",
    "㎥": "m3",
    "m³": "m3",
    "″": '"',
    "”": '"',
    "“": '"',
    "''": '"',
    "’’": '"',
    "‘‘": '"',
    "mmh₂o": "mmh2o",
    "inh₂o": "inh2o",
}


def parse_number(text) -> float | None:
    """'1,764,000' → 1764000.0; returns None when no number is present."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = re.search(_NUMBER, str(text))
    return float(match.group(0).replace(",", "")) if match else None


def _normalize_unit(unit: str) -> str:
    unit = unit.strip()
    for src, dst in _UNIT_ALIASES.items():
        unit = unit.replace(src, dst)
    return unit.lower().replace(" ", "").replace("³", "3")


def to_pa(value: float, unit: str) -> float:
    return value * PRESSURE_TO_PA[_normalize_unit(unit)]


def to_m3h(value: float, unit: str) -> float:
    return value * AIRFLOW_TO_M3H[_normalize_unit(unit)]


def to_mm(value: float, unit: str) -> float:
    return value * LENGTH_TO_MM[_normalize_unit(unit)]


_PRESSURE_RE = re.compile(
    rf"({_NUMBER})\s*(kPa|Pa|mm\s*Aq|mm\s*H2O|mmH₂O|in\.?\s*H2O|in\.?\s*wg|in\.?\s*wc)", re.I
)
_AIRFLOW_RE = re.compile(
    rf"({_NUMBER})\s*(CFM|CMH|CMM|(?:m3|m³|㎥)\s*/\s*(?:h|hr|min|s|sec))", re.I
)


def _apply_aliases(text: str) -> str:
    for alias, unit in _UNIT_ALIASES.items():
        text = text.replace(alias, unit)
    return text


def parse_pressure(text: str) -> float | None:
    """'0.71 inH2O' → 176.85 (Pa). Returns None when no pressure value is found."""
    match = _PRESSURE_RE.search(_apply_aliases(text or ""))
    if not match:
        return None
    unit = re.sub(r"\s+", "", match.group(2)).replace("in.", "in")
    return round(to_pa(parse_number(match.group(1)), unit), 3)


def parse_airflow(text: str) -> float | None:
    """'2,500CFM' → 4247.53 (m³/h); '0.83㎥/s' → 2988.0."""
    match = _AIRFLOW_RE.search(_apply_aliases(text or ""))
    if not match:
        return None
    unit = _normalize_unit(match.group(2)).replace("/hr", "/h").replace("/sec", "/s")
    return round(to_m3h(parse_number(match.group(1)), unit), 3)


_GE = r"이상|More than|at least|≥|>=|min(?:imum)?\.?"
_LE = r"이하|이내|Less than|at most|≤|<=|max(?:imum)?\.?"
_GT = r"초과|over|greater than"
_LT = r"미만|under|below"


def parse_comparison(text: str) -> dict | None:
    """Parse a requirement such as '95.4% 이상' or 'Less than 100'.

    Returns {operator, value, value_max?, unit?, raw}; operator is one of
    '>=', '<=', '>', '<', '==', 'range'.
    """
    if not text:
        return None
    raw = text.strip()
    unit_token = r"%|[A-Za-zµ㎜㎥][A-Za-z0-9µ㎜㎥³/]*"
    range_match = re.search(
        rf"({_NUMBER})\s*({unit_token})?\s*[~～\-–]\s*({_NUMBER})\s*({unit_token})?", raw
    )
    unit_match = re.search(rf"(?:{_NUMBER})\s*({unit_token})", raw)
    unit = unit_match.group(1) if unit_match else None
    if range_match and not re.search(rf"{_GE}|{_LE}|{_GT}|{_LT}", raw, re.I):
        return {
            "operator": "range",
            "value": parse_number(range_match.group(1)),
            "value_max": parse_number(range_match.group(3)),
            "unit": range_match.group(4) or range_match.group(2) or unit,
            "raw": raw,
        }
    value = parse_number(raw)
    if value is None:
        return None
    for pattern, operator in ((_GE, ">="), (_LE, "<="), (_GT, ">"), (_LT, "<")):
        if re.search(pattern, raw, re.I):
            return {"operator": operator, "value": value, "unit": unit, "raw": raw}
    return {"operator": "==", "value": value, "unit": unit, "raw": raw}


_DIA = r"(?:OD|Ø|ø|φ|Φ)\s*(?=\d)"
_TRIPLE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:mm|")?\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*(?:mm|")?'
    r'(?:\s*[×xX*]\s*(\d+(?:\.\d+)?)(?:\s*[~～\-–]\s*(\d+(?:\.\d+)?))?)?\s*(mm|"|inch)?',
    re.I,
)


def parse_dimension(text: str) -> dict | None:
    """Parse filter dimensions into mm.

    '592 × 592 × 292 mm'            → w/h/d
    '24 x 24 x 12"'                 → inches converted to mm
    '610×610×400~600mm'             → d=400, d_max=600
    'OD445 x OD324 x L660mm'        → dia=445, dia2=324, len=660
    '원통 Ø324 × 660 mm + 원추 Ø324/Ø215 × 660 mm' → dia=324, dia2=215, len=660
    When both inch and mm notations are given, the mm one wins.
    """
    if not text:
        return None
    raw = text.strip()
    src = _apply_aliases(raw)
    empty = {"w": None, "h": None, "d": None, "d_max": None, "dia": None, "dia2": None, "len": None}

    if re.search(_DIA, src):
        inch = '"' in src and "mm" not in src.lower()
        factor = 25.4 if inch else 1.0
        diameters = list(
            dict.fromkeys(float(v) for v in re.findall(rf"{_DIA}(\d+(?:\.\d+)?)", src))
        )
        lengths = re.findall(r'(?:\bL|×|x|\*)\s*(\d+(?:\.\d+)?)\s*(?:mm|"|$|\s)', src, re.I)
        return {
            **empty,
            "dia": round(diameters[0] * factor, 1) if diameters else None,
            "dia2": round(min(diameters[1:]) * factor, 1) if len(diameters) > 1 else None,
            "len": round(float(lengths[0]) * factor, 1) if lengths else None,
            "unit": "mm",
            "raw": raw,
        }

    matches = list(_TRIPLE.finditer(src))
    if not matches:
        return None
    match = next((m for m in matches if (m.group(5) or "").lower() == "mm"), matches[0])
    span = match.group(0)
    inch = (match.group(5) or "").lower() in ('"', "inch") or '"' in span
    factor = 25.4 if inch else 1.0

    def mm(value):
        return round(float(value) * factor, 1) if value else None

    return {
        **empty,
        "w": mm(match.group(1)),
        "h": mm(match.group(2)),
        "d": mm(match.group(3)),
        "d_max": mm(match.group(4)),
        "unit": "mm",
        "raw": raw,
    }
