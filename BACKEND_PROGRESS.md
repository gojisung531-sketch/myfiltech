# 백엔드 인수인계

- 상태: **Backend B0 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 다음 단계 자동 진행 없음.
- 작업폴더: `C:\Users\김가은\Documents\ChatGPT\it와비즈니스혁신\filtech-backend`
- 브랜치: `feature/backend-foundation` 확인. 시작 시 작업 트리 깨끗함.
- 완료 커밋: 이 기록을 포함한 `HEAD` — `chore(backend): verify B0 local PostgreSQL runtime and seed blocking`. 실제 해시는 `git log -1 --oneline`으로 확인.
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
