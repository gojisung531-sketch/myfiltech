# 13. 구현 로드맵 (마일스톤 · 완료 기준)

각 마일스톤 완료 시 체크하고 README의 “기능 현황”을 갱신한다. 마일스톤 하나 = 하나 이상의 PR/커밋 묶음.

## M0. 프로젝트 골격
- [x] 로컬 PostgreSQL 18에 `filtech` 역할·DB 생성([01](01-architecture.md) §4.1), `backend/.env.example`
- [x] Django 프로젝트 `backend/config`, settings 분리(base/dev/test), DRF, SimpleJWT, CORS
- [x] `accounts.User(AbstractUser)` + `AUTH_USER_MODEL` (첫 migrate 전)
- [x] Vue 3 + Vite + Bootstrap 5.0.2 + Router + Pinia + axios, `/api` 프록시
- [x] ruff, eslint/prettier, pytest 설정
- [x] `core.AppSetting` + seed(post_migrate) — Phase 2 로그인 잠금 설정에 필요해 M0에서 선행
- **완료 기준**: `migrate` 후 `runserver` / `npm run dev` 동작, 빈 대시보드 렌더. ✅ 2026-10-05

## M1. 인증 · 기본 관리자 · LLM 설정 게이트
- [x] 로그인/리프레시/로그아웃/me, 역할 권한 클래스
- [x] `ensure_admin` + post_migrate (admin / admin1234!)
- [x] `/api/system/status`, 프론트 전역 가드, 관리자 상단 우측 로그인
- [x] LLM 모델(Provider/ModelOption/Settings), Fernet 암호화, 설정 화면, 연결 테스트
- [x] 사용자 관리(입찰담당자 추가)
- **완료 기준**: 새 DB에서 앱 접속 → 관리자 로그인 페이지로 이동 → 로그인 → API Key 화면 → 저장·테스트 성공 → 대시보드 접근 가능. 입찰담당자 계정 생성·로그인. ✅ 2026-10-06 (헤드리스 Chromium 시나리오 19/19 통과)

## M2. 문서 파서 · 회사 자료
- [x] 파서: TXT/DOCX/PDF/HWP/HWPX/XLS/XLSX, 스캔 PDF 감지
- [x] Document/MetadataSchema/DocumentMetadata, 분류 규칙, seed 스키마
- [x] 회사 자료 규칙 추출기(datasheet/test_report/certificate/delivery_record)
- [x] Company/Product/TestReport/Certificate/DeliveryRecord 모델·CRUD API·관리 화면
- [x] `load_initial_data --only company`
- [x] Job 큐 + `run_jobs`
- **완료 기준**: [12](12-initial-data.md) §2.2 기대값과 일치(테스트 통과), §5 파서 테스트 통과. ✅ 2026-10-06 (pytest 237개, 브라우저 시나리오 27개 항목 확인)

## M3. LLM 서비스 · 프롬프트 · 튜닝 설정
- [x] providers(anthropic/openai/gemini/fake), `run_task`, 스키마 검증·재시도, LLMCallLog
- [x] PromptTemplate·AppSetting seed, 관리자 편집/버전/롤백/테스트 화면
- [x] LLM 문서 분류·메타데이터 추출 보완, 문서 검토 화면(메타데이터 CRUD, 적용)
- **완료 기준**: 3개 제공자 중 최소 Claude로 실제 호출 성공, 다른 제공자는 FakeProvider 단위 테스트 + 키 있으면 수동 확인.
  - ✅ 2026-10-06: Claude Opus 5.5 실제 호출 성공 — 문서 분류, 메타데이터 추출(22필드), 스캔 PDF 전사·추출. 실제 호출에서 Anthropic 구조화 출력 제한 2건(유니온 타입 16개 제한, 스키마 문법 크기 제한)을 발견해 스키마 규칙을 바꿨고([07](07-llm-integration.md) §2), seed 스키마 20종의 실제 API 승인을 확인. OpenAI·Gemini는 키가 없어 FakeProvider·요청 구성 테스트만.

## M4. 입찰 공고 관리 · 요구사항 추출
- [x] BidNotice/BidAttachment/BidItem/BidRequirement, 관리자 등록(파일 다중/텍스트)·수정·삭제
- [x] `bid.extract` + 규칙 후처리 + 단위 정규화, 누락 카테고리 자리표시
- [x] 제품 매칭 + 적합도
- [x] `load_initial_data --only bids` (won/lost)
- **완료 기준**: [12](12-initial-data.md) §3.3 기대값 충족(실 LLM 수동 점검 기록), 8건 적재·추출 완료.
  - 2026-10-06: 20230342721 기대값을 FakeLLM 고정 응답으로 자동 테스트, 8건 적재(LLM 없이) 확인.
  - 2026-10-06 실 LLM(Claude Opus 5.5) 점검: 20230342721·20131021333 §3.3 기대값 일치. 8건 중 6건 추출 완료 → 2026-10-06 재점검으로 20210829431·20221213131 추출 완료(8/8), 20221213131 §3.3 기대값 일치. `bid.extract` 출력이 8192 토큰을 넘어 잘리는 문제를 발견해 작업별 `max_output_tokens` 32000으로 조정.

## M5. 판정
- [x] grades.py, rules.py, evidence.py, service.py, `evaluation.judge`
- [x] 판정 API, 수정·이력·되돌리기
- **완료 기준**: [12](12-initial-data.md) §4 R1–R20 테스트 통과.
  - 2026-10-06: R1–R20 통과(`apps/evaluation/tests/test_rules.py`). 실 LLM 판정(20230342721, 52건): 규칙 32건 + LLM 20건, 근거·답변·질의 문안 확인. `evaluation.judge` 출력 잘림(8192 토큰) 발견 → 32000으로 조정.

## M6. 입찰담당자 화면
- [x] 대시보드 카드(총/확인/미확인) + 목록 필터·정렬
- [x] 공고 상세 5탭(요구사항/비교/판정/초안/확인), 확인 완료 처리
- **완료 기준**: 담당자가 공고를 열어 판정을 수정하고 확인 완료하면 대시보드 수치가 바뀐다.
  - 2026-10-06: 브라우저 E2E로 확인(판정 실행 → 수정·이력·되돌리기 → 확인 완료 → 대시보드 확인 1/미확인 8).

## M7. 초안 · PDF
- [x] Compliance Matrix / 체크리스트 / 기술질의서 / 검토 보고서 생성·편집·버전
- [x] WeasyPrint PDF(개별 + 통합), 한글 폰트
- **완료 기준**: 20230342721 공고로 통합 PDF 생성, 한글·표·색상 정상, 수정 내용 반영.
  - 2026-10-06: 브라우저 E2E로 4종 초안 생성 → 편집·확정 → 재생성 시 v2(수정본 v1 보존) → 통합 PDF(30쪽, Noto Sans KR 임베드, CM A4 가로, 판정 색상·HIGH 띠) 다운로드, 체크리스트 완료 표시가 PDF에 반영됨을 확인. 실 LLM 점검: 4종 초안 모두 LLM 다듬기 반영, `draft.*` 출력 잘림 → 32000 조정, 빈 질의서 응답 1회 재시도 추가.

## M8. 마무리
- [x] 운영 화면(Job, LLM 로그), 에러 처리·토스트, 접근성 점검
- [x] README 최종 갱신(설치·운영·백업)
- [x] (선택) XLSX 내보내기 — Compliance Matrix·체크리스트 ([09](09-drafts-and-reports.md) §6)

## 향후 과제 (범위 밖)
- 나라장터 공고 자동 수집 및 신규 공고 알림
- 낙찰/유찰(won/lost) 이력 기반 적합도 학습·유사 공고 추천
- OCR 엔진 내장, `.doc` 변환
- 문서 임베딩 기반 근거 검색(pgvector)
