# 02. 데이터 모델

모든 모델은 `created_at`, `updated_at`(auto) 를 가진다(`core.TimeStampedModel`). 수정 추적이 필요한 모델은 `created_by`, `updated_by`(FK User, null) 도 가진다. 아래 표에서 생략.

## 1. accounts

### User (`AbstractUser` 상속)
| 필드 | 타입 | 설명 |
|---|---|---|
| username, password, email, first_name, last_name, is_active | (상속) | |
| role | Char choices `ADMIN` / `BID_MANAGER` | 기본 `BID_MANAGER` |
| display_name | Char(50) | 화면 표시명 |
| department | Char(50), blank | |
| phone | Char(30), blank | |
| must_change_password | Bool | 기본 관리자 생성 시 true |
| failed_login_attempts | Int | 연속 로그인 실패 횟수 (성공 시 0) |
| locked_until | DateTime null | 로그인 잠금 해제 시각 ([03](03-auth-and-access.md) §1) |

- `AUTH_USER_MODEL = "accounts.User"` — **첫 마이그레이션 전에 설정**.
- `is_admin_role` property: `role == ADMIN or is_superuser`.
- 기본 관리자: `admin / admin1234!`, `role=ADMIN`, `is_staff=True` ([03](03-auth-and-access.md)).

## 2. core

### AppSetting — 튜닝용 key-value
| 필드 | 타입 |
|---|---|
| key | Char(100) unique (예: `evaluation.cert_validity_margin_days`) |
| value | JSONField |
| value_type | `int`/`float`/`bool`/`str`/`json` |
| group | Char (`evaluation`, `extraction`, `report`, `jobs`, `upload`, `fit`) |
| description | Text |

seed 기본값 목록은 [07](07-llm-integration.md) §6.

### Job — [01](01-architecture.md) §5 참조.

## 3. documents — 업로드 문서 공통

### Document
| 필드 | 타입 | 설명 |
|---|---|---|
| title | Char(255), blank | 표시 제목 (텍스트 입력 문서는 필수, 파일은 원본 파일명 사용) |
| file | FileField | `documents/%Y/%m/<uuid>.<ext>` |
| original_filename | Char(255) | |
| file_format | `TXT`/`DOCX`/`DOC`/`HWP`/`HWPX`/`PDF`/`XLS`/`XLSX` | |
| file_size, sha256 | Int, Char(64) | sha256 중복 업로드 경고 |
| source_text | Text, blank | "Text로 입력" 시 원문 (파일 없이 생성 가능) |
| extracted_text | Text | 파서 결과 (페이지 구분자 `\f`) |
| extracted_tables | JSON list | 파서가 인식한 표 `[{page, rows: [[셀, ...], ...]}]` — 규칙 추출기가 재사용 |
| page_count | Int, null | |
| category | FK MetadataSchema(null) | 문서 분류 |
| category_confidence | Float, null | |
| category_source | `AUTO`/`MANUAL` | |
| status | `UPLOADED`/`PARSING`/`PARSED`/`NEEDS_OCR`/`EXTRACTING`/`EXTRACTED`/`REVIEWED`/`FAILED` | |
| error_message | Text, blank | |
| owner_type | `COMPANY`/`BID` | 회사자료인지 입찰첨부인지 |

### MetadataSchema — 문서 분류별 메타데이터 정의 (관리자 CRUD)
| 필드 | 타입 | 설명 |
|---|---|---|
| code | Char unique | 아래 분류 코드 |
| name | Char | 한글명 |
| owner_type | `COMPANY`/`BID` | |
| description | Text | LLM 분류 프롬프트에 사용 |
| filename_patterns | JSON list[str] | 정규식. 파일명 기반 1차 분류 |
| fields | JSON list[FieldDef] | `{key, label, type(str/int/float/date/bool/list/dimension/grade/json), unit?, required, description, example}` |
| target_model | Char, blank | 추출 후 매핑할 도메인 모델 (`company.Product` 등) |
| priority | Int | 파일명 규칙 매칭 순서 (작을수록 먼저). 구체적인 분류가 먼저 오도록 seed |
| is_active | Bool | |

**seed 분류 (code: 이름 → target_model)**

| code | 이름 | owner | target |
|---|---|---|---|
| `company_profile` | 회사 소개/정보 | COMPANY | company.Company |
| `datasheet` | 제품 기술사양서 | COMPANY | company.Product |
| `test_report` | 시험성적서 | COMPANY | company.TestReport |
| `certificate` | 인증서/확인서 | COMPANY | company.Certificate |
| `delivery_record` | 납품실적 | COMPANY | company.DeliveryRecord (행 단위 복수) |
| `bid_notice` | 입찰공고문 | BID | bids.BidNotice |
| `bid_spec` | 규격서/시방서 (한난물자규격서, 구매규격서, 제조·구매 규격서, 시방서) | BID | bids.BidItem / BidRequirement |
| `bid_item_list` | 물품명세서/구매내역서/구매청구품목명세서/산출내역서 | BID | bids.BidItem |
| `bid_contract_terms` | 물품구매계약 일반·특수조건 | BID | BidRequirement(납기·하자·제출서류) |
| `bid_evaluation_criteria` | 계약이행능력심사 세부기준 | BID | BidRequirement(자격) |
| `bid_restriction_reason` | 제한경쟁사유서 | BID | BidRequirement(실적·자격) |
| `bid_drawing` | 도면 | BID | BidItem(치수 보강) |
| `bid_other` | 기타 첨부 | BID | – |

필드 정의 상세는 [06](06-document-processing.md) §4.

### DocumentMetadata — 추출/수정 가능한 메타데이터 값 (관리자 CRUD)
| 필드 | 타입 | 설명 |
|---|---|---|
| document | FK Document (CASCADE) | |
| key | Char(100) | schema field key, 또는 관리자 정의 임의 키 |
| label | Char(100) | |
| value | JSONField | 정규화된 값 |
| raw_value | Text | 원문 표기 (예: `0.71 inH2O`) |
| unit | Char(20), blank | 정규화 단위 |
| source | `RULE`/`LLM`/`MANUAL` | |
| confidence | Float, null | |
| evidence_page | Int, null | |
| evidence_quote | Text, blank | 원문 인용 (≤300자) |
| is_locked | Bool | 관리자가 수정하면 true → 재추출 시 덮어쓰지 않음 |

unique(document, key) — 단, `list` 타입은 value에 배열로 저장.

## 4. company — 회사 자료 (구조화)

### Company (싱글턴, pk=1)
name, ceo, business_no(사업자번호), address, phone, email, homepage, established_date, employees, is_sme(중소기업 여부), sme_cert_valid_until(date, null), g2b_registered_items(JSON list: `{code: "4016150501", name: "공기여과기"}`), main_products(Text), description(Text), source_documents(M2M Document).

### Product
| 필드 | 타입 | 예 (FT-VB500) |
|---|---|---|
| model_no | Char unique | FT-VB500 |
| name | Char | 컴팩트 V-bank 필터 (4V) |
| filter_type | choices `PANEL`/`POCKET_BAG`/`V_BANK`/`MINI_PLEAT_HEPA`/`CARTRIDGE_PULSE`/`DEMISTER`/`CARBON`/`OTHER` | V_BANK |
| application | Text | 가스터빈 흡기 최종단 |
| width_mm, height_mm, depth_mm | Float, null | 592/592/292 |
| diameter_mm, diameter2_mm, length_mm | Float, null | 원통/원추 카트리지용 |
| dimension_text | Char | 원문 |
| dimension_variants | JSON list | 주문제작 가능 치수/옵션 |
| media | Char | 유리섬유 (소수성 처리) |
| frame_material | Char | ABS 수지 |
| frame_options | JSON list | `[{"material":"SUS304","model":"FT-EP700S","note":"주문제작"}]` |
| gasket | Char | |
| rated_airflow_m3h | Float | 4250 |
| initial_dp_pa | Float | 130 |
| final_dp_pa | Float | 600 |
| airflow_dp_curve | JSON list `[{airflow_m3h, dp_pa}]` | |
| iso16890_class | Char, blank | ISO ePM1 85% |
| iso29461_class | Char, blank | T9 |
| en1822_class | Char, blank | |
| en779_class | Char, blank | (성적서 기반) F9 |
| ashrae_merv | Int, null | |
| max_temp_c, max_rh | Float | 70 / 100 |
| fire_rating | Char | UL 900 준용 난연시험 적합 |
| revision | Char | Rev.3 · 2026-01 |
| is_active | Bool | |
| source_document | FK Document null | |
| extra | JSON | 기타 메타데이터 |

### TestReport
report_no(unique), product(FK, null), model_no_text, sample_name, sample_dimension, standard(Char: `ISO 16890-1~4:2016`), standard_family(choices `ISO16890`/`ISO29461`/`EN1822`/`EN779`/`ASHRAE52_1`/`ASHRAE52_2`/`UL900`/`KS`/`OTHER`), is_obsolete_standard(Bool), test_date, issue_date, lab_name, lab_accreditation(Char: KOLAS...), is_official_certification(Bool — 예: UL "준용" 시험은 false), result_class(Char: `ISO ePM1 85%`), test_airflow_m3h, initial_dp_pa, results(JSON: 측정값 dict, 입경별 효율 배열 등), conditions(JSON), notes, source_document.

### Certificate
cert_no(unique), name(ISO 9001 품질경영시스템 인증서), cert_type(`ISO9001`/`ISO14001`/`ISO45001`/`DIRECT_PRODUCTION`/`SME`/`KS`/`PATENT`/`OTHER`), standard(ISO 9001:2015), holder, scope(Text), product_codes(JSON list — 직접생산확인 세부품명번호 등), issuer, issue_date, valid_from, valid_until, notes, source_document.
- 계산 필드 `status`: `VALID`/`EXPIRING`(유효기간 ≤ N일, `AppSetting: evaluation.cert_expiring_days`=90)/`EXPIRED` — 기준일은 호출 시 전달(기본 오늘, 판정 시 입찰 마감일).

### DeliveryRecord (납품실적 행)
delivered_ym(Char `2023-10` 또는 date), client(발주처), project_name(사업명), item_desc(품목), model_nos(JSON list[str] — 원문 모델명. `models`는 Django 모듈명과 충돌해 사용 불가), products(M2M Product), quantity(JSON: `[{model, qty, unit}]`), amount_krw(BigInt null — 원본에 없음), is_power_plant(Bool), plant_type(`CCPP`/`THERMAL`/`CHP`/`OTHER`), notes(“E12 동급, SUS304 프레임 사양 아님”), source_document.

## 5. bids

### BidNotice
| 필드 | 타입 | 설명 |
|---|---|---|
| notice_no | Char, blank | 입찰공고번호 (예: `20230323830-00`). 본문에서 추출 |
| source_ref | Char, blank | 적재 폴더명 등 외부 참조 (예: `20230342721`) |
| title | Char(300) | 공고명 |
| buyer_org | Char | 수요기관 (한국동서발전(주)울산발전본부) |
| contracting_org | Char | 계약기관 (부산지방조달청) |
| buyer_contact, contract_contact | JSON | `{name, dept, phone}` |
| plant_name | Char, blank | 발전소/사업장 |
| is_power_plant | Bool, null | 발전소 관련 공고 여부 |
| bid_method | Char | 제한(총액), 계약이행능력심사 |
| procurement_type | Char | 물품/제조 |
| item_category_code | Char | 세부품명번호 (4016150501) |
| item_category_name | Char | 공기여과기 |
| budget_krw | BigInt null | 사업금액(VAT 포함) |
| estimated_price_krw | BigInt null | 추정가격(VAT 제외) |
| bid_open_at, bid_close_at, opening_at | DateTime null | 입찰서 제출 시작/마감, 개찰 |
| qualification_deadline_at | DateTime null | 실적심사신청 등 자격서류 마감 |
| delivery_terms | Char | 계약 후 150일 이내 |
| delivery_place | Char | |
| warranty_terms | Char | 하자담보 2년 |
| summary | Text | LLM 요약 (3~5줄) |
| fit_score | Int null | 0–100 |
| fit_reason | Text | |
| (후보 제품) | `BidProductMatch` 참조 | 품목별 후보 — 아래 표 |
| outcome | `PENDING`/`WON`/`LOST`/`NOT_BID` | 기본 PENDING |
| review_status | `UNREVIEWED`/`REVIEWED` | 대시보드 확인/미확인 |
| reviewed_by, reviewed_at | FK User, DateTime | |
| processing_status | `DRAFT`/`EXTRACTING`/`EXTRACTED`/`EVALUATING`/`EVALUATED`/`FAILED` | |
| processing_error | Text, blank | 마지막 추출/판정 실패 사유 (편집 화면에 표시) |
| source_text | Text, blank | Text 직접 입력 공고 |
| extra | JSON | 기타 메타데이터. `locked_fields`: 관리자가 수정한 필드 목록(재추출 시 덮어쓰지 않음), `verdict_counts`(판정 요약 캐시), `placeholders`(자리표시로 추가한 카테고리), `fit_breakdown`·`rule_fit_score`(적합도 규칙 내역) 등 |
| created_by | FK User null | |

### BidProductMatch (품목별 후보 제품, specs/08 §6.1)
bid(FK CASCADE), item(FK BidItem CASCADE), product(FK Product CASCADE), score(Float 0–1), reason(Text — 점수 구성 설명), rank(Int, 1=최우선). unique(item, product). 품목당 상위 3개 저장, rank 1이 `BidItem.matched_product` 기본값.

### BidAttachment
bid(FK CASCADE), document(OneToOne Document), role(=Document.category.code 복사, 표시용), is_primary(공고문 여부), order(Int).

### BidItem (품목)
bid(FK), item_no(Char: 품번/순번), name(GT Air Intake Final Filter), spec_text(규격 원문), filter_type(Product.filter_type choices, null), width_mm/height_mm/depth_mm/diameter_mm/diameter2_mm/length_mm (Float null, 범위 허용 시 `depth_mm_max`), quantity(Float), unit(EA/세트/식), material_no(자재번호), notes, source_attachment(FK BidAttachment null), matched_product(FK Product null — 담당자 변경 가능), match_score(Float null), depth_mm_max(Float null).
- 재추출 시 품목은 `item_no` 기준으로 갱신(같은 품번은 수정, 새 품번은 생성, 사라진 품번은 잠긴 요구사항이 참조하지 않을 때만 삭제).

### BidRequirement (핵심 요구사항 — 판정 단위)
| 필드 | 타입 | 설명 |
|---|---|---|
| bid | FK | |
| item | FK BidItem null | null = 공고 공통 요구사항(자격, 서류 등) |
| category | choices | `DIMENSION`, `FILTER_TYPE`, `FILTER_GRADE`, `EFFICIENCY`, `PRESSURE_DROP`, `AIRFLOW`, `MATERIAL`, `ENVIRONMENT`(온습도), `FIRE_RATING`, `TEST_STANDARD`, `CERTIFICATION`(인증·자격), `TRACK_RECORD`(납품실적), `DELIVERY`(납기), `SUBMISSION_DOC`(제출서류), `WARRANTY`, `INSPECTION`(시험·검사), `OTHER` |
| title | Char | “초기 차압” |
| requirement_text | Text | 원문 요약 (“0.71 inH2O 이하 @2,770 m³/h”) |
| normalized | JSON | 비교용 정규화 값. [08](08-compliance-evaluation.md) §3 스키마 |
| is_mandatory | Bool | 필수/권장 |
| source_attachment | FK BidAttachment null | |
| source_page | Int null | |
| source_quote | Text | 원문 인용 |
| order | Int | |
| source | `LLM`/`RULE`/`MANUAL` | |
| is_locked | Bool | 관리자 수정 시 true |

## 6. evaluation

### RequirementEvaluation (요구사항 1:1, 최신본)
| 필드 | 타입 | 설명 |
|---|---|---|
| requirement | OneToOne BidRequirement | |
| verdict | `MET`/`NEEDS_SUPPLEMENT`/`NEEDS_CONFIRMATION` | |
| risk_level | `LOW`/`MEDIUM`/`HIGH` | HIGH = 입찰 자격 상실·불합격 가능 |
| company_value | Text | 회사 측 대응 값 (“130 Pa @4,250 m³/h (AFT-2025-0613)”) |
| auto_answer | Text | 자동 답변 (Compliance Matrix 응답 문구) |
| rationale | Text | 판정 근거 설명 |
| action_items | JSON list[str] | 보완 조치 (예: “ASHRAE 52.2 시험 의뢰”) |
| clarification_question | Text, blank | 확인 필요 시 발주처 질의 문안 |
| evidences | JSON list | `[{type: product/test_report/certificate/delivery_record/bid_quote, id, label, page, quote}]` |
| decided_by | `RULE`/`LLM`/`RULE+LLM`/`MANUAL` | |
| rule_trace | JSON | 규칙 엔진 계산 과정 (디버깅·근거 표시용) |
| ai_verdict, ai_answer | Char, Text | 자동 판정 원본 (수동 수정 후에도 보존) |
| is_modified | Bool | 담당자 수정 여부 |
| modified_by, modified_at | FK User, DateTime | |
| llm_call | FK LLMCallLog null | |

### EvaluationHistory
evaluation(FK), snapshot(JSON: verdict·risk_level·company_value·auto_answer·rationale·action_items·clarification_question·evidences·decided_by), changed_by(null = 자동 판정), changed_at — 자동 판정 저장·담당자 수정·되돌리기마다 기록.

## 7. drafts

### DraftDocument
bid(FK), doc_type(`COMPLIANCE_MATRIX`/`BID_CHECKLIST`/`TECHNICAL_QUERY`/`REVIEW_REPORT`), title, content(JSON — 유형별 구조, [09](09-drafts-and-reports.md)), status(`DRAFT`/`FINAL`), version(Int), generated_by(`AUTO`/`MANUAL`), is_modified, used_llm(Bool — LLM 다듬기 반영 여부), created_by/updated_by(FK User null), unique(bid, doc_type, version). 최신 버전 = 최대 version. 재생성은 최신 버전을 덮어쓰되, 담당자가 수정한 버전이거나 `new_version=true`면 새 버전을 만든다.

## 8. llm

### LLMProviderConfig
provider(unique `OPENAI`/`ANTHROPIC`/`GEMINI`), api_key_encrypted(Binary/Text), api_key_last4(Char 4), base_url(Char blank — 프록시용), is_enabled(Bool), last_verified_at, last_verify_ok(Bool null), last_verify_error(Text).

### LLMModelOption
provider, model_id(`claude-opus-5-5`), display_name(`Claude Opus 5.5`), supports_pdf_input(Bool), max_output_tokens(Int null — 비어 있으면 LLMSettings 값 사용), is_default(Bool per provider), is_active, order. 관리자 CRUD.

### LLMSettings (싱글턴)
active_provider, active_model(FK LLMModelOption), temperature(Float), max_output_tokens(Int), timeout_sec(Int), max_retries(Int), json_mode(Bool), per_task_overrides(JSON: `{"evaluation": {"model": "...", "temperature": 0}}`).

### PromptTemplate
key(unique per version — `document.classify`, `document.extract_metadata`, `bid.extract`, `bid.fit_score`, `evaluation.judge`, `draft.compliance_matrix`, `draft.checklist`, `draft.technical_query`, `draft.report_summary`), name, description, system_prompt(Text), user_prompt_template(Text, `{{ variable }}` Jinja2-like — Django Template 엔진 사용 금지, `string.Template` 혹은 jinja2 sandbox), output_schema(JSON Schema), version(Int), is_active(Bool — key당 하나), notes, updated_by.

### LLMCallLog
task_key, provider, model_id, prompt_template(FK null, version 기록), request_tokens, response_tokens, latency_ms, status(`OK`/`ERROR`/`INVALID_JSON`), error, request_excerpt(앞 2,000자), response_text, created_at, job(FK null). **API Key 미포함.**

## 9. ERD 요약

```
User ─┬─< Job
      └─(reviewed_by) BidNotice ─┬─< BidAttachment ── Document ─< DocumentMetadata
                                 ├─< BidItem ──(matched)── Product
                                 ├─< BidRequirement ── RequirementEvaluation ─< EvaluationHistory
                                 └─< DraftDocument
Document >── MetadataSchema
Company(1) ; Product ─< TestReport ; Certificate ; DeliveryRecord >─< Product
LLMProviderConfig ; LLMModelOption ; LLMSettings(1) ; PromptTemplate ; LLMCallLog ; AppSetting
```
