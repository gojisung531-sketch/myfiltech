# 시험성적서 관리대장 검토 대기 저장구조 (B2A)

현재 단계는 모델·마이그레이션 파일·격리된 테스트만 제공한다. 개발 DB에는 적용하지 않았으며, 적재 명령·API·승인·정식 자료 전환·제품 연결·PDF 연결은 없다. B1 리더는 계속 읽기 전용이다.

## 모델과 키

두 모델은 `apps/company/models.py`에 있으며 기존 `TimeStampedModel`의 `created_at`, `updated_at`을 가진다.

| 모델 | 필드 | 역할 |
|---|---|---|
| ReportRegisterVersion | id | 내부 식별자 |
| | sha256: Char(64), unique | 원본 바이트의 소문자 SHA256. 정규식 검증과 DB 제약 적용 |
| | display_name: Char(255) | 최초 기록한 표시 파일명. 경로/이름은 버전 키가 아님 |
| | parser_version: Char(100) | 해당 payload를 생성한 파서의 명시적 버전/코드 리비전 |
| | source_metadata: JSON, default=dict | B1 file 정보의 날짜 체계 등 재현 메타데이터. 원본 파일 자체가 아님 |
| ReportRegisterRow | id | 내부 식별자 |
| | file_version: FK(PROTECT), related_name=rows | 파일 버전. 행이 있으면 버전 삭제 차단 |
| | sheet_name: Char(128), row_number: PositiveInteger | 실제 시트명과 Excel 행 번호. 빈 시트명/1~1,048,576 밖 행은 DB 제약으로 거절 |
| | payload: JSON, default=dict | B1 원본 행 객체 전체. 임의 필드 제거·수치 보정 없이 저장할 자리 |
| | review_status: Char(20) | 기본 PENDING(검토 대기), NEEDS_CONFIRMATION(확인 필요). 승인/평가 가능 상태는 없음 |
| | ownership: Char(12) | UNKNOWN(기본), FILTECH, THIRD_PARTY |
| | test_target: Char(20) | UNKNOWN(기본), MEDIA, FINISHED_PRODUCT, OTHER |
| | is_lab_accredited: nullable Bool | null=공인 여부 미확인. 기관명만으로 추론하지 않음 |
| | is_official_certification: nullable Bool | null=공식 인증 여부 미확인. 공인시험과 별개 |
| | original_report_verified: nullable Bool | null=원본 성적서 대조 미실시/미확인. true/false는 별도 근거로 대조 성공/실패를 확인한 경우만 사용 |

원본 행의 유일 제약은 **(file_version, sheet_name, row_number)** 이다. `No.`, 성적서번호, 모델명, 발행일은 키가 아니다. 별도 조회용 성적서번호/모델 열을 복제하지 않으며 원문은 payload에서 확인한다. 번호 공란·중복, 다른 시트의 동일 번호, 같은 번호의 여러 시료를 허용한다. 병합된 식별정보를 공유해도 물리적인 두 행은 두 기록으로 남는다.

`clean()`은 payload가 JSON 객체인지, 비어 있지 않을 때 source의 SHA/시트/행이 관계형 출처와 일치하는지 검사한다. payload를 수정하지 않는다. Django의 일반 `save()`/`bulk_create()`는 `full_clean()`을 자동 호출하지 않으므로 B2B는 명시적인 전체 검증을 해야 한다. 빈 dict 기본값은 아직 자료가 없는 상태이며 정식 근거가 아니다. JSON 구조/의미 검증 전체, 변경 불가 DB 트리거, 범용 승인 이력 엔진은 이번에 만들지 않았다.

## B1 필드 대응과 미확인 상태

- B1 `file.sha256` → 버전 `sha256`, `file.name` → `display_name`; `file.date_system` 등은 `source_metadata`로 보존한다. 현재 B1 코드에는 파서 버전 출력이 없으므로 B2B에서 리더 코드 리비전과 대응되는 명시적 버전을 정해야 한다. 파일명만 보고 파서를 추정하지 않는다.
- B1 한 기록의 `source`, `fields`, `unmapped_cells`, `warnings`, `review` 및 향후 부가 키를 **그대로 payload 전체**에 보존한다. `source.sheet/row`를 관계형 좌표에도 기재하고, `source.file_sha256`과 버전 SHA 일치를 확인한다.
- `fields` 안의 셀/요청 셀 주소, raw_value/xml_value/value, number_format, headers/unit, normalized와 적용식, formula/cached_value/공유 수식 기준, merged_range를 분해하거나 제거하지 않는다. 날짜는 B1의 ISO 표현과 원시 Excel 일련번호를 함께 보존한다.
- 예를 들어 병합 시료의 요청 셀과 기준 셀이 달라도 `source.row`는 실제 시료 행이다. 기준 셀의 행으로 바꾸어 중복을 합치면 안 된다.
- B1 `review.original_report_verified=false`는 리더가 원본 PDF 검증을 수행하지 않았다는 표시다. 이것을 새 관계형 상태의 false(실제 대조 실패)로 복사하지 않는다. 원본 payload에는 그대로 남기고 새 세 가지 확인 상태는 모두 null로 시작한다. `review`와 관계형 검토 상태는 각각 파싱 당시 기록과 별도의 검토 상태다.
- ISO 29463을 포함한 규격 원문/버전·시료·조건·결과는 payload에 보존한다. `StandardFamily`로 강제 변환하거나 EN 1822/ISO 29461로 치환하지 않는다. 관리대장의 성능 행/재질 시료 행 집계나 SHEET/Model 기재 수를 제품 수로 해석하지 않는다.

## 파일 개정과 파서 개정

1. 동일 SHA는 동일 바이트의 파일 버전이다. 경로/파일명 변경으로 버전을 추가하지 않으며, 최초 표시명을 덮어쓰거나 경로별 버전을 만들지 않는다. 경로 별칭 수집은 현재 범위 밖이다.
2. 원본 바이트가 달라지면 새 SHA 버전을 만들 수 있다. 새 버전의 동일 시트/행 좌표도 별개 출처다. 옛 payload/행을 덮어쓰거나 두 버전의 같은 좌표가 동일 시료라고 자동 판별하지 않는다.
3. 동일 SHA·동일 파서 버전을 재처리할 때 기존 payload와 같으면 재사용하는 방식으로 B2B 멱등성을 설계한다. 내용이 다르면 자동 update하지 말고 중단해 차이를 검토한다.
4. 동일 SHA에 다른 파서 버전의 해석을 덮어쓰지 않는다. 현재 버전/행 모델은 하나의 최초 파서 해석만 보존한다. 새 해석은 별도 버전 표기가 있는 Git 제외 로컬 미리보기로 보존하고 DB 재적재를 보류한다. 여러 파서 실행 결과의 동시 저장은 별도 요청 후 설계한다. 파서가 바뀌었다는 이유로 원본 SHA를 조작하거나 다른 파일 버전을 꾸미지 않는다.

이 원칙은 향후 적재 경로가 지켜야 하는 정책이다. 현재 ORM을 임의로 호출하는 작업자에게까지 완전한 불변성을 강제하는 시스템은 아니며, 적재/갱신/승인 서비스 자체가 아직 없다.

## 평가 엔진과의 분리 및 후속 연결 제약

예정 흐름은 `원본 → B1 읽기 전용 preview → 별도 요청/검증 후 B2B 검토 대기 저장`까지다. 정식 Product/TestReport/Certificate로 이어지는 단계는 아직 없다. 두 모델에는 해당 테이블 FK, 자동 매핑, save 시그널, 승인 함수, 평가 쿼리·관리 API 등록이 없다. 분류/확인 값만 바꿔도 자동 승격되지 않는다.

- `evaluation/context.py::EvaluationContext.for_bid`는 현재 Product/TestReport/Certificate/DeliveryRecord만 조회하며 새 대기 모델을 읽지 않는다. `Company.load()`로 빈 회사 singleton이 생성될 수 있으나 성적서 승격과 다르다. 테스트에서 둘을 구분한다.
- `company/models.py::TestReport`의 `report_no(unique=True)`와 단일 product FK는 중복/다중 시료를 그대로 담을 수 없다. 허위 번호 생성·자동 병합으로 우회하지 않는다.
- `company/mapping.py::_test_report_fields`는 모델명으로 Product를 찾고, “준용” 포함 여부로 `is_official_certification`을 추론한다. `apply()`는 성적서번호 기준 update_or_create와 제품 사양서 등록 시 미연결 성적서 자동 연결을 수행한다. 검토 대기 적재에서 이 경로를 호출하면 안 된다.
- 기존 `TestReport.is_official_certification` 기본값 true, `StandardFamily` 열거형, `evaluation/grades.py`의 규격/등급 호환성 및 관련 규칙은 이번에 바꾸지 않는다. 후속 정식 전환 전에 nullable 상태·승인 근거·규격 확장의 API/serializer/규칙/테스트 영향을 함께 검토해야 한다.
- `evaluation/evidence.py`의 product/report/record 근거는 고정 page=1을 사용한다. 관리대장 셀을 그 함수에 넘기거나 이를 원본 PDF 페이지로 간주하면 안 된다. PDF 문서/페이지 연결이 없으면 아무 페이지도 만들지 않는다. 후속 연결은 실제 PDF 출처를 별도로 확인하고 고정 페이지 제약부터 해결해야 한다.

## B2B 시작 조건과 남은 확인

- 별도 사용자 요청 후 개발 DB 적용 대상·백업/보존 계획·마이그레이션을 검토한다. B2A에서 생성한 마이그레이션은 테스트 DB에서만 실행했다. 기존 `--noreload` 서버에는 새 모델이 아직 로드되지 않았으며 서버 재시작도 별도 조정 사항이다.
- 원본 SHA, 파서 버전, B1 레이아웃과 파일·행 건수를 재확인한다. 모든 행의 전체 payload 형식/출처를 검증하고 `full_clean()` 및 중복 충돌 처리·transaction을 포함한 전용 적재 경로를 먼저 만든다. B2A는 그 경로를 제공하지 않는다.
- 기본 검토 대기/UNKNOWN/null을 지킨 채 적재하고, Product/TestReport/Certificate·판정·LLM과 분리된 상태를 다시 확인한다. 단위·백분율·수식 캐시·모델 공란·미지의 시료 소유를 자동 보정하지 않는다.
- 루트 specs/README는 이번 수정 범위 밖이므로 변경하지 않았다. 통합 시 `specs/02-data-model.md`에 이 두 모델과 정식 자료와의 경계를 반영하는 문서 동기화가 필요하다.
- 필텍 확인 질문: 당사/타사 및 여재/완제품 구분, 같은 번호의 여러 시료가 뜻하는 관계, 모델 연결 기준, 원본 성적서·단위·시험조건의 확인 자료는 무엇인가? 답을 추정하거나 질문을 외부로 발송하지 않는다.
