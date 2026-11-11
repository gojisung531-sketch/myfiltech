# 분석·초안 입력 추적 — B6C

회사자료나 제품 선택이 바뀌어도 조회는 기존 결과를 그대로 보존한다. 새 실행부터 입력을 보존하고, 조회에서 입력 일치 여부를 계산한다. B6C에서 실제 분석·초안 생성·LLM·워커를 실행하지 않았다. 후속 Claude 검증 예산의 사용액은 0달러다.

## 상태와 표시 계약

|status|표시|의미|
|---|---|---|
|CURRENT|현재 입력과 일치|완료된 실행의 전체 입력과 현재 입력이 같은 추적 범위에서 일치함. 사업 요건 충족·정확성·제출 승인이 아님|
|STALE|갱신 필요|보존된 입력과 현재 입력이 다르거나 초안의 상위 판정이 갱신 필요|
|UNKNOWN|확인 불가|전체 과거 입력/완료·결과 연결이 없거나 검증할 수 없음. 현재 값을 과거 입력으로 소급 지정하지 않음|

`manual_modified=true`는 별도로 표시한다. 수동 수정본은 입력이 일치해도 `requires_review=true`이며 자동 덮어쓰기 안내를 하지 않는다. 입력 확인 불가도 직원 확인/후속 명시 실행의 대상이며 자동 재판정·재생성으로 이어지지 않는다.

기존 결과에 남은 B5C 실행 기록·B5D `analysis_context.input_sha256`은 부분 기록이다. 새 스키마의 전체 입력을 재구성하는 것으로 간주하지 않는다. B6C migration은 기존 판정/초안의 nullable `analysis_run`을 null로 남기며 백필 데이터 migration이 없다.

## 저장과 비교 범위

`core.AnalysisRun`은 실행 종류(EVALUATION/DRAFT), 시작·완료 시각, 옵션, 입력 JSON과 SHA256, 실행 전 수동 결과 지문, 완료 결과 스냅샷, 완료/실패 상태를 저장한다. 입력은 생성 후 모델 저장에서 수정할 수 없고 완료 결과 스냅샷도 수정하지 않는다. 일반 서비스의 명시 실행만 이 행을 만들며 GET은 생성하지 않는다. 현재 운영 DB에는 B6C에서 만든 실행 행이 없다.

|입력|추적 범위|
|---|---|
|정식 회사자료|Company, 전체 Product(비활성 포함), TestReport, Certificate, DeliveryRecord의 행 값·식별자·시각, 회사 원본/실적 제품 M2M|
|관련 문서|회사 원본·정식 자료 FK·대상 공고 첨부를 통해 연결된 Document의 원본 식별정보·기존 추출 텍스트/표·분류, 해당 DocumentMetadata/MetadataSchema|
|실제 파일|등록 SHA와 현재 업로드 바이트 SHA/가용성. 읽기 해시만 계산하며 재추출·OCR·원본 복사/변경 없음|
|공고 입력|업무 공고 필드, 요구조건 전체, 품목/사용자 제품 선택, 저장 후보 제품·점수/순위|
|기준·정책|기준일/모드, 정의된 evaluation/matching/report 설정과 llm.max_input_chars의 유효값, 활성 모델·생성 파라미터, 활성 evaluation/draft 프롬프트, 명시한 규칙/생성 소스 파일 SHA|
|초안 추가 입력|저장 판정 행 전체(수동 수정/근거/실행 연결 포함), 초안 생성에 참조하는 fit_score/fit_reason·bid.extra|

보수적으로 회사 전체를 의존 범위로 잡는다. 개별 요구에서 쓰지 않은 정식 인증/제품이나 메타데이터 변경도 갱신 필요가 될 수 있다. 부분 영향 최적화는 구현하지 않았다. 행의 updated_at도 보존하므로 내용이 같더라도 정식 재저장만으로 갱신 필요가 될 수 있다.

분석에 사용되지 않는 Job·LLM 로그·인증 토큰·사용자 로그인·검토 대기 관리대장151행은 입력에서 제외한다. provider 키/암호문/접속 URL·.env는 조회/복호화/스냅샷 대상이 아니다. 정책 JSON과 프롬프트 자체는 비밀키 보관 장소로 사용하지 않는다. 전체 입력 JSON은 회사 원문을 포함할 수 있어 DB 내부 provenance로만 보관하며 API는 식별 해시·이유를 제공한다.

## 실행 중 변경과 수동 보존

새 실행의 경계는 다음과 같다. B6C에서는 이 경로를 격리 테스트에서만 실행했다.

1. 짧은 트랜잭션에서 입력 테이블과 기존 결과에 대한 잠금을 잡고 입력/기존 결과 지문을 보존한다. 기존 서비스의 빈 Company singleton 초기화는 명시 실행 시에만 이 경계 안에서 수행한다.
2. 잠금을 해제한 뒤 기존 규칙/생성 계산을 수행한다. 기존 판정 배치 결과는 메모리에 모으고 중간 판정을 저장하지 않는다.
3. 저장 트랜잭션에서 같은 입력 테이블을 잠그고 현재 입력 및 기존 결과 지문을 다시 확인한다. 달라지면 `InputsChanged`로 저장 전체를 거부한다.
4. 모든 결과/이력/실행 연결을 함께 저장하고 입력을 한 번 더 확인한 뒤 완료한다. 저장 중 입력 변경이나 중간 실패도 이전 결과/이력을 보존하며, 실패 실행 기록은 FAILED로 남긴다.

PostgreSQL 경계 잠금은 추가/삭제 행도 방지하는 테이블 잠금이다. 실행 계산/외부 요청 동안 유지하는 설계가 아니지만 호출자가 전체 서비스를 별도 외부 transaction.atomic으로 감싸면 잠금 수명이 외부 트랜잭션까지 연장될 수 있다. 외부 장기 트랜잭션으로 호출하지 않아야 한다. SQLite 등의 다른 DB에 같은 동시성 보장을 주장하지 않는다.

기본 `keep_modified=True`는 기존 수동 판정을 그대로 건너뛰며 해당 행의 과거 실행 연결도 유지한다. 명시적 keep_modified=False라는 기존 덮어쓰기 옵션은 남아 있으나 B6C에서 사용하지 않았다. 실행 중 발생한 수동 편집은 이 옵션과 무관하게 지문 차이로 새 저장을 거부한다. 수동 제품 선택을 매칭 후보로 교체하는 동작은 없다.

수동 초안 내용·제목·확정 상태를 보존하고 이후 명시 생성은 새 버전을 만든다. 수동 저장이 실행 입력을 최신으로 재지정하지 않는다. 판정 자동 복원은 자동 이력의 원래 analysis_run_id를 복원하고, 이력이 실행 연결을 모르면 null/UNKNOWN으로 되돌린다. 변경자가 없는 수동 이력을 자동 이력으로 오인하지 않는다. 기존 이력 JSON을 갱신하지 않는다.

## 추가 API

|경로|추가 필드|
|---|---|
|GET `/api/bids/{id}/freshness`|판정 요약/각 판정, 모든 저장 초안 버전의 최신성, 현재 관찰 입력 해시/시각|
|기존 판정 목록·요구조건 include=evaluation|각 판정 `freshness`|
|기존 초안 목록·상세·버전 목록|각 저장 버전 `freshness`|
|기존 비교표|행별 freshness, `stored_result`, `current_reference`, `temporal_alignment`; 전체 판정 freshness와 legacy_flat_fields_mix_time_contexts|

기존 응답 필드·권한·내용은 보존했다. 상태 조회는 쓰기/Job/새 판정/LLM을 호출하지 않는다. 실제 기존 API11종의 모든 기존 중첩 필드 값을 대조했다.

`freshness`의 핵심 필드:

- `status/status_label`, `reasons[]`(변경 component·label·추가/삭제/수정 ID)
- `analysis_run_id`, `input_hash`, `current_input_hash`
- `analysis_at/analysis_completed_at`: 보존된 실행에서만 제공. 기존 입력 미상의 결과는 null
- `result_saved_at/last_edited_at`: 결과 저장/수정 시각. 분석 시각으로 사용하지 않는다
- `manual_modified`, `generated_result_unchanged`, `requires_review`, `automatic_refresh=false`

초안에는 별도 실행 입력과 상위 판정 상태를 사용한다. 판정 수동 답변 수정만으로도 해당 판정의 입력 일치는 유지될 수 있으나 이를 입력으로 사용했던 초안은 STALE이다. 새 초안이 현재 저장 판정을 읽었다고 해서 입력 미상/오래된 판정이 최신으로 승격되지는 않는다. 누락 판정이 있으면 전체 판정 요약도 CURRENT로 표시하지 않는다.

예시 (식별자는 합성 값):

```json
{
  "status": "STALE",
  "status_label": "갱신 필요",
  "analysis_run_id": 101,
  "analysis_at": "2026-10-26T09:00:00+09:00",
  "reasons": [{
    "code": "CERTIFICATES_CHANGED", "component": "certificates", "label": "인증 자료",
    "added_ids": [22], "deleted_ids": [], "modified_ids": []
  }],
  "manual_modified": true,
  "requires_review": true,
  "automatic_refresh": false
}
```

## 비교 화면 연계

프런트는 `stored_result`(기존 판정·회사 기재값·사유/근거·freshness)와 `current_reference`(현재 선택 제품·제조사 사양·현재 인증/성적서·실적)를 다른 시점으로 표시해야 한다. 기존 평면 필드는 호환을 위해 유지하지만 `legacy_flat_fields_mix_time_contexts=true`이고 `temporal_alignment=SEPARATE_CURRENT_REFERENCE_AND_STORED_RESULT`다. 두 값이 같은 입력 시점의 비교라고 표시하지 않는다. UNKNOWN을 현재 입력의 자동 충족/미달로 바꾸지 않는다.

CURRENT/STALE/UNKNOWN, 분석 시각·변경 사유·수동 수정 표시는 기존 충족/보완/확인 필요 판정과 별개다. 새로고침으로 재분석 버튼이나 유료 작업을 자동 실행하지 않는다. 프런트 배지/화면은 이번에 구현하지 않았다. 기존 PDF/XLSX 내용도 재생성하지 않았으며 내려받은 파일 자체에 새 최신성 표시를 붙이는 작업은 후속이다.

## 한계와 실제 결과

- 변경 이벤트별 작성자·변경 사유 대장, 승인 개정 번호, 단계별 매칭/적합도 출력의 최신성, 부분 영향 분석은 미구현이다. 임의 DB/파일 변경을 지속 감시하는 이벤트 시스템이 아니며 각 실행/조회 경계의 상태를 비교한다. 시각/값까지 원상복구한 중간 ABA 변경의 전 이력을 보장하지 않는다.
- 원본 파일은 SHA와 기존 추출/정식 값으로 식별하며 옛 원본 바이트를 자동 아카이브/복구하지 않는다. 모델 입력/프롬프트/정책 JSON은 보존하지만 확률적 LLM 답변의 동일 재현이나 외부기관 진위·효력을 보장하지 않는다.
- 명시한 소스 SHA 외의 모든 전이 의존성·Python/패키지·폰트/OS·외부 공급자 서비스 변경은 추적하지 않는다. 파일 시스템과 DB의 완전한 분산 트랜잭션은 없으며 최종 해시 확인 뒤 외부 파일이 바뀌면 다음 조회에서 차이를 확인한다.
- 실제 기존 판정37개·초안4종은 모두 UNKNOWN, analysis_run_id=null이다. 새 실행 행0, 실제 재판정/초안 생성/LLM0. 기존 Job1·2/수동 제품 선택/이력45/관리대장151행을 보존했다.
- 격리 검사57개 통과, 최종 실제 읽기32건 모두200, 기존 응답11종 호환 확인. 실제 원문·백업·API 대조 파일은 Git 제외 `.venv/b6c/`에만 있다.

## 복구

변경 전 `.venv/b6c/before-b6c.dump`와 `media-before.zip`, 원행/테이블/파일 해시 기록이 있다. dump TOC와 ZIP CRC/내용 SHA를 확인했으며 실제 복원은 하지 않았다. 전체 백업을 현재 DB에 바로 덮어쓰지 않는다.

B6C에서는 core.AnalysisRun 테이블과 nullable FK2개만 추가했고 백필/실행 행은0이다. 이후 실행이 없다면 기존 결과 원행과 비교한 뒤 코드·schema rollback을 별도로 계획할 수 있다. 새 실행이 생긴 뒤에는 스냅샷과 결과 연결을 먼저 별도 보존해야 한다. 다운 migration은 새 연결/실행 기록을 잃으므로 자동 복구 명령으로 사용하지 않는다. 먼저 격리 DB에 복원해 비교하고 B6C 이후 수동 변경을 구분한다.
