"""Filter grade systems and comparisons (specs/08 §5.1).

Grades are only compared within the same system; cross-system equivalence is never assumed.
"""

import re
from dataclasses import dataclass

EN1822_ORDER = ["E10", "E11", "E12", "H13", "H14", "U15", "U16", "U17"]
ISO29461_ORDER = [f"T{n}" for n in range(5, 13)]
EN779_ORDER = ["G1", "G2", "G3", "G4", "M5", "M6", "F7", "F8", "F9"]
ISO16890_GROUPS = {"COARSE": 0, "EPM10": 1, "EPM2.5": 2, "EPM1": 3}

FAMILY_LABELS = {
    "ISO16890": "ISO 16890",
    "ISO29461": "ISO 29461-1",
    "EN1822": "EN 1822",
    "EN779": "EN 779",
    "ASHRAE52_2": "ASHRAE 52.2 (MERV)",
    "ASHRAE52_1": "ASHRAE 52.1",
}

_FAMILY_HINTS = [
    (r"16890|ePM|coarse", "ISO16890"),
    (r"29461", "ISO29461"),
    (r"1822|HEPA|ULPA|EPA", "EN1822"),
    (r"779", "EN779"),
    (r"52[._ ]?2|MERV", "ASHRAE52_2"),
    (r"52[._ ]?1|arrestance", "ASHRAE52_1"),
]


@dataclass(frozen=True)
class Grade:
    family: str
    label: str
    rank: float

    def __str__(self):
        return f"{FAMILY_LABELS.get(self.family, self.family)} {self.label}"


def family_of(text: str | None) -> str | None:
    for pattern, family in _FAMILY_HINTS:
        if re.search(pattern, text or "", re.I):
            return family
    return None


def _ordered(order: list[str], label: str, family: str) -> Grade | None:
    return Grade(family, label, order.index(label)) if label in order else None


def parse_grade(text: str | None, family: str | None = None) -> Grade | None:
    """Parse one grade. `family` (e.g. from the requirement's standard) disambiguates."""
    if not text:
        return None
    text = str(text).strip()
    family = family or family_of(text)
    candidates = parse_grades(text)
    if family:
        candidates = [g for g in candidates if g.family == family]
    return candidates[0] if candidates else None


def parse_grades(text: str | None) -> list[Grade]:
    """All grades mentioned in a text, e.g. 'EN779 F9 (ASHRAE 52.2 MERV 15 이상)'."""
    text = text or ""
    found: list[Grade] = []
    for match in re.finditer(
        r"(ePM\s?1(?![0-9])|ePM\s?2[.,]5|ePM\s?10|Coarse)\s*(\d{1,3})\s*%", text, re.I
    ):
        group = match.group(1).upper().replace(" ", "").replace(",", ".")
        group = "COARSE" if group.startswith("COARSE") else group
        pct = int(match.group(2))
        label = f"{'Coarse' if group == 'COARSE' else group.replace('EPM', 'ePM')} {pct}%"
        found.append(Grade("ISO16890", label, ISO16890_GROUPS[group] * 1000 + pct))
    for match in re.finditer(r"(?<![A-Za-z])([EHU])\s?(1[0-7])(?!\d)", text):
        grade = _ordered(EN1822_ORDER, f"{match.group(1)}{match.group(2)}", "EN1822")
        if grade:
            found.append(grade)
    for match in re.finditer(r"(?<![A-Za-z])T\s?(\d{1,2})(?!\d)", text):
        grade = _ordered(ISO29461_ORDER, f"T{match.group(1)}", "ISO29461")
        if grade:
            found.append(grade)
    for match in re.finditer(r"(?<![A-Za-z])([GMF])\s?([1-9])(?!\d)", text):
        grade = _ordered(EN779_ORDER, f"{match.group(1)}{match.group(2)}", "EN779")
        if grade:
            found.append(grade)
    for match in re.finditer(r"MERV\s?(\d{1,2})", text, re.I):
        found.append(Grade("ASHRAE52_2", f"MERV {int(match.group(1))}", int(match.group(1))))
    return found


def meets(actual: Grade, required: Grade) -> bool | None:
    """True/False within the same system; None when systems differ (not comparable).

    ISO 16890 groups (ePM1, ePM2.5, ...) measure different particle sizes, so only the same
    group is compared.
    """
    if actual.family != required.family:
        return None
    if actual.family == "ISO16890" and int(actual.rank // 1000) != int(required.rank // 1000):
        return None
    return actual.rank >= required.rank


def product_grades(product) -> list[Grade]:
    grades: list[Grade] = []
    for text, family in (
        (product.iso16890_class, "ISO16890"),
        (product.iso29461_class, "ISO29461"),
        (product.en1822_class, "EN1822"),
        (product.en779_class, "EN779"),
    ):
        grade = parse_grade(text, family)
        if grade:
            grades.append(grade)
    if product.ashrae_merv:
        grades.append(Grade("ASHRAE52_2", f"MERV {product.ashrae_merv}", product.ashrae_merv))
    return grades


def required_grade(normalized: dict) -> Grade | None:
    """Grade from a FILTER_GRADE / TRACK_RECORD normalized value: {standard, class}."""
    if not normalized:
        return None
    family = family_of(normalized.get("standard"))
    return parse_grade(normalized.get("class") or normalized.get("raw"), family)
