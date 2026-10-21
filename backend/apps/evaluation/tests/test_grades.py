import pytest

from apps.evaluation.grades import family_of, meets, parse_grade, parse_grades, required_grade


@pytest.mark.parametrize(
    "text,family,label",
    [
        ("EN 1822(E 11)", None, "E11"),
        ("H13", "EN1822", "H13"),
        ("ISO ePM1 85%", None, "ePM1 85%"),
        ("ISO Coarse 65%", None, "Coarse 65%"),
        ("T9", "ISO29461", "T9"),
        ("EN779 기준 F9등급", None, "F9"),
        ("MERV 14이상", None, "MERV 14"),
    ],
)
def test_parse_grade(text, family, label):
    assert parse_grade(text, family).label == label


def test_parse_grades_finds_every_system():
    grades = parse_grades("EN779 기준 F9등급 (ASHRAE 52.2 기준 MERV 15 이상)")
    assert {(g.family, g.label) for g in grades} == {("EN779", "F9"), ("ASHRAE52_2", "MERV 15")}


def test_meets_within_same_system_only():
    e12, e11, h13 = (parse_grade(x, "EN1822") for x in ("E12", "E11", "H13"))
    assert meets(e12, e11) is True
    assert meets(e11, e12) is False
    assert meets(h13, e12) is True
    f9 = parse_grade("F9", "EN779")
    t9 = parse_grade("T9", "ISO29461")
    assert meets(t9, f9) is None  # no cross-system equivalence
    epm1_85 = parse_grade("ePM1 85%")
    assert meets(epm1_85, parse_grade("ePM1 80%")) is True
    assert meets(epm1_85, parse_grade("ePM2.5 70%")) is None  # different ISO 16890 groups


def test_required_grade_and_family():
    assert required_grade({"standard": "EN1822", "class": "E 11"}).label == "E11"
    assert required_grade({}) is None
    assert family_of("ASHRAE 52.2") == "ASHRAE52_2"
    assert family_of("ASHRAE52_2") == "ASHRAE52_2"  # normalized code
    assert family_of("EN 779:2012") == "EN779"
