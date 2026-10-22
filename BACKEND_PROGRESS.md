# 백엔드 인수인계 — Backend B4B

- 상태: **B4B 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 인증·시험규격·제출서류·난연의 미등록/미확인 처리와 합성 자동 검사만 보완. 실제 공고 판정·정답셋/정확도 검증·DB 적재/설정 변경·제품 연결·LLM 호출 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B4A `4399dd3` 이후 깨끗한 상태에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `fix(backend): distinguish missing evidence from confirmed shortfalls` (`git log -1 --oneline`).
- 변경: `backend/apps/evaluation/rules.py`, `tests/{test_missing_evidence_rules.py,test_rules.py,test_qualification_rules.py}`(evaluation 아래), `backend/docs/{evaluation-rule-policy.md,company-data-revision-plan.md}`, 이 파일. 모델·마이그레이션·매핑·API/권한·프런트·루트 공통 문서·다른 worktree·원본 변경 없음.

## 변경한 의미와 보존한 분기

- 인증 종류가 미등록이면 회사 미보유/신규 취득을 단정하지 않고 **NEEDS_CONFIRMATION + 원본/내부 등록 확인**. SME null과 true+유효기간 미상도 확인 필요이며 필수 자료 HIGH 위험 유지. SME false·실제 인증 만료는 NEEDS_SUPPLEMENT, 알려진 유효 인증의 MET 유지.
- 시험규격은 품목이 있으면 선택 제품의 성적서만 사용. 미매칭이면 확인 필요이며 회사 전체/타 제품 자료를 빌리지 않음. 회사 공통 요구는 회사 범위 조회 유지. 같은 family 미등록도 원본/등록 확인부터 안내하며 시험 의뢰를 확정하지 않음.
- 발행일 미상은 연령 제한 유무와 무관하게 확인 필요. 알려진 모든 자료가 제한을 초과하면 보완 필요 유지. 날짜 미상 후보를 오래된 것으로 삭제하지 않음. 날짜/기관 조건을 통과하는 후보가 있으면 그 후보만 근거로 선택.
- 명시 기관 정보의 빈값/미확인/지원하지 않는 조건과 명시적 비공인·미인정을 구분. KOLAS 요구에 일반 공인 표기만 있으면 미확인. 실제 기관 부정은 보완 필요 유지. 제한된 문자열 구분이며 기관의 인정서/시험 범위 전체 체계는 아님.
- 제출 성적서/실적이 없으면 미보유를 단정하지 않음. 일부 후보가 있어도 품목·기간·원본·금액·시점 전체의 제출 적합성은 확인 필요로 남기고 후보 근거를 제공. 품목별 제출 후보도 선택 제품으로 제한. 인증서와 회사 작성 서류의 기존 충족 분기는 유지. 실적 수치 규칙 전체를 재작성하지 않음.
- 난연 자료 미등록/제품 미매칭은 확인 필요와 원본 등록 확인. 공식 Listing 요구에 명시적 비공식 자료만 있는 보완 필요, 기존 공식/허용된 준용 시험의 충족 분기 유지. 모든 결과를 확인 필요로 바꾸지 않음.
- RuleResult/API verdict 문자열·기존 권한·수동 수정/복원 계약 유지. 공식인증 Boolean 기본 true/준용 문구 추론, 인증 시작일/복수 기간/예외, 시험 판본·여재/완제품·고정 page=1 및 나머지 치수/등급/효율/차압/실적 규칙은 남은 범위. 이번에 업무 숫자·허용오차를 새로 하드코딩하거나 기존 값을 임의 변경하지 않음.

## 자동 검사와 실행 환경

- 신규 검사부터 작성: 수정 전 **29 failed / 16 passed**, 수정 후 최초 45 passed. 추가 경계(설정 연령 제한·다른 규격·폐지규격 날짜·제품별 실적 후보)를 포함한 **최종 신규 50 passed**. 합성 unsaved 객체를 사용하며 DB 접근 허용 표식 없음, Company.load/컨텍스트 DB 로드 금지, 설정은 명시적 테스트 대체. 기업 원문/가상 문서 fixture 사용 없음.
- 관련 B3A/B2B/B2A/B1·단위·등급·accounts·설정·기존 회사자료 API/적재 차단 회귀 묶음 **230 passed (9.37s, 당시 신규45 포함)**. 이후 추가한 5경계를 포함해 신규50 재확인(0.21s). 중복 제외 검사 항목은 235개이며 전체 pytest 통과라는 뜻이 아님. 변경된 옛 fixture 기반 규칙 검사 두 파일의 기대 의미는 갱신했지만 해당 가상 문서 경로는 실행/복원하지 않음. 기존 원본 누락 실패 8개·WeasyPrint 문제 미해결, 일괄 skip/삭제 없음.
- 시작 시 개발 **5432/8000 리스너 없음**, 개발 DB 읽기 전용 접속은 시간 초과. 기존 개발 DB/서버를 기동·재시작하지 않음. 별도 테스트는 기존 PostgreSQL 18.6 바이너리로 **`backend/.venv/b4b/pg-test` / 127.0.0.1:15432 / test_filtech_b4b**만 사용. 실제 .env는 바꾸지 않고 로컬 테스트 설정에서 endpoint를 고정·검사. pytest가 test_ DB를 제거한 뒤 잔존 테스트 DB 없음 확인, 임시 서버 PID13800만 경로/포트 확인 후 종료.
- 외부 Python socket 접속 시도 0회(격리된 로컬 PostgreSQL libpq 제외). `check` 문제0, `makemigrations --check --dry-run` 변경 없음은 기존 dummy DB/접속 차단 runner로 검증. 변경 Python4개 ruff·format, `git diff --check` 통과.
- 명령/로그: `backend/.venv/b4b/run_tests.py`로 신규 규칙/등급 및 B3A/B2/B1·accounts·core 설정·선택 회사 API/초기 적재 차단 테스트 실행. `tests-before.log`, `tests-after.log`, `regressions.log`, `tests-final-unit.log`, `check.log`, `migration-check.log`를 Git 제외 보관. 기존 개발 DB를 test DB로 재사용/flush하지 않았고 회사자료 fixture 19개를 복원·적재하지 않음.

## 실제 자료·정책 차이와 다음 필수 작업

- 기존 개발 DB가 꺼져 있어 행 건수/논리 내용 해시의 최신 SQL 대조와 현재 저장 AppSetting/활성 PromptTemplate 조회는 **미확인**. 이를 테스트 DB 결과로 대신하지 않음. 개발 pgdata **1,564개 파일**, media **4개**, .env, B4A 공고번호 불일치 기록의 SHA는 작업 전후 동일(`offline-preservation.json`). 기존 검토 대기/공고/첨부 대상에 쓰기·제품 연결·판정 저장·재분석을 하지 않음.
- **새 규칙은 테스트/별도 프로세스에만 반영됨.** 기존 서버 반영/기동·재시작 없음, 기존 저장 판정은 갱신되지 않았고 최신 결과로 간주하면 안 됨. 테스트용 Q: 매핑은 Unicode 대상 경로 대조 후 해제 완료. 개발용 경로/.env는 유지.
- `apps/core/defaults.py`와 `apps/llm/prompt_defaults.py`의 옛 판정 정의는 서로 같지만 증빙/시험규격 부족을 넓게 보완 필요로 설명하여 이번 개인 정의와 차이가 있음. 현재 저장값/프롬프트는 개발 DB 접속 불가로 확인하지 못함. 운영 seed/프롬프트/설정을 덮어쓰지 않음. 실제 LLM 검증 전 규칙·저장 판정 정의·활성 프롬프트를 개정/보존 절차와 함께 맞춰야 함.
- `backend/docs/evaluation-rule-policy.md`: 변경 전후 분기, 실제 미달/정보 미상, 기존 정책값(설정과 고정값)·근거 미확인 범위, 남은 제약, 검사/서버 미반영 기록. 설정화와 업무적 타당성 검증을 구분함.
- **다음 필수 단계 설계**는 `backend/docs/company-data-revision-plan.md`: 정식 자료 개정 식별자/분석 입력 스냅샷, 자료·코드/정책 변경 후 재분석 필요, 매칭/후보·적합도·판정·파생 초안의 재계산 범위, 수동 선택/판정/초안 보존·재확인, 검토 대기와 정식 반영 구분, GET/새로고침의 유료 분석 금지. 이번 모델/마이그레이션/API 구현은 하지 않음.
- 공고 폴더/파일명 **20230342721**과 본문 **20230323830-00** 관계는 여전히 미확인. 번호·파일명·DB/첨부 조합을 수정하지 않음. B4A 최종 상세는 `.venv/b4a/review-v2/`이며 초기 초안과 구분. 별도 범위 지정 전 실제 공고 분석/정답셋·자료 적재·제품 연결·LLM·다음 개정 추적 구현을 자동 진행하지 않고 중단.

---

# 이전 B4A 인수인계 (당시 관찰 기록)

- 상태: **B4A 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 실제 과거 공고 한 건의 근거 대조·자료 공백·필텍/멘토 질문·판정 코드 점검 후보만 정리. 판정/정답셋/정확도 검증 완료가 아님.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B3A `e8947be`의 깨끗한 작업본에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `docs(backend): review evidence and gaps for one real bid pilot` (`git log -1 --oneline`).
- 커밋 변경은 **`backend/docs/analysis-pilot-plan.md`와 이 파일만**. 기능/API/모델/마이그레이션/파서/판정 코드·프런트·루트 공통 문서·다른 worktree 수정 없음. 상세 기업 원문·모델/개별 성적서번호·성능 수치·파일 원본은 커밋하지 않음.

## 검토 범위·확인된 사실과 미확인

- 대상: 지정 폴더 **20230342721**의 공고문·규격서·품목명세서·사유서와 개발 DB **bid=1**의 첨부 네 개. **최우선 공백: 공고문 파일명 번호와 달리 본문의 입찰공고번호는 20230323830-00**(추출 L34-35, S-identity). 정정공고/오분류를 추정하지 않고 공고·첨부 조합 확정을 보류. 이하 10묶음은 지정 첨부에 대한 후보이며 특정 공고의 확정 요구조건/적격성이 아님. DB notice_no/source_ref/마감도 비어 있고 title은 첫 첨부명, DRAFT. DB sha256 공란도 보정하지 않음. 지정 원본과 업로드 media 네 개의 바이트 SHA는 동일하지만 번호 상충을 해결하지는 않음.
- 기업 루트 **117개 파일**을 목록으로 구분한 뒤 관련 소개서·카탈로그·직접생산/중소기업/공급·정비 자격 자료와 기존 관리대장 미리보기만 사용. 관련 원본 파일 **11개**. 개찰이력·다른 공고·가상 회사자료·fixture를 실제 기술 근거로 쓰지 않음.
- 요구조건 **10개 묶음의 부분집합**: 페어 형식/치수/여재, 순유효면적, 등급/규격, 평균효율/중량법, 초기차압/풍량, 고습 차압변동, 공인기관/원본·시험대상별 제출, 물품 제조 등록/직접생산, 중소기업/예외, 단일 계약 실적/제출. 수치·연산자·규격/판본·조건·예외 및 선택하지 않은 범위를 상세 JSON에 보존. 전체 요구사항 추출/적격성 확인으로 보고하지 않음.
- 관련 제품 설명과 관리대장 후보를 찾았으나 시험 판본·시험풍량·평균/초기/MPPS 항목·페어/단품·여재/완제품·소유 관계는 미확인. 소개서/카탈로그 주장을 원본 시험 결과로 보지 않으며 모델명으로 연결하지 않음. 사용 습도와 차압변동 시험, 최소 보증과 실제 측정값을 구분함.
- 제품코드 문자 일치만으로 후보를 정하지 않고 외형/구조와 조건으로 범위를 좁힘. 관련 관리대장 **네 행**의 전체 payload를 B1 보존 미리보기와 정확히 대조. 원본 관리대장 바이트 SHA도 B1과 일치. 모든 151행을 사람이 검토/분류한 것은 아님. 나머지 행은 다음 작업의 선행 검토 조건이 아님.
- 후보 개별 성적서 원본은 제공 파일명 목록·후보 번호 검색·선택 문서 검토 **확인 범위에서 파일 미발견**. 회사가 원본을 보유하지 않는다고 단정하지 않음. 관리대장 좌표는 성적서 PDF 페이지가 아니며 원본 대조 완료/당사 완제품/공인시험·공식인증 상태를 저장하지 않음.
- 현재 검토일과 과거 입찰 마감·실적 공고일 기준을 구분. 제공 소개서는 현재 연도의 자료이며 과거 소개서 변경 이력은 재현하지 않음. 별도 최신 자격 문서의 범위·기관·기간은 소개서 요약과 별개로 확인. 직접생산 문서의 현재/과거 기간 행도 분리했으며 당시 정보망 상태·유지를 재현했다고 하지 않음.
- 먼저 확인할 질문: **폴더·파일명/본문 공고번호 불일치 원인과 올바른 첨부 조합**. 이후 관련 두 후보의 원본 성적서/시료·제품 대응, 제안 페어 도면·순유효면적/고습 시험, 병기 시험표준·판본의 인정 기준, 단일 계약 한 건의 실적증명·금액·완료일, 현재/당시 자격 유지·신청 자료. 질문은 작성만 했으며 외부 발송 없음.

## 코드 점검·상세 산출물

- 우선 수정/실험 후보 **5개**: ① 미등록/미확인과 실제 부족·근거 사용 자격 구분(모델명 연결/공식인증 추론 포함), ② 표준 판본·시험대상·효율 항목의 비교 가능성, ③ 차압/풍량/습도 조건 및 실제 비교값과 인용 근거 일치, ④ 인증 시작/종료·품목 특이사항·실적 공고일 기준, ⑤ 고정 page=1 대신 실제 위치/미상 보존.
- `evaluation/{rules.py,grades.py,evidence.py,context.py}`, `company/{mapping.py,models.py}`, 관련 추출/단위 코드의 **정적 관찰**만 수행. 다른 등급 체계 비교 차단·정규화된 필수특이사항 검사는 이미 있는 보호장치로 구분. 실제 함수 호출/동작 실패 재현/수정은 하지 않음. 정확한 코드 위치·현재 구현·다음 합성 사례·기업 확인 필요 항목은 `backend/docs/analysis-pilot-plan.md`에 기록.
- Git 제외 **최종 상세는 `backend/.venv/b4a/review-v2/analysis-pilot-detail.md`**, 같은 폴더의 `review-notes.json`(10묶음 사실·공백·질문·추론, verdict 모두 null), `evidence-index.json`(**34개** 인용/셀 근거의 경로·SHA·위치), `identity-discrepancy.json`, `original-report-search.json`. 상세 실제 값·개별 성적서번호·모델 후보는 이 로컬 자료에만 보존. 기업 파일 목록은 상위 `b4a/corporate-inventory.json`.
- 보조 자료: 상위 b4a의 `selected-pdf-text.json`, 원본 HWP 저장 텍스트/추출 표, 품목 셀 JSON, 선택 PDF 페이지 PNG 및 최종 review-v2의 `verified-notice-db-correspondence.json`, `review-validation.json`, `static-code-observations.json`, `preservation-verification.json`. 기존 출력은 덮어쓰지 않음. 상위 b4a의 초안 상세는 식별 상충 반영 전 기록으로 보존했으며 최종 참조는 review-v2만 사용. .venv 전체 Git 제외 확인.

## 검증·보존과 다음 시작점

- HWP 두 개는 기존 파서 재추출과 DB 텍스트 일치. 위치는 추출 구획/행/표로 기록하고 HWP의 PAGE를 물리 페이지로 대응하지 않음. 텍스트 인용은 정확 일치 검사, 스캔 사유서·공급 등록증은 OCR 없이 렌더링 직접 판독으로 명시. 관련 PDF 페이지/표를 육안 대조하고 카탈로그 좌우 표 혼합을 피함. 원본에서 단위가 불명확한 정보는 null로 남김.
- 원본 **11개 SHA**와 기존 media **4개 SHA** 종료 대조 동일. DB 시작/종료는 각각 `default_transaction_read_only=on` + `REPEATABLE READ, READ ONLY`로 확인. **public 39개 테이블의 건수·전체 내용/시각 해시 모두 동일**. 인증/토큰 테이블도 변화 없음. `db-before.json`/`db-after.json`에는 테이블 건수·해시만 보존.
- 버전1개/대기151행·payload·검토/미확인 상태·updated_at 보존. Company1, Product/TestReport/Certificate/DeliveryRecord0, 공고1·첨부4·문서4, LLM 로그0 보존. 정식 자료 0을 회사의 실제 제품/성적서 미보유로 해석하지 않음.
- 기존 8000 리스너 **5048**, PostgreSQL 5432 **5332** 시작/종료 동일. 서버/DB 재시작·워커·로그인/토큰 발급·API 분석 호출 없음. Company.load/평가 컨텍스트·매핑/적재·초안/LLM 서비스는 호출하지 않음. DB 쓰기·제품 연결·분류/검토 저장·원본 파일 수정 없음.
- 문서 검토 단계이므로 pytest·의미 없는 단위 테스트·기존 전체 테스트를 반복하지 않음. 원문 인용·위치·후보 payload·해시/보존 및 코드 관찰 anchor를 확인하고 `git diff --check` 통과. 기존 B3A 테스트 결과는 아래 당시 기록이며 B4A 판정 정확도 측정으로 사용하지 않음.
- 다음은 **공고번호·첨부 조합부터 확인하고 별도 범위 지정 후** 위 코드 우선순위와 최소 자료로 수정/합성 사례 설계 또는 관리자 검토 화면 연계를 진행. 이후 두 후보의 원본/제품 대응과 핵심 조건을 확인하며 전체 151행 검토·자동 연결·판정 실행을 자동 진행하지 않는다. 현재 상세 대조는 사람 검토 전 후보 상태로 보존하고 중단.

---

# 이전 B3A 인수인계 (당시 관찰 기록)

- 상태: **B3A 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 관리자 전용 검토 대기 조회 API만 구현·검증. 제품 연결·정식 전환·검토 수정·판정·LLM 호출·프런트 수정 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B2B `6b73be5`의 깨끗한 작업본에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `feat(backend): add admin-only report register read APIs` (`git log -1 --oneline`).
- 변경: `backend/apps/company/report_register_api.py`, `backend/apps/company/urls.py`, `backend/apps/company/tests/test_report_register_api.py`, `backend/docs/report-register-api.md`, 이 파일만. 모델·마이그레이션·기존 API 구현·파서·적재/매핑/평가 서비스·환경 설정 변경 없음.

## 실제 경로와 UI 연결 계약

- `GET /api/report-register-versions`, `GET /api/report-register-versions/{id}`: 파일 버전과 현재 DB 행 수, 상세의 시트별/검토상태별 집계. 저장 당시 metadata 집계와 구분하며 source_metadata/서버 경로/백업 위치를 응답하지 않음.
- `GET /api/report-register-rows`, `GET /api/report-register-rows/{id}`: 출처·6개 실제 value 요약·관계형 review·경고 수/코드·시각. 전체 원본 payload는 상세에만 변형 없이 반환. 최상위 미확인 Boolean null과 payload.review의 false를 별개로 보존.
- 기존 `IsAdminRole`, GET/HEAD/OPTIONS만 허용. 익명 401, 담당자 403, 관리자 쓰기 405. 기존 인증·LLM 게이트는 변경하지 않음.
- 행 필터: file_version/sheet_name/review_status/ownership/test_target. q는 번호/모델/시료명/규격/기관의 `fields.*.value`만 부분 검색. 없는 키·null 안전, 셀/수식/경고/원문 전체 검색 없음. 잘못된 필터 400, 없는 상세/페이지 404, 빈 결과 200/count=0.
- 기존 count/next/previous/results 페이지네이션, 기본 20·최대 200. 버전 id순, 행 file_version_id/sheet_name/row_number/id순. DB JSON 투영·count/limit/offset 사용, 전체 payload 목록 로딩·N+1·새 인덱스/캐시 없음.
- 응답 필드/타입·합성 예시·빈값·오류·PDF와 관리대장 셀 출처의 차이는 **`backend/docs/report-register-api.md`** 참조. 다음 별도 범위는 관리자 검토 대기 화면을 이 네 경로에 연결하는 것. 화면 구현/연결은 아직 하지 않음. 다른 worktree/채팅 수정·메시지 없음.

## 검사 결과와 실행 방법

- 신규 API 테스트 **33개**, B1/B2A/B2B·단위·accounts 권한·기존 회사자료 API/초기 적재 차단 회귀 포함 **164 passed (4.51s)**. 별도 `test_filtech_b2a` PostgreSQL에서 최소 합성 자료로 실행 후 테스트 DB 제거. 실제 개발 DB에 테스트 입력/계정 생성·flush 없음. Python 외부 socket 시도 0회(로컬 PostgreSQL libpq 제외).
- 익명/담당자/관리자 권한, 네 경로의 HEAD/OPTIONS·쓰기 거절, 집계·20/7 페이지·최대 크기·고정 순서, 중복 번호 유지, null/없는 모델, 실제 value만 검색, 필터/400/404, payload.review와 관계형 값의 분리 확인. 목록 SQL은 count+페이지 **2쿼리**, full payload 미선택. 조회 전후 대기/정식/판정 자료 불변과 기존 정식 API의 대기 자료 미노출 검증.
- 명령은 기존 `.venv/b2a/run_tests.py`에 `apps/company/tests/test_report_register_api.py`, `test_report_staging_service.py`, `test_report_register_staging.py`, `test_report_preview.py`, `apps/core/tests/test_units.py`, `apps/accounts` 및 선택한 기존 회사자료/적재 차단 테스트를 전달. 전체 출력: `backend/.venv/b3a/tests.log`.
- `check` 문제 0개, `makemigrations --check --dry-run` 변경 없음(기존 접속 차단 runner). 변경 Python 3개 ruff/format 및 `git diff --check` 통과. 기존 자료 누락 실패 8개·WeasyPrint DLL 문제는 해결/전체 테스트 통과로 처리하지 않음.

## 서버 반영·실제 조회·자료 보존

- 기존 --noreload 서버의 포트·실행 명령·부모 실행 파일·두 프로세스의 실제 작업 경로를 대조한 뒤 **현재 backend Django만 한 번 재시작**. 이전 시작 PID 13608/리스너 24964 → 현재 시작 **24552**/8000 리스너 **5048**. PostgreSQL **5332**(5432)는 그대로이며 UI/워커/다른 프로세스 종료·시작 없음.
- 기동 명령: backend 작업 경로에서 `.venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload`. 기존 .env·DB·인증 키·옵션 유지, `Start-Process -WindowStyle Hidden` 사용. 새 stdout/stderr: `backend/.venv/b3a/server.stdout.log`, `server.stderr.log`. 중복 서버 없음.
- 실제 HTTP: 상태 200(llm_configured=false), 관리자 로그인/내 정보 200, 네 조회 경로 200. 버전 **id=1/151행**, **성능127·재질24**, PENDING151 확인. 첫/다음 각20행·페이지 재조회 일치/중복 없음, 상세 payload와 DB 원문 일치, 모델 없는 재질 상세 null·시트 필터24행, 잘못된 필터400·없는 상세404·빈 결과200 확인. 원문/번호 목록·토큰은 출력/커밋하지 않음.
- 실제 담당자 계정은 없어 임의 생성하지 않음. 담당자 거절은 격리 테스트 검증 결과임. 새 경로 익명401도 실제 HTTP로 확인.
- 조회 전후 public **39개 테이블**의 건수/전체 내용 해시를 대조. 정상 로그인으로 `accounts_user.last_login` 및 `token_blacklist_outstandingtoken`만 변화. 나머지 37개 테이블의 payload·검토 상태·updated_at 포함 내용 해시 동일. 버전1개/대기151행의 PENDING/UNKNOWN/UNKNOWN·미확인 플래그 null 유지.
- 기존 Company1, Product/TestReport/Certificate/DeliveryRecord0, 공고1·첨부4·문서4·LLM 로그0 보존. 기존 공고 목록과 정식 자료 네 목록도 HTTP200 확인. 기존 media **4개 파일 해시 동일**. 자료 재적재·migration 적용·원본 엑셀 재파싱·Company.load/get_or_create·평가/LLM 실행 없음.
- Git 제외 검증 자료: `backend/.venv/b3a/` 아래 테스트 로그, `before-http.json`/`after-http.json`(테이블 건수/해시만), `media-before.json`, `live-verification.json`, `restart.json`, 재기동 전후 작업 경로 확인 자료와 로컬 검증 도구. 기존 B2B 백업은 보존. 루트 공통 문서 동기화가 필요하면 후속 조정하며 이번 수정 범위 밖 파일은 손대지 않음.
- 소유/여재·완제품 분류 확정, 검토 수정/이력, 제품 연결, 정식 전환, 원본 PDF 검증, LLM 및 다음 단계 자동 진행은 하지 않음. 다음 요청을 기다림.

---

# 이전 B2B 인수인계 (당시 관찰 기록)

- 상태: **B2B 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 개발 DB 백업·B2A migration 적용·실제 관리대장 한 버전의 검토 대기 적재/재실행 검증 완료. 제품 연결·정식 성적서 전환·판정·LLM·새 API·프런트 수정 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B2A `ba437ef` 이후 깨끗한 상태에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `feat(backend): stage report register rows with atomic idempotent import` (`git log -1 --oneline`).
- 변경: `backend/apps/company/{report_preview.py,report_staging.py,management/commands/stage_filtech_reports.py,tests/test_report_staging_service.py}`, `backend/docs/report-register-staging.md`, 이 파일. 기존 모델/마이그레이션 파일·API/평가/매핑 코드는 변경하지 않음.

## 실제 DB와 저장 결과

- 대상 확인: **127.0.0.1:5432/filtech**, 역할 filtech, PostgreSQL 18.6. 적용 전 이력 43개·테이블 37개. 미적용 계획은 `company.0002_report_register_staging`의 CreateModel 두 개뿐임을 코드/`migrate --plan`으로 확인.
- 복구용 custom-format pg_dump: `backend/.venv/b2b/filtech-before-b2b-20261022-075035-194448.dump` (**190,674바이트**). SHA256 `02f4b109ce1a03b1fcd26f912cc7e0c05b424f18e29e16e7c0e9153bef4a65fb`. 자격 증명은 기존 설정→자식 프로세스 환경으로만 전달. 기존 백업 덮어쓰기 없음.
- `pg_restore --list` 성공 및 공고 TABLE DATA 목록 확인. 같은 이름의 `.list`, `backup-manifest.json` 보관. **실제 복원 시험은 하지 않음**. DB 삭제/복원/재초기화/flush 없음.
- 백업 검증 후 `manage.py migrate company 0002_report_register_staging --noinput` 적용 성공. 이후 `migrate --plan` 미적용 작업 없음. 기존 테이블에서 변경된 것은 migration 이력/content type/permission 등록 3종뿐이며 데이터 테이블 해시는 유지됨. 현재 public 테이블 39개.
- 실제 파일 SHA256: `0257bb970c4198796baae08fa6b2b6dc4bdc5750e530096e7d9a728443009afe`. B1 값과 실행 전후 동일. 실제 입력 경로는 아래 B1 기록 참조. 원본 파일 수정 없음.
- 실제 dry-run → 성능 **127행**, 재질 **24시료 행**, 총 **151행** 확인 후 apply. 저장된 **ReportRegisterVersion ID 1**, 파일 버전 1개·원본 행 151개. payload 151개 전체를 SHA/시트/행별 B1 객체와 대조해 일치 확인.
- 151개 모두 관계형 상태 **PENDING/UNKNOWN/UNKNOWN**, `is_lab_accredited`/`is_official_certification`/`original_report_verified` 모두 **null**. B1 payload.review의 false는 원문에 보존하며 관계형 false로 복사하지 않음. 이 수는 제품 수/원본 PDF 검증 수가 아님.
- 같은 명령 재실행 → **새 버전 0·새 행 0, 기존 버전 1·151행 재사용**. 대기 테이블의 전체 내용 해시(payload·검토 상태·metadata·updated_at 포함) 동일. 실제 DB에 고의 충돌/오류 자료를 만들지 않음.
- 백업 직전부터 최종 대조까지 Company **1**, Product/TestReport/Certificate/DeliveryRecord **0**, 공고 **1**, 첨부 **4**, 문서 **4**, LLM 호출 로그 **0**의 건수와 내용 해시 보존. 기존 media **4개**의 파일 해시 동일. 검증에서 Company.load()/평가 컨텍스트를 실제 DB에 호출하지 않음.
- 기존 PostgreSQL PID **5332**, Django 시작 PID **13608**/8000 리스너 **24964** 유지. 재시작·워커 시작 없음. `GET /api/system/status` **200**, llm_configured=false. `--noreload` 서버는 이전 코드 그대로이며 별도 CLI만 새 저장 코드를 사용한다. 대기 목록 HTTP API는 없음.

## 명령·파서·충돌 정책

- `stage_filtech_reports <xlsx>` 기본은 **dry-run**. 쓰기는 `--apply --expected-sha256 <확인한 소문자 SHA256>` 필수. force/update/replace 옵션 없음. 기존 `preview_filtech_reports`는 읽기 전용 유지.
- 고정 파서 상수: **`filtech-report-register/1`**. 리더 코드에 선언하며 현재 HEAD/시각/사용자 옵션으로 만들지 않음. metadata.parser에 `report_preview.py`·`core/units.py`의 LF 정규화 SHA256과 openpyxl **3.1.5** 버전 보존. B1 반환 payload 형식/해석은 변경하지 않음.
- 전체 JSON 저장 가능성, 비어 있지 않은 source/fields, 필수 구조·셀 근거·단위/수식 구조·SHA/시트/행·유일 좌표를 쓰기 전에 검증. 전체 원본 객체를 변형 없이 보존. metadata에는 file·시트별 집계/경고·파서 지문만 저장하고 원문 행/번호 목록을 중복 저장하지 않음.
- 한 파일 전체 `transaction.atomic`, 새 버전/각 행에 `full_clean()` 실행. SHA별 PostgreSQL transaction advisory lock과 기존 버전/행 잠금으로 동시 실행 직렬화. 중간 실패/DB 제약/원본 변경 시 전체 롤백.
- 동일 SHA·파서/지문·좌표 집합·payload면 기존 자료만 재사용. 이름 변경도 동일 버전이며 표시명/시각/수동 검토 플래그를 수정하지 않음. 파서/지문·payload·좌표 집합 불일치나 일부 행만 있는 버전은 충돌로 중단하고 보충/삭제하지 않음. 다른 SHA는 일반 정책상 새 버전 가능하나 이번 실제 실행은 위 한 버전만 수행.
- 실제 실행: `& .venv/Scripts/python.exe manage.py stage_filtech_reports '<B1 실제 원본 경로>' --apply --expected-sha256 0257bb970c4198796baae08fa6b2b6dc4bdc5750e530096e7d9a728443009afe`. 실제 apply/재실행은 `.venv/b2b/run_guarded_stage.py`로 외부 socket·LLM provider 호출을 차단한 상태에서 수행하여 두 실행 모두 시도 0회 확인.

## 검사·로컬 자료와 다음 범위

- 신규 적재 검사 **23개**, B1/B2A·단위·B0 차단 회귀 포함 **100 passed**. 별도 `test_filtech_b2a` PostgreSQL 테스트 DB에서만 오류/충돌/동시 실행/롤백 검증 후 자동 제거. 실제 개발 DB를 pytest 대상으로 사용하거나 flush하지 않음. 최소 합성 입력만 사용.
- 기본 dry-run 무변경, 최초 적재, 재실행/검토 상태/시각 유지, 이름 변경 멱등, 동일 번호 다중 행, 구조·SHA·좌표/JSON 오류, 파서/지문/payload/부분 집합 충돌, 중간 실패 롤백, 적재 중 원본 변경, B1 합성 workbook 왕복, 공식 자료/LLM 분리 및 동일 SHA 동시 실행을 확인.
- `check` 통과, `makemigrations --check --dry-run` 변경 없음(접속 차단 로컬 runner 사용), 적용 후 실제 `manage.py check`도 문제 0개. 변경 Python 4개 ruff·format 및 `git diff --check` 통과. 기존 자료 누락 실패 8개와 WeasyPrint 문제는 해결/전체 통과로 처리하지 않음.
- 로컬 Git 제외 자료는 `backend/.venv/b2b/`: `tests.log`, `check.log`, `migration-check.log`, `migrate-plan.log`, `migrate.log`, `migrate-plan-after.log`, `dry-run.json`, `apply.json`, `reapply.json`, `actual-verification.json`, `preservation-verification.json`, `http-status.json`, `guard-results.jsonl`, 백업/목록, 각 단계 테이블 건수/해시·media manifest. 원문 값/번호 목록·비밀값을 stdout/문서/커밋에 복사하지 않음. 백업과 상세 JSON의 Git 제외 확인.
- 다음은 별도 범위 지정 후 진행: 대기 목록 API/화면, 당사/타사·여재/완제품 검토, 동일 번호의 여러 시료 관계, 제품 연결 기준, 원본 성적서/단위/조건 확인 및 정식 성적서 구조 개편. 제품 연결·정식 전환·규격/등급 호환·고정 PDF page=1 우회 금지. 분석 정확도/원본 성적서 검증 완료로 보고하지 않음. 외부 질문 발송 없음.

---

# 이전 B2A 인수인계 (당시 관찰 기록)

- 상태: **B2A 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 저장 모델·마이그레이션 파일·테스트·설계 문서만 구현. 개발 DB 적용·실제 자료 적재·제품 연결·판정·LLM 호출·새 API 없음. B2B 자동 진행 금지.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B1 `597ffb2` 이후 깨끗한 상태에서 시작. B0 환경·기존 데이터·서버 보존.
- 완료 커밋: `ba437ef` — `feat(backend): add isolated report register staging models`.
- 변경: `backend/apps/company/models.py`, `backend/apps/company/migrations/0002_report_register_staging.py`, `backend/apps/company/tests/test_report_register_staging.py`, `backend/docs/report-register-staging.md`, 이 파일만. 프런트·루트 공통 문서·기존 API/serializer·기존 평가/매핑 코드·B1 리더 변경 없음.

## 저장구조와 기존 엔진 분리

- `ReportRegisterVersion`: SHA256(unique, 소문자 64자리 검증/DB 제약), 최초 표시 파일명, 명시적 parser_version, source_metadata(JSON callable default=dict). 동일 SHA는 이름/경로/파서 변경만으로 두 버전이 될 수 없음. 다른 SHA의 개정본은 별도 버전으로 보존.
- `ReportRegisterRow`: 파일 버전 FK(PROTECT)·시트·행의 복합 고유키, B1 전체 payload(JSON default=dict), 검토 PENDING·소유 UNKNOWN·시험대상 UNKNOWN 기본값. 소유는 당사/타사/불명, 대상은 여재/완제품/기타/불명 구분 가능. 빈 시트와 Excel 행 범위 밖 좌표는 DB 제약으로 거절.
- 성적서번호·No.·모델명을 고유키로 사용하지 않음. 번호 공란/중복·다중 시료·병합 기준 셀·단위/변환식/조건/수식 캐시·매핑 밖 값·규격 원문은 payload에 그대로 보존. ISO 29463 자동 치환 없음.
- 공인시험(`is_lab_accredited`), 공식인증(`is_official_certification`), 원본 성적서 대조(`original_report_verified`)는 **서로 다른 nullable Boolean, 기본 null**. B1 payload의 원본 대조 false를 관계형 상태로 자동 복사하지 않음.
- Product/TestReport/Certificate FK·등록 시그널·적재/승인/승격 서비스·API·PDF 연결 없음. 기존 EvaluationContext 조회는 새 대기 모델을 읽지 않으며 분류/인증 플래그만 지정해도 승격되지 않음.
- `clean()`은 출처 SHA/시트/행 충돌과 잘못된 payload/source 객체를 거절하며 원문을 고치지 않음. 일반 ORM save/bulk_create는 full_clean을 자동 실행하지 않으므로 B2B는 별도 검증 필수. 무조건 append-only를 강제하는 이력 엔진은 만들지 않음.
- 같은 SHA를 새 파서로 재해석할 때 기존 parser_version/payload를 덮어쓰지 않고 별도 버전 표시의 Git 제외 미리보기로 남긴 뒤 DB 저장 보류. 다중 파서 실행의 동시 저장은 후속 설계. 자세한 필드·B1 대응·개정 정책은 `backend/docs/report-register-staging.md` 참조.

## 검사와 실제 DB 미적용 확인

- 새 migration `company.0002_report_register_staging`은 **CreateModel 두 개뿐**이며 기존 TestReport/규격군/Boolean 기본값/평가 규칙 변경이나 데이터 마이그레이션 없음.
- 생성 및 `check`, `makemigrations --check --dry-run`은 로컬 `.venv/b2a/offline_manage.py`로 실행. 해당 프로세스에만 dummy DB backend를 지정하고 DB 연결·Python socket 접속을 예외로 차단. 설정 파일/.env 변경 없이 실행했으며 접속 시도 **0회**. `check` 문제 0개, 마이그레이션 누락 검사 `No changes detected`.
- 신규 저장구조 **21개 테스트**: SHA/이름/파서 충돌, 좌표 중복/범위, 다른 행·시트의 동일 성적서번호, 공란 식별정보, 다른 SHA의 같은 좌표, JSON/병합/조건/단위/캐시 왕복, 독립적인 JSON 기본값, 미확인 null과 명시적 false, 보호 삭제, 잘못된 출처/FK, 평가 자료와의 분리.
- B1 미리보기·단위 유틸·B0 회사자료 차단 회귀 포함 **77 passed**. 실제 제품 fixture/기업 엑셀/상세 JSON 사용 없음. 기존 가상 회사자료 복원/적재 없음.
- 테스트는 전용 PostgreSQL **`test_filtech_b2a`**에서 새 migration과 저장을 검증한 뒤 pytest가 DB를 제거함. 모델 테스트는 접속 DB가 `test_` 이름이며 current_database()와 일치하는지도 확인. 개발 DB 재사용/flush 없음. Python 외부 socket 접속 시도 0회(로컬 PostgreSQL 테스트 연결은 libpq 사용).
- 명령: `& .venv/Scripts/python.exe .venv/b2a/run_tests.py apps/company/tests/test_report_register_staging.py apps/company/tests/test_report_preview.py apps/core/tests/test_units.py apps/documents/tests/test_documents_api.py::test_load_initial_data_endpoint apps/documents/tests/test_documents_api.py::test_company_seed_command_is_blocked --tb=short`.
- 기존 제품/정식 성적서/인증에 같은 모델명·번호가 있어도 대기 행 저장 전후 값 불변, 평가 컨텍스트에는 기존 정식 자료만 조회됨. 빈 평가 컨텍스트가 `Company.load()`로 만드는 회사 singleton은 테스트에서 구분하여 확인. 실제 판정 실행 없음.
- 개발 DB 스키마/마이그레이션 이력을 읽기 전용으로 대조: 시작/종료 모두 **43개 적용 이력·37개 public 테이블**, 새 migration 적용 이력/대기 테이블 **없음**. 개발 DB에는 `migrate`를 실행하지 않음. 병행 UI의 로그인·공고 데이터 변화는 전체 불변이라고 주장하지 않으며 손대지 않음.
- 변경 Python 3개 파일(모델/마이그레이션/테스트)의 ruff·format 검사와 `git diff --check` 통과. 기존 자료 누락 실패 8개와 WeasyPrint DLL 문제는 이번에 해결/전체 통과 처리하지 않음.
- 로컬 검사 도구/로그: `backend/.venv/b2a/{offline_manage.py,b2a_test_settings.py,run_tests.py,tests.log,check.log,migration-check.log,dev-schema-before.json,dev-schema-after.json}`. 스키마 대조 파일에는 테이블명/마이그레이션명만 저장. 전부 Git 제외이며 비밀값/기업 원문 커밋 없음.
- 기존 PostgreSQL PID **5332**(5432), Django 시작 PID **13608**/리스너 PID **24964**(8000) 유지, 재시작·워커 시작 없음. **실행 중인 --noreload 서버는 새 모델을 아직 반영하지 않음.** B2A 저장 기능이 실제 서버에서 사용 가능하다고 보고하지 않음.

## B2B 조건과 확인 질문

- **별도 요청 후** 개발 DB 적용 대상/보존 계획을 확인하고 migration 적용·서버 반영을 조정한다. 그다음 원본 SHA/파서 버전·행 건수·전체 payload/source 일치를 검증하고 멱등성/충돌 중단/transaction이 있는 전용 대기 적재 경로를 만든다. 아직 적재 명령이 없으며 기존 B1 명령은 읽기 전용 그대로임.
- 대기 자료 저장과 정식 성적서/제품 연결은 다른 단계다. 기존 TestReport 번호 고유 제약/단일 product, mapping.py의 모델명 자동 연결·공식인증 추론, evidence.py의 고정 page=1을 그대로 우회 사용하면 안 됨. 규격군/등급 호환성과 기존 Boolean 변경 영향도 후속 검토. 루트 specs/README 동기화 제안은 설계 문서에 남겼으며 이번 범위 밖 파일은 수정하지 않음.
- 필텍 확인 질문: 당사/타사·여재/완제품을 구분할 근거는 무엇인가? 같은 번호의 여러 시료는 어떤 관계인가? 모델 연결 기준은 무엇인가? 원본 성적서와 단위/시험조건을 확인할 자료는 무엇인가? 추정 답변이나 외부 질문 발송 없음.

---

# 이전 B1 인수인계 (당시 관찰 기록)

- 상태: **B1 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 읽기 전용 관리대장 미리보기만 구현. B2·DB 적재·제품 연결·판정·LLM 호출은 진행하지 않음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 시작 시 깨끗함. B0 `43a85d3`을 보존하고 환경 재설치·초기화 없이 진행.
- 완료 커밋: `597ffb2` — `feat(backend): add read-only Filtech report register preview`.
- 변경: `backend/apps/company/report_preview.py`, `backend/apps/company/management/{__init__.py,commands/__init__.py,commands/preview_filtech_reports.py}`, `backend/apps/company/tests/test_report_preview.py`, 이 파일. 프런트·루트 공통 문서·모델·마이그레이션·API 변경 없음.

## B1 결과와 데이터 문제

- 입력: `C:\Users\김가은\Desktop\2026-2학기\IT와비즈니스혁신\찐 프로젝트\기업제공 자료\필텍 시험성적서 관리대장.xlsx`. 원본 읽기만 수행.
- 입력 SHA256 전후 동일: `0257bb970c4198796baae08fa6b2b6dc4bdc5750e530096e7d9a728443009afe`.
- 성능: **127개 데이터 행**, 성적서번호 기재 셀 120개, `SHEET/Model` 기재 **40행**. 이전 조사 127/40과 일치. 선언 범위 `A1:BS1048576`, 실제 저장 셀 7,807개, 병합 32개. XML 스트리밍으로 저장된 셀만 처리하며 max_row만큼 펼치지 않음.
- 재질: **24개 시료 행**, 번호 등 식별정보가 직접 기재된 행은 **23개**. `B23:E24` 영역의 열별 병합으로 24행이 23행의 번호·일자·기관을 공유함. 이전 23행 관찰과의 차이는 이 추가 시료 행이며, 임의 합치기/삭제 없이 두 행과 병합 기준 셀을 보존. 저장 셀 440개, 병합 4개. 모델 열 자체 없음.
- 성능 누락: 모델 87행, 성적서번호/발행일/시험기관 각 7행, 시험규격 11행, 풍량 9행, 초기차압 13행. 효율 관련 수치가 없는 행 86개(등급 기록 여부와 별개). 빈값을 0으로 보정하지 않음.
- 성적서번호 중복 **12그룹/33개 행**(성능 21행, 재질 12행; 시트 간 중복 그룹 0). 번호가 같아도 행을 모두 유지. 순번 `No.` 중복도 성능 3그룹/6행, 재질 1그룹/2행을 별도 보고. 병합 시료도 중복 관찰에 포함되며 오류로 단정하지 않음.
- 풍량 단위 `ft3/m` 6개는 분모 의미를 추정하지 않고 변환 보류. 시험조건 포함 여재 차압 단위 22개도 조건을 지우거나 다른 시험값과 합치지 않음. 명확한 m³/h·Pa·mmAq 등만 기존 단위 유틸로 변환하고 적용식을 별도 저장.
- 백분율 서식이 있는 수치 100셀은 원값·서식과 백분율 변환값을 분리. 0~1 숫자만 보고 백분율로 추정하지 않음. 수식 셀 87개(공유 수식 셀 49개 포함)는 캐시·수식 속성·공유 기준 셀 보존 및 미검증 경고. 실제 파일에 캐시 누락은 없으나 누락 경계 테스트 통과. 재계산 없음.
- 기존 매핑 밖의 기재 셀은 성능 1개, 재질 4개를 원주소/원값과 함께 별도 보존. 임의 필드 의미를 부여하지 않음.
- 각 기록: 파일 SHA256·시트·행 및 필드별 실제/요청 셀 주소·병합 범위·원값·XML 값·표시 형식·헤더/단위 근거 보존. 날짜는 원시 Excel 일련번호와 ISO 날짜를 분리. 소유/시험대상은 UNKNOWN, 제품 연결 미시도, 공인시험/공식인증은 null. **관리대장은 원본 성적서 PDF 검증 근거가 아님**.

## 실행과 로컬 미리보기

- 재사용 함수: `apps.company.report_preview.preview_filtech_reports(path)`; ORM·SDK·네트워크를 사용하지 않음. 현재 관찰한 성능/재질 헤더 배치만 지원, 주요 헤더가 달라지면 추측하지 않고 오류. 지원하지 않는 시트는 경고로 남김.
- 기본 명령은 시트별 건수·누락·중복·경고 요약만 출력. `--output`을 지정해야 상세 JSON을 쓰며, 기존 출력과 원본은 덮어쓰지 않음. 상세 파일에는 기업 원문이 있으므로 Git 제외 위치만 사용.
- 아래 명령은 작업폴더의 `backend`에서 실행. 이미 생성된 출력이므로 재실행 시 다른 Git 제외 JSON 경로를 지정하거나 `--output` 없이 요약만 확인.

```powershell
& .venv/Scripts/python.exe manage.py preview_filtech_reports 'C:\Users\김가은\Desktop\2026-2학기\IT와비즈니스혁신\찐 프로젝트\기업제공 자료\필텍 시험성적서 관리대장.xlsx' --output .venv/b1-preview/preview.json
```

- 상세: `backend/.venv/b1-preview/preview.json`; 요약: `summary.json`; 셀 대조: `cell-verification.json`; DB/네트워크 차단 검사: `guarded-command-verification.json`; 테스트: `tests.log` (모두 같은 b1-preview 폴더). `git check-ignore`로 상세 파일 제외 확인. 원본·JSON·비밀값·업로드 파일 커밋 없음.

## B1 검증 및 현재 실행 상태

- 별도 openpyxl 읽기 전용 리더로 성능 **7,677셀**, 재질 **400셀**의 값·서식 대조 완료. 대표 근거: 성능 `C4/B4/D4/I4/J8/AH4/AR4`, 모델 공란 `J4`, 백분율 `BB8`, mmAq 변환 `AR13`; 재질 `E3/C3/D3/H3`, 병합 시료 24행→23행 기준 셀. 원문 값 전체는 출력하지 않음.
- 신규 경계 테스트 11개: 거짓 최대 행·스타일 전용 행 제외, 병합/중복 보존, 단위 불명/부호/문자/누락, 0·백분율 서식/이스케이프, 수식 캐시 누락·공유 수식, 1900/1904 날짜, 잘못된 헤더/ZIP/숫자, DB 차단·LLM 미호출·요약 출력·덮어쓰기 방지.
- `pytest apps/company/tests/test_report_preview.py apps/core/tests/test_units.py apps/documents/tests/test_documents_api.py::test_load_initial_data_endpoint apps/documents/tests/test_documents_api.py::test_company_seed_command_is_blocked --tb=short` → **56 passed**. 기존 차단 정책 테스트는 격리된 pytest 테스트 DB만 사용.
- `manage.py check` 문제 0개; 변경 Python 파일의 `ruff check`·`ruff format --check`, `git diff --check` 통과. 전체 pytest·브라우저/프런트 연동·PDF 생성은 실행하지 않음. B0 자료 누락 8개 실패와 WeasyPrint DLL 문제는 그대로 후속 과제로 보존.
- 실제 입력 명령은 Django DB 연결과 socket 접속을 예외로 차단한 상태에서도 성공. **DB 연결 시도 0, 네트워크 접속 시도 0**. 해당 최종 실행 직전/직후 실제 DB **37개 테이블**의 건수·내용 해시 모두 동일. 회사/제품/성적서/인증/납품실적 및 LLM 호출 로그 0건 확인.
- 단, B1 전체 작업 시간 동안에는 기존 서버에 다른 클라이언트의 로그인·공고 생성·첨부 POST/DELETE 요청이 관찰됨(로그 21:02~21:05). 전체 시간대 스냅샷에서 accounts_user, token_blacklist_outstandingtoken, bids_bidnotice, bids_bidattachment, documents_document가 달라졌으므로 **DB 전체가 B1 내내 불변이었다고 주장하지 않음**. 해당 기존/병행 데이터를 변경·삭제하지 않음. 비교 파일은 `db-before.json`, `db-after.json`에 건수/해시만 저장.
- 기존 PostgreSQL PID **5332**(5432), Django 시작 PID **13608**/리스너 PID **24964**(8000) 유지. 서버 재시작·워커 실행 없음. 로그와 P: 매핑/재개 방법은 아래 B0 기록 참조. 현재 서버는 B0의 `--noreload` 프로세스이며 B1은 CLI 전용이라 재시작 불필요.

## B2 설계 질문 — 사용자 지정 전 착수 금지

1. `SHEET/Model` 40개 기재는 여재 모델인가 완제품 모델인가? 당사/비교 타사/용도/시험대상을 어떻게 확인하고 승인된 제품에 연결할 것인가?
2. 성적서번호 중복과 하나의 성적서에 여러 시료 행을 어떻게 표현할 것인가? 기존 `TestReport.report_no(unique=True)`와 단일 product FK만으로는 출처/시료/조건별 다중 기록을 안전하게 표현하기 어려움.
3. 시험규격에 ISO 29463 기재가 21행 있으나 기존 StandardFamily에는 없음. 규격 원문/버전과 규격군, 여재/완제품 시험조건·효율 지표를 어떻게 분리할 것인가?
4. 기존 `is_official_certification=True` 기본값을 실제 자료 확인 전 어떻게 UNKNOWN 상태로 관리할 것인가? 공인시험·공식인증을 구별할 근거는 별도 확인 필요.
5. 관리대장 버전 SHA/시트/셀과 원본 PDF 문서/페이지를 어떻게 함께 보존할 것인가? 번호/일자 누락과 `ft3/m`·조건부 단위·수식 캐시의 검토/승인 절차는 무엇인가?

---

# 이전 B0 인수인계 (당시 관찰 기록)

- 상태: **Backend B0 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 다음 단계 자동 진행 없음.
- 작업폴더: `C:\Users\김가은\Documents\ChatGPT\it와비즈니스혁신\filtech-backend`
- 브랜치: `feature/backend-foundation` 확인. 시작 시 작업 트리 깨끗함.
- 완료 커밋: `43a85d3` — `chore(backend): verify B0 local PostgreSQL runtime and seed blocking`.
- 추적 변경: `backend/apps/documents/tests/test_documents_api.py`, `BACKEND_PROGRESS.md`만.
- 프런트·API 계약·모델·분석 엔진·공통 설정 변경 없음. Phase 0 복사·초기화, 가상 회사자료 설치·적재, 원격 push·배포 없음.

## 실행 환경과 현재 서버

- 기존 PostgreSQL 명령·서비스·프로세스·설치 레지스트리·기본 경로와 5432/8000 리스너가 없음을 확인한 뒤 새 전용 환경 구성.
- Python `3.12.10`: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`로 이 폴더의 `backend/.venv` 신규 생성. 다른 작업폴더 가상환경·비밀값 공유 없음.
- `backend/requirements.txt` 설치 완료. Django `5.2.18`, psycopg `3.3.6`; `pip check` 통과.
- `backend/.env.example`을 바탕으로 전용 `.env` 생성. Django/Fernet/DB 비밀값은 무작위 생성, 출력·커밋하지 않음. LLM 키 미설정.
- 공식 배포 확인: [PostgreSQL Windows](https://www.postgresql.org/download/windows/), [EDB 바이너리](https://www.enterprisedb.com/download-postgresql-binaries).
- EDB 공식 링크 `https://sbp.enterprisedb.com/getfile.jsp?fileid=1260609`에서 PostgreSQL `18.6` Windows x64 ZIP 다운로드.
- ZIP: `backend/.venv/postgresql-binaries.zip`; SHA256 `E2246BA91D22345BC3D017586C09EDE52D9DF180B1EEB480F050445F1CAD84E2` (로컬 계산값). 서버 bin/lib/share 1,583개 파일 크기·CRC를 ZIP과 대조 완료.
- 바이너리: `backend/.venv/postgresql-runtime/pgsql`; 클러스터: `backend/.venv/pgdata`. Windows 서비스 등록·관리자 권한·Docker 불필요.
- 한글 절대경로에서 initdb의 UTF8 오류가 발생해 **`P:`를 이 폴더의 `backend/.venv`에 subst 매핑**하고 초기화 성공. 파일은 모두 백엔드 폴더 안에 있음. 재부팅 후 매핑 재생성 필요.
- DB: `127.0.0.1:5432/filtech`, 역할 `filtech` (LOGIN, CREATEDB; 테스트 DB 생성용). SCRAM 인증, IPv4 루프백만 수신. 기존 DB 삭제·수정 없음.
- 클러스터 관리자 비밀번호: `.venv/pg-bootstrap-password`, 앱 DB 비밀번호: `.env`에만 보관. `.env`와 `.venv`는 `git check-ignore` 확인 완료.
- PostgreSQL 실행 유지: PID **5332**, `P:\postgresql-runtime\pgsql\bin\postgres.exe`. 로그 `backend/.venv/postgres.log`.
- Django 실행 유지: 시작 PID **13608** (`.venv\Scripts\python.exe`), 리스너 PID **24964** (venv가 실행한 Python 3.12), `127.0.0.1:8000`.
- Django 명령: `manage.py runserver localhost:8000 --noreload`. 로그 `backend/.venv/server.stdout.log`, `backend/.venv/server.stderr.log`. 숨김 백그라운드 프로세스로 시작함.
- 워커: `manage.py run_jobs --once` → `Processed 0 job(s).` 확인 후 종료. **상주 워커는 없음**. 비동기 작업이 필요한 후속 단계에서 별도 시작 필요.

## 관찰한 검증 결과

- `manage.py check` → 문제 0개. `manage.py migrate --noinput` → 43개 마이그레이션 적용. `manage.py migrate --check` → 종료 코드 0.
- `manage.py ensure_admin` → 기존 ADMIN 유지, 멱등 확인. 최초 migrate에서 `admin` 생성, `must_change_password=True`. 기본 로그인 정보는 기존 `specs/03-auth-and-access.md` 참조.
- 실제 HTTP: `GET /api/system/status` 200, `llm_configured=false`, `active_provider=null`, `app_version=0.1.0`, `admin_must_change_password=true`.
- 실제 HTTP: 익명 `/api/auth/me` 401 → 관리자 로그인 200 → 인증된 `/api/auth/me` 200(ADMIN) → `/api/settings/app` 200.
- 실제 HTTP: refresh 200 → logout 204 → 같은 refresh 재사용 401. 토큰은 출력하지 않음.
- `Origin: http://localhost:5173`으로 상태 API 호출 시 `Access-Control-Allow-Origin` 일치 확인. UI는 기존 `/api` 프록시로 연결 가능.
- DB 조회: Company/Product/TestReport/Certificate/DeliveryRecord/Document/BidNotice/Job/LLMCallLog 모두 **0건**. 저장된 LLM API 키 없음. 유료 AI 호출 없음.
- HTTP 검사 기록: `backend/.venv/b0-http.log` (토큰·비밀번호 미포함).
- 브라우저·프런트 실제 화면 연동, 전체 pytest, 실제 자료 분석은 실행하지 않음.

## 테스트 변경과 결과

- 최초 `pytest apps/accounts apps/core apps/documents/tests/test_documents_api.py::test_load_initial_data_endpoint --tb=short` → **87 passed, 1 failed**. 실패는 옛 기대값 `company.created == 19`가 현재 차단 응답에 없는 `KeyError`.
- API 테스트를 `company.blocked=True` 및 안내문·회사/제품/문서 미생성 검사로 수정. 입찰 로더만 mock하여 실제 과거 공고 파일·LLM과 분리하고, 가상 회사 로더 미호출·입찰담당자 403 및 작업 미생성 확인.
- `load_initial_data --only company --no-llm`의 CommandError와 자료 미생성 회귀 검사 추가. 제품 코드·API 응답 변경 없음.
- `pytest apps/accounts apps/core apps/documents/tests/test_documents_api.py --tb=short` → **97 passed, 8 failed**. 로그 `backend/.venv/b0-tests.log`.
- 7개 실패: `test_upload_extracts_without_applying_by_default`, `test_preview_then_apply`, `test_auto_apply_setting`, `test_metadata_edit_locks_and_survives_reextract`, `test_list_filters`, `test_delete_document_removes_file`, `test_schema_in_use_cannot_be_deleted`. 모두 기존 `initial-data/company` 가상 PDF 누락(FileNotFoundError); 복구·재설치하지 않음.
- 나머지 `test_scanned_pdf_needs_ocr`: 실제 과거 공고 `bid_sample/won/20210829431/제한경쟁사유서.pdf`가 현재 기본 INITIAL_DATA_DIR에 없어 FileNotFoundError. 가상 회사자료 문제와 구분.
- 최종 핵심 검사: `pytest apps/accounts apps/core apps/documents/tests/test_documents_api.py::test_load_initial_data_endpoint apps/documents/tests/test_documents_api.py::test_company_seed_command_is_blocked --tb=short` → **89 passed**. 로그 `backend/.venv/b0-focused-tests.log`. 일괄 skip 또는 전체 통과 처리 없음.
- `ruff check apps/documents/tests/test_documents_api.py`, `git diff --check` 통과.

## 미확인 사항과 다음 시작점

- 이 가상환경의 `import weasyprint`는 Windows 네이티브 `libgobject-2.0-0` 누락으로 실패. Django 서버는 정상이나 PDF 생성은 미확인. 기존 Phase 0의 다른 환경 성공 보고를 이 폴더의 성공으로 간주하지 않음. 후속 PDF 작업 시 Pango/GLib 설치 및 DLL 경로 설정 필요.
- 실제 공고가 필요한 후속 단계에서는 기존 `filtech-personal/initial-data`를 INITIAL_DATA_DIR로 읽기 전용 참조 가능(`bid_sample` 존재만 확인). 이번에는 설정·적재하지 않음.
- 회사자료에 의존하는 `company_data` 픽스처와 광범위한 기존 테스트는 후속 단계에서 최소 테스트 입력/실제 자료 검증으로 재설계해야 함. 이 단계에서 가상 회사자료 복원·실제 자료 매핑 변경하지 않음.
- 다음 작업은 사용자 지정 후 시작. B0 재검사는 아래 명령 사용. 이미 실행 중이면 중복 서버를 시작하지 말고 포트/PID/명령부터 확인.

## 재개 명령 (PowerShell, 작업폴더의 backend에서)

```powershell
Set-Location 'C:\Users\김가은\Documents\ChatGPT\it와비즈니스혁신\filtech-backend\backend'
Get-NetTCPConnection -LocalPort 5432,8000 -State Listen -ErrorAction SilentlyContinue
subst  # P:가 이 폴더의 .venv인지 확인; 다른 경로면 덮어쓰지 않음
# P:가 없을 때만:
subst P: (Resolve-Path .venv).Path
# PostgreSQL이 정지된 경우에만:
& P:/postgresql-runtime/pgsql/bin/pg_ctl.exe -D P:/pgdata -l P:/postgres.log -w start
& .venv/Scripts/python.exe manage.py check
& .venv/Scripts/python.exe manage.py migrate --check
# 8000 서버가 없을 때만 (현재 터미널에서 유지):
& .venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload
# 별도 터미널, 후속 비동기 작업이 필요할 때만:
& .venv/Scripts/python.exe manage.py run_jobs
```

- 의도적으로 종료할 때만: Django의 위 PID가 여전히 같은 명령인지 확인 후 종료; DB는 `& P:/postgresql-runtime/pgsql/bin/pg_ctl.exe -D P:/pgdata -m fast -w stop`. 다른 서버를 임의 종료하지 않음.
- `.env`/DB 비밀번호를 다시 생성하거나 initdb를 재실행하지 말 것. 매핑·클러스터·비밀값은 로컬에 유지되어 있음.
