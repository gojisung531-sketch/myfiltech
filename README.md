# vc_filtech — FilTech Bid Assistant

발전소(가스터빈 흡기·공조) 입찰 공고 중 (주)필텍 공기필터 제품에 적합한 공고를 찾고, 공고의 핵심 요구사항을 회사 제품 사양·시험성적서·인증·납품실적과 비교해 **충족 / 보완 필요 / 확인 필요**로 판정한 뒤 **Compliance Matrix, 입찰 체크리스트, 발주처 기술질의서, 검토 보고서(PDF)** 초안을 만드는 Web App.

> 현재 상태: **전체 마일스톤 M0–M8 완료** (초안 · PDF · XLSX, 운영 화면 포함) — 진행 현황은 [specs/13-roadmap.md](specs/13-roadmap.md)

## 주요 기능

**입찰담당자**
- ID/비밀번호 로그인
- 대시보드: 총 입찰 건수 · 확인 건수 · 미확인 건수 + 공고 목록(적합도, 마감일, 판정 요약)
- 공고 상세: ① 핵심 요구사항 → ② 회사 자료 비교 → ③ 판정·근거·자동 답변(수정 가능) → ④ 초안 생성 → ⑤ 확인·수정·PDF 다운로드

**관리자**
- 상단 우측 로그인, 기본 계정 자동 생성 (`admin` / `admin1234!` — 최초 로그인 후 변경 권장)
- 입찰담당자 추가·관리
- 회사 정보 · 제품 · 시험성적서 · 인증서 · 납품실적 CRUD (TXT / DOCX / HWP / HWPX / PDF 업로드 또는 텍스트 입력, 분류별 메타데이터 자동 추출·수정)
- 입찰 공고 + 다중 첨부 등록·수정·삭제, 핵심 요구사항 자동 추출
- LLM 선택(ChatGPT / Claude / Gemini), API Key·모델(기본 Claude Opus 5.5)·프롬프트·튜닝 설정 — 모두 PostgreSQL 저장
- 운영: 백그라운드 작업 목록(재시도·취소), LLM 호출 로그(토큰·지연·응답 원문), initial-data 다시 적재
- API Key 미설정 시: 관리자 로그인 페이지로 이동 → 로그인 후 바로 API Key 입력 화면

## 기술 스택

| 영역 | 스택 |
|---|---|
| Frontend | Vue.js 3, Vite, Bootstrap 5.0, HTML5/CSS3 (SPA) |
| Backend | Python 3.12, Django 5.2, Django REST Framework, Django ORM |
| Database | PostgreSQL 18 (로컬 설치) |
| LLM | OpenAI / Anthropic / Google Gemini SDK |
| PDF | WeasyPrint + Noto Sans KR (`backend/fonts`, SIL OFL) |

```
Vue.js SPA ──HTTP/JSON──▶ Django REST Framework ──Django ORM──▶ PostgreSQL
```

## 저장소 구조

```
CLAUDE.md        Claude Code 작업 지침 (vibe coding 규칙)
specs/           상세 요구사항 (00 개요 ~ 13 로드맵)
initial-data/    초기 데이터 (읽기 전용)
  company/         회사 자료: 인증서 3, 기술사양서 6, 납품실적 1, 시험성적서 9 (PoC용 가상 자료, PDF)
  bid_sample/      입찰 공고 샘플: won/ 8건 (HWP·HWPX·XLS·XLSX·PDF), lost/ (비어 있음)
backend/         Django 5.2 + DRF (config/, apps/core, accounts, llm, documents, company, bids, evaluation, drafts), fonts/
frontend/        Vue 3 + Vite SPA
```

## 스펙 문서

| # | 문서 |
|---|---|
| 00 | [개요 · 용어 · 결정 사항](specs/00-overview.md) |
| 01 | [아키텍처 · 디렉터리 · 환경 변수](specs/01-architecture.md) |
| 02 | [데이터 모델](specs/02-data-model.md) |
| 03 | [인증 · 권한 · API Key 게이트](specs/03-auth-and-access.md) |
| 04 | [관리자 기능](specs/04-admin-features.md) |
| 05 | [입찰담당자 기능](specs/05-bid-manager-features.md) |
| 06 | [문서 처리 (HWP 파싱 · 분류 · 메타데이터)](specs/06-document-processing.md) |
| 07 | [LLM 연동 · 프롬프트 · 튜닝](specs/07-llm-integration.md) |
| 08 | [요구사항 추출 · 판정 규칙](specs/08-compliance-evaluation.md) |
| 09 | [초안 · PDF 보고서](specs/09-drafts-and-reports.md) |
| 10 | [REST API](specs/10-api.md) |
| 11 | [Frontend](specs/11-frontend.md) |
| 12 | [초기 데이터 · 테스트 시나리오](specs/12-initial-data.md) |
| 13 | [로드맵](specs/13-roadmap.md) |

## 빠른 시작

```bash
cp backend/.env.example backend/.env   # DJANGO_SECRET_KEY, FIELD_ENCRYPTION_KEY, DATABASE_URL 설정 (생성 명령은 파일 안 주석 참고)

# PDF(WeasyPrint)용 시스템 라이브러리 — Ubuntu/WSL 기준 (대부분 이미 설치되어 있음)
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b   # 선택: libharfbuzz-subset0 (폰트 서브셋 경고 제거)

# 로컬 PostgreSQL 18에 역할·DB 생성 (최초 1회, 자세한 내용은 specs/01 §4.1)
sudo -u postgres psql -c "CREATE ROLE filtech WITH LOGIN PASSWORD 'filtech' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE filtech OWNER filtech ENCODING 'UTF8' TEMPLATE template0;"

# Backend — http://127.0.0.1:8000
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # 셸의 `python`은 Windows pyenv를 가리키므로 python3.12 사용
pip install -r requirements.txt
python manage.py migrate          # 기본 관리자 admin / admin1234! · AppSetting · LLM 모델 기본값 자동 생성
python manage.py load_initial_data # 회사 자료 19건 + 입찰 공고 샘플 8건 적재 (LLM 설정 시 공고 추출까지 실행)
#   --only company|bids   한쪽만 적재 · --no-llm  LLM 호출 없이 적재(공고는 '등록됨' 상태로 남음) · --mode update  다시 추출
python manage.py runserver 8000
python manage.py run_jobs         # 별도 터미널: 백그라운드 작업 워커 (문서 추출 등)

# Frontend — http://localhost:5173 (/api, /media → :8000 프록시)
cd ../frontend
npm install && npm run dev
```

### 검사 · 테스트

```bash
cd backend && pytest && ruff check . && ruff format --check .
cd frontend && npm run lint && npm run build
```

### 첫 실행

1. http://localhost:5173 접속 → LLM API Key가 없으므로 **관리자 로그인** 화면으로 이동합니다.
2. `admin` / `admin1234!` 로 로그인 → 바로 **LLM 설정**(API Key 입력) 화면으로 이동합니다.
3. 제공자(Claude / ChatGPT / Gemini)를 고르고 API Key를 저장하면 연결 테스트가 자동 실행됩니다.
4. 상단 경고 배너의 안내에 따라 관리자 비밀번호를 변경하고, **사용자** 메뉴에서 입찰담당자를 추가합니다.
5. **입찰 공고** 메뉴에서 공고를 등록(파일 여러 개 + 본문 붙여넣기)하고 **추출 실행**을 누르면 공고 메타데이터·품목·핵심 요구사항이 추출되고 후보 제품·적합도가 계산됩니다. 수정한 메타데이터·요구사항은 잠겨서 다시 추출해도 유지됩니다. 추출은 `run_jobs` 워커가 처리합니다.
6. 입찰담당자는 **대시보드**에서 공고를 열어 ① 핵심 요구사항 ② 회사 자료 비교 ③ 판정 및 자동 답변을 확인합니다. **판정 실행**은 규칙 엔진으로 먼저 판정하고 LLM이 근거 서술·답변을 작성합니다(규칙 판정은 LLM이 바꾸지 않음). 판정은 수정·이력 확인·AI 판정으로 되돌리기가 가능하고, **확인 완료**를 누르면 대시보드 확인 건수에 반영됩니다. 판정도 `run_jobs` 워커가 처리합니다.
7. **④ 초안 생성** 탭에서 Compliance Matrix · 입찰 체크리스트 · 발주처 기술질의서 · 검토 보고서를 생성합니다(판정 결과 기반, LLM이 문장을 다듬음 — LLM 실패 시 규칙 기반 초안). 편집 화면에서 셀·문단을 고쳐 저장하고, 버전을 고르거나 확정할 수 있습니다. 담당자가 수정한 버전은 재생성해도 덮어쓰지 않고 새 버전을 만듭니다. Compliance Matrix와 체크리스트는 **XLSX**로도 내려받을 수 있습니다. 상단 **PDF 다운로드**는 표지 → 검토 보고서 → 요구사항·판정 → Compliance Matrix(A4 가로) → 체크리스트 → 기술질의서 통합 보고서입니다.
8. **설정 → 프롬프트**에서 문서를 골라 [테스트 실행]으로 LLM 응답을 확인할 수 있습니다. 프롬프트와 **설정 → 튜닝** 값은 모두 DB에 저장되며 즉시 적용됩니다.

기본 관리자는 `migrate` 시 ADMIN 계정이 하나도 없을 때만 만들어집니다. 수동 실행: `python manage.py ensure_admin`.

## 운영

| 항목 | 방법 |
|---|---|
| 백그라운드 작업 | 문서 처리 · 공고 추출 · 판정 · 초안 생성은 모두 `python manage.py run_jobs` 워커가 처리합니다. 워커가 꺼져 있으면 작업이 ‘대기’로 남습니다. **설정 → 작업**에서 상태·오류 확인, 실패 작업 재시도, 대기 작업 취소. |
| LLM 사용량 | **설정 → LLM 호출 로그**: 오늘/이번 달 호출 수·토큰 합계, 호출별 지연·오류·응답 원문. API Key는 로그에 남지 않습니다. |
| 튜닝 | **설정 → 튜닝**: 판정 기준일 모드, 허용오차, 배치 크기, 적합도 가중치, 보고서 하단 문구(`report.disclaimer`) 등 — 저장 즉시 반영. |
| 초기 데이터 | **회사 자료 → 문서** 또는 **입찰 공고** 화면의 [initial-data 적재], 또는 `python manage.py load_initial_data [--only company\|bids] [--mode update] [--no-llm]`. |
| 로그 | Django 로그는 표준 출력(콘솔). API Key·토큰 문자열은 마스킹됩니다. |

### 백업 · 복구

데이터는 PostgreSQL과 업로드 파일(`MEDIA_ROOT`, 기본 `backend/media/`) 두 곳에 있습니다. 둘을 함께 백업하세요.

```bash
# 백업
pg_dump -h 127.0.0.1 -U filtech -Fc filtech > filtech_$(date +%Y%m%d).dump
tar czf media_$(date +%Y%m%d).tar.gz -C backend media

# 복구 (빈 DB에)
pg_restore -h 127.0.0.1 -U filtech -d filtech --clean --if-exists filtech_YYYYMMDD.dump
tar xzf media_YYYYMMDD.tar.gz -C backend
```

`backend/.env`의 `FIELD_ENCRYPTION_KEY`가 바뀌면 DB에 암호화 저장된 API Key를 복호화할 수 없습니다 — 키를 백업과 함께 안전하게 보관하거나, 복구 후 LLM 설정에서 API Key를 다시 입력하세요.

## 주의

- `initial-data/company/`의 자료는 PoC 테스트용 **가상 자료**입니다.
- 생성되는 모든 판정·문서는 **초안**이며 제출 전 담당자 검토가 필요합니다.
