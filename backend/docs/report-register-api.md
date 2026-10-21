# 검토 대기 관리대장 조회 API (B3A)

프런트의 관리자 검토 대기 화면 연결용 읽기 계약이다. 저장된 JSON/관계형 자료만 조회하며 Excel 재파싱·적재·검토 수정·제품 연결·정식 성적서 전환·판정·LLM 호출을 하지 않는다. 새 모델/마이그레이션은 없다. 이 API를 제공했다고 원본 성적서 검증이나 제품 분류가 완료된 것은 아니다.

## 경로와 권한

| 경로 | 응답 |
|---|---|
| GET /api/report-register-versions | 버전 목록, 페이지네이션 |
| GET /api/report-register-versions/{id} | 버전 정보 + 현재 시트/검토상태 집계 |
| GET /api/report-register-rows | 원본 시료 행 목록, 검색/필터/페이지네이션 |
| GET /api/report-register-rows/{id} | 한 행 요약/관계형 검토 상태 + 저장 원본 payload 전체 |

- 기존 JWT 인증과 `IsAdminRole`을 그대로 사용한다. 기존 정의에 따라 ADMIN 또는 superuser만 허용한다. 익명 401, 입찰담당자 403이다. LLM 미설정 상태에서도 관리자는 조회할 수 있다.
- GET/HEAD/OPTIONS만 허용한다. 관리자도 POST/PUT/PATCH/DELETE는 405이며 검토 수정/승격 action은 없다. 기존 `/api/test-reports` 등 정식 자료 API에는 대기 행을 포함하지 않는다.
- 기존 `/api` prefix와 trailing slash 없는 SimpleRouter를 재사용한다. 기존 API 계약/권한은 변경하지 않았다.

## 목록·정렬·파라미터

목록 응답은 기존 `StandardPagination`의 `{count, next, previous, results}`이다. count는 필터 후 전체 건수(integer), next/previous는 페이지 URL 또는 null, results는 해당 페이지의 배열이다. 기본 20개, page_size가 200을 넘으면 200개로 제한한다. page는 1부터 시작한다.

버전 목록은 id 오름차순, 행 목록은 file_version_id → sheet_name → row_number → id 오름차순으로 고정한다. 별도 정렬 옵션은 없다. 페이지네이션은 DB count/limit/offset으로 수행한다. 목록에서 payload 전체나 source_metadata를 읽어 Python으로 전체 표를 펼치지 않으며, FK별 추가 쿼리를 만들지 않는다.

| 파라미터 | 대상/타입 | 동작 |
|---|---|---|
| page | 두 목록, 양의 정수 | 미지정 1. 정상 숫자이나 마지막 페이지 밖이면 404 |
| page_size | 두 목록, 양의 정수 | 기본 20, 최대 200으로 제한 |
| file_version | 행 목록, 양의 버전 id | 일치하는 버전만. 존재하지 않는 유효 id는 빈 목록 |
| sheet_name | 행 목록, 비어 있지 않은 문자열(최대 128자) | 정확히 일치. 원본 시트명 유지, 공백 제거 없음 |
| review_status | 행 목록, PENDING / NEEDS_CONFIRMATION | 관계형 검토 상태로 필터 |
| ownership | 행 목록, UNKNOWN / FILTECH / THIRD_PARTY | 관계형 소유 구분으로 필터 |
| test_target | 행 목록, UNKNOWN / MEDIA / FINISHED_PRODUCT / OTHER | 관계형 시험대상으로 필터 |
| q | 행 목록, 최대 200자 문자열 | 아래 다섯 실제 value의 대소문자 무시 부분 검색(OR). 앞뒤 공백 제거, 빈 문자열은 검색 없음 |

검색은 `payload.fields.{report_no,model,sample_name,test_standard,lab_name}.value`만 대상으로 한다. issue_date, raw_value, 셀 주소, 수식, 경고, unmapped_cells, payload.review는 검색 대상이 아니다. JSON null/없는 키는 문자열 "null"로 만들어 검색하지 않는다. 필터와 q는 AND로 결합하며 결과가 없어도 200/count=0이다.

숫자 파라미터는 최대 9223372036854775807을 허용한다. 잘못된 숫자/0/음수/빈 필터나 열거값은 일관된 400이다. 정의되지 않은 파라미터는 기존 serializer 방식대로 무시하며 반복된 키는 마지막 값을 사용한다. 상세 id가 없거나 형식에 맞지 않으면 404이다.

## 버전 응답

목록과 상세의 공통 필드:

| 필드 | 타입/기준 |
|---|---|
| id | integer, 파일 버전 id |
| sha256 | string, 원본 바이트 SHA256 |
| display_name | string, 저장된 표시 파일명 |
| parser_version | string, 저장된 파서 버전 |
| row_count | integer, **현재 DB에 저장된 해당 버전의 행 수** |
| created_at / updated_at | ISO 8601 시각 문자열 |

상세만 `sheet_counts: {시트명: integer}`, `review_status_counts: {상태: integer}`를 추가한다. 현재 관계형 행으로 계산하므로 B2B 당시 메타데이터의 집계와 별개다. 행이 없으면 row_count=0, 두 집계는 `{}`다. source_metadata 전체, 파일 시스템 경로, 환경값, 백업 위치는 응답 필드가 아니다.

## 행 응답

| 필드 | 타입/기준 |
|---|---|
| id / file_version | integer, 대기 행 id / 파일 버전 FK id |
| source | `{file_sha256: string, sheet: string, row: integer}`. 관계형 파일 버전·시트·행 좌표 |
| summary | report_no/model/sample_name/test_standard/lab_name/issue_date의 6개 키. 저장된 B1 fields의 **value**를 그대로 반환 |
| review | 아래 관계형 검토 필드 6개 |
| warning_count | integer, 보존된 warnings 배열의 항목 수(중복 포함) |
| warning_codes | string 배열, 보존된 code의 중복을 제거한 정렬 목록 |
| created_at / updated_at | ISO 8601 시각 문자열 |
| payload | **상세만**. 저장된 원본 행 JSON 전체, 변형 없음 |

summary 값은 보통 문자열/날짜 ISO 문자열이며, 원본 value의 JSON 타입을 유지한다. 없는 키/JSON null은 null, 원래 빈 문자열은 ""로 남긴다. 모델 공란을 시료명/임의 제품명으로 보충하지 않는다. 성적서번호가 같아도 행 id/좌표가 다르면 별개 결과다.

관계형 review는 `review_status`, `ownership`, `test_target`(위 열거형 문자열), `is_lab_accredited`, `is_official_certification`, `original_report_verified`(각 Boolean 또는 null)이다. null은 미확인이며 false로 바꾸지 않는다. 이 값들은 별도의 관계형 검토 상태다.

반면 **payload.review는 파싱 당시 보존한 원문 스냅샷**이다. B1의 `original_report_verified=false`는 리더가 PDF 대조를 수행하지 않았다는 표시이며 대조 실패로 재해석하면 안 된다. 관계형 상태와 달라도 조회 중 동기화/저장하지 않는다.

payload의 source/fields/unmapped_cells/warnings/review 및 셀·단위·수식 캐시·공유 수식·병합 근거는 저장된 그대로다. 위치는 **관리대장 셀 출처**이며 원본 시험성적서 PDF 페이지를 뜻하지 않는다. PDF 페이지/문서 id를 만들어 붙이지 않는다.

최소 합성 예시(실제 기업자료 아님):

```json
{"id":7,"file_version":2,"source":{"file_sha256":"합성 예시 해시","sheet":"성능","row":4},"summary":{"report_no":"TEST-ONLY","model":null,"sample_name":"","test_standard":"TEST STANDARD","lab_name":"TEST LAB","issue_date":null},"review":{"review_status":"PENDING","ownership":"UNKNOWN","test_target":"UNKNOWN","is_lab_accredited":null,"is_official_certification":null,"original_report_verified":null},"warning_count":1,"warning_codes":["missing_value"],"created_at":"2026-10-22T09:00:00+09:00","updated_at":"2026-10-22T09:00:00+09:00"}
```

## 오류·검증 범위

- 입력 오류 400: 기존 `{detail:"입력값을 확인하세요.", code:"invalid", errors:{파라미터:[오류]}}` 형식. 인증/권한/없는 id/미지원 메서드도 기존 공통 에러 형식을 사용한다.
- 검토 상태 저장·승격·제품 연결 endpoint는 없다. HEAD/OPTIONS도 쓰지 않는다. 조회는 Company.load/get_or_create, 적재/매핑/평가/LLM 서비스나 파서를 호출하지 않는다.
- 테스트는 최소 합성 입력과 격리된 test_ PostgreSQL DB를 사용한다. 실제 서버 조회는 기존 대기 자료를 읽기만 하며 기업 원문·상세 payload·토큰을 대화/검증 로그에 출력하지 않는다. UI는 별도 단계에서 이 계약에 연결해야 한다.
