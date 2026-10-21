# 시험성적서 관리대장 검토 대기 저장구조 (B2B)

파일 버전/원본 행 모델과 검토 대기 전용 적재 서비스·명령을 제공한다. B2B에서 개발 DB 백업 후 `company.0002_report_register_staging`을 적용하고 실제 한 버전 151행을 대기로 저장했다. B1 리더는 계속 읽기 전용이며 API·승인·정식 자료 전환·제품 연결·PDF 연결은 없다.

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

- B1 `file.sha256` → 버전 `sha256`, `file.name` → `display_name`; `file.date_system` 등은 `source_metadata.file`로 보존한다. B1 모듈에 고정 상수 `PARSER_VERSION = "filtech-report-register/1"`을 정의했다. B1 반환 payload를 바꾸거나 쓰기 기능을 추가하지 않았다.
- B1 한 기록의 `source`, `fields`, `unmapped_cells`, `warnings`, `review` 및 향후 부가 키를 **그대로 payload 전체**에 보존한다. `source.sheet/row`를 관계형 좌표에도 기재하고, `source.file_sha256`과 버전 SHA 일치를 확인한다.
- `fields` 안의 셀/요청 셀 주소, raw_value/xml_value/value, number_format, headers/unit, normalized와 적용식, formula/cached_value/공유 수식 기준, merged_range를 분해하거나 제거하지 않는다. 날짜는 B1의 ISO 표현과 원시 Excel 일련번호를 함께 보존한다.
- 예를 들어 병합 시료의 요청 셀과 기준 셀이 달라도 `source.row`는 실제 시료 행이다. 기준 셀의 행으로 바꾸어 중복을 합치면 안 된다.
- B1 `review.original_report_verified=false`는 리더가 원본 PDF 검증을 수행하지 않았다는 표시다. 이것을 새 관계형 상태의 false(실제 대조 실패)로 복사하지 않는다. 원본 payload에는 그대로 남기고 새 세 가지 확인 상태는 모두 null로 시작한다. `review`와 관계형 검토 상태는 각각 파싱 당시 기록과 별도의 검토 상태다.
- ISO 29463을 포함한 규격 원문/버전·시료·조건·결과는 payload에 보존한다. `StandardFamily`로 강제 변환하거나 EN 1822/ISO 29461로 치환하지 않는다. 관리대장의 성능 행/재질 시료 행 집계나 SHEET/Model 기재 수를 제품 수로 해석하지 않는다.

## 파일 개정과 파서 개정

1. 동일 SHA는 동일 바이트의 파일 버전이다. 경로/파일명 변경으로 버전을 추가하지 않으며, 최초 표시명을 덮어쓰거나 경로별 버전을 만들지 않는다. 경로 별칭 수집은 현재 범위 밖이다.
2. 원본 바이트가 달라지면 새 SHA 버전을 만들 수 있다. 새 버전의 동일 시트/행 좌표도 별개 출처다. 옛 payload/행을 덮어쓰거나 두 버전의 같은 좌표가 동일 시료라고 자동 판별하지 않는다.
3. 동일 SHA·동일 파서 버전/지문·동일 좌표 집합과 payload면 기존 버전/행을 재사용한다. 파일명·metadata·updated_at·수동 검토/소유/인증 상태를 덮어쓰지 않는다. 내용이 다르거나 일부 행만 있으면 자동 update/보충/삭제하지 않고 충돌로 중단한다.
4. 동일 SHA에 다른 파서 버전의 해석을 덮어쓰지 않는다. 현재 버전/행 모델은 하나의 최초 파서 해석만 보존한다. 새 해석은 별도 버전 표기가 있는 Git 제외 로컬 미리보기로 보존하고 DB 재적재를 보류한다. 여러 파서 실행 결과의 동시 저장은 별도 요청 후 설계한다. 파서가 바뀌었다는 이유로 원본 SHA를 조작하거나 다른 파일 버전을 꾸미지 않는다.

적재 서비스는 위 원칙을 검사한다. 현재 ORM을 임의로 호출하는 작업자에게까지 완전한 불변성을 강제하는 시스템은 아니며, 갱신/승인/정식 전환 서비스는 없다.

## B2B 명령·트랜잭션·파서 정책

`apps/company/report_staging.py::stage_filtech_reports`는 B1 결과를 검증한 뒤 두 대기 테이블에만 쓴다. 명령 기본값은 dry-run이다.

```powershell
# backend 폴더에서 실행. 기본은 조회만 수행한다.
& .venv/Scripts/python.exe manage.py stage_filtech_reports '<관리대장.xlsx>'
# 쓰기는 두 옵션을 명시해야 한다. 확인한 실제 파일 해시를 전달한다.
& .venv/Scripts/python.exe manage.py stage_filtech_reports '<관리대장.xlsx>' --apply --expected-sha256 '<소문자 SHA256>'
```

- 파서 버전은 실행 시각/Git HEAD/사용자 옵션으로 만들지 않는다. 해석 변경 시 명시적으로 올린다. `report_preview.py`, `core/units.py` 소스의 LF 정규화 SHA256 및 openpyxl 버전을 metadata.parser에 남긴다. 파서 버전을 올리지 않았더라도 지문/의존 버전이 달라지면 동일 SHA 재적재를 거절한다.
- 빈 source/fields, 필수 행 구조, JSON 왕복 불가능/비유한 값, 잘못된/중복 좌표, 셀 근거/수식 구조, 파일 SHA/시트/행 불일치를 쓰기 전에 거절한다. 원본 행 객체 전체를 그대로 저장하며 모르는 부가 키를 제거하지 않는다. 해석 규격/단위/시료 매핑을 바꾸지 않는다.
- 파일 해시는 읽기 전/후와 트랜잭션 안의 쓰기 전/후에 재확인한다. expected SHA 불일치나 적재 중 원본 변경도 전체 중단/롤백 대상이다. 실제 실행에서는 B1에서 확인한 SHA/성능 127·재질 24행을 확인한 한 버전만 저장했다.
- 한 파일 전체를 `transaction.atomic()`으로 처리하고 새 버전/각 행의 `full_clean()`을 명시적으로 호출한다. SHA에서 파생한 PostgreSQL transaction advisory lock으로 동일 SHA의 동시 CLI 실행을 직렬화하고 기존 버전/행에도 row lock을 사용한다. DB 제약 충돌이나 행 하나의 실패도 부분 적재를 남기지 않는다.
- dry-run은 조회만 하며 버전/행/검토 상태/시각을 수정하지 않는다. apply 재실행도 일치하면 읽기/잠금만 수행한다. 파서/지문, payload, 좌표 집합 충돌은 기존 자료를 건드리지 않고 중단한다. force/update/replace 옵션은 없다.
- metadata에는 B1 file·시트별 건수/누락/경고/병합 범위·중복 그룹 건수·제약 안내·파서 지문을 보존한다. records 전체나 성적서번호 목록을 버전 metadata에 중복 저장하지 않는다. stdout/예상 오류는 모드·건수·SHA·버전 ID·안전한 충돌 코드만 표시한다.

## 평가 엔진과의 분리 및 후속 연결 제약

구현 흐름은 `원본 → B1 읽기 전용 preview → 검증/명시적 apply → B2B 검토 대기 저장`까지다. 정식 Product/TestReport/Certificate로 이어지는 단계는 아직 없다. 두 모델에는 해당 테이블 FK, 자동 매핑, save 시그널, 승인 함수, 평가 쿼리·관리 API 등록이 없다. 분류/확인 값만 바꿔도 자동 승격되지 않는다.

- `evaluation/context.py::EvaluationContext.for_bid`는 현재 Product/TestReport/Certificate/DeliveryRecord만 조회하며 새 대기 모델을 읽지 않는다. `Company.load()`로 빈 회사 singleton이 생성될 수 있으나 성적서 승격과 다르다. 테스트에서 둘을 구분한다.
- `company/models.py::TestReport`의 `report_no(unique=True)`와 단일 product FK는 중복/다중 시료를 그대로 담을 수 없다. 허위 번호 생성·자동 병합으로 우회하지 않는다.
- `company/mapping.py::_test_report_fields`는 모델명으로 Product를 찾고, “준용” 포함 여부로 `is_official_certification`을 추론한다. `apply()`는 성적서번호 기준 update_or_create와 제품 사양서 등록 시 미연결 성적서 자동 연결을 수행한다. 검토 대기 적재에서 이 경로를 호출하면 안 된다.
- 기존 `TestReport.is_official_certification` 기본값 true, `StandardFamily` 열거형, `evaluation/grades.py`의 규격/등급 호환성 및 관련 규칙은 이번에 바꾸지 않는다. 후속 정식 전환 전에 nullable 상태·승인 근거·규격 확장의 API/serializer/규칙/테스트 영향을 함께 검토해야 한다.
- `evaluation/evidence.py`의 product/report/record 근거는 고정 page=1을 사용한다. 관리대장 셀을 그 함수에 넘기거나 이를 원본 PDF 페이지로 간주하면 안 된다. PDF 문서/페이지 연결이 없으면 아무 페이지도 만들지 않는다. 후속 연결은 실제 PDF 출처를 별도로 확인하고 고정 페이지 제약부터 해결해야 한다.

## 백업·적용 기록과 남은 확인

- 2026-10-22, 대상 `127.0.0.1:5432/filtech`(역할 filtech, PostgreSQL 18.6)와 적용 계획이 `company.0002`의 CreateModel 두 개뿐임을 확인했다. 실제 개발 DB를 pytest DB로 쓰거나 flush하지 않았다.
- 기존 `.env`를 읽어 pg_dump 자격 증명을 자식 프로세스 환경에만 전달했다. 백업은 `backend/.venv/b2b/filtech-before-b2b-20261022-075035-194448.dump`(190,674바이트). SHA256 `02f4b109ce1a03b1fcd26f912cc7e0c05b424f18e29e16e7c0e9153bef4a65fb`. pg_restore --list 성공, 같은 이름의 `.list`와 backup-manifest.json에 검사 기록 보관. **실제 복원 시험은 하지 않았다.** 기존 백업 덮어쓰기·DB 삭제/복원/재초기화 없음.
- 백업 검증 뒤 `manage.py migrate company 0002_report_register_staging --noinput` 적용. Django의 migration 이력/content type/permission 등록은 마이그레이션 부수 메타데이터이며 공고·첨부·정식 회사자료 변경과 구분한다. 후속 migrate --plan은 미적용 작업 없음.
- 실제 버전 ID 1에 성능 127·재질 24, 총 151행을 저장하고 모든 payload를 B1 결과와 대조했다. 전부 PENDING/UNKNOWN/UNKNOWN 및 확인 3개 null. 재실행은 151행 재사용, 새 버전/행 0개이고 payload·metadata·updated_at·검토 상태 해시가 동일했다.
- 공고/첨부/문서·정식 회사자료 테이블과 media 파일 4개는 적재 직전/후 동일했다. 기존 Company singleton 1개도 유지했으며 실제 DB 검증에 Company.load()/평가 컨텍스트를 호출하지 않았다. Product/TestReport/Certificate/DeliveryRecord 및 LLM 호출 로그는 0건 유지. 외부 socket·LLM provider 호출을 차단한 실제 명령도 성공했다.
- 기존 PID 5332(DB)·24964(8000 리스너)를 유지했고 상태 API 200을 확인했다. `--noreload` 서버는 재시작하지 않았고 여전히 이전 코드가 로드되어 있다. 별도 CLI가 새 코드를 사용하는 것이며 새 대기 HTTP API는 없다.
- 검사/백업/대조 자료는 모두 Git 제외 `.venv/b2b/`에 보관한다. 분석 정확도·원본 PDF 검증 완료로 해석하지 않는다. 다음 범위는 대기 목록 API/화면, 소유/여재·완제품 검토, 제품 연결 기준 및 정식 성적서 구조 설계를 별도로 정한 후 진행한다.
- 루트 specs/README는 이번 수정 범위 밖이므로 변경하지 않았다. 통합 시 `specs/02-data-model.md`에 이 두 모델과 정식 자료와의 경계를 반영하는 문서 동기화가 필요하다.
- 필텍 확인 질문: 당사/타사 및 여재/완제품 구분, 같은 번호의 여러 시료가 뜻하는 관계, 모델 연결 기준, 원본 성적서·단위·시험조건의 확인 자료는 무엇인가? 답을 추정하거나 질문을 외부로 발송하지 않는다.
