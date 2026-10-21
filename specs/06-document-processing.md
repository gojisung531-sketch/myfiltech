# 06. 문서 처리 (텍스트 추출 · 분류 · 메타데이터 추출)

## 1. 파이프라인

```
Document 생성 (파일 or source_text)
  └─ [1] parse      → extracted_text, page_count     (status: PARSING → PARSED | NEEDS_OCR | FAILED)
  └─ [2] classify   → category (+confidence)          (규칙 → LLM)
  └─ [3] extract    → DocumentMetadata 행들           (규칙 → LLM, 잠긴 값 보존)
  └─ [4] map        → 도메인 엔티티 갱신 제안/적용   (company.* / bids.*)
```
- 각 단계는 독립 재실행 가능(`POST /api/documents/{id}/reprocess {from_step}`).
- 처리 코드 위치: `apps/documents/parsers/`, `apps/documents/pipeline.py`.

## 2. 형식별 파서 (`parsers/<fmt>.py`, 공통 인터페이스 `parse(path) -> ParseResult(text, pages:list[str], tables:list, warnings)`)

`tables`는 `Document.extracted_tables`에 저장해 규칙 추출기가 재파싱 없이 사용한다. 표를 지원하는 형식: PDF, DOCX, HWPX, XLS/XLSX(시트 = 표).

| 형식 | 방법 | 비고 |
|---|---|---|
| TXT | charset-normalizer로 인코딩 감지(UTF-8, CP949/EUC-KR) | |
| DOCX | python-docx: 문단 + 표(행은 ` \| ` 구분), 머리글/바닥글 제외 | |
| DOC | LibreOffice(`soffice --headless --convert-to docx`) 설치 시에만 | 미설치 시 “지원하지 않는 형식” 안내 |
| PDF | pdfplumber, 페이지별 텍스트 + `extract_tables`. **회전된 글자(변환 행렬 b·c ≠ 0)는 워터마크로 보고 제거** — initial-data의 대각선 “SAMPLE · 가상 자료” 워터마크가 본문에 섞이는 것을 확인함 | 전체 텍스트 < `extraction.min_text_chars_per_page`(30)×페이지 → **스캔 PDF** 판정 |
| HWP 5.0 | **olefile + zlib 자체 구현** (아래 §2.1) | pyhwp 사용 금지(AGPL) |
| HWPX | zip → `Contents/section*.xml` 의 `hp:p` / `hp:t` 순회, 표는 `hp:tbl/hp:tr/hp:tc` | |
| XLS | xlrd | 공고 첨부 전용 |
| XLSX | openpyxl(`data_only=True`) | 공고 첨부 전용 |

### 2.1 HWP 5.0 추출 규칙 (실제 샘플로 검증됨)
- `FileHeader` 스트림 offset 36 비트0 = 압축 여부. 비트1 = 암호화(→ 미지원 오류), 배포용 문서(`ViewText` 스트림) → 미지원 안내.
- `BodyText/Section0..N` 스트림을 순서대로 `zlib.decompress(data, -15)`.
- 레코드 헤더 32bit: `tag = h & 0x3FF`, `level = (h>>10)&0x3FF`, `size = h>>20` (0xFFF면 다음 4바이트가 크기).
- `HWPTAG_PARA_TEXT (=67)` 의 UTF-16LE 텍스트를 읽되 **제어 문자 처리 필수**:
  - 문자 컨트롤(1 WCHAR): 0, 10(줄바꿈→`\n`), 13(문단 끝), 24–31
  - 인라인/확장 컨트롤(8 WCHAR = 16바이트를 통째로 건너뜀): 1–9, 11–12, 14–23. 단 9(탭)는 `\t`로 치환
  - 이를 지키지 않으면 `捤獥汤捯`, `氠瑢`, `漠杳`, `浵╦` 같은 깨진 문자가 섞인다(샘플에서 확인).
- 표: `HWPTAG_LIST_HEADER(72)`/`HWPTAG_TABLE(77)` 를 이용해 셀 단위로 묶고, 행 단위로 ` | ` 결합하여 표 구조를 최대한 보존(1차 구현은 셀 텍스트를 순서대로 줄 단위 출력해도 됨 — 단, 표 시작/끝에 `[표]`/`[/표]` 마커).
- 테스트 픽스처: `initial-data/bid_sample/won/**/*.hwp` 전체가 예외 없이 파싱되고 깨진 문자(U+4E00–U+9FFF 중 한자 비율 비정상) 없이 나와야 한다.

### 2.2 스캔 PDF / 이미지
- 활성 모델이 PDF 입력을 지원(`LLMModelOption.supports_pdf_input`)하면 PDF를 그대로 LLM에 보내 **텍스트 전사 + 메타데이터 추출**을 한 번에 수행. 전사 결과를 `extracted_text`에 저장하고 `DocumentMetadata.source=LLM`.
- 미지원이거나 LLM 미설정이면 `status=NEEDS_OCR`, UI에 “스캔 문서 — 텍스트를 직접 입력하거나 LLM 설정 후 재처리” 안내. (선택: Tesseract `kor` 설치 시 OCR)
- 샘플: `제한경쟁사유서.pdf`, `제한 경쟁 사유서.pdf` 2건이 스캔 PDF.

### 2.3 정리(normalization)
- 연속 공백·빈 줄 축약, 엑셀 끝쪽 빈 열 제거, 전각/반각 정리(`×`, `x`, `*` 치수 구분자 통일은 메타데이터 단계에서).
- 페이지 구분 `\f`. 위치 인용을 위해 페이지 번호 보존(HWP는 페이지 정보가 없으므로 `null`, 대신 문단 인덱스).
- 법령·약관성 첨부(`물품구매계약일반조건`, `계약이행능력심사 세부기준`)는 길다(15–36k자). 요구사항 추출 시 **분류별 가중치**: 공고문·규격서·명세서 전문, 계약조건/심사기준은 핵심 조항(납기, 지체상금, 하자, 제출서류, 신인도 등)만 LLM에 발췌 전달 — 키워드 기반 발췌 규칙 `AppSetting: extraction.excerpt_keywords`.

## 3. 문서 분류

1. **경로/파일명 규칙**(`MetadataSchema.filename_patterns`, `priority` 오름차순으로 첫 매칭), 예:
   - `공고문|공고서|입찰공고` → `bid_notice`
   - `규격서|시방서|사양서(?!.*기술사양서)` → `bid_spec`
   - `명세서|구매내역서|산출내역서|품목` → `bid_item_list`
   - `계약.*조건` → `bid_contract_terms`, `이행능력심사|세부기준` → `bid_evaluation_criteria`, `제한.?경쟁.?사유서` → `bid_restriction_reason`, `도면` → `bid_drawing`
   - `기술사양서|Data Sheet` → `datasheet`, `시험성적서|Test Report|^AFT-` → `test_report`, `인증서|증명서|확인서` → `certificate`, `납품실적` → `delivery_record`
   - 적재 시 폴더명(`certificates/`, `datasheets/`, `records/`, `test_reports/`)이 최우선.
2. **본문 키워드 규칙**(앞 2,000자): “시 험 성 적 서”, “Test Report No.”, “제품 기술사양서”, “인증서”, “입찰공고”, “물자규격서” 등.
3. 규칙으로 분류하지 못했거나 신뢰도 < 0.8 이면 (LLM이 설정된 경우) **LLM 분류**(`document.classify` 프롬프트: 활성 분류 목록 + description + 앞 4,000자 → `{code, confidence, reason}`).
4. 관리자가 수동 변경 시 `category_source=MANUAL`.

## 4. 분류별 메타데이터 필드 (seed)

필드 타입 `dimension`은 `{w, h, d, dia, dia2, len, unit:"mm", raw}`, `grade`는 `{standard, class, raw}`.

| 분류 | 필드 (key: 설명) |
|---|---|
| datasheet | model_no, product_name, filter_type, application, dimension, media, frame_material, frame_options, gasket, rated_airflow_m3h, initial_dp_pa, final_dp_pa, airflow_dp_curve, iso16890_class, iso29461_class, en1822_class, max_temp_c, max_rh, fire_rating, related_test_reports(list: report_no, standard, issue_date, result), revision |
| test_report | report_no, client, sample_name, model_no, sample_dimension, standard, test_date, issue_date, lab_name, lab_accreditation, result_class, test_airflow_m3h, test_aerosol, conditioning, initial_dp_pa, efficiency_by_size(list), epm1/epm2_5/epm10, coarse, mpps_um, integral_eff, local_eff, leak_test, dust_holding_g, eff_0_4um_initial, eff_0_4um_conditioned, notes(“UL 공식 인증 아님”, “폐지 규격” 등) |
| certificate | cert_no, cert_name, standard, holder, scope, product_codes, issue_date, valid_from, valid_until, issuer |
| delivery_record | as_of, records(list: delivered_ym, client, project_name, item_desc, models, quantities, notes) |
| company_profile | name, ceo, business_no, address, phone, email, is_sme, g2b_items, main_products |
| bid_notice | notice_no, title, buyer_org, contracting_org, contacts, bid_method, item_category_code/name, budget_krw, estimated_price_krw, bid_open_at, bid_close_at, opening_at, qualification_deadline_at, delivery_terms, delivery_place, warranty_terms, split_delivery, qualifications(list), required_documents(list) |
| bid_spec | spec_title, issuing_dept, written_date, items(list: name, size, quantity, type, media, frame), performance(list: item, test_standard, condition, metric, operator, value, unit), test_and_inspection, submission_docs, delivery_terms, warranty |
| bid_item_list | items(list: no, material_no, name, spec, unit, quantity, remarks) |
| bid_contract_terms | delivery_terms, penalty(지체상금), warranty, inspection, required_documents |
| bid_evaluation_criteria | criteria(list: 항목, 배점, 기준), pass_score |
| bid_restriction_reason | restriction_type, track_record_requirement, reason |

## 5. 메타데이터 추출 방식

1. **규칙 추출기(우선)** — 분류별 정규식/표 파서(`apps/documents/extractors/<category>.py`). initial-data 회사 자료(가상 PDF)는 레이아웃이 고정적이므로 **규칙만으로 100% 추출**되어야 한다(LLM 없이도 seed 가능). 예: `성적서 번호\n(AFT-\d{4}-\d{4})`, `외형 치수 \(W×H×D\)\n(.+)`.
2. **LLM 추출(보완)** — 해당 분류에 규칙 추출기가 없거나, 규칙이 **필수(required) 필드**를 채우지 못했을 때만 호출한다(규칙으로 충분한 문서에 비용을 쓰지 않기 위해). 규칙이 찾지 못한 필드만 `document.extract_metadata` 프롬프트(분류의 fields 정의 → JSON Schema 자동 생성)로 요청한다. 응답은 찾은 필드만 담은 배열 `[{key, value, raw, page, quote, confidence}]`(값은 문자열, specs/07 §2). LLM 미설정·호출 실패 시 규칙 결과만 저장하고 문서 안내 문구로 “LLM 단계 보류”를 남긴다.
3. 병합: `is_locked` 값 > RULE > LLM. 충돌 시 RULE 우선하되 LLM 값은 `extra.alternatives`에 보존.
4. **단위 정규화** (`apps/core/units.py`) — 저장 시 정규 단위로 변환하고 `raw_value`에 원문 보존:
   - 압력 → Pa: `mmAq`·`mmH2O` ×9.80665, `inH2O`·`in.wg` ×249.089, `kPa` ×1000
   - 풍량 → m³/h: `CFM` ×1.699011, `m³/s`·`㎥/s` ×3600, `CMH`·`CMM`(×60)
   - 길이 → mm: `inch`·`"`·`″` ×25.4. 치수 문자열 `24 x 24 x 12"`, `594×594×95㎜`, `OD445 x OD324 x L660mm`, `610×610×400~600mm`(범위) 파싱
   - 면풍속 m/s 유지, 온도 ℃
   - 단위 변환 함수는 단위 테스트 필수.
5. 숫자 표기 정리: `1,764,000`, `95.4% 이상`, `More than 90`, `Less than 100`, `이하/이상/미만/초과/이내` → `{operator: <=|>=|<|>|==|range, value, value_max?}`.

## 6. 도메인 매핑 (map 단계)
- datasheet → Product upsert(model_no 기준), related_test_reports는 TestReport 존재 시 연결.
- test_report → TestReport upsert(report_no) + Product 연결(model_no). `standard`에 “폐지” 포함 또는 EN 779 → `is_obsolete_standard=True`. “준용” 포함 → `is_official_certification=False`.
- certificate → Certificate upsert(cert_no), cert_type은 standard/이름으로 판정.
- delivery_record → 기존 해당 source_document 행 삭제 후 재생성, 모델명으로 Product M2M 연결. 발주처에 “발전|화력|복합|열병합|지역난방” → `is_power_plant=True`.
- bid_* → [08](08-compliance-evaluation.md) §2 공고 통합 추출에서 사용.
- 매핑은 관리자 “적용” 시 실행(회사 자료). `AppSetting: extraction.auto_apply_company`=false 기본. 초기 데이터 적재 시에는 자동 적용.
