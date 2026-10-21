import pytest

from apps.documents.classify import classify

pytestmark = pytest.mark.django_db

BID_EXPECTED = {
    "20100219717-00_2010휠터교체 시방서.hwp": "bid_spec",
    "20100219717-00_재입찰공고(2010년휠터교체).hwp": "bid_notice",
    "20100302781-00_공고문(에어필터).hwp": "bid_notice",
    "20100302781-00_물품명세서(에어필터).xls": "bid_item_list",
    "20100302781-00_시방서(에어필터).hwp": "bid_spec",
    "20131021333-00_1382440245277_입찰공고문.hwp": "bid_notice",
    "20131021333-00_1382440245281_구매내역서.xls": "bid_item_list",
    "20131021333-00_1382440245300_한난물자규격서.hwp": "bid_spec",
    "20131021333-00_1382440245318_물품구매계약특수조건.hwp": "bid_contract_terms",
    "20131021333-00_1382440245333_중소기업자간 경쟁제품 중 물품의 구매에 관한 계약이행능력심사 세부기준.hwp": "bid_evaluation_criteria",
    "20131021333-00_1382440245357_첨부3._물품구매계약일반조건_전문.hwp": "bid_contract_terms",
    "20170221175-00_1487049929046_공고서.hwp": "bid_notice",
    "산출내역서.hwp": "bid_item_list",
    "제조 구매 규격서.hwp": "bid_spec",
    "20170333287-00_1490074767008_도면.xlsx": "bid_drawing",
    "구매 청구 품목 명세서.xlsx": "bid_item_list",
    "정비용 기자재 구매규격서.hwp": "bid_spec",
    "제한경쟁사유서.pdf": "bid_restriction_reason",
    "제한 경쟁 사유서.pdf": "bid_restriction_reason",
    "1. 입찰공고문(Final Filter)_v1.hwp": "bid_notice",
    "2. 한난물자규격서_v1.hwp": "bid_spec",
    "3. 물품구매계약특수조건_v1.hwp": "bid_contract_terms",
    "4. 중소기업자간 경쟁제품 중 물품의 구매에 관한 세부기준 개정 전문.hwpx": "bid_evaluation_criteria",
}


@pytest.mark.parametrize("filename,expected", BID_EXPECTED.items())
def test_bid_filenames(filename, expected):
    result = classify(filename=filename, text="", owner_type="BID")
    assert result.schema.code == expected
    assert result.method == "filename"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("company/datasheets/FT-VB500_기술사양서.pdf", "datasheet"),
        ("company/test_reports/AFT-2025-0402_FT-VB500.pdf", "test_report"),
        ("company/certificates/C03_직접생산확인증명서.pdf", "certificate"),
        ("company/records/납품실적_목록_2021-2026.pdf", "delivery_record"),
    ],
)
def test_company_folder_hint_wins(path, expected):
    result = classify(filename="x.pdf", text="", owner_type="COMPANY", path_hint=path)
    assert (result.schema.code, result.confidence) == (expected, 1.0)


def test_company_filename_without_folder():
    result = classify(filename="FT-VB500_기술사양서.pdf", text="", owner_type="COMPANY")
    assert result.schema.code == "datasheet"


def test_content_keywords_fallback():
    result = classify(
        filename="scan_001.pdf", text="시 험 성 적 서\nTest Report No. X", owner_type="COMPANY"
    )
    assert (result.schema.code, result.method) == ("test_report", "content")


def test_owner_type_limits_categories():
    result = classify(filename="공고문.hwp", text="", owner_type="COMPANY")
    assert result.schema is None and result.method == "none"
