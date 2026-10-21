# PERSONAL_PROGRESS — 공통 출발 기록

## 병렬 작업으로 전환
- Phase 0의 작업본·가상자료 차단·프런트 빌드 확인을 기준 상태로 보존한다. DB·서버 검증은 백엔드 B0로 이관한다.
- Git 작성자 설정은 사용자 제공 정보로 이 저장소에만 적용한다. 기준 커밋은 main의 `git log -1`로 확인한다.
- 기준 폴더 filtech-personal은 main, UI 폴더 filtech-ui는 feature/ui-refresh, 백엔드 폴더 filtech-backend는 feature/backend-foundation을 사용한다.
- 이후 실제 최신 상태는 UI_PROGRESS.md / BACKEND_PROGRESS.md에 역할별로 기록한다. 이 공통 파일은 양쪽이 수정하지 않는다.
- PARALLEL_WORK.md의 파일 소유권·기존 API 유지·실행 환경 규칙을 따른다.
- 공고샘플 8건은 specs/12에 실제 과거 공고로 명시되어 있음을 확인했다. 가상 회사자료와 구분한다. 원문 파일은 로컬에 남기고 Git 이력에서는 제외한다.
- 아래 기록의 '커밋 없음', '작성자 미설정'은 전환 전 상태다. 당시 검사 내역은 재실행한 것으로 간주하지 않는다.

## Phase 0 당시 상태 (보존용 과거 기록)
- 단계: **Phase 0 — 부분완료** (작업본·차단·프런트 빌드 완료 / 커밋·DB 미완)
- 브랜치: `feature/ui-refresh` (아직 커밋 없음, unborn). 최근 커밋: 없음
- 다음 시작 지점: ① 아래 "커밋 막힘" 해결 → 기준 커밋 ② Phase 1 (색상/디자인 변수)

## 작업 경로
- 작업본: `Documents\ChatGPT\it와비즈니스혁신\filtech-personal` (수정은 여기서만)
- 원본(수정 안 함): `Desktop\...\Sapina 프롬프트\vc_filtech-main\vc_filtech-main`

## 한 일
1. 참고 원본을 작업본으로 복사 (robocopy). 제외: `initial-data/company`(가상 회사자료), `.env*`(`backend/.env.example`만 보존), `.git`, `node_modules`, `.venv`, `__pycache__`, 캐시, `dist`. 기업제공 자료는 복사·분석하지 않음.
   - `initial-data/bid_sample/won`(공고 샘플 8건)은 회사자료가 아니라 유지. 가상 샘플 여부는 팀 확인 필요.
2. 가상 회사자료 적재 차단 (최소 범위, `load_company()` 자체는 테스트용으로 유지):
   - `backend/apps/documents/loader.py` — `COMPANY_SEED_BLOCKED_MESSAGE` 추가
   - `backend/apps/documents/tasks.py` — `LOAD_INITIAL_DATA` 잡이 company를 실행하지 않고 `{"blocked":true,"message"}` 반환 (API `/api/admin/load-initial-data` 포함)
   - `backend/apps/documents/management/commands/load_initial_data.py` — `--only company`는 오류, 기본 실행은 company 건너뛰고 안내 출력(bids는 기존대로)
   - `frontend/src/views/admin/documents/DocumentListView.vue` — 적재 버튼 제거, 실제 자료 등록 안내문으로 교체
3. `git init`(main) 후 `feature/ui-refresh` 체크아웃. 337개 파일 스테이징 대상, .env·node_modules·.venv·dist 제외 확인.

## 재사용 파일 (개요)
- 프런트: `frontend/src/{main.js,router/index.js,layouts,components,views/{admin,bids},stores,api,utils}`, Vue3+Vite+Bootstrap 5.0.2+Pinia. 사용자 화면: `views/bids/BidDetailView.vue`(5단계), 관리자: `views/admin/{documents,company,bids,ops}`.
- 백엔드: `apps/{core,accounts,llm,documents,company,bids,evaluation,drafts}`, `config/settings/base.py`(INITIAL_DATA_DIR, DATABASE_URL 필수), 초기적재 `documents/loader.py`·`bids/loader.py`.
- 스펙: `specs/00~13`, 판정 규칙 `specs/08-compliance-evaluation.md`.

## 실행·결과
- `npm ci` 성공, `npm run build` 성공 (vite, 1.7s).
- `python -m venv backend/.venv` + `pip install -r requirements.txt` 성공 (weasyprint import 성공).
- `manage.py check` (더미 DATABASE_URL/키 주입) → 이슈 0건.
- 미실행: `npm run lint`, pytest, migrate, 서버 기동, 브라우저 확인.

## 막힘 / 미확인
- **커밋 막힘**: git `user.name/email` 미설정(전역·로컬). 임의 생성하지 않음. 설정 후 `git add -A && git commit -m "baseline: personal copy"` 필요 (기준 커밋을 main에 만들고 싶으면 설정 후 main에서 커밋 → `git checkout -b feature/ui-refresh`; 현재는 unborn 브랜치라 main 커밋이 없음).
- **PostgreSQL 없음**: `psql`/서비스 미설치 → migrate·서버·pytest 미확인. `backend/.env`는 만들지 않음(`.env.example` 참고). 재개: PG 18 설치 후 DB/역할 생성(specs/01 §4.1) → `.env` 작성 → `cd backend; .venv\Scripts\python manage.py migrate; ...runserver`.
- **테스트의 샘플 의존성(기록)**: `documents/tests/test_documents_api.py::test_load_initial_data_endpoint`는 company 19건 적재를 기대 → 차단으로 실패 예정. `test_initial_company.py`, `test_llm_pipeline.py`, `bids/tests/*`, `company`/`evaluation` 일부도 `initial-data/company` 가상 자료에 의존(이 폴더가 작업본에 없어 실패 예상). 후속 단계에서 픽스처 분리 필요.
- `BidAdminListView.vue`의 "initial-data 적재" 버튼은 남아 있음(bids 샘플 적재만 동작, company는 차단 메시지). 문구 정리는 후속.
- README/CLAUDE.md는 가상 회사자료 전제 그대로(수정 안 함).

## 단계별 완료 기록
- Phase 0: 부분완료 (위 참조)
