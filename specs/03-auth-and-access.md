# 03. 인증 · 권한 · 초기 흐름

## 1. 로그인

- ID(username) + 비밀번호. 관리자와 입찰담당자가 **같은 로그인 API**를 쓰되 화면 진입점이 다르다.
  - 입찰담당자: `/login` (전체 화면 로그인 폼)
  - 관리자: **화면 상단 우측 로그인 영역**(드롭다운 폼) 및 `/admin/login` 전용 페이지
- API: `POST /api/auth/login {username, password}` → `{access, refresh, user}`
  - `user`: `{id, username, display_name, role, must_change_password}`
- Access 토큰 30분, Refresh 7일(설정 가능). 프론트는 401 시 refresh 1회 시도 후 실패하면 로그인 화면으로.
- `/admin/login`에서 BID_MANAGER가 로그인하면 “관리자 권한이 없습니다” 표시 후 토큰 폐기.
- 로그인 실패 5회 연속 시 5분 잠금(계정 기준, `AppSetting: auth.lockout_*`). 실패 응답은 `401 invalid_credentials`(존재하지 않는 ID와 동일 메시지), 잠금 중에는 `403 account_locked`. 상태는 `User.failed_login_attempts`, `User.locked_until`에 저장. 관리자의 비밀번호 초기화 시 잠금 해제.
- 로그아웃: refresh 토큰 블랙리스트.

## 2. 역할과 권한

| 리소스 | ADMIN | BID_MANAGER |
|---|---|---|
| 사용자 관리 | CRUD | 본인 비밀번호 변경만 |
| 회사정보·제품·성적서·인증·실적 | CRUD | 조회 |
| 문서 업로드·메타데이터 | CRUD | 조회 |
| 입찰 공고·첨부·요구사항 | CRUD | 조회 (요구사항은 조회만) |
| 판정·답변 | 수정 | 수정 |
| 초안 생성·수정·PDF | 가능 | 가능 |
| 공고 확인 완료 처리 | 가능 | 가능 |
| LLM·프롬프트·튜닝 설정 | CRUD | 불가 |
| LLM 호출 로그 | 조회 | 불가 |

## 3. 기본 관리자 자동 생성

- App 시작 시 `role=ADMIN` 사용자가 하나도 없으면 `admin / admin1234!` 생성 (`must_change_password=True`, `is_staff=True`).
- 구현: `accounts.apps.AccountsConfig`에서 `post_migrate` 시그널 + `python manage.py ensure_admin` 명령. 서버 기동 스크립트(`runserver` 전 / 컨테이너 entrypoint)에서 `migrate` 후 `ensure_admin` 실행. **멱등**해야 한다.
- 이미 `admin` 사용자가 있으나 ADMIN이 아니면 덮어쓰지 않고 경고 로그만 남긴다.
- 로그인 후 `must_change_password`면 상단 경고 배너 + 비밀번호 변경 링크 (강제 차단은 하지 않음).

## 4. API Key 미설정 시 흐름 (필수)

**정의**: “LLM 설정 완료” = `LLMSettings.active_provider`의 `LLMProviderConfig`가 존재하고, `is_enabled=True`이며 API Key가 저장되어 있음.

- 공개 API `GET /api/system/status` (인증 불필요):
  ```json
  { "llm_configured": false, "active_provider": null, "app_version": "0.1.0", "admin_must_change_password": true }
  ```
- 프론트 라우터 전역 가드(앱 최초 로드 및 라우트 이동 시):
  1. `llm_configured=false` 이고 현재 사용자가 ADMIN이 아니면 → `/admin/login?redirect=/admin/settings/llm&reason=llm_not_configured` 로 이동. 로그인 화면에 “LLM API Key가 설정되지 않았습니다. 관리자로 로그인하여 설정하세요.” 안내.
  2. 관리자 로그인 성공 후 `llm_configured=false`면 **바로 `/admin/settings/llm`(API Key 입력 화면)** 으로 이동하고 입력 폼에 포커스.
  3. ADMIN은 LLM 미설정 상태에서도 관리자 화면 접근 가능(회사 자료 업로드는 가능, 단 추출 작업은 “LLM 미설정” 오류 대신 규칙 기반 추출만 수행하고 LLM 단계는 보류 표시).
  4. API Key 저장 시 `system` 스토어 갱신 → 가드 해제 (위 정의대로 Key 저장·사용 설정이 기준. 연결 테스트는 저장 시 자동 실행되며 실패해도 Key는 저장되고 결과를 화면에 표시 — [04](04-admin-features.md) §4).
- 백엔드도 방어: LLM이 필요한 엔드포인트는 미설정 시 `409 {code: "llm_not_configured"}` 반환. 프론트 axios 인터셉터가 이 코드를 받으면 위 1번 흐름 실행.

## 5. 사용자 관리 (관리자)

- 입찰담당자 추가: username, 초기 비밀번호, display_name, department, email, phone, role(기본 BID_MANAGER).
- 수정, 비활성화(삭제 대신 `is_active=False`; 물리 삭제는 이력 없는 사용자만 — 로그인 이력(`last_login`)이 없는 사용자, `DELETE ?hard=true`), 비밀번호 초기화.
- 마지막 ADMIN은 비활성화/역할 변경 불가.
