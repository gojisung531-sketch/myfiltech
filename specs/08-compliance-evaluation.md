# 08. 요구사항 추출 · 비교 · 판정

## 1. 개요

```
EXTRACT_BID  : 첨부 텍스트 → bid.extract(LLM) + 규칙 보강 → BidNotice 메타, BidItem[], BidRequirement[]
               → 제품 매칭 → 적합도
EVALUATE_BID : 요구사항마다 ① 증거 수집 → ② 규칙 엔진 → ③ LLM 판정/답변 → ④ 저장(수정본 보호)
```
코드: `apps/bids/extraction.py`, `apps/evaluation/{rules.py, grades.py, matching.py, evidence.py, service.py}`.

## 2. 공고 통합 추출 (`bid.extract` 출력 스키마)

```json
{
  "notice": {
    "notice_no": "20230323830-00", "title": "[울산발전본부] GT#7,8 입구 공기 1차 필터(Pulse Filter) 구매",
    "buyer_org": "한국동서발전(주)울산발전본부", "contracting_org": "부산지방조달청",
    "plant_name": "울산발전본부", "is_power_plant": true,
    "bid_method": "제한(총액), 계약이행능력심사", "item_category_code": "4016150501", "item_category_name": "공기여과기",
    "budget_krw": 370062000, "estimated_price_krw": 336420000,
    "bid_open_at": "2023-04-03T10:00:00+09:00", "bid_close_at": "2023-04-05T12:00:00+09:00",
    "opening_at": "2023-04-05T13:00:00+09:00", "qualification_deadline_at": "2023-04-04T18:00:00+09:00",
    "delivery_terms": "계약 후 150일 이내", "delivery_place": "...", "warranty_terms": "2년",
    "summary": "..."
  },
  "items": [
    {"item_no": "1", "name": "GT Inlet Air Pulse Filter Cartridge (Cylindrical)", "spec_text": "OD324 x L660mm",
     "filter_type": "CARTRIDGE_PULSE", "dimension": {"dia": 324, "len": 660, "unit": "mm", "raw": "OD324 x L660mm"},
     "quantity": 1400, "unit": "EA", "material_no": "2190164", "source": {"attachment": "정비용 기자재 구매규격서.hwp", "page": null, "quote": "..."}}
  ],
  "requirements": [
    {"item_no": "1|null", "category": "PRESSURE_DROP", "title": "초기 차압",
     "requirement_text": "0.71 inH2O 이하 @2,770 m³/h(1,630 CFM)",
     "normalized": {"metric": "initial_dp", "operator": "<=", "value": 176.9, "unit": "Pa", "raw": "0.71 inH2O",
                    "at_airflow_m3h": 2770},
     "is_mandatory": true, "source": {"attachment": "...", "page": null, "quote": "Initial Pr. Drop : 0.71 inH2O 이하"}}
  ]
}
```

- 추출 후 **규칙 후처리**: 단위 재환산 검증(LLM이 계산한 값과 `units.py` 계산값이 1% 이상 다르면 규칙 값 사용), 날짜 형식 정규화, 공고번호 정규식 `\d{11}-\d{2}`. `DELIVERY`에 `months_after_contract`만 있으면 `days_after_contract = 개월 × 30`으로 채운다(원 값 유지).
- **요구사항 누락 방지 체크**: 아래 기본 카테고리가 하나도 없으면 `NEEDS_CONFIRMATION` 자리표시 요구사항을 자동 생성(“공고에 ○○ 요구사항이 명시되어 있지 않음 — 확인 필요”): `DIMENSION`, `FILTER_GRADE` 또는 `EFFICIENCY`, `PRESSURE_DROP`, `TEST_STANDARD`, `CERTIFICATION`, `DELIVERY`, `SUBMISSION_DOC`.
- 공고문 내 “입찰참가자격”은 항목별로 분해: 물품 등록(세부품명번호), 직접생산확인, 중소기업확인서, 실적제한(기간·금액·규격), 지역제한 등 → `CERTIFICATION` / `TRACK_RECORD`.
- 재추출 시 `is_locked` 요구사항은 유지, 나머지는 교체(기존 판정은 요구사항 삭제와 함께 삭제). 수동 수정된 판정이 있는 요구사항은 삭제 전 경고.

## 3. 정규화 값(`normalized`) 스키마 — 카테고리별

| category | normalized 예 |
|---|---|
| DIMENSION | `{"w":610,"h":610,"d":305,"d_max":null,"dia":null,"dia2":null,"len":null,"unit":"mm","nominal_inch":"24x24x12","raw":"..."}` |
| FILTER_TYPE | `{"type":"V_BANK","keywords":["V-Bank","클립 결합"]}` |
| FILTER_GRADE | `{"standard":"EN1822","class":"E11","operator":">=","raw":"EN 1822(E 11)"}` |
| EFFICIENCY | `{"metric":"avg_eff_0_4um"/"gravimetric"/"epm1"/"mpps_integral"/"E1"/"E2"/"E3","operator":">=","value":95.4,"unit":"%","test_standard":"EN779"}` |
| PRESSURE_DROP | `{"metric":"initial_dp"/"final_dp","operator":"<=","value":176.9,"unit":"Pa","at_airflow_m3h":2770,"raw":"0.71 inH2O"}` |
| AIRFLOW | `{"value":4250,"unit":"m3/h","raw":"2,500CFM"}` |
| MATERIAL | `{"part":"frame"/"media"/"gasket"/"liner","required":["Heat Resistance Plastic"],"forbidden":["recycled pulp"]}` |
| ENVIRONMENT | `{"max_temp_c":100,"max_rh":100}` |
| FIRE_RATING | `{"standard":"UL900"/"방염","class":null}` |
| TEST_STANDARD | `{"standard":"ASHRAE52_2","edition":null,"lab_requirement":"국가공인기관","raw":"..."}` |
| CERTIFICATION | `{"cert_type":"DIRECT_PRODUCTION"/"SME"/"ISO9001"/"G2B_ITEM"...,"product_code":"4016150501","valid_on":"bid_close_at"}` |
| TRACK_RECORD | `{"period_years":10,"min_amount_krw":112140000,"single_contract":true,"spec_condition":"EN779 F9 이상 GT 공기 입구필터","product_types":["CARTRIDGE_PULSE"]}` |
| DELIVERY | `{"days_after_contract":150,"partial_allowed":false,"schedule":[{"label":"시제품","days":30}]}` |
| SUBMISSION_DOC | `{"doc":"EN 1822 시험성적서 원본","timing":"납품 시"/"입찰 시"/"계약 시","issuer_type":"COMPANY"/"LAB"/"AUTHORITY"/"SURETY"}` |
| WARRANTY | `{"months":24}` |
| INSPECTION | `{"type":"입회시험"/"공인기관 시험","standard":"EN1822","samples":2}` |
| OTHER | `{}` |

## 4. 증거 수집 (`evidence.py`)

요구사항별 후보 근거:
- 품목 요구사항 → 품목의 `matched_product`(담당자 변경 가능) + 해당 제품의 TestReport 전부 + 그 제품이 포함된 DeliveryRecord.
- 공통 요구사항 → Company, Certificate 전부, DeliveryRecord 전부, 문서 목록.
- 품목이 지정되지 않은 제품 사양 요구사항(치수·형식·등급·효율·차압·풍량·재질·환경·난연)은 공고의 매칭 제품이 하나뿐이면 그 제품을 대상 제품으로 쓴다. 대상 제품이 없으면 규칙은 `매칭 제품 없음`으로 판정한다(DIMENSION·FILTER_TYPE은 NEEDS_SUPPLEMENT(HIGH), 그 외는 LLM 위임).
- 각 근거는 `{type, id, label, page, quote}` 로 판정에 첨부.

## 5. 규칙 엔진 (`rules.py`) — 결정적 판정

규칙은 `(requirement, evidence, ctx) -> RuleResult | None` 함수 목록. `None`이면 LLM에 위임. `RuleResult = {verdict, risk_level, company_value, rationale, trace, action_items}`.

**판정 기준일 `ctx.reference_date`** — `AppSetting: evaluation.reference_date_mode`:
- `AUTO`(기본): 입찰 마감일이 오늘 이후면 마감일, 이미 지났으면 **오늘**(과거 공고를 현재 회사 자료로 “재입찰 시뮬레이션”). 이 경우 UI·보고서에 “과거 공고 — 오늘 기준 판정” 배지.
- `BID_CLOSE`: 항상 입찰 마감일 (과거 공고 사후 분석용)
- `TODAY`: 항상 오늘
- 마감일 정보가 없으면 오늘. 실적 기간(“공고일 기준 최근 10년”)도 같은 기준일로 계산.

### 5.1 등급 체계 (`grades.py`)
| 체계 | 순서 (낮음 → 높음) |
|---|---|
| ISO 16890 | 그룹 `Coarse < ePM10 < ePM2.5 < ePM1`, 같은 그룹은 % 비교 (ePM1 85% > ePM1 60%) |
| ISO 29461-1 | `T5 < T6 < T7 < T8 < T9 < T10 < T11 < T12` |
| EN 1822 | `E10 < E11 < E12 < H13 < H14 < U15 < U16 < U17` |
| EN 779 (폐지) | `G1 < G2 < G3 < G4 < M5 < M6 < F7 < F8 < F9` |
| ASHRAE 52.2 | `MERV 1 … 16` (정수) |
| ASHRAE 52.1 | 중량법 효율 % (Arrestance) |

- **서로 다른 체계 간 자동 동등 판정 금지.** 참고용 근사 매핑표 `AppSetting: evaluation.grade_reference_map`(예: `EN779 F9 ≈ ISO 16890 ePM1 80%+ ≈ MERV 15`)은 근거 서술·질의서 문구에만 사용.

### 5.2 카테고리별 규칙

| 카테고리 | 규칙 |
|---|---|
| DIMENSION | 제품 치수(또는 `dimension_variants`)와 각 축 비교, 허용오차 `evaluation.dimension_tolerance_mm`. 인치 공칭치수(24"=592/594/595/610 계열)는 `nominal_dimension_map`으로 동일군 판단. 일치 → MET. 같은 공칭군이지만 실제치수 차이 > 허용오차(예: 요구 610×610, 제품 592×592) → NEEDS_SUPPLEMENT(MEDIUM, “610 사양 제작 가능 여부 확인/도면 제출”). 범위 요구(400~600mm) 는 범위 포함 여부. 매칭 제품 없음 → NEEDS_SUPPLEMENT(HIGH). |
| FILTER_TYPE | `filter_type` 일치 → MET, 불일치 → 대안 제품 탐색 후 없으면 NEEDS_SUPPLEMENT(HIGH). |
| FILTER_GRADE | 요구 체계와 **같은 체계**의 성적서(또는 제품 등급)가 있고 등급 ≥ 요구 → MET(근거: 성적서). 같은 체계 등급 < 요구 → NEEDS_SUPPLEMENT(HIGH). 같은 체계 자료 없음, 다른 체계만 있음 → NEEDS_SUPPLEMENT(MEDIUM, “요구 규격(○○)으로 시험 필요”, 참고 근사 등급 서술). 공고에 “동등 이상” 문구 → NEEDS_CONFIRMATION + 질의 문안(“ISO 16890 ePM1 85% 성적서로 EN779 F9 동등 인정 가능 여부”). |
| EFFICIENCY | 같은 metric·같은 시험규격 측정값이 성적서에 있으면 수치 비교 → MET / NEEDS_SUPPLEMENT(HIGH). 측정값 없음 → NEEDS_CONFIRMATION 또는(다른 규격만) NEEDS_SUPPLEMENT(MEDIUM). |
| PRESSURE_DROP | 같은 풍량이면 제품 정격/성적서 값 비교. 풍량이 다르면 `airflow_dp_curve` 선형 보간(곡선 범위 내만) 후 비교하고 trace에 계산식 기록 → MET이라도 risk MEDIUM + “성적서 풍량과 상이, 보간값” 명시. 곡선 범위 밖 → NEEDS_CONFIRMATION. 최종차압(“More than 625 Pa” 요구): 권장 최종 차압 ≥ 요구 → MET, 아니면 NEEDS_SUPPLEMENT. |
| AIRFLOW | 정격풍량 ≥ 요구 → MET, 미만 → NEEDS_SUPPLEMENT. 시스템 총풍량(“Total Inlet Air Flow 1,764,000 m³/h”)은 수량×정격으로 검토 → 정보성, NEEDS_CONFIRMATION. |
| MATERIAL | 요구 재질이 제품 재질 문자열에 포함(동의어 사전: `ABS/플라스틱/Plastic`, `SUS304/Stainless`, `아연도/Galvanized`) → MET. `frame_options`에만 있음(주문제작) → NEEDS_SUPPLEMENT(MEDIUM, “주문제작 사양, 실적 없음” 등 비고 반영). 금지 재질 포함 → NEEDS_SUPPLEMENT(HIGH). 판단 불가 → LLM. |
| ENVIRONMENT | max_temp/max_rh 비교 → MET / NEEDS_SUPPLEMENT. |
| FIRE_RATING | 공식 인증 요구(UL Listing/Classified) + 회사는 `is_official_certification=False` 준용시험만 → NEEDS_SUPPLEMENT(MEDIUM). 시험 성적 요구면 준용 성적서로 MET 가능하되 rationale에 “공식 Listing 아님” 명시. 국내 “방염 시험” 요구 + 자료 없음 → NEEDS_SUPPLEMENT. |
| TEST_STANDARD | 해당 규격 성적서 보유 → MET, 단 `is_obsolete_standard`면 risk MEDIUM + “폐지 규격(EN 779:2012 → ISO 16890 대체)” 서술. 성적서 연령 제한(공고 명시 또는 `test_report_max_age_years`) 초과 → NEEDS_SUPPLEMENT. 미보유 → NEEDS_SUPPLEMENT(MEDIUM, “시험 의뢰”). 시험기관 요건(국가공인/KOLAS) 확인. |
| CERTIFICATION | Certificate 존재 & `valid_until ≥ reference_date` → MET. 만료 → NEEDS_SUPPLEMENT(필수면 HIGH). 만료 임박(`cert_expiring_days`) → MET + risk MEDIUM. 직접생산확인은 **세부품명번호 일치**까지 확인 — 불일치/판별 불가(예: 회사 `4013xxxx` vs 요구 `4016150501`) → NEEDS_CONFIRMATION(HIGH). 중소기업확인서·나라장터 물품 등록 → Company 필드 확인, 없으면 NEEDS_CONFIRMATION. |
| TRACK_RECORD | 기간 내(`reference_date - period_years`) DeliveryRecord 중 제품유형·사양조건 충족 건 탐색. 사양조건(예: “EN779 F9 이상 GT 입구필터”) 충족 실적 없음 → NEEDS_SUPPLEMENT(HIGH, 입찰 자격 미달 가능). 사양은 맞으나 `amount_krw` 없음 → NEEDS_CONFIRMATION(“실적증명서 금액 확인”). 모두 충족 → MET. |
| DELIVERY | Company/Product에 표준 납기 정보(`AppSetting: company.standard_lead_time_days`, 제품별 `extra.lead_time_days`)가 있으면 비교, 없으면 NEEDS_CONFIRMATION(LOW, “생산팀 납기 확인”). |
| SUBMISSION_DOC | 문서 매핑: 시험성적서/인증서/실적증명 → 해당 자료 보유 시 MET, 미보유 NEEDS_SUPPLEMENT. 회사가 작성·발급하는 서류(납품서, 계약이행계획서, 치수 및 외관검사 성적서, 하자/계약이행증권, 시험·검사계획서) → MET(LOW) + action_items(“납품 시 작성/발급”). |
| WARRANTY / INSPECTION / OTHER | 규칙 없음 → LLM. 입회시험·국가공인기관 시험 요구는 action_items에 일정/비용 반영. |
| (자리표시) | `normalized.placeholder=true`인 요구사항(§2 누락 방지) → NEEDS_CONFIRMATION(MEDIUM) + 발주처 질의 문안. |

## 6. 제품 매칭 & 적합도 (`matching.py`)

### 6.1 품목 ↔ 제품 매칭 점수 (0–1)
`0.35×형식 일치 + 0.30×치수 일치(축별, 공칭군 부분점수) + 0.25×등급/효율 충족 + 0.10×용도 키워드(GT 흡기/공조/클린룸)`. 상위 3개 저장(`BidProductMatch`), 1순위를 `BidItem.matched_product`.

### 6.2 공고 적합도 (0–100)
`fit.weights` 기반:
- product_type(40): 품목 중 매칭점수 ≥ 0.6 인 비율
- power_plant(15): 발전소 공고 여부(`fit.power_plant_keywords`, 수요기관명)
- qualification(25): 자격 요구사항(인증·실적·물품등록) 규칙 사전판정 결과(MET 비율, HIGH 위험 시 0)
- spec_coverage(20): 회사가 요구 시험규격 성적서를 보유한 비율
- 해당 요구사항이 공고에 없으면 그 항목은 만점(제한 없음)으로 계산한다(qualification, spec_coverage). 품목이 없으면 product_type은 0점.
- 규칙 점수 산출 후 `bid.fit_score` 프롬프트로 사유 문장 생성(점수 보정은 ±10 이내만 허용, 범위를 벗어나면 잘라냄). LLM 미설정·실패 시 규칙 점수와 구성 설명만 저장.
- 구현 순서: 자격 사전판정에 필요한 `grades.py`와 `CERTIFICATION`·`TRACK_RECORD` 규칙, 판정 기준일은 Phase 5(M4)에서 먼저 구현하고, 나머지 카테고리 규칙은 Phase 6(M5)에서 구현한다.
- 표시 구간: ≥70 높음(녹), 40–69 보통(황), <40 낮음(회).

## 7. 판정 실행 (`service.py`)

```
for req in bid.requirements:
    if req.evaluation and req.evaluation.is_modified and keep_modified: continue
    ev = collect_evidence(req)
    rr = rules.evaluate(req, ev, ctx)              # None 가능
    if settings.evaluation.use_llm:
        out = llm.run_task("evaluation.judge", {...rule_result: rr, evidence: ev})
        verdict = rr.verdict if rr else out.verdict  # 규칙 판정은 LLM이 바꿀 수 없음
        risk    = max(rr.risk, out.risk) if rr else out.risk
    else:
        out = template_answer(rr)                    # 규칙 결과로 문장 생성
    save(..., decided_by = RULE / LLM / RULE+LLM, ai_verdict=verdict, ai_answer=answer)
```
- LLM 판정이 `MET`인데 evidence_refs가 비어 있으면 **NEEDS_CONFIRMATION으로 강등**.
- 판정 배치: 요구사항 여러 개를 한 번의 LLM 호출로 묶어도 됨(`AppSetting: evaluation.batch_size`=10). 출력은 요구사항 id별 배열.
- 판정 완료 후 공고 `processing_status=EVALUATED`, 판정 요약 카운트 캐시(`extra.verdict_counts`).

### 7.1 자동 답변 문안 가이드 (Compliance Matrix 응답)
- MET: “충족 — FT-VB500 초기차압 130 Pa @4,250 m³/h (시험성적서 AFT-2025-0613)”
- NEEDS_SUPPLEMENT: “보완 필요 — 보유 성적서는 ISO 16890 ePM1 85%(AFT-2025-0402)이며 요구 규격 ASHRAE 52.2 성적서 미보유. 계약 전 공인기관 시험 의뢰 예정.”
- NEEDS_CONFIRMATION: “확인 필요 — 요구 세부품명번호(4016150501)와 당사 직접생산확인 품목번호 일치 여부 확인 필요.”

## 8. 수정
- 담당자 수정은 `verdict, risk_level, company_value, auto_answer, rationale, action_items, clarification_question, evidences` 전부 가능.
- 수정 시 `is_modified=True`, `modified_by/at`, `EvaluationHistory` 스냅샷.
- 자동 판정(규칙/LLM)을 저장할 때도 `EvaluationHistory`에 스냅샷을 남긴다(`changed_by=null`). “AI 판정으로 되돌리기” = 마지막 자동 판정 스냅샷 복원(`is_modified=False`).
- 판정 재실행 시 `keep_modified=true`(기본)면 수정된 판정은 그대로 두고, false면 덮어쓴다(이전 내용은 이력에 남음).
