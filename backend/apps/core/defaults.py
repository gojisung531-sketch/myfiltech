"""Seed defaults for AppSetting (specs/07-llm-integration.md §6).

Only keys whose default value is fully specified in the spec are listed here.
"""

from typing import NamedTuple

# specs/07 §4.2
VERDICT_DEFINITIONS = """MET(충족): 회사 자료(사양서/성적서/인증서/실적)에 요구사항을 만족함을 직접 입증하는 근거가 있고 유효함.
NEEDS_SUPPLEMENT(보완 필요): 회사가 대응 가능성은 있으나 증빙·사양·유효기간·시험규격이 부족하거나 다름
  (예: 인증 만료, 다른 규격 성적서만 보유, 주문제작 옵션, 시험 추가 필요, 요구 미달로 사양 변경 필요).
NEEDS_CONFIRMATION(확인 필요): 공고 요구가 모호하거나 회사 자료가 없어 판단 불가 → 발주처 질의 또는 내부 확인 필요.
규칙 엔진 결과(rule_result.verdict)가 있으면 그 판정을 바꾸지 말고 근거 서술과 답변만 작성합니다."""


class SettingDefault(NamedTuple):
    value: object
    value_type: str
    description: str


APP_SETTING_DEFAULTS: dict[str, SettingDefault] = {
    "llm.max_input_chars": SettingDefault(150000, "int", "LLM 입력 최대 문자 수"),
    "extraction.min_text_chars_per_page": SettingDefault(
        30, "int", "페이지당 최소 문자 수 (미만이면 스캔 PDF로 판정)"
    ),
    "extraction.low_confidence_threshold": SettingDefault(
        0.7, "float", "이 값 미만 신뢰도의 메타데이터는 검토 화면에서 강조"
    ),
    "extraction.auto_apply_company": SettingDefault(
        False, "bool", "회사 자료 추출 결과를 검토 없이 자동 반영"
    ),
    "extraction.excerpt_keywords": SettingDefault(
        [
            "납기",
            "납품기한",
            "지체상금",
            "하자",
            "제출서류",
            "시험성적서",
            "실적",
            "자격",
            "직접생산",
            "중소기업",
            "검사",
        ],
        "json",
        "장문 첨부(계약조건·심사기준)에서 발췌할 키워드",
    ),
    "bid.auto_evaluate_after_extract": SettingDefault(
        True, "bool", "공고 추출 완료 후 판정 자동 실행"
    ),
    "evaluation.cert_expiring_days": SettingDefault(90, "int", "인증서 만료 임박 기준(일)"),
    "evaluation.test_report_max_age_years": SettingDefault(
        0, "int", "시험성적서 유효 연수 제한 (0=제한 없음, 공고 명시 시 공고 우선)"
    ),
    "evaluation.dimension_tolerance_mm": SettingDefault(3, "int", "치수 허용오차(mm)"),
    "evaluation.nominal_dimension_map": SettingDefault(
        {
            "24": [592, 594, 595, 610],
            "20": [490, 492, 495, 508],
            "12": [287, 292, 295, 305],
            "4": [95, 96, 98, 100, 102],
            "2": [45, 46, 48, 50],
            "1": [20, 22, 25],
        },
        "json",
        "인치 공칭치수 ↔ 실제 mm (필터 업계 표준 공칭치수)",
    ),
    "evaluation.grade_reference_map": SettingDefault(
        [
            {"EN779": "F7", "ISO16890": "ePM1 50–65%", "ASHRAE52_2": "MERV 13"},
            {"EN779": "F8", "ISO16890": "ePM1 65–80%", "ASHRAE52_2": "MERV 14"},
            {"EN779": "F9", "ISO16890": "ePM1 80% 이상", "ASHRAE52_2": "MERV 15"},
        ],
        "json",
        "타 규격 등급 참고용 근사표 — 근거 서술·질의 문안에만 사용 (자동 동등 판정 금지)",
    ),
    "evaluation.verdict_definitions": SettingDefault(
        VERDICT_DEFINITIONS, "str", "판정 정의 (evaluation.judge 프롬프트 변수)"
    ),
    "evaluation.use_llm": SettingDefault(True, "bool", "false면 규칙 판정만 수행"),
    "evaluation.reference_date_mode": SettingDefault(
        "AUTO", "str", "판정 기준일 (AUTO / BID_CLOSE / TODAY)"
    ),
    "evaluation.batch_size": SettingDefault(10, "int", "판정 LLM 호출당 요구사항 수"),
    "fit.weights": SettingDefault(
        {"product_type": 40, "power_plant": 15, "qualification": 25, "spec_coverage": 20},
        "json",
        "적합도 가중치",
    ),
    "fit.power_plant_keywords": SettingDefault(
        ["발전", "화력", "복합", "열병합", "지역난방", "가스터빈", "GT", "CCPP"],
        "json",
        "발전소 공고 판별 키워드",
    ),
    "report.disclaimer": SettingDefault(
        "본 문서는 시스템이 자동 생성한 초안이며 최종 제출 전 담당자 검토가 필요합니다. (가상 자료 기반)",
        "str",
        "보고서·PDF 하단 문구",
    ),
    "report.company_logo": SettingDefault(None, "str", "보고서 로고"),
    "jobs.concurrency": SettingDefault(2, "int", "백그라운드 작업 동시 실행 수"),
    "jobs.run_inline": SettingDefault(
        False, "bool", "작업을 요청 내에서 동기 실행 (개발/테스트용)"
    ),
    "upload.max_mb": SettingDefault(50, "int", "업로드 파일 최대 크기(MB)"),
    "auth.lockout_threshold": SettingDefault(5, "int", "연속 로그인 실패 허용 횟수"),
    "auth.lockout_minutes": SettingDefault(5, "int", "로그인 잠금 시간(분)"),
    "company.standard_lead_time_days": SettingDefault(
        None, "int", "표준 납기(일). 비어 있으면 납기 판정은 '확인 필요'"
    ),
}
