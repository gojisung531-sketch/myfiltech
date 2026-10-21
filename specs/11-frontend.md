# 11. Frontend (Vue 3 + Vite + Bootstrap 5.0)

## 1. 기본
- Vue 3 Composition API(`<script setup>`), Vue Router 4(history mode), Pinia, axios.
- Bootstrap **5.0.2** CSS/JS(`import 'bootstrap'`), bootstrap-icons. jQuery 사용 금지. UI 라이브러리 추가 금지(필요 시 직접 컴포넌트).
- 글꼴: Noto Sans KR(웹폰트) 또는 시스템 한글 폰트.
- 상태: `stores/auth`(user, tokens — localStorage 저장, refresh 자동), `stores/system`(llm_configured), 화면별 store는 필요 시.
- 공통 컴포넌트: `AppNavbar`, `HeaderLoginBox`(우측 상단 로그인), `JobProgress`(job 폴링·진행바·완료 콜백), `VerdictBadge`, `RiskDot`, `FitScoreBar`, `FileDropzone`(다중 파일, 확장자 검사), `EditableTable`, `MetadataTable`, `DocumentViewer`(텍스트/PDF iframe), `ConfirmModal`, `ToastHost`, `EmptyState`.

## 2. 레이아웃
- 상단 navbar: 좌측 로고 “FilTech Bid Assistant” + 메뉴(대시보드 / [관리자] 회사자료, 입찰공고, 사용자, 설정), **우측 상단: 미로그인 시 관리자 로그인 드롭다운(ID·비밀번호·로그인 버튼)**, 로그인 시 사용자명·역할 배지·비밀번호 변경·로그아웃.
- `must_change_password`면 navbar 아래 경고 배너.
- LLM 미설정 시 관리자에게 상단 빨간 배너 “LLM API Key 미설정 — 설정하기”.

## 3. 라우트

| Path | View | 권한 |
|---|---|---|
| `/login` | LoginView (입찰담당자) | 공개 |
| `/admin/login` | AdminLoginView (`?redirect`, `?reason`) | 공개 |
| `/` | DashboardView (카드 3개 + 공고 목록) | 🅱 |
| `/bids/:id` | BidDetailView (탭 ①~⑤: `?tab=requirements|comparison|evaluation|drafts|review`) | 🅱 |
| `/bids/:id/drafts/:type` | DraftEditorView | 🅱 |
| `/account/password` | ChangePasswordView | 🅱 |
| `/admin/company` | CompanyInfoView | 🅰 |
| `/admin/products`, `/admin/products/:id` | ProductList/Detail | 🅰 |
| `/admin/test-reports`, `/admin/certificates`, `/admin/delivery-records` | 각 List/Detail | 🅰 |
| `/admin/documents`, `/admin/documents/:id` | DocumentList / DocumentReviewView(메타데이터 검토·적용) | 🅰 |
| `/admin/metadata-schemas` | MetadataSchemaView | 🅰 |
| `/admin/bids`, `/admin/bids/new`, `/admin/bids/:id/edit` | BidAdminList / BidCreate / BidEdit(메타·첨부·품목·요구사항 탭) | 🅰 |
| `/admin/users` | UserAdminView | 🅰 |
| `/admin/settings/llm` | LLMSettingsView (API Key 입력) | 🅰 |
| `/admin/settings/prompts` | PromptSettingsView | 🅰 |
| `/admin/settings/tuning` | TuningSettingsView | 🅰 |
| `/admin/jobs`, `/admin/llm-logs` | 운영 | 🅰 |

### 3.1 전역 가드 (순서)
1. 앱 시작 시 `system.fetchStatus()` (1회 + 설정 저장 후 갱신).
2. `!llm_configured && !auth.isAdmin && to.path !== '/admin/login'` → `/admin/login?redirect=/admin/settings/llm&reason=llm_not_configured`.
3. 인증 필요 라우트인데 미로그인 → 관리자 라우트는 `/admin/login?redirect=`, 그 외 `/login?redirect=`.
4. 관리자 라우트에 BID_MANAGER → `/` + 토스트 “권한 없음”.
5. 관리자 로그인 성공 시: `!llm_configured` → `/admin/settings/llm`, 아니면 `redirect` 또는 `/`.

## 4. 주요 화면 상세

### DashboardView
- 카드 3개(총/확인/미확인) — 클릭 시 필터. 아래 필터 바 + 목록 테이블([05](05-bid-manager-features.md) §2.2). 행 클릭 → `/bids/:id`.

### BidDetailView
- 헤더 카드 + 액션 버튼, Bootstrap nav-tabs 5개. 탭 전환은 쿼리스트링 유지.
- ③ 판정 탭: 아코디언/표 하이브리드 — 행 접힘 상태에서 판정·요구·답변 요약, 펼치면 근거(evidence 리스트: 클릭 시 `DocumentViewer` 오프캔버스), 편집 버튼 → 모달 폼. 상단 필터(판정별, HIGH만, 수정됨만).
- 판정/초안 Job 실행 중에는 `JobProgress` 표시, 완료 시 자동 새로고침.

### DraftEditorView
- 유형별 편집기: Compliance Matrix·체크리스트 = `EditableTable`, 질의서·보고서 = 섹션별 textarea + 질문 목록 편집. 저장/버전 선택/PDF 다운로드.

### LLMSettingsView
- 제공자 라디오 카드 3개(로고 대신 텍스트+아이콘), 선택 카드에 API Key 입력(password, 보기 토글), Base URL, [저장] [연결 테스트] 결과 alert. 모델 드롭다운 + “모델 관리” 모달. 파라미터 폼. `reason=llm_not_configured`로 진입 시 상단 안내 alert + Key 입력 포커스.

### DocumentReviewView
- 좌: DocumentViewer, 우: 분류 선택 + MetadataTable(인라인 편집, 행 추가/삭제, 잠금 아이콘, 신뢰도 색) + 매핑 diff + [적용].

## 5. UX 규칙
- 모든 비동기 동작 로딩 표시, 실패 시 toast(서버 `detail`).
- 파괴적 동작(삭제)은 ConfirmModal.
- 날짜 표시 `YYYY-MM-DD HH:mm`, 금액 `₩370,062,000`, 마감 D-day 배지.
- 판정 라벨/색상 일관: 충족(success), 보완 필요(warning), 확인 필요(info/primary).
- “AI 초안 — 검토 후 사용” 문구를 판정·초안 화면 상단에 상시 표시.
