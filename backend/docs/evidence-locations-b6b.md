# 근거 위치 API 계약 — B6B

조회 시 기존 인용과 원본 연결을 대조해 위치를 계산한다. 기존 필드·권한·저장 값은 유지하며 추가 필드만 제공한다. DB 쓰기, 파이프라인 재추출, OCR, 판정, 초안 생성, LLM, Job 실행은 없다. 위치 계산 결과를 새 판정이나 과거 판정의 근거 개정으로 저장하지 않는다.

## 제공 경로

|경로|추가 정보|
|---|---|
|`GET /api/company`|`evidence_locations`: 필드별 B6A 수동 원본·위치·인용 목록|
|`GET /api/certificates` 및 `/{id}`|`evidence_locations`: 해당 번호의 수동 메타데이터에 있는 위치만 반환|
|`GET /api/bids/{id}/requirements` 및 `/{rid}`|`source_location`: 저장 `source_quote`/`source_attachment`의 대조 결과|
|요구조건 `?include=evaluation`, `GET /api/bids/{id}/evaluations`|기존 `evidences[]`에 `source_location` 추가|
|`GET /api/bids/{id}/comparison`|행별 `source_location`, `stored_evidence_locations`, `current_company_locations`, `stored_evaluation_updated_at`, `current_references_revise_stored_evaluation=false`; 기존 `certificates[]`에 관계 구분과 위치 추가|
|`GET /api/documents/{id}/locate?quote=...&page=...`|임의 인용의 읽기 전용 대조. `page`는 PDF 물리쪽 제한으로만 사용. 인용 최대8000자, page 지정 시 양의 정수. 수동 확인을 주장하는 입력 옵션은 없음|
|`GET /api/documents/{id}/text`|기존 pages/page_count/tables 유지; `extracted_text`, `text_sha256`, `pages_kind` 추가|

문서 접근은 기존 인증/권한을 그대로 따른다. 원본은 기존 `/api/documents/{id}/download`에서 인증을 포함해 받는다. 새 공개 파일 URL이나 서버 로컬 경로는 만들지 않는다.

## 위치 객체

공통 필드는 `document_id`, `role`, 변경하지 않은 `quote`, `declared_page`, `location_kind`, `location_value`, `candidates`, `status`, `quote_status`다. 문서가 있으면 이름/형식·원본 SHA·`download_url`·`text_url`·`text_sha256`·`source_verification`·`comparison_basis`를 제공한다. 문서/출처가 없으면 문서 관련 부가 필드가 없을 수 있다.

- `location_kind`: `PDF_PAGE`, `SPREADSHEET_CELL`, `EXTRACTED_TEXT_RANGE`, 미확정이면 `NONE`.
- `location_value`: 단일 연결 위치. 여러 인용 후보가 있으면 null로 두고 모두 `candidates[]`로 제공한다. 후보의 kind/value/matched_text/match_mode를 사용한다.
- `source_verification`: 실제 업로드 바이트 SHA와 Document.sha256의 일치 여부. `VERIFIED`는 파일 동일성을 의미하며 저장 추출 텍스트의 원본 재현 정확도나 과거 판정 당시 바이트의 보장을 뜻하지 않는다.
- `declared_page_kind`: PDF는 `PHYSICAL_PDF_PAGE`, 그 외는 `LEGACY_NON_PHYSICAL_PAGE`. HWP/XLSX의 기존 page_count·source_page·evidence.page를 물리쪽으로 승격하지 않는다.
- `comparison_basis`: `STORED_EXTRACTED_TEXT`, `ORIGINAL_WORKBOOK_CELLS`, `B6A_MANUAL_METADATA`.

|status|뜻과 UI 처리|
|---|---|
|`EXACT_MATCH`|인용과 동일한 문자열이 한 곳. 해당 후보로 이동/강조 가능|
|`WHITESPACE_MATCH`|공백·줄바꿈만 무시하면 한 곳. 실제 `matched_text`를 강조하고 저장 quote는 그대로 표시|
|`MULTIPLE_MATCHES`|모든 공백 정규화 일치를 반환. 첫 후보 자동 선택 금지. 사용자가 후보를 고르게 한다|
|`QUOTE_NOT_FOUND`|문장부호 등은 고치지 않고 불일치 표시. 인용을 자동 수정하거나 유사 문장을 근거로 승격하지 않는다|
|`MANUAL_REVIEWED_PAGE`|B6A의 실제 수동 페이지를 파일 SHA·물리쪽 범위와 대조. 페이지 이동은 가능; `quote_status=HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED`이므로 OCR/문자 좌표 강조를 주장하지 않는다|
|`PAGE_ONLY`|명시된 물리 PDF 페이지는 확인, 대조 가능한 저장 텍스트가 없음. 페이지 이동만 가능, 인용 자동 대조는 `NOT_CHECKED`|
|`NO_QUOTE`|빈 인용을 모든 위치에 일치시키지 않음|
|`NO_VERIFIABLE_TEXT`|PDF 저장 텍스트가 없거나 실제 물리쪽과 구획 수가 달라 자동 페이지 연결 불가|
|`INVALID_PAGE`|제공 원본의 물리쪽 범위를 벗어남|
|`SOURCE_CHANGED`, `SOURCE_UNAVAILABLE`, `SOURCE_UNREADABLE`, `SOURCE_UNVERIFIED`|원본 변경/누락/읽기 실패/해시 부재. 자동 이동·강조를 확정하지 않음|
|`MISSING_DOCUMENT`, `MISSING_SOURCE`, `AMBIGUOUS_SOURCE`|문서나 수동 원본 연결이 없거나 중복. 다른 문서로 추정 연결하지 않음|

`QUOTE_NOT_FOUND`라도 `physical_page_verified=true`이면 명시된 PDF `declared_page`는 확인된 쪽이다. 이때 페이지 열기와 인용 강조의 검증 상태는 분리한다. 문서 전체를 여는 기능은 미확정 위치에도 제공할 수 있지만 확정 위치 강조처럼 표시하지 않는다.

## 형식별 이동·강조

**PDF:** `value.page`는 제공 PDF의 1부터 시작하는 물리쪽이다. `physical_page_verified`/`physical_page_count`는 실제 파일의 쪽 구조로 확인한다. 인쇄 쪽수와 다를 수 있다. 기존 download는 attachment 응답이므로 프런트는 인증된 바이트를 받아 PDF 뷰어에서 해당 물리쪽을 열어야 한다. URL fragment만으로 서버가 인라인 뷰어/강조를 구현했다고 가정하지 않는다. 이번에는 bbox/OCR 좌표를 만들지 않았다. 저장 페이지 텍스트에서 일치한 경우에만 `page_text_start/end`와 페이지 텍스트 해시가 있다.

**Excel:** 원본을 읽기 전용으로 열어 `sheet`와 실제 A1 `cell`을 반환한다. 빈 행/열을 제거한 추출 표의 인덱스를 셀 번호로 사용하지 않는다. 셀 내부의 인용 문자 start/end도 제공한다. 수식은 원문 문자열로만 읽고 실행하거나 캐시값을 재계산하지 않는다. 현재는 셀 하나 안의 연속 인용을 검색하며, 여러 셀을 합친 임의 문장/범위를 추정하지 않는다.

**HWP/일반 추출 텍스트:** `EXTRACTED_TEXT_RANGE`의 start/end는 `/text` 응답의 **extracted_text 전체 문자열**에 대한 0부터 시작하는 Unicode code point 범위이며 end는 제외한다. JS에서는 `slice(start_utf16, end_utf16)`을 사용할 수 있다. 먼저 `text_sha256`이 같은지 확인한 뒤 실제 `matched_text` 범위를 강조한다. text 페이지 배열을 다시 join해 다른 문자열에 오프셋을 적용하지 않는다.

`extracted_line_start/end`와 `extracted_block`은 저장 추출 텍스트의 행·빈 줄 경계 구획이다. 원본 HWP 레코드 문단 번호가 아니며 `original_hwp_section/paragraph`는 미확인 null이다. `section_heading`은 근처에서 실제로 나타난 번호형 텍스트 행을 표시하는 보조 맥락으로, 항목의 의미상 범위는 `section_scope_verified=false`다. `unverified_printed_marker`의 PAGE/1/5 등도 확인하지 않은 인쇄 표지 문자열일 뿐 이동용 물리쪽이 아니다. `/text.pages_kind=EXTRACTION_CHUNKS_NOT_PHYSICAL_PAGES`도 같은 제한을 알린다. HWP 원본 쪽으로 이동하거나 원본 뷰어에서 같은 구간을 강조하는 기능은 구현하지 않았다.

## 과거 판정과 현재 참고 자료

- `role=REQUIREMENT_SOURCE`: 저장 요구조건 인용의 출처.
- `role=STORED_EVALUATION_EVIDENCE`: **저장돼 있던** evidence의 type/id/page/quote만 대조한다. B6A의 새 인증서·수동 인용으로 빈 근거를 채우지 않는다. `saved_reference`를 함께 제공한다.
- `role=CURRENT_COMPANY_REFERENCE`: 현재 인증/회사 자료 메타데이터의 참고 위치. `fields`, `metadata_id/key`, 수동 확인 방식, `record_value_consistency`를 제공한다. 현재 값이 수동 검토 당시 값과 다르면 `DIFFERS_FROM_REVIEW`; 전체 결과의 오래됨 감지 기능은 아니다.
- 비교표의 인증 관계는 저장 ID가 실제 있으면 `SAVED_ID_REFERENCE`, 현재 등록 자료를 참고로 찾았으면 `CURRENT_REFERENCE_ONLY`. 위치가 잘 연결되어도 기존 판정 충족으로 전환하지 않는다.
- 저장 evidence에 원본 Document ID 스냅샷이 없으면 기존 type/id의 현재 원본 연결을 이용하고 `document_binding=CURRENT_RECORD_LINK`, `historical_source_snapshot_verified=false`를 명시한다. 명시 저장 ID가 있더라도 당시 파일 SHA를 검증할 저장 스냅샷이 없으므로 역사적 파일 동일성을 주장하지 않는다. 이번 기능은 개정 이력/오래됨 자동 표시나 재판정이 아니다.

## 예시 (합성 값, 실제 기업 원문 아님)

같은 문서의 두 번째 물리쪽에서 수동 확인한 명의:

```json
{
  "document_id": 101,
  "role": "CURRENT_COMPANY_REFERENCE",
  "fields": ["holder"],
  "quote": "Example Co.",
  "status": "MANUAL_REVIEWED_PAGE",
  "quote_status": "HUMAN_TRANSCRIBED_NOT_MACHINE_CHECKED",
  "location_kind": "PDF_PAGE",
  "location_value": {"page": 2},
  "physical_page_verified": true,
  "historical_evaluation_use": "NOT_ASSERTED"
}
```

HWP의 저장 추출 문자열이 `required words`일 때의 핵심 범위:

```json
{
  "document_id": 102,
  "role": "REQUIREMENT_SOURCE",
  "quote": "required words",
  "status": "EXACT_MATCH",
  "location_kind": "EXTRACTED_TEXT_RANGE",
  "location_value": {
    "start": 0, "end": 14, "start_utf16": 0, "end_utf16": 14,
    "offset_unit": "UNICODE_CODE_POINT", "end_exclusive": true,
    "original_hwp_section": null, "original_hwp_paragraph": null
  }
}
```

엑셀 단일 위치는 `location_kind=SPREADSHEET_CELL`, `location_value={"sheet":"Items","cell":"B5","start":0,"end":7,"cell_text":"ITEM001"}`처럼 제공한다. 동일 값이 다른 시트/셀에도 있으면 `MULTIPLE_MATCHES`, `location_value=null`과 각 셀 후보를 반환한다.

## 실제 검증과 남은 위치

공고2의37개는 HWP 인용 **동일32 / 공백 차이3**, 인용 불일치1, 스캔 PDF 물리쪽만 확인1이다. 요구조건14는 원문 따옴표 차이로 불일치이며 저장 인용을 고치지 않았다. 요구조건6은 물리1쪽을 직접 시각 확인했지만 재추출/OCR 없이 API는 PAGE_ONLY로 유지했다. 원본 HWP의 물리쪽·원본 레코드 문단 ID·추출 충실도는 미확인이다.

저장 판정 evidence71개는 위 공고 인용37개와 제품 참고34개다. 제품 참고34개는 저장 모델 인용이 지정 PDF 페이지 안에서 여러 번 나타나므로 `MULTIPLE_MATCHES`로 남겼다. 같은 페이지를 여는 것과 해당 모델 인용 중 하나를 자동 강조하는 것은 구분한다. 이를34개 독립 제품이나 새로운 판정으로 보지 않는다.

인증21건의 필드별 수동 위치171개와 회사11필드의13개 위치를 재사용했다. 스캔에 대한 자동 문자 일치/이미지 강조는 미구현이다. Excel 첨부는37개 요구조건의 직접 출처로 저장돼 있지 않다. 원본 위치 조회로 실제 두 품목의 셀을 확인했으며 이를 요구조건이나 제품의 추정 연결로 저장하지 않았다. 실제 기업 인용·위치·원응답 대조표는 Git 제외 `.venv/b6b/`에만 있다.
