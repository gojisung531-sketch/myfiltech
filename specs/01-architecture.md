# 01. 아키텍처

## 1. 구성

```
Vue.js 3 SPA (Vite, Bootstrap 5.0)
    │  HTTP / JSON  (Authorization: Bearer <JWT>)
    ▼
Django REST Framework  ──▶  LLM Provider (OpenAI / Anthropic / Gemini)
    │  Django ORM                ▲
    ▼                            │
PostgreSQL  ◀── Job 워커 (python manage.py run_jobs)
    │
파일 저장소 (MEDIA_ROOT, 로컬 디스크)
```

## 2. 기술 스택 / 버전

| 영역 | 선택 |
|---|---|
| Python | 3.12 |
| Django | 5.2 LTS |
| DRF | 3.15+ |
| 인증 | djangorestframework-simplejwt |
| DB 드라이버 | psycopg 3 |
| CORS | django-cors-headers |
| 환경 변수 | `.env` 로더·`DATABASE_URL` 파서는 표준 라이브러리로 직접 구현 (`config/env.py`) |
| DB | PostgreSQL 18 — **로컬 설치 서버 사용** (docker / docker compose 사용 안 함) |
| 문서 파싱 | pypdf(또는 pdfplumber), python-docx, olefile(HWP 5.0 직접 파싱), zipfile+lxml(HWPX), openpyxl(XLSX), xlrd(XLS), charset-normalizer(TXT) |
| LLM SDK | `anthropic`, `openai`, `google-genai` |
| 암호화 | cryptography (Fernet) |
| PDF 생성 | WeasyPrint (HTML 템플릿 → PDF, Noto Sans KR 폰트 번들) |
| 테스트 | pytest, pytest-django, factory_boy |
| Frontend | Vue 3, Vite 5+, Vue Router 4, Pinia, axios, bootstrap@5.0.2(정확히 고정) + @popperjs/core, bootstrap-icons |
| Lint | ruff(backend), eslint + prettier(frontend) |

> HWP 파싱에 `pyhwp`(AGPL)는 사용하지 않는다. olefile 기반 자체 추출기를 구현한다 ([06](06-document-processing.md) §2).

## 3. 디렉터리 구조

```
vc_filtech/
├── CLAUDE.md
├── README.md
├── specs/
├── initial-data/                # 읽기 전용
│   ├── company/{certificates,datasheets,records,test_reports}/
│   └── bid_sample/{won,lost}/<공고폴더>/<첨부들>
├── backend/
│   ├── .env.example            # backend/.env로 복사해 작성 (backend/.env는 커밋 금지)
│   ├── manage.py
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── config/                  # settings/{base,dev,test}.py, urls.py, wsgi.py
│   ├── fonts/NotoSansKR-{Regular,Bold}.otf  # Noto CJK SubsetOTF (SIL OFL 1.1, OFL.txt)
│   └── apps/
│       ├── core/                # AppSetting, Job, 공통 유틸, 단위 변환(units.py), 권한
│       ├── accounts/            # User, 기본 관리자 생성, 인증 API
│       ├── documents/           # Document, DocumentMetadata, MetadataSchema, parsers/
│       ├── company/             # Company, Product, TestReport, Certificate, DeliveryRecord
│       ├── bids/                # BidNotice, BidAttachment, BidItem, BidRequirement
│       ├── evaluation/          # RequirementEvaluation, rules.py, grades.py, service.py
│       ├── drafts/              # DraftDocument, 생성기, PDF 렌더러, templates/
│       └── llm/                 # LLMProviderConfig, LLMSettings, PromptTemplate, providers/, services.py, defaults.py
└── frontend/
    ├── index.html
    ├── vite.config.js           # /api, /media → localhost:8000 프록시
    └── src/
        ├── main.js, App.vue
        ├── api/                 # axios 인스턴스 + 리소스별 모듈
        ├── stores/              # auth, system, bids ...
        ├── router/index.js      # 가드: 인증/역할/LLM 설정 여부
        ├── layouts/             # AppLayout(상단 네비 + 우측 로그인)
        ├── views/               # 화면 ([11](11-frontend.md))
        └── components/
```

## 4. 환경 변수 (`backend/.env`)

`backend/.env.example`을 `backend/.env`로 복사해 채운다. 설정 로더(`config/settings/base.py`)는 `backend/.env`를 읽고, 이미 설정된 OS 환경 변수는 덮어쓰지 않는다.

| 변수 | 예 | 설명 |
|---|---|---|
| `DJANGO_SECRET_KEY` | | 필수 |
| `DJANGO_DEBUG` | `true` | |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `DATABASE_URL` | `postgres://filtech:filtech@127.0.0.1:5432/filtech` | 로컬 PostgreSQL 18 (§4.1) |
| `FIELD_ENCRYPTION_KEY` | Fernet 키 | API Key 암호화. 없으면 기동 실패(dev에서는 SECRET_KEY로 파생 허용 + 경고) |
| `MEDIA_ROOT` | `./media` | 업로드 파일 |
| `INITIAL_DATA_DIR` | `../initial-data` | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | 운영에서는 같은 오리진 서빙 권장 |
| `MAX_UPLOAD_MB` | `50` | |
| `TIME_ZONE` | `Asia/Seoul` | |

**LLM API Key와 모델은 환경 변수가 아니라 DB에 저장**한다(요구사항).

### 4.1 로컬 PostgreSQL 준비 (최초 1회)

로컬에 설치된 PostgreSQL 18 서버(`127.0.0.1:5432`, 클러스터 `18/main`)를 그대로 사용한다. docker / docker compose는 사용하지 않는다.

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE filtech WITH LOGIN PASSWORD 'filtech' CREATEDB;   -- CREATEDB: pytest가 test DB 생성
CREATE DATABASE filtech OWNER filtech ENCODING 'UTF8' TEMPLATE template0;
SQL
psql "postgres://filtech:filtech@127.0.0.1:5432/filtech" -c 'select version();'   # 접속 확인
```

- 운영 비밀번호는 `.env`에만 두고 커밋하지 않는다.
- 테스트(pytest-django)는 같은 서버에 `test_filtech` DB를 만들었다가 지운다 — 역할에 `CREATEDB` 권한 필요.

## 5. 백그라운드 작업 (Job)

LLM 호출은 수십 초 이상 걸리므로 요청-응답 내에서 실행하지 않는다.

- `core.Job` 모델: `type`, `status`(PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED), `target_type`, `target_id`, `payload`(JSON), `progress`(0–100), `message`, `result`(JSON), `error`, `created_by`, `created_at`, `started_at`, `finished_at`, `attempts`.
- 워커: `python manage.py run_jobs` — `SELECT ... FOR UPDATE SKIP LOCKED`로 PENDING 하나씩 가져와 실행, 2초 폴링. 동시 실행 수 설정(`AppSetting: jobs.concurrency`, 기본 2, 스레드).
- 작업 유형: `EXTRACT_DOCUMENT`, `EXTRACT_BID`, `EVALUATE_BID`, `GENERATE_DRAFT`, `LOAD_INITIAL_DATA`.
- 프론트는 `GET /api/jobs/{id}`를 2초 간격 폴링하여 진행률 표시.
- 실패 시 `error`에 사용자용 메시지(한국어)와 내부 상세(로그) 분리. 재시도 버튼 제공.
- 개발 편의: `AppSetting: jobs.run_inline=true`(테스트/개발) 이면 동기 실행.

## 6. 공통 API 규칙

- Prefix `/api/`. JSON, snake_case.
- 페이지네이션: `?page=&page_size=` (기본 20), 응답 `{count, next, previous, results}`.
- 에러: `{ "detail": "메시지", "code": "llm_not_configured", "errors": {field: [..]} }`.
- 파일 업로드: `multipart/form-data`.
- 날짜: ISO 8601, `Asia/Seoul`.

## 7. 보안

- 비밀번호: Django 기본 해시(PBKDF2). 비밀번호 검증기 활성화(최소 8자). 기본 관리자 비밀번호 `admin1234!`는 최초 로그인 시 변경 권장 배너 표시.
- 업로드 확장자 화이트리스트 + MIME 스니핑, 파일명은 UUID로 저장(원본명은 DB에 보관).
- `:Zone.Identifier` 등 ADS 잔재 파일과 숨김 파일은 업로드/적재 시 무시.
- 역할 기반 권한: DRF permission `IsAdminRole`, `IsBidManagerOrAdmin`.
- API Key는 응답에 마스킹, 로그 필터로 `sk-`, `AIza` 등 패턴 마스킹.
