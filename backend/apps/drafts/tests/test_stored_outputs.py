"""Stored, rule-only outputs: no source fixtures, extraction or evaluation execution."""

import re
from io import BytesIO

import pdfplumber
import pytest
from openpyxl import load_workbook

from apps.bids.models import BidItem, BidNotice, BidRequirement
from apps.company.models import Product
from apps.documents.models import Document
from apps.drafts import generators, pdf, xlsx
from apps.drafts.models import DraftDocument, DraftType
from apps.drafts.service import generate_draft, report_contents, save_draft
from apps.evaluation.models import RequirementEvaluation
from apps.llm.models import LLMCallLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def stored_bid(fake_llm, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Draft output must not call an LLM, extraction or evaluation")

    monkeypatch.setattr(generators, "run_task", forbidden)
    bid = BidNotice.objects.create(
        title="합성 공고 출력 검증",
        notice_no="SYNTHETIC",
        extra={"b5c_run": {"reference_date": "2026-10-25", "confirmed_item_product_links": 0}},
    )
    document = Document.objects.create(
        owner_type="COMPANY",
        file_format="PDF",
        original_filename="synthetic-catalog.pdf",
        page_count=3,
        extracted_text="SYNTHETIC-MODEL",
    )
    product = Product.objects.create(
        model_no="SYNTHETIC-MODEL",
        source_document=document,
        extra={"manufacturer_source": {"page": 3, "quote": "SYNTHETIC-MODEL"}},
    )
    item = BidItem.objects.create(bid=bid, item_no="1", name="합성 품목")
    for category, norm, linked in [
        ("DIMENSION", {"dia": 320, "len": 650}, True),
        (
            "ENVIRONMENT",
            {
                "min_temp_c": None,
                "interpretation_review": {"status": "NEEDS_CONFIRMATION", "reason": "부호 확인"},
            },
            False,
        ),
        ("CERTIFICATION", {"cert_type": "G2B_ITEM"}, False),
        ("SUBMISSION_DOC", {"timing": "제작 착수 전 승인", "applicability": "필요시"}, False),
    ]:
        req = BidRequirement.objects.create(
            bid=bid,
            item=item if linked else None,
            category=category,
            title=category,
            requirement_text="합성 요구조건 한글",
            normalized=norm,
        )
        trace = (
            {
                "candidate_comparisons": [
                    {
                        "product_id": product.pk,
                        "candidate_verdict": "MET",
                        "rationale": "합성 치수 일치",
                    }
                ]
            }
            if linked
            else {}
        )
        RequirementEvaluation.objects.create(
            requirement=req,
            verdict="NEEDS_CONFIRMATION",
            risk_level="MEDIUM",
            company_value="제안 제품 미확정",
            auto_answer="확인 필요",
            rationale="합성 자료 범위 확인",
            decided_by="RULE",
            rule_trace=trace,
            evidences=[
                {
                    "type": "product",
                    "id": product.pk,
                    "label": "제조사 기재",
                    "page": 3,
                    "quote": "SYNTHETIC-MODEL",
                }
            ]
            if linked
            else [],
        )
    return bid


def test_actual_saved_rule_only_content_and_version_protection(stored_bid):
    bid = stored_bid
    baseline = LLMCallLog.objects.count()
    for kind in DraftType.values:
        draft = generate_draft(bid, kind, allow_llm=False)
        assert draft.version == 1 and not draft.used_llm
        assert draft.content["analysis_context"]["counts"]["NEEDS_CONFIRMATION"] == 4
        assert "가상 자료 기반" not in draft.content["notice"]
    matrix = DraftDocument.latest(bid, DraftType.COMPLIANCE_MATRIX)
    assert all(row["compliance"] == "확인 필요" for row in matrix.content["rows"])
    assert (
        matrix.content["rows"][0]["candidate_comparisons"][0]["comparison_label"]
        == "후보 기재값 일치"
    )
    same = generate_draft(bid, DraftType.COMPLIANCE_MATRIX, allow_llm=False)
    assert matrix.pk == same.pk
    content = same.content
    content["rows"][0]["remark"] = "수동 메모 보존"
    save_draft(same, content=content)
    newer = generate_draft(bid, DraftType.COMPLIANCE_MATRIX, allow_llm=False)
    assert newer.version == 2
    same.refresh_from_db()
    assert same.content["rows"][0]["remark"] == "수동 메모 보존"
    contents, versions = report_contents(bid)
    assert (
        versions[DraftType.COMPLIANCE_MATRIX] == 2
        and contents[DraftType.COMPLIANCE_MATRIX] == newer.content
    )
    assert LLMCallLog.objects.count() == baseline


def test_known_dimensions_are_not_buyer_questions_and_unknown_conditions_are(stored_bid):
    content, _ = generators.technical_query(stored_bid, allow_llm=False)
    assert len(content["questions"]) == 1
    assert "사용온도" in content["questions"][0]["question"]
    assert all(q["audience"] == "INTERNAL" for q in content["internal_questions"])
    assert any("형식·치수는 비교" in q["question"] for q in content["internal_questions"])
    assert all("사용온도" not in q["question"] for q in content["internal_questions"])


def test_unconfirmed_report_never_looks_like_a_final_bid_decision(stored_bid):
    content, _ = generators.review_report(stored_bid, allow_llm=False)
    assert content["recommendation"] == "CONDITIONAL"
    assert "최종 입찰 결정이 아닙니다" in content["decision_notice"]
    assert content["candidate_review"][0]["final_verdict"] == "확인 필요"
    content, _ = generators.checklist(stored_bid, allow_llm=False)
    assert any(s["title"] == "제작 전 승인" for s in content["sections"])
    assert any("조건부 적용" in i["note"] for s in content["sections"] for i in s["items"])


def test_xlsx_retains_final_rows_candidate_scope_and_blocks_formula_injection(stored_bid):
    content, _ = generators.compliance_matrix(stored_bid, allow_llm=False)
    content["rows"][0]["response"] = ' \t=HYPERLINK("https://invalid.example","x")'
    data = xlsx.render_xlsx(stored_bid, DraftType.COMPLIANCE_MATRIX, content, version=1)
    wb = load_workbook(BytesIO(data))
    assert wb.sheetnames == ["Compliance Matrix", "후보 비교"]
    assert all(c.data_type != "f" for ws in wb for row in ws for c in row)
    assert wb.worksheets[0].cell(6, 8).value.startswith("'")
    assert [wb.worksheets[0].cell(r, 7).value for r in range(6, 10)] == ["확인 필요"] * 4
    assert "최종 공고 판정과 별개" in wb["후보 비교"].cell(1, 1).value
    for value in ["=1+1", "+cmd", "-cmd", "@SUM(A1)", "\t=1", "\n=1"]:
        assert xlsx.safe_value(value).startswith("'")
    assert xlsx.safe_value(-3) == -3


def test_pdf_uses_real_korean_font_and_saved_versions(stored_bid):
    pdf.prepare_native_runtime()
    for kind in DraftType.values:
        generate_draft(stored_bid, kind, allow_llm=False)
    contents, versions = report_contents(stored_bid)
    html = pdf.report_html(stored_bid, contents, [], versions=versions)
    data = pdf.render_pdf(html)
    with pdfplumber.open(BytesIO(data)) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        assert "검토 보고서 v1" in text and "Compliance Matrix v1" in text
        assert "후보 기재값 일치" in text and "내부 확인 항목" in text
        assert any(
            "NotoSansKR" in re.sub(r"[^A-Za-z]", "", c["fontname"])
            for page in document.pages
            for c in page.chars
        )
        assert len({round(page.width) for page in document.pages}) == 2


def test_gets_and_explicit_no_llm_api_preserve_analysis(stored_bid, manager_client, inline_jobs):
    baseline = list(RequirementEvaluation.objects.values())
    response = manager_client.post(
        f"/api/bids/{stored_bid.pk}/drafts/COMPLIANCE_MATRIX/generate",
        {"allow_llm": False},
        format="json",
    )
    assert response.status_code == 202 and response.data["job"]["status"] == "SUCCEEDED"
    assert not DraftDocument.latest(stored_bid, DraftType.COMPLIANCE_MATRIX).used_llm
    response = manager_client.get(
        f"/api/bids/{stored_bid.pk}/drafts/COMPLIANCE_MATRIX/xlsx?version=1"
    )
    assert response.status_code == 200 and response.content.startswith(b"PK")
    assert list(RequirementEvaluation.objects.values()) == baseline
    assert LLMCallLog.objects.count() == 0
