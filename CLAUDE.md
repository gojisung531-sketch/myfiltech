# CLAUDE.md

## 개인 버전 작업 시 우선 적용

사용자의 개인 버전 요구사항과 `PARALLEL_WORK.md`를 먼저 따른다. 아래 기존 명세는 참고 기준이며, 실제 필텍 자료만 사용한다는 정책과 충돌하는 가상 회사자료 적재를 실행하지 않는다. 팀 노션과 원본 자료를 수정하지 않는다. UI 담당은 frontend와 UI_PROGRESS.md, 백엔드 담당은 backend와 BACKEND_PROGRESS.md를 수정한다. 공통 API·의존성·이력은 임의로 깨뜨리지 않는다. 요청된 단계 하나만 수행하고 인수인계 후 멈춘다.

이 파일은 Claude Code가 이 저장소에서 작업할 때 따라야 할 지침이다. 구현 전에 반드시 관련 `specs/*.md`를 먼저 읽는다.

## 프로젝트 한 줄 요약

발전소(가스터빈 흡기·공조) 입찰 공고 중 (주)필텍의 공기필터 제품에 적합한 공고를 찾고, 공고의 핵심 요구사항을 회사 제품 사양·시험성적서·인증·납품실적과 비교·판정하여 **Compliance Matrix / 입찰 체크리스트 / 기술질의서 / 검토 보고서(PDF)** 초안을 만드는 Web App.

## 스펙 문서 (Single Source of Truth)

| 파일 | 내용 |
|---|---|
| [specs/00-overview.md](specs/00-overview.md) | 목표, 사용자, 용어집, 범위 |
| [specs/01-architecture.md](specs/01-architecture.md) | 기술 스택, 디렉터리 구조, 환경 변수, 비동기 작업 |
| [specs/02-data-model.md](specs/02-data-model.md) | Django 모델 전체 정의 |
| [specs/03-auth-and-access.md](specs/03-auth-and-access.md) | 인증, 권한, 기본 관리자, API Key 미설정 시 흐름 |
| [specs/04-admin-features.md](specs/04-admin-features.md) | 관리자 기능 |
| [specs/05-bid-manager-features.md](specs/05-bid-manager-features.md) | 입찰담당자 기능 (대시보드 → 공고 상세 5단계) |
| [specs/06-document-processing.md](specs/06-document-processing.md) | TXT/DOCX/HWP/PDF 파싱, 문서 분류, 메타데이터 추출 |
| [specs/07-llm-integration.md](specs/07-llm-integration.md) | ChatGPT/Claude/Gemini 연동, 모델·프롬프트·튜닝 설정 |
| [specs/08-compliance-evaluation.md](specs/08-compliance-evaluation.md) | 요구사항 추출·비교·판정(충족/보완 필요/확인 필요) 규칙 |
| [specs/09-drafts-and-reports.md](specs/09-drafts-and-reports.md) | 초안 문서 및 PDF 보고서 |
| [specs/10-api.md](specs/10-api.md) | REST API 엔드포인트 |
| [specs/11-frontend.md](specs/11-frontend.md) | 화면, 라우팅, 컴포넌트 |
| [specs/12-initial-data.md](specs/12-initial-data.md) | `initial-data/` 적재 및 기대 결과, 테스트 시나리오 |
| [specs/13-roadmap.md](specs/13-roadmap.md) | 구현 순서(마일스톤)와 완료 기준 |

스펙과 코드가 충돌하면 스펙을 따른다. 스펙을 바꿔야 하면 **코드보다 스펙을 먼저 수정**하고 변경 이유를 커밋 메시지에 적는다.

## 기술 스택 (변경 금지)

- Frontend: Vue.js 3 + Vite, Bootstrap **5.0.x** (`bootstrap@5.0.2`), HTML5/CSS3, SPA (Vue Router, Pinia, axios)
- Backend: Python 3.12, Django 5.2 LTS, Django REST Framework, Django ORM, REST/JSON
- DB: PostgreSQL 18 — 로컬 설치 서버(`127.0.0.1:5432`) 사용. **docker / docker compose 사용 금지**
- 사용자 모델: `accounts.User(AbstractUser)` + `role` 필드 (ADMIN / BID_MANAGER)

## 디렉터리

```
backend/    Django 프로젝트 (config/, apps/*)
frontend/   Vue 3 + Vite SPA
specs/      상세 요구사항
initial-data/  초기 데이터 (읽기 전용 — 수정·삭제 금지)
```

## 자주 쓰는 명령

```bash
# DB: 로컬 PostgreSQL 18 (최초 1회 역할·DB 생성 — specs/01 §4.1)
pg_lsclusters                         # 18/main online 확인

# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # 셸의 `python`은 Windows pyenv를 가리킴 — 사용 금지
pip install -r requirements.txt
python manage.py migrate              # 기본 관리자(admin / admin1234!) 자동 생성
python manage.py load_initial_data    # initial-data/ 적재
python manage.py runserver 8000
python manage.py run_jobs             # 백그라운드 작업 워커 (별도 터미널)
pytest

# Frontend
cd frontend
npm install
npm run dev        # http://localhost:5173 (/api → :8000 프록시)
npm run build
npm run lint
```

## 코딩 규칙

- **LLM 호출은 반드시 `apps/llm/services.py`의 단일 진입점**을 통해서만 한다. 뷰·모델에서 SDK를 직접 import 하지 않는다.
- **프롬프트·모델명·temperature 등 튜닝 값은 코드에 하드코딩하지 않는다.** DB(`PromptTemplate`, `LLMSettings`, `AppSetting`)에서 읽는다. 코드에는 seed 기본값만 둔다(`apps/llm/defaults.py`).
- LLM 응답은 항상 JSON 스키마로 받고 Pydantic/DRF serializer로 검증한다. 검증 실패 시 1회 재시도 후 `확인 필요`로 떨어뜨린다 — 절대 임의로 `충족` 처리하지 않는다.
- 판정은 **규칙 엔진(결정적) → LLM(보조)** 순서. 규칙으로 확정 가능한 수치 비교는 LLM 결과로 뒤집지 않는다 ([specs/08](specs/08-compliance-evaluation.md)).
- 모든 판정에는 근거(evidence: 문서·페이지·인용문)가 있어야 한다. 근거 없는 `충족`은 금지.
- API Key는 암호화 저장(Fernet), 응답·로그에 평문 노출 금지 (마스킹 `sk-...abcd`).
- 사용자 대면 문자열(UI, 생성 문서)은 한국어. 코드·식별자·커밋 메시지는 영어.
- 시간대 `Asia/Seoul`, 날짜 비교는 timezone-aware.
- 새 모델·필드 추가 시 마이그레이션 생성, `specs/02-data-model.md` 동기화.
- 테스트: 판정 규칙(`apps/evaluation/rules.py`)과 문서 파서는 단위 테스트 필수. LLM은 테스트에서 `FakeLLMProvider`로 대체.

## 작업 흐름

1. 작업 범위에 해당하는 spec 읽기 → 2. 구현 → 3. 테스트 → 4. **README.md 갱신**(실행 방법·기능 현황·환경 변수가 바뀌었을 때마다) → 5. 커밋.
- `specs/13-roadmap.md`의 마일스톤 체크박스를 완료 시 갱신한다.
- 불명확한 요구사항은 추측해서 넓게 구현하지 말고 spec의 "결정 사항/미결 사항"을 확인하고, 없으면 사용자에게 묻는다.

## 주의

- `initial-data/bid_sample/{won,lost}/<폴더>/`는 **실제 과거 공고**(2010–2023, 폴더 1개 = 공고 1건, `won`=낙찰·`lost`=미낙찰). 대부분 HWP이고 XLS/XLSX/스캔 PDF가 섞여 있다. `*:Zone.Identifier` 파일은 무시한다. HWP 파서는 컨트롤 문자 처리 규칙([specs/06](specs/06-document-processing.md) §2.1)을 반드시 따른다.
- 과거 공고를 현재 회사 자료로 판정하므로 판정 기준일 규칙([specs/08](specs/08-compliance-evaluation.md) §5 `reference_date_mode`)을 지킨다.
- `initial-data/company/`의 자료는 **PoC용 가상 자료**다. 생성 문서·보고서 하단에 "가상 자료 기반 초안" 문구를 넣을 수 있도록 설정(`AppSetting: report.disclaimer`)을 둔다.
- 생성 결과물은 모두 "초안"이며 최종 제출 전 담당자 검토가 필요함을 UI에 명시한다.
