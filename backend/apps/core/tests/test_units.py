import pytest

from apps.core.units import (
    parse_airflow,
    parse_comparison,
    parse_dimension,
    parse_number,
    parse_pressure,
    to_m3h,
    to_mm,
    to_pa,
)


def test_parse_number():
    assert parse_number("1,764,000 m3/h") == 1764000
    assert parse_number("95.4% 이상") == 95.4
    assert parse_number("-") is None
    assert parse_number(None) is None


@pytest.mark.parametrize(
    "value,unit,expected",
    [(8, "mmAq", 78.4532), (1, "mmH2O", 9.80665), (0.71, "inH2O", 176.853), (1, "kPa", 1000)],
)
def test_pressure_units(value, unit, expected):
    assert to_pa(value, unit) == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize(
    "value,unit,expected",
    [(2500, "CFM", 4247.53), (0.83, "m³/s", 2988), (10, "CMM", 600), (3400, "CMH", 3400)],
)
def test_airflow_units(value, unit, expected):
    assert to_m3h(value, unit) == pytest.approx(expected, rel=1e-4)


def test_length_units():
    assert to_mm(24, "inch") == pytest.approx(609.6)
    assert to_mm(1, '"') == pytest.approx(25.4)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0.71 inH2O 이하", 176.853),
        ("0.71 in. H2O", 176.853),
        ("8mmAq 이하(시험풍속 2.5m/sec)", 78.453),
        ("10.2 ㎜H2O이하", 100.028),
        ("130 Pa", 130),
        ("Less than 250", None),
    ],
)
def test_parse_pressure(text, expected):
    assert parse_pressure(text) == (pytest.approx(expected, rel=1e-4) if expected else None)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2,500CFM(4,250m3/h)", 4247.528),
        ("1,760CFM (0.83㎥/s)", 2990.259),
        ("0.83m3/s", 2988.0),
        ("4,250 m³/h", 4250.0),
    ],
)
def test_parse_airflow(text, expected):
    assert parse_airflow(text) == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize(
    "text,operator,value,extra",
    [
        ("95.4% 이상", ">=", 95.4, {"unit": "%"}),
        ("More than 90", ">=", 90, {}),
        ("Less than 100", "<=", 100, {}),
        ("8mmAq 이하", "<=", 8, {"unit": "mmAq"}),
        ("계약 후 150일 이내", "<=", 150, {}),
        ("100 미만", "<", 100, {}),
        ("10 초과", ">", 10, {}),
        ("75% ~ 84%", "range", 75, {"value_max": 84, "unit": "%"}),
        ("0.1 ~ 0.3", "range", 0.1, {"value_max": 0.3, "unit": None}),
        ("최소 1,764,000 m3/h(490 m3/s)이상", ">=", 1764000, {"unit": "m3/h"}),
        ("E12", "==", 12, {}),
    ],
)
def test_parse_comparison(text, operator, value, extra):
    result = parse_comparison(text)
    assert result["operator"] == operator
    assert result["value"] == pytest.approx(value)
    for key, expected in extra.items():
        assert result[key] == expected


def _dim(text):
    result = parse_dimension(text)
    return {k: v for k, v in result.items() if v is not None and k not in ("raw", "unit")}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("592 × 592 × 292 mm", {"w": 592, "h": 592, "d": 292}),
        ("594×594×95㎜", {"w": 594, "h": 594, "d": 95}),
        ('24 x 24 x 12"', {"w": 609.6, "h": 609.6, "d": 304.8}),
        ('24"×24"×16~24"', {"w": 609.6, "h": 609.6, "d": 406.4, "d_max": 609.6}),
        ("610×610×400~600mm", {"w": 610, "h": 610, "d": 400, "d_max": 600}),
        ("668mm x 592mm x 360mm [7P]", {"w": 668, "h": 592, "d": 360}),
        ("594*594*50(W*H*D) 데미스터용", {"w": 594, "h": 594, "d": 50}),
        ('24 x 24 x 4" (nominal) 594 x 594 x 95 mm (nominal)', {"w": 594, "h": 594, "d": 95}),
        ("OD445 x OD324 x L660mm", {"dia": 445, "dia2": 324, "len": 660}),
        ("OD12.75'' x L26\"", {"dia": 323.8, "len": 660.4}),
        (
            "원통 Ø324 × 660 mm + 원추 Ø324/Ø215 × 660 mm (1세트)",
            {"dia": 324, "dia2": 215, "len": 660},
        ),
    ],
)
def test_parse_dimension(text, expected):
    assert _dim(text) == pytest.approx(expected)


def test_parse_dimension_rejects_non_dimension():
    assert parse_dimension("") is None
    assert parse_dimension("규격서 참조") is None
