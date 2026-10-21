# 백엔드 인수인계 — Backend B1

- 상태: **B1 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 읽기 전용 관리대장 미리보기만 구현. B2·DB 적재·제품 연결·판정·LLM 호출은 진행하지 않음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 시작 시 깨끗함. B0 `43a85d3`을 보존하고 환경 재설치·초기화 없이 진행.
- 완료 커밋: 이 기록을 포함한 `HEAD` — `feat(backend): add read-only Filtech report register preview` (`git log -1 --oneline`으로 해시 확인).
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
