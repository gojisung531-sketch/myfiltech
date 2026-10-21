# 09. 초안 문서 · PDF 보고서

모든 초안은 `DraftDocument.content`(JSON)에 구조화 저장하고, 화면 편집과 PDF 렌더링이 같은 JSON을 사용한다. 생성은 `GENERATE_DRAFT` Job.

## 1. Compliance Matrix (`COMPLIANCE_MATRIX`)

```json
{
  "header": {"bid_title": "...", "notice_no": "...", "buyer_org": "...", "prepared_by": "홍길동", "prepared_at": "2026-10-05", "company": "(주)필텍"},
  "rows": [
    {"no": 1, "requirement_id": 12, "item": "품번1 Cylindrical", "category": "차압",
     "clause": "구매규격서 2.2 시험결과", "requirement": "Initial Pr. Drop 0.71 inH2O(≈177 Pa) 이하 @2,770 m³/h",
     "offered": "FT-CP200 120 Pa @1,100 m³/h (AFT-2024-1105)", "compliance": "보완 필요",
     "response": "…", "evidence": "AFT-2024-1105 p.2", "remark": ""}
  ]
}
```
- 행 = 요구사항 1:1 (판정 결과 반영). 정렬: 품목 → 카테고리 순서.
- `response`는 판정 auto_answer를 기반으로 `draft.compliance_matrix` LLM이 문장 다듬기(선택, `evaluation.use_llm`).
- 화면: 셀 편집 표. PDF: A4 가로.

## 2. 입찰 체크리스트 (`BID_CHECKLIST`)

```json
{
  "sections": [
    {"title": "입찰 참가 자격", "items": [
      {"text": "나라장터 공기여과기(4016150501) 제조물품 등록", "due": "2023-04-04", "owner": "", "status": "TODO|DONE|NA", "verdict": "확인 필요", "note": ""}]},
    {"title": "입찰 시 제출서류", "items": []},
    {"title": "실적심사 / 적격심사", "items": []},
    {"title": "계약 시 제출서류", "items": []},
    {"title": "납품 시 제출서류", "items": []},
    {"title": "시험 · 검사 준비", "items": []},
    {"title": "주요 일정", "items": [{"text": "전자입찰서 제출 마감", "due": "2023-04-05T12:00"}]}
  ]
}
```
- 원천: `CERTIFICATION`, `TRACK_RECORD`, `SUBMISSION_DOC`, `INSPECTION`, `DELIVERY` 요구사항 + 판정 action_items + 공고 일정.
- 마감일 역산 일정(예: 시험 의뢰 = 납품기한 − 30일)은 LLM 제안, 담당자 수정.
- 화면에서 체크 상태 토글 가능(저장).

## 3. 발주처 기술질의서 (`TECHNICAL_QUERY`)

```json
{
  "header": {"to": "한국동서발전(주)울산발전본부 담당자 귀하", "from": "(주)필텍 기술영업부", "date": "…", "subject": "[공고번호] 공고명 관련 기술 질의"},
  "intro": "귀 기관의 … 관련하여 아래와 같이 질의드리오니 회신 부탁드립니다.",
  "questions": [
    {"no": 1, "reference": "구매규격서 2.2 시험결과", "question": "…", "background": "…", "proposed_alternative": "…", "requirement_id": 12}
  ],
  "closing": "…"
}
```
- 원천: `NEEDS_CONFIRMATION` 전부 + `NEEDS_SUPPLEMENT` 중 대체안 제안이 가능한 항목(규격 동등 인정, 치수, 재질). 각 판정의 `clarification_question`을 정리.
- 공문 어투, 질문당 3~5문장.

## 4. 검토 보고서 (`REVIEW_REPORT`) — 내부용

```json
{
  "executive_summary": "…",
  "recommendation": "BID | CONDITIONAL | NO_BID",
  "recommendation_reason": "…",
  "bid_overview": {...},
  "fit": {"score": 72, "reason": "…", "matched_products": [...]},
  "stats": {"met": 10, "needs_supplement": 5, "needs_confirmation": 3, "high_risk": 2},
  "key_risks": ["…"],
  "next_actions": [{"action": "…", "owner": "", "due": ""}],
  "requirements_table": "COMPLIANCE_MATRIX 참조"
}
```

## 5. PDF 생성

- WeasyPrint + Django 템플릿(`apps/drafts/templates/pdf/*.html`), 폰트 `backend/fonts/NotoSansKR` 임베드(@font-face). 한글 깨짐 없는지 테스트.
- 공통 레이아웃: 헤더(회사명/로고, 문서명, 공고번호), 바닥글(페이지 x/y, 생성일시, `report.disclaimer`), 표 머리행 반복(`thead { display: table-header-group }`).
- 판정 색상: 충족 #198754, 보완 필요 #fd7e14, 확인 필요 #0d6efd, HIGH 위험 행 왼쪽 빨간 띠.
- 엔드포인트:
  - `GET /api/bids/{id}/drafts/{type}/pdf` — 개별 초안 최신 버전
  - `GET /api/bids/{id}/report.pdf` — 통합 보고서: 표지 → 검토 보고서 → 요구사항·판정(근거 포함) → Compliance Matrix → 체크리스트 → 기술질의서
- 파일명: `{notice_no or bid_id}_{문서유형}_{YYYYMMDD}.pdf` (Content-Disposition RFC 5987 UTF-8 인코딩).
## 6. XLSX 내보내기 (Compliance Matrix · 체크리스트)

- openpyxl. `GET /api/bids/{id}/drafts/{type}/xlsx[?version=]` — `COMPLIANCE_MATRIX`, `BID_CHECKLIST`만 지원(그 외 404). PDF와 같은 초안 JSON(최신 또는 지정 버전)을 사용한다.
- 파일명: `{notice_no or bid_id}_{문서유형}_{YYYYMMDD}.xlsx` (PDF와 같은 규칙).
- Compliance Matrix: 시트 1개. 상단에 공고명·공고번호·수요기관·작성자/일자, 이어서 표(No, 품목, 구분, 요구사항, 조항, 제안 사양, 충족 여부, 응답, 근거, 비고). 머리행 고정(freeze), 자동 필터, 줄바꿈, 충족 여부 글자색(충족 #198754, 보완 필요 #fd7e14, 확인 필요 #0d6efd), HIGH 위험 행은 첫 열 빨간 채움.
- 체크리스트: 시트 1개. 열(섹션, 상태, 항목, 기한, 담당, 판정, 비고), 섹션 순서 유지, 상태는 완료/미완료/해당 없음 한글 표기.
- 바닥에 `report.disclaimer` 문구 1행.
