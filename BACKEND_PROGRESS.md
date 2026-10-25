# 백엔드 인수인계 — Backend B5D

- 상태: **B5D 완료, 여기서 중단** (2026-10-26, Asia/Seoul). 코드 확인에 그치지 않고 공고 ID2의 실제 저장 판정으로 규칙 초안 4종을 저장하고 실제 API에서 XLSX 2개·PDF 5개를 내려받아 내용/렌더링을 확인했다. 새 LLM 요청·SDK 재시도·JSON 복구·재추출·재판정·상시 워커 실행은 모두 **0**.
- `feature/backend-foundation`, 깨끗한 B5C **f5133cc** 이후 이어감. 완료 커밋은 **이 기록을 포함한 HEAD** — `feat(backend): generate and verify stored draft exports`. 변경은 backend/**와 이 파일뿐. 프런트·다른 worktree·노션·기업 원본·루트 공통 문서 변경, 초기화/push/배포 없음.

## 실제 생성·저장과 버전

- 기존 `apps/drafts.service.generate_draft`로 **allow_llm=False, new_version=True**를 명시해 최초 한 차례 생성. 대응표 **ID1/v1**, 체크리스트 **ID2/v1**, 기술질의서 **ID3/v1**, 검토보고서 **ID4/v1**. 모두 AUTO/DRAFT, used_llm=false, is_modified=false. 저장 전 초안은 0개였으며 저장 후 JSON을 실제 GET으로 다시 대조했다. 출력 형식을 보완할 때 초안을 다시 생성하거나 저장 내용을 덮어쓰지 않았다.
- 일반 생성 API는 선택 Boolean `allow_llm`을 작업에 전달하며 생략 시 기존 기본 동작을 보존한다. 전역 AI 설정/키/모델/활성 v2 프롬프트는 변경하지 않았다. 기존 정책상 수정되지 않은 자동 초안은 기본 재생성 시 같은 버전을 갱신하고, `new_version=True` 또는 수동 수정본은 다음 버전을 만든다. 수동본 보호는 격리 회귀 검사로 확인했다.
- 4종 모두 **저장 판정 기준일 2026-10-25**, 생성일 2026-10-26을 구분하고 동일한 판정/정규화/trace 입력 SHA와 검토 고지를 저장했다. **최종 37개 확인 필요**와 **후보별 비교 12개**를 분리했다. 후보 일치/차이를 확정 충족/미달·시험 성적서 제출 완료로 올리지 않았다.
- 체크리스트 **21항목**, 제작 전 승인 시점을 별도 표시. 기술질의서는 **내부 확인31 / 발주처 확인4**로 분리하고 이미 기재된 형식·치수 자체를 다시 질문하지 않는다. 검토보고서의 CONDITIONAL은 **추가 확인 후 직원 검토**, 점수 null은 미산정, 직원 최종 결정/제출본 아님을 명시한다. 자료 미등록을 미보유·입찰 불가로 단정하지 않는다.

## 실제 다운로드·파일 검증

- 최종 결과물은 모두 Git 제외 **backend/.venv/b5d/outputs-final/**. 아래 개별 4종은 저장 **v1**, 통합도 동일한 4개 v1 JSON을 한 조회에서 선택해 사용한다. 실제 저장 조회·다운로드 API 모두 200, MIME/크기/ZIP CRC 또는 PDF 파싱을 확인했다.
  - `COMPLIANCE_MATRIX_v1.xlsx`: 대응표 **37행** + 별도 후보 비교 시트 **12행**.
  - `BID_CHECKLIST_v1.xlsx`: 단일 시트 **21항목**.
  - `COMPLIANCE_MATRIX_v1.pdf`: **12페이지**.
  - `BID_CHECKLIST_v1.pdf`: **4페이지**.
  - `TECHNICAL_QUERY_v1.pdf`: **3페이지**.
  - `REVIEW_REPORT_v1.pdf`: **3페이지**.
  - `INTEGRATED_REPORT.pdf`: **30페이지** (표지·검토보고서·요구조건/판정·대응표·체크리스트·기술질의서).
- XLSX는 저장 JSON과 대응표 37행×10열·체크리스트 21항목·후보 12행을 대조하고 한글/근거/판정·필터·고정 머리행·수식 셀 없음 확인. 수식 주입 보호를 모든 외부 문자열에 적용하며 선행 공백/탭/개행과 XML 제어문자를 처리하고 숫자는 숫자로 보존한다. 실제 다운로드 파일을 Artifact Tool로 읽어 **3시트의 대표 6범위**를 렌더링/시각 확인했으며 파일을 재수출하지 않았다.
- PDF는 **5파일 전체 52페이지**를 PDFium으로 렌더링하고 연락판/긴 표와 후보 구획을 확대 확인했다. 모든 페이지의 한글 폰트 임베딩·페이지 경계·깨진 글리프를 검사. 개별/통합 양쪽에서 대응표 37개 요구조건/최종 판정, 체크리스트 21항목, 내부31/외부4 질문, 검토보고서 총평/미확정 조건의 실제 텍스트를 대조했다. 최종 검사 오류 **0**. 긴 문장·표 셀·후보 제목/근거 묶음·가로/세로 페이지 전환·v1 표기를 확인했다. 일부 표는 다음 페이지로 이어지며 내용이 누락되지 않는다.
- 실제 Excel 데스크톱/브라우저 화면 조작 검증은 하지 않았다. 합성 검사와 실제 파일 검증을 전체 분석 정확도나 법적/기술적 완전성으로 표현하지 않는다. 초기 `outputs/`는 형식 보완 전 기록이며 **최종 전달은 outputs-final/**이다.

## PDF 실행 환경과 관련 검사

- 기존 WeasyPrint 70의 libgobject-2.0-0 로딩 실패를 재현했다. 공식 MSYS2 저장소 메타데이터/패키지 SHA를 검증해 Pango 의존성 **39패키지의 런타임 파일119개**를 `.venv/pdf-runtime/mingw64`에 분리 추출했다. 시스템 설치/후처리 실행·Python 재설치·.env 초기화 없음. 패키지 버전/URL/SHA·라이선스는 `.venv/pdf-runtime/manifest.json`과 share/licenses에 있다.
- 기존 Noto Sans KR 두 폰트/OFL 사본의 SHA를 대조했다. 기존 P:→이 backend/.venv 별칭을 유지하며 프로세스에 `WEASYPRINT_DLL_DIRECTORIES=P:/pdf-runtime/mingw64/bin`, `FONTCONFIG_FILE=P:/pdf-runtime/fonts.conf`를 전달했다. Fontconfig는 같은 별칭의 폰트/캐시를 사용한다. 실제 개발 서버에서 한글 PDF 생성/다운로드 성공. 시스템 전역 환경/.env는 그대로다.
- `backend/docs/draft-output-b5d.md`에 실행/버전 정책·Windows 준비·이후 Render의 Pango/GObject/PangoFT2/HarfBuzz/Fontconfig와 한글 폰트/OFL·캐시 조건을 기록했다. Render 배포/원격 설정 변경은 하지 않았고 실제 Linux 렌더링은 후속 배포 환경에서 별도 확인해야 한다.
- 관련 회귀 **7 passed** (`apps/drafts/tests/test_stored_outputs.py` 6개 + 기존 validate_content 1개). 규칙 저장·수동 버전 보존·질문 구분·확인 필요/조건부·후보와 최종 구분·XLSX 주입 방지·실제 네이티브 PDF·API 저장 조회/출력 경로 검사. 테스트 Python 외부 socket 시도0, 유료 통신 대체/금지. 가상 회사자료 fixture 복원이나 관련 없는 전체 검사 반복 없음.
- drafts Python16개 ruff check/format, Django check(문제0), git diff --check 통과. 모델/마이그레이션 변경 없음. 검사 기록 `regressions-final.log`, `check.log`, 실제 파일 검사 `file-review-private-final.json`/`file-inspection-final.log`, `xlsx-render-final.log`.

## 보존·동시 변경·서버

- 작업 전 일관된 읽기 스냅샷으로 `.venv/b5d/before-b5d.dump` (**714732 bytes**, SHA256 `b8735cfa693843606c77c074b38f87deb920f86d5075b110704e406be76dcfa9`)와 `media-before.zip` (SHA256 `fee72b124564b0ccd6fd5df669a3286db5dd5d13537ea87c073131350b14ec1d`) 생성. TOC/ZIP CRC/내용 SHA 확인, 실제 복원은 미실행. 복구는 먼저 격리 DB/별도 미디어 폴더에 복원해 대조하고 B5D 초안4개와 동시 수동 작업을 구분해야 한다. **현재 DB를 전체 백업으로 덮어쓰면 후속 수동 작업이 사라지므로 그렇게 복구하지 않는다.**
- public39테이블 중 **34개 전체 해시 동일**: 요구조건·판정37/이력45·회사자료·검토 대기151·설정/키/프롬프트 등 보존. B5D가 추가한 데이터는 초안4개뿐. 기존 미디어10개/공고 원본4개/.env/백업/최종 다운로드 SHA 대조 통과. 원문·기업 값·키·토큰·DB 백업·출력물은 Git 제외 로컬에만 있다.
- **동시 변경을 발견해 보존했다.** 백업 대비 나머지 변경은 accounts_user.last_login, outstanding token 신규3개(기존13개 불변), 품목ID1의 matched_product_id **null→1**/updated_at, 별도 작업2개와 초안 테이블이다. 품목 연결은 **00:42:10**에 바뀌었으며 B5D 서비스/다운로드는 연결을 변경하지 않았다. 로그인 기록 외 계정 필드/기존 토큰/다른 품목 필드는 동일. 변경을 되돌리거나 B5D의 제품 확정 작업으로 보고하지 않는다.
- 별도 **Job ID1 EXTRACT_BID(00:35:37), ID2 EVALUATE_BID(00:42:15)**가 ID2 대상 PENDING/attempts0/started_at null로 존재한다. B5D는 이를 생성·실행·취소하지 않았다. **다음 단계에서 run_jobs 전체 실행 전 이 대기 작업의 의도를 먼저 확인해야 한다.** 새 LLM 로그0(기존 총2개), 판정/이력 해시 불변. 이번 출력은 새 수동 연결 후 재판정한 결과가 아니라 **기존 B5C 판정과 후보 trace의 저장 스냅샷**이며, 수동 연결만으로 기존 후보 판정을 확정 충족으로 바꾸지 않았다.
- 마지막 실제 상태 API200·ID1/2 첨부 각4·관리대장151(PENDING151)·비교37행·저장 초안4종 GET200. 이 GET 전후39테이블 동일, 유료 호출/작업 생성 없음. 근거 `http-final.json`, `preservation-verification.json`, `concurrent-changes-audit-verified.json`, `download-manifest-final.json` (각 파일 크기/SHA/API/버전).
- 소스/네이티브 환경·최종 출력 형식 반영을 위해 Django만 총2회 재기동, 기존 cwd/.venv/.env/localhost:8000/--noreload 유지. 최종 launcher **10316**, listener **408**. PostgreSQL **26452/5432**, 프런트 **20648/5173**는 재시작하지 않고 유지. 서버 로그/시작 환경은 `.venv/b5d/server-final-*`에 있다. 상시 워커 없음.

## 다음 시작점

- 실무자는 로컬 출력물/저장 v1을 검토할 수 있다. 후보별 기재값 비교·미확정 조건·내부 질문과 발주처 질문은 구분돼 있으며 질문 발송은 하지 않았다. 기존 회사자료로 확인되는 항목은 활용하고 성적서 미확보를 전체 검토 중단 조건으로 삼지 않는다.
- 회사자료 개정/오래된 결과 자동 표시 기능은 **여전히 미구현**. 현재 입력 SHA/기준일은 실행 기록이며, 후속 회사자료/제품 선택 변경이 초안·판정을 자동 갱신하지 않는다. 특히 위 수동 제품 연결과 저장 B5C 판정의 시점 차이를 확인한 뒤 별도 승인된 후속 단계에서 수동 수정 보존·비교 갱신을 검증한다. B5D에서 재추출·재판정·초안 유료 다듬기·배포로 확장하지 않는다.

---

# 백엔드 인수인계 — Backend B5C

- 상태: **B5C 완료, 여기서 중단** (2026-10-25, Asia/Seoul). 공고 ID2를 재추출하지 않고 실제 카탈로그 후보 자료 등록·회사 비교/판정 한 차례·저장/조회·원문/결과 대조 완료. 초안 생성/다운로드·전체 회사자료 적재·151행 정식 전환·제품/시험 시료 추정 연결·직원 최종 입찰 결정은 실행하지 않음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 깨끗한 B5B `354f54d` 이후 상태에서 이어감. 완료 커밋은 **이 기록을 포함한 HEAD** — `feat(backend): compare catalog candidates with guarded judgments`. 변경은 backend/**와 이 파일뿐. 프런트·다른 worktree·팀 노션·기업 원본·루트 공통 문서 변경, reset/clean/push 없음.

## 등록 자료와 실제 비교 결과

- 실제 기업 원본을 다시 SHA 대조하고 카탈로그 p3 **좌측 Cartridge Pulse Filters 구획**과 소개서 p9를 이미지/텍스트로 확인. 오른쪽 다른 제품 표와 혼합하지 않음. **회사 문서 ID10·11**, 수동 비교 메타데이터2행, **카탈로그에 명시된 모델의 Product ID1·2**만 등록. 회사의 source_documents에 두 문서 연결. 원본=업로드 사본 SHA 일치. Document PARSED/메타데이터 MANUAL이며 LLM 회사자료 추출·시험성적서 생성 결과가 아님.
- 형식·원통/원추·명시 치수·F9 재질 선택·등급·제조사 환경 사양을 해당 근거 범위에서 입력. 페어 성능은 `extra.manufacturer_claims`에 대상/연산자/단위/한계를 별도 보존하고 개별 제품의 정격풍량·차압 필드는 비워 둠. 소개서의 다른 풍량 조건·모델 불명 페어 표는 별도 참고 메타데이터이며 카탈로그 모델에 합치지 않음. 정확한 실제 회사 값·모델명·인용/원본 경로는 Git 제외 로컬 입력 기록에만 보존.
- 기존 점수식으로 **BidProductMatch 후보4행** 저장(품목2 × 모델2). 두 품목 `matched_product`/`match_score`는 기존 null 그대로. **확정 연결0**, 정식 TestReport/Certificate/DeliveryRecord 생성0, 151행 정식 전환/시료 연결0. 후보 비교를 직원이 선택한 제안 사양으로 간주하지 않음.
- 실제 요구조건 **37개 판정 저장**, 최종 **충족0·보완 필요0·확인 필요37(HIGH5)**. 후보별 형식/치수의 일치·불일치는 실제 규칙 trace에 남겼으나, 제안 모델/옵션이 미확정이므로 이를 확정 공고 충족·미달로 올리지 않음. 카탈로그 기재 효율의 하한·페어 시험대상/풍량·원문 해석 제한, 시험/자격/이행 직접 근거의 미등록을 항목별 이유로 구분. 세 종류 결과를 만들기 위해 임의 값을 등록하지 않음. **모두 확인 필요라는 결과는 비교 미실행이나 회사 전체 미달의 뜻이 아님**.
- 상태 `EVALUATED`, 검토 상태 `UNREVIEWED` 유지. `fit_score=null` 및 fit 캐시 없음: 미확정 후보로 종합 적합도나 최종 입찰 가능 점수를 계산하지 않음. 초안/다운로드/상시 워커/다른 공고 판정0. 실제 비교 API 37행의 회사 값·판정·이유가 저장 판정과 동일하고, 근거 document_id/페이지/인용은 실제 문서와 연결됨.

## 기존 추출 보존·해석 정리

- 원문으로 분명한 기관명을 본문 표기로 정정. **요구조건18개**의 정규화/조건부 필수 여부만 변경: req5·9·13·16·21·22·23·24·26·27·28·29·30·31·32·33·34·37. 변경 전후/출처/파서 텍스트 위치를 `.venv/b5c/prepared-inputs-private.json`, `requirements-before.json`에 보존. 원응답/공고 원문·원 인용·첨부·품목·제목/카테고리·물리 페이지 미확인 상태는 그대로.
- 도면 승인 시점은 제작 착수 전으로 정리. QIP/ITP는 ‘필요시’ 적용과 본문/부록 부수 범위를 구분해 조건부로 기록. Liner/End cap 재질 대안은 ANY(OR), 구성품별 적용은 별도 확인. 판본/표준 병행·효율 지표 명칭을 원문 범위 내 구조화. 원문 인용은 고쳐 만들지 않음.
- 온도 최저값·추정 풍량 단위는 확정값에서 비워 두고 원래 값은 변경 전 기록에 보존. 시험 종료 차압은 `test_endpoint_dp`/TEST_CONDITION으로, 총 풍량은 SYSTEM으로 분리. 고습 차압 변화와 사용 습도 한계·순유효면적과 카탈로그 구성품 면적 합계를 대체하지 않음. 개스킷 비고/지정 관계·KS 우선/승인 예외·중소기업 예외·설치/수량 구성 범위는 확인 필요 유지. 명확하지 않은 부분을 임의로 충족/미달 처리하지 않음.
- `normalized.interpretation_review`는 실제 `rules.evaluate`에서 다른 규칙보다 먼저 적용하고 `merge`에서도 LLM 답변이 이 제한·미확정 후보를 숨기지 못하게 함. 현재 프런트가 새 메타데이터를 별도로 표시하지 않아도 기존 판정/이유/회사 값에 제한이 남는다. 브라우저에서 표시된 모습은 직접 검증하지 않음.

## 실제 호출·후처리·경로

- 실행 전 `match_items` 자동 1순위 연결, `update_fit`의 별도 유료 설명, 판정 배치/저장 경로를 확인. `match_items(confirm=False)`와 기존 `evaluate_bid(rules_first=True, source_scoped=True, keep_modified=True)`를 사용. 전역 설정/일반 API 기본 동작/활성 프롬프트 변경 없이 지정 ID2만 직접 실행했으며 큐를 처리하지 않음.
- **규칙32개, 미처리5개(req6·8·15·35·36)는 evaluation.judge 1배치**. 실제 **Claude Sonnet 5.5 / claude-sonnet-5-5 / 활성 v2**, HTTP **1회(200)**, SDK 재시도0, JSON 복구0, 추가/복구 유료 실행0. 입력 **6,916 tokens**, 출력 **4,300 tokens**를 실제 SDK usage/새 LLMCallLog **id2**와 대조. 비용 금액은 확인되지 않아 추정하지 않음. 기존 B5B LLM 로그 id1·원응답 보존. 연결 테스트/재추출/fit/draft 호출0.
- 물리 요청은 실제 SDK의 **httpx2.Client.send**에서 전송 전 이벤트·재시도 헤더·응답을 계수. 원래 설정의 SDK retry 범위와 JSON 복구 한도를 실행 전에 기록했고 실제 요청은 1회뿐. 요청/회사 입력/응답은 Git 제외 기록, 키/토큰/복호화 키는 출력/새 저장하지 않음.
- **후처리8항목만 로컬 보정**, 유료 재실행 아님. 첫 저장은 실적 규칙의 ‘등록 없음→미달’ 오류 때문에 보완1/확인36이었다. req2 규칙을 고쳐 확인 필요로 변경하고 최초 자동 이력 보존. req17·19는 계열만 같아도 원통/원추 형상을 일치로 보던 후보 내부 trace를 수정(최종 확인 필요 판정은 그대로). 확인된 실측/수치 미달 규칙을 일괄 확인 필요로 바꾸지 않으며 합성 검사에서 실제 미달을 유지함.
- 나머지5건은 LLM 원응답/이력을 보존하면서 회사 직접 참조가 없는 설명을 공개 사실로 승격하지 않도록 문안을 제한. 실제 요청의 회사 제품 목록은 모델/이름 중심이었으며 **32개 규칙에 쓴 모든 카탈로그 값을 LLM도 전부 검토했다고 주장하지 않음**. ‘사양자료가 없다’·추정 수량/퍼센트·조건 부재·위치를 새 사실처럼 쓰지 않고, 등록 카탈로그 사양과 해당 이행/자격의 직접 근거 미확인을 구분해 보정. 다음 요청 구성은 제품별 실제 사양·제조사 주장/출처도 포함하도록 개선했으나 같은 입력으로 LLM을 다시 호출하지 않음.
- 최종 판정37행·자동 이력 **45행(최초37+로컬 보정8)**. 원래 `actual-call-receipt.json`의 최초 결과 카운트와 `final-result.json`/DB 최신 카운트를 구분한다. 뒤늦게 원영수증이나 원응답을 덮어쓰지 않음. 로컬 보정은 `postcheck-corrections-private.json`, `shape-trace-postcheck-private.json`, 각 자동 스냅샷으로 추적.

## 검증·보존·서버·백업

- 관련 합성 회귀 **81 passed** (`test_catalog_comparison.py`, B4B missing_evidence, grades). 알려진 충족/실제 미달/미상 구분, 제안 후보와 확정 선택, 원통/원추 형상, 페어와 개별 조건·하한 해석, 해석 검토 우선/LLM 문안 제한, 실적 부재, 작성 준비 미확인, 출처/없는 페이지 차단, 수동 판정 이력 보존, 회사 값/문서 연결, 반복 GET 무부작용을 확인. FakeProvider/가짜 judge 사용, 테스트 외부 socket0. 실제 공고의 전체 정확도 수치나 전체 테스트 통과/브라우저 검증으로 확대하지 않음. 관련 없는 가상 company_data 전체 검사 재실행/복원/skip 없음.
- 변경 Python8개 ruff check/format 통과, Django check 문제0, makemigrations --check --dry-run 변경0(검사 DB/네트워크 차단), git diff --check 통과. 모델/마이그레이션/의존성/프런트 변경 없음.
- 실제 상태 API200, 비교/판정/기존 공고1/공고2/관리대장151/활성v2/제품/회사 문서 조회 **14개 확인**, 비교/판정은 반복 조회. 37행의 company_value·판정·rationale 대응, 실제 문서 ID/페이지/원 인용 연결 확인. **GET 전후39테이블 해시 동일**, 유료/Job/판정 재실행0. API 검증이며 브라우저 화면·다운로드 검증은 미실행.
- 작업 전 public39테이블 일관 스냅샷과 미디어8개 백업. 최종 변경은 **10테이블**: 새 회사 문서/수동 메타데이터/회사-문서 연결/제품/후보, ID2의 지정 필드/정규화, 새 판정/자동 이력/LLM로그뿐. 나머지29테이블 해시 동일. 변경 테이블의 기존 행 또는 보호 필드는 dump의 COPY 원행/원 해시 및 변경 전 입력과 대조. 기존 공고1·품목2·첨부4·공고 원문/인용·미디어8개, 대기151행 전체, 회사 기존 필드, 키/설정/활성v2/기존 수동 작업/초안 보존. 새 미디어2개는 원본 해시와 일치. 기존 공고1 번호 불일치도 보존.
- 백업 `.venv/b5c/before-b5c.dump` **668,524 bytes**, SHA256 `f1e5e20ae783d73d75b69c0b4a22bd4f485bc31b96d34353b2d1f6215a1ba1ff`; `.venv/b5c/media-before.zip` SHA256 `7a82e3489573c14a1becd20c4d7797b10b9b1710b5b8c4528a3d2aaea371258e`. pg_export_snapshot과 같은 snapshot으로 pg_dump -Fc, TOC/zip CRC·내용 SHA 검증. 복원 시험/개발 DB 복원·migrate·flush·initdb 없음. 원본/백업/토큰/회사 입력/응답은 Git 제외.
- 복구 필요 시 백업 해시를 확인하고 먼저 격리 DB/폴더에 복원해 대조한다. 이번에 변경한 ID2 지정 필드/정규화와 새 모델/문서/후보/판정/이력/LLM 로그를 식별한 뒤 이후 수동 작업과 구분해 선택적으로 복구해야 한다. 현재 DB를 통째 덮어쓰거나 기존 미디어·다른 작업을 삭제하지 않는다. 실제 복구는 하지 않음.
- 시작 시 5432/8000 미응답·P: 매핑 없음 확인 후 기존 `.venv`의 P: 매핑/pgdata/바이너리만 재사용해 PostgreSQL 재개(클러스터 재초기화 없음). Django는 기존 venv/cwd/.env/localhost:8000/--noreload로 시작하고 최종 형상 비교 코드 반영을 위해 한 번 교체. 최종 launcher **20424**, listener **25300/8000**, PostgreSQL **26452/5432** 유지. 프런트 **20648/5173** 관찰, 직접 시작/재시작/수정하지 않음. 상시 워커 없음.
- 로컬 증거 `.venv/b5c/`: `backup-verification.json`, `prepared-inputs-private.json`, `registration.json`, `execution-plan-before-call.json`, `actual-judge-input-private.json`, `actual-response-1.json`, `actual-http-events.jsonl`, `actual-call-receipt.json`, 후처리 기록2개, `regressions-verified-final.log`, `check.log`, `migration-check.log`, **`http-verification-exit.json` / `preservation-verification-exit.json` / `db-after-exit.json`**, `server-final-start.json`/로그. 초기 검증 스크립트의 파일 인코딩/비공개 SHA API 필드 가정/기존 대상 포함 해시 비교 문제는 검증 도구에서 수정했고 업무 데이터 복구/유료 재실행으로 해결하지 않음.

## 다음 시작점·필요 확인

- 현재 저장 결과는 직원 검토용 후보 비교다. **직원에게 실제 제안할 두 모델과 재질/개스킷 옵션을 확인**하면 후보를 확정 연결할 수 있는 범위가 정해진다. 먼저 현재 카탈로그 사양·확인 필요 이유를 보여 줄 수 있으며, 성적서 확보나 151행 전수 검토가 전체 비교의 선행조건은 아니다. 원본/시험기관·조건/실적·제출 서류는 해당 요구에 필요한 항목만 다음 미팅에서 병행 확인. 질문 실제 발송0.
- `backend/docs/catalog-comparison-b5c.md`에 실행 경로/데이터 수준/추가 API 필드·한계 기록. 다음 실행 전에 해석 검토가 남은 부호·단위·OR/범위·판본/조건·예외·시점을 확인하고 제안 모델 선택과 수동 판정 보존을 확인한다. 준비된 ID2를 일반 ‘재추출’로 다시 처리하지 않는다.
- **자료 개정·오래된 결과 자동 표시 기능은 여전히 미구현**. 현재 API/판정 서비스는 최신 회사자료를 다시 읽지만 저장 결과는 B5C 입력의 스냅샷이다. 다음 단계에서 실제 회사 입력 해시/구획/값·프롬프트/설정을 실행 기록과 대조하여 변경을 식별하고 `keep_modified=True`/이력 보존을 검증한다. 완전한 개정 추적 시스템·프런트 경고 표시를 구현했다고 주장하지 않는다. B5C에서 멈춘다.

---
# 백엔드 인수인계 — Backend B5B

- 상태: **B5B 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 실제 공고 한 건 등록·Claude 요구조건 추출·DB 저장/재조회 및 원문 대조까지. 제품 생성/연결·회사자료 적재/정식 전환·제품 매칭·적합도·요구조건 판정·초안·상시 워커는 **실행하지 않음**. 직원의 최종 입찰 결정을 확정하지 않음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 깨끗한 B5A `0071031`에서 이어감. 완료 커밋은 **이 기록을 포함한 HEAD** — `feat(backend): extract one real bid without downstream analysis` (`git log -1 --oneline`). 자기 변경은 backend/**와 이 파일뿐. 프런트/팀 노션/다른 worktree/기업 원본/루트 공통 문서 수정, 초기화/push 없음.

## 실제 등록·호출·저장 결과

- **공고 ID2**, `20210829431-00`, `[울산발전]GT #7,8 입구 공기필터(Pulse Filter)구매`. 공고번호/source_ref/공고문 파일명·본문을 교차 조회하여 기존 대상0건 확인 후 등록. 기존 공고 **ID1과 첨부4개는 그대로**. 현재 같은 대상1건이며 source_ref=`20210829431`; 낙찰 여부를 폴더명으로 확정하지 않고 기존 기본 outcome 유지.
- 실제 첨부 **4개**: HWP 공고문·규격서, XLSX 품목명세서, 스캔 PDF 사유서. 새 attachment/document ID **6·7·8·9**, 원본=등록 SHA=업로드 사본 SHA 모두 일치. 새 미디어4개 추가, 기존4개는 바이트/경로 보존. Document는 **PARSED**이며 문서별 메타데이터 추출/OCR/전사 완료를 뜻하지 않음.
- **실제 Claude Sonnet 5.5 정상 실행 1차례 성공**, `bid.extract`만 호출. 클라이언트 HTTP 요청 **1회(200)**, SDK 재시도 **0**, JSON 복구 **0**, 수동 복구 실행 **0**. 입력 **33,428 tokens**, 출력 **21,800 tokens**(SDK usage와 실제 LLMCallLog 대조). 선택/응답 모델 모두 `claude-sonnet-5-5`, 프롬프트 **v2**. 실제 금액은 응답에서 확인되지 않아 추정 비용을 제시하지 않음. 연결 테스트를 다시 호출하지 않음.
- LLMCallLog 새 **1행/id1**, task=`bid.extract`, status=OK. **품목2개, 요구조건37개, placeholder0개** 실제 저장·재조회. `processing_status=EXTRACTED`, `review_status=UNREVIEWED`, `fit_score=null`, fit_reason 비어 있음, rule_fit_score/fit_breakdown/verdict_counts 없음. 두 품목 matched_product=null, BidProductMatch/RequirementEvaluation/EvaluationHistory/DraftDocument/Job 추가0.
- 기존 Claude 키·Sonnet 선택·온도/토큰/timeout/SDK재시도·task override·활성 v2 9개·전역 자동판정 설정을 **변경하지 않음**. 키는 기존 SDK 요청 경로에서만 복호화해 사용하며 키/토큰/기업 원문을 출력·Git 저장하지 않음.

## 분리한 실행 경로·스캔 입력

- 기존 일반 `process_attachments → run_pipeline`에는 문서 분류/메타데이터 LLM이 있고, `extract_bid` 뒤 match_items/update_fit, `extract_bid_job` 뒤 auto_evaluate enqueue가 있음을 확인. **일반 API 기본 동작/응답·전역 설정은 유지**하고 `extract_bid(..., extraction_only=True)` / `manage.py extract_bid_only --bid-id <승인된ID>`를 추가. 관리 명령은 지정 공고만 직접 실행하며 큐를 drain하지 않음. **완료된 ID2에는 다시 실행하지 말 것**.
- 추출 전용은 기존 add_attachment/_quick_process의 로컬 파싱·규칙 분류만 재사용하고 run_pipeline/회사자료 컨텍스트/제품 매칭/fit/판정/초안을 호출하지 않음. handler의 Boolean `payload.extraction_only=true`도 같은 범위이며 자동 판정 enqueue 생략. 등록/실패 상태만 허용하고 기존 매칭·fit·수동/잠금 요구조건·판정·초안이 있으면 호출 전에 거부해 보존.
- 통합 입력에서 빈 텍스트 PDF를 버리던 경로 보완: **최종 bid.extract에 첨부4개의 입력과 사유서 원본 PDF FileInput1개**를 전달. 원본 PDF SHA를 실제 generate 요청에서 확인. 원본 PDF 직접 입력이지 OCR 텍스트·사람 전사문이 아님. PDF 사유서에서 나온 requirement6은 1페이지 이미지와 직접 대조함. HWP2/XLSX1은 저장 로컬 텍스트 입력. PDF 텍스트층은 여전히0자이며 원본 없이 내용을 만들어 채우지 않음.
- 추출 전용에서는 비PDF 읽기 실패/누락 원본·PDF 미지원 모델·전체 첨부/렌더링 프롬프트 입력 한도 초과를 호출 전에 거부한다. JSON 복구 때도 원본 PDF 입력 유지. 다른 문서 단계에 PDF를 보냈다는 사실로 통합 입력을 추정하지 않음.
- HWP PAGE/파서 pages·시트 순번을 물리 페이지로 저장하지 않음. HWP/XLSX source_page=null; PDF만 알려진 페이지 범위 내 저장. placeholder 문구는 ‘추출 결과에서 확인 못함 — 원문 확인 필요’로 수정하여 ‘공고에 명시되지 않음’을 확정하지 않음.
- `extra.extraction_run`: 첨부 ID/원본 SHA·텍스트 SHA·입력 모드, 프롬프트 버전/요청 해시, provider/model 및 관련 파라미터, 실제 호출 로그 ID 기록. `extraction_source_review`는 인용의 문자/공백/인용부호 차이·미발견/첨부 누락·PDF 직접 확인 필요를 구분. 자동 기술 검증/개정 추적 시스템은 아니며 원문 인용을 자동으로 고쳐 만들지 않는다.

## 원문 대조 완료 범위·미해결

- 주요 기술/자격/납기/제출 **22묶음**을 원문과 대조하고 **37개 전부의 출처 연결/인용 대응**을 확인. 정확 문자열32, 공백 차이3, 인용 부호 차이1(req14; 공고문 추출L347의 따옴표 누락), PDF 이미지 직접 판독1(req6/p1). 인용 부호 차이를 정확 문자열 일치로 보고하지 않음. HWP 물리 페이지는 미확인 유지. XLSX는 통합 입력 포함 및 두 품목 자재번호·수량을 사람이 대조했으며 요구조건의 실제 인용 출처는 HWP2/PDF1이다.
- 확인 범위: 공고번호/구매결의번호·기관 표기·마감, 원통/원추 두 품목·치수·각 수량, Synthetic/discharged·EPDM·Liner/End cap, F9/MERV·평균효율/중량 포집률, 초기/시험종료 차압·풍량·단위, EN7792012/ASHRAE52.2·분진·DEHS or KCL·감독 승인, 순유효면적·고습 변동·운전 환경, 제조 등록/직접생산/중소기업과 예외, 단일 계약 실적, 납기/분할·검수·납품 원본/부수·도면/QIP/ITP·하자·계약확약·KS 우선/승인 예외. **전체 기술·법적 완전성이나 정확도 비율/적격성은 검증하지 않음**.
- 남은 문제: ① buyer_org가 본문 ‘울산화력발전처’를 ‘울산발전본부’로 정규화하여 원문 표기와 다름, ② SME 신청 예외/부적격4조건·조합2개사/배정비율/별도 참가 금지·특별법인 조건이 충분히 구조화되지 않음, ③ 온도 선행 대시/음수 부호와 min_temp_c=40 해석 미확정, ④ 초기 차압 조건의 원문 m/h→m³/h 추정·순유효면적 단위 미확정, ⑤ Liner/End cap OR가 required 배열에서 AND로 오용될 위험, ⑥ 시험 종료450Pa/시스템 총 풍량을 제품 성능 문턱과 혼동할 위험, ⑦ QIP ‘필요시’·KS ‘우선/승인 예외’와 필수 Boolean, 도면의 제작전 승인/모델 timing=납품시·부록 부수 차이, ⑧ 효율 metric slug/판본·표준 병행 조건의 후속 규칙 호환을 검토해야 함. 공급1400Set·각1400EA·공고1식은 포장/구성 단위 차이일 수 있어 모델의 ‘수량충돌’ 표기를 미달로 확정하지 않음.
- 명확한 코드 문제 **AIRFLOW 값이 맞으면 unit을 넣지 않던 분기**는 공통 정규화에서 수정/회귀 검사. 실제 req32에는 **단위 m3/h 한 항목만 로컬 재정규화**했고 숫자/raw/원응답은 그대로. LLM 재호출0. 다른 의미/부호/예외를 추정 보정하지 않았으며 `extra.b5b_review`에 부분 검토와 해당 요구조건 ID를 기록. 이 검토 메타데이터를 프런트 경고로 표시하는 기능은 추가하지 않았으므로, 비교 단계 전에 미해결 항목을 검토해야 함.
- 실제 원문·모델 응답·각 항목 조건/위치/질문은 Git 제외 `.venv/b5b/original-comparison-private.json`, `result-context-private.json`, `attempt-1-response-1.json`, `source-review-initial.json`, `local-normalization-and-review-apply.json`에 보존. 조건 미추출을 공고 전체 부재로 확정하지 않음. 결과를 고르기 위한 반복 호출/자동 판정은 하지 않음.

## 회사자료 병행 준비 — 원본 성적서는 전체 비교의 선행조건 아님

- 사용자 보충 지시 반영: **현재 카탈로그/실제 데이터시트로 확인되는 모델·형식·치수·재질·기재 성능은 해당 항목의 제조사 자료 근거로 비교 가능**. 카탈로그 정보를 전부 배제하지 않음. 명시 치수는 치수 비교 근거이며, 기재 성능은 제조사 주장 수준/조건을 표시한다. 이를 검증된 실측·기관 인정·다른 조건 시험·성적서 원본 제출 완료로 확대하지 않음. 원본/시험기관/시험조건 없이는 확정할 수 없는 요건만 별도 확인 필요로 두고, 미확보를 미보유/미달로 단정하지 않음.
- 기존 카탈로그 p3왼쪽·소개서 p9의 실제 후보 필드/출처를 `.venv/b5b/company-comparison-preparation-private.json`에 재사용해 **현재 자료로 다음 비교에 착수 가능한 입력**을 준비. 독립 데이터시트는 기존 파일명 목록에서 확인되지 않아 있다고 만들지 않음. 도면은 모든 제품의 비교 선행자료가 아니며, 이 공고의 도면 제출/제작 승인 조항 또는 현 자료로 설치 치수를 못 확인하는 경우에만 설명한다.
- 실무자 미팅 질문 **4개**를 실제 파일/페이지/행에 연결해 준비만 함(발송0): 카탈로그p3왼쪽/소개서p9의 제안 모델·옵션, 관리대장 성능10·55 관련 원본/소유·시료/시험조건, 카탈로그의 순유효면적·고습 차압변동을 보완할 자료, 소개서p23의 단일 계약 증빙. 원본은 다음 미팅에서 요청하며 **151행 전수 분류/성적서 확보/모든 도면 확보를 비교 착수 조건으로 요구하지 않음**. 제품·시료 추정 연결/정식 전환0. 활성 v2 프롬프트와 판정 정의는 이번에 변경하지 않았고 회사자료 비교 LLM을 호출하지 않음.

## 보존·검증·백업·실행 상태

- 작업 전 Git 제외 `.venv/b5b/before-b5b.dump`(623,927 bytes, SHA256 `30e6c310812fb25543a28c7cb798ac2e7a38467c911402ec3e6c5910373f0c9f`)에 **pg_export_snapshot과 같은 일관된 읽기 스냅샷으로 pg_dump -Fc**. `.venv/b5b/media-before.zip`(SHA256 `6d998aa4fdbb67a74e689244fa8d20fc32a37a47f9443612307d3424e3771dfc`)은 기존4파일의 CRC/내용 SHA 검증. pg_restore --list/TOC 확인, 실제 복원 시험은 미실행. .env/암호화 키를 새로 만들거나 DB 복원·migrate·초기화하지 않음.
- 백업·원문·응답·토큰은 Git 제외/대화 미출력. 복구 필요 시 운영 DB 덮어쓰기 대신 먼저 별도 격리 DB에 dump를 복원해 원본/대상 행을 대조하고, 이 작업의 새 공고/첨부/추출/로그와 기존 수동 작업을 구분해 선택적으로 복구해야 한다. 미디어 zip은 기존 경로 원본을 별도 폴더에 풀어 SHA 대조 후 사용. **B5B에서 실제 복구/삭제를 실행하지 않음**.
- 실제 public39테이블 해시 대조: 변경은 새 공고/첨부/품목/요구조건/문서/LLM로그의 **6테이블**뿐. 이6개에서도 새 대상 행을 제외한 전체 기존 행의 건수/해시가 시작과 동일. 다른33테이블·회사자료·PENDING151/UNKNOWN/세 nullable 검증값·기존 판정/수동/초안·설정/모델/키/프롬프트·.env 모두 동일. 기존 공고1 번호 불일치도 그대로. 기존media4파일/확인한 원본 SHA 보존. 새 업로드4개는 원본과 해시 일치.
- 관련 최종 회귀 **364 passed, 1 deselected**. 첫 넓은 실행의 `test_item_matched_product_by_manager`는 기존 `company_data` 가상 원본 폴더 누락으로 setup error(당시353 passed/1 error). 이 비관련 검사는 명시적으로 제외하고 이유를 보존했으며 가상 자료 복원/테스트 삭제/일괄 skip/전체 통과 선언 안 함. 새 합성17검사는 추출 전용 경로/기본 동작 보존·판정 연쇄 금지·원본 PDF/JSON복구·입력 누락/렌더링 한도·출처/페이지/placeholder·정규화·기존 수동/판정/초안 보호 검사. 테스트 외부 socket 접속0, FakeProvider 사용이며 실제 API 결과와 구분.
- 변경 Python4개 ruff check/format, Django check 문제0, makemigrations --check --dry-run 변경0, git diff --check 통과. check/migration 검사는 DB/네트워크 차단. 실제 공고 재추출/추가 유료 검증 없음.
- 실제 서버 상태 API200(llm_configured=true), ID2 상세/품목/요구조건200(4첨부/2품목/37요구조건·fit null), ID1/관리대장151/활성v2 조회200. 반복 GET 후 새 LLM/Job/판정 없음. source/보호 검사 반영과 마지막 렌더링 입력 한도 검사 반영 때 **Django만 총2차례 재기동**, 기존 cwd/venv/.env/localhost:8000/--noreload 유지. 최종 launcher **4128**, listener **22936**. PostgreSQL **21016/5432**, 프런트 **15088/5173**는 재시작하지 않고 유지. `server-final-start.json`, `http-verification-final.json`, `final-exit-check.json`에 종료 확인 기록; 최종 반복 GET 후39테이블 전체가 보존 검사 시점과 동일. 상시 워커 없음.
- 증거는 `.venv/b5b/`: `backup-verification.json`, `source-manifest.json`, `registration.json`, `execution-plan-before-call.json`, `attempt-1-started.json`, `attempt-1-result.json`, **`actual-call-receipt.json`**, `regressions-final-complete.log`, `check.log`, `migration-check.log`, `http-verification.json`, `preservation-verification.json`, `server-*.json`/서버 로그. 초기 HTTP hook이 SDK의 httpx2 대신 httpx를 감싸 0으로 적힌 원시 계수는 **확정 요청 수가 아님**. 설치된 SDK 경로/INFO httpx2의 200 한 건·SDK 재시도 로그0·generate 한 번·실제 로그/usage를 교차 대조한 `actual-call-receipt.json`의 **HTTP1/SDK0/JSON0**으로 정정 확정. 추가 호출로 계수를 확인하지 않음.

## 다음 시작점

- ID2는 실제 추출 성공·원문 일부 대조 상태이며 **회사 판정·적합도·초안은 미실행**. 일반 API의 ‘추출’은 기존 전체 연쇄 기본값이므로 완료 공고를 무심코 다시 실행하지 않는다. 원문 대조22묶음의 미해결 부분(기관/온도/단위/OR·예외·시점·시험조건/대상/정규화)을 사람이 확인·보완한 뒤, 현재 카탈로그의 항목별 근거로 다음 회사자료 비교에 착수할 수 있다. 원본 성적서는 해당 요건에 한해 후속 미팅 질문으로 병행한다.
- `backend/docs/bid-extraction-only.md`에 명령/격리 범위·PDF/출처 처리·다음 회사자료 근거 범위 정리. 완전한 자료 개정/stale 추적은 여전히 미구현이며 `company-data-revision-plan.md`의 입력 식별·수동 보존 계약을 따른다. 직원 최종 결정 자동화·제품/시료 연결·일괄 자료 분석으로 확장하지 않고 B5B에서 멈춤.

---

# 이전 B5A 인수인계 (당시 관찰 기록)

- 상태: **B5A 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 저장 정책/활성 프롬프트 정합성 수정·검증과 시연 입력 준비 상태 확인까지. 실제 분석·추출·판정·초안·워커·제품 생성/연결·정식 전환·자료 적재·유료 LLM·연결 테스트 재실행 **0회**. 테스트의 합성 판정/가짜 응답은 실제 업무 분석과 구분한다.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 깨끗한 `bfacaaf`에서 시작, B4B `5156670`과 서버 재개 이력 보존. 완료 커밋은 **이 기록을 포함한 HEAD** — `fix(backend): align stored evaluation policy and verify B5A readiness` (`git log -1 --oneline`). 변경은 backend/**와 이 파일뿐. 프런트·다른 worktree·팀 노션·기업 원본·루트 공통 문서 변경, push/초기화 없음.

## 실제 적용 정책·활성 버전

- 저장 `AppSetting:evaluation.verdict_definitions` **한 키만** 갱신. MET=비교 가능한 조건의 유효한 직접 근거, NEEDS_SUPPLEMENT=비교 가능한 실제 자료/명시적 사실로 확인된 미달·부족, NEEDS_CONFIRMATION=미등록/미매칭/원본·조건·기간 정보 부족. DB 부재를 회사 미보유로 단정하지 않고 실제 미달을 미상으로 일괄 낮추지도 않는다.
- 새 기본 정책은 `apps/core/evaluation_policy.py` 한 곳에서 관리하고 기존 AppSetting/프롬프트 기본값이 공유. 시스템 프롬프트에 카탈로그·소개서·매칭 후보·PENDING 행의 직접 근거 격상 금지, 단위/표준·판본/시험조건·대상/기준일 비교, 인용·ID·페이지·시트·셀 생성 금지, 미확인 위치 처리, 초안의 저장/수동 판정 보존 원칙을 반영.
- **실제 활성 9개 모두 v2**: `document.classify`, `document.extract_metadata`, `bid.extract`, `bid.fit_score`, `evaluation.judge`, `draft.compliance_matrix`, `draft.checklist`, `draft.technical_query`, `draft.report_summary`. 기존 v1 9개는 본문·작업 템플릿·스키마·메모·작성자·타임스탬프 그대로 보존하고 활성 플래그만 해제. 새 v2는 공통 시스템 정책과 새 버전 메모만 변경, 작업 텍스트/스키마/메타데이터는 복제 보존. 기존 판정·수동 작업·초안을 재계산하지 않음.
- 적용 도구 `apps/llm/management/commands/align_evaluation_policy.py`: 기본은 읽기 전용 계획, `--apply --backup <새 .venv JSON>`일 때만 관련 행 잠금→배타적 백업 생성→트랜잭션 내 한 키 변경/새 버전 활성화. 알려진 옛 정책/공통 시스템만 자동 변경하며 수동 판정 정의·시스템/작업 텍스트·활성 누락은 검토 없이 덮어쓰지 않고 중단. 기존 백업 덮어쓰기 금지, 재실행은 변경 0건. 일반 seed도 v1 내용을 덮어쓰지 않고 새 버전 생성, 수동/비활성 프롬프트 보존으로 수정. 개발 DB에 seed/migrate를 실행하지 않음.
- `evaluation/evidence.py`와 인증 근거의 **고정 page=1·요약값을 인용문처럼 만드는 처리 제거**. 구조화 자료의 원본 위치·인용은 page=0/quote=""(미확인)이며 제품 label도 등록 요약으로 표시. API 필드 형태는 유지. 요구사항의 실제 첨부/위치가 있으면 내부 요청 payload의 `source`로 전달한다. 기존 저장 근거는 소급 수정하지 않음.
- 실제 저장 연결 상태: **ANTHROPIC / Claude Sonnet 5.5 (`claude-sonnet-5-5`)**, 키 존재·활성화·기존 연결 성공 기록 확인. 키 복호화/출력/재등록/검증 호출 없음. provider/model/파라미터 테이블 해시와 .env가 시작 시점과 동일. temperature0.2, 기본8192/timeout180/retries2 및 기존 작업별 override(판정/추출/초안32000 등), AUTO·use_llm=true·자동 추출후 판정=true·auto_apply_company=false·run_inline=false를 **변경하지 않음**.

## 검증 결과와 보존 대조

- **339 passed**: `apps/llm apps/core apps/accounts`, B4B missing_evidence/grades, B1 preview, B2 staging/service, B3A 조회 API, 초기 회사 적재 차단 2검사. 별도 `test_filtech_b2a`에서 `.venv/b2a/run_tests.py` 사용. 외부 Python socket 접속 시도 **0**, SDK/FakeProvider 대체. 신규 회귀는 삼분류 의미→저장 정책→실제 `_judge`/run_task 요청, 백업/원자적 롤백/멱등/수동 이력, 새 버전 번호, GET 무부작용, 최신 정식 입력 재조회/대기 제외, 합성 수동 판정 재실행 보존을 검사. 실제 공고 정확도·전체 pytest·브라우저 검증으로 표현하지 않음. 기존 company_data 원본 누락/WeasyPrint 문제는 복구·skip하지 않음.
- Django check 문제0, makemigrations --check --dry-run 변경0(둘 다 DB/네트워크 차단); 변경 Python10개 ruff check/format 및 git diff --check 통과. 모델/마이그레이션 변경 없음.
- **저장값 재조회와 실제 요청 구성 확인**: 정식 Company/Product/TestReport/Certificate/DeliveryRecord → `EvaluationContext.for_bid` → `_requirement_payload`/규칙 → `_judge`의 저장 AppSetting → `services.run_task`의 활성 PromptTemplate·task_config(override 포함) → LLMRequest 경로를 대조. 실제 개발 DB에서는 합성 빈 입력으로 9개 요청을 구성하고 전송 직전 가짜 provider에서 중단. READ ONLY 연결·SDK 생성/키 복호화/로그 쓰기 차단하에 v2 정책·Sonnet5.5·기존 파라미터를 확인. 실제 회사 판정 함수는 실행하지 않음. **개발 LLMCallLog 0→0, 실제 LLM/연결 테스트 0회**.
- 개발 DB public **39개 테이블**의 건수/전체 내용 해시 대조. 자체 변경은 core_appsetting 한 키와 llm_prompttemplate 새9버전/구9활성 해제뿐. 다른 AppSetting은 이전 한 행을 SQL 읽기에서만 재구성한 전체 테이블 해시로 동일 확인; 구9버전은 필드별로 대조. 회사1, 정식 Product/TestReport/Certificate/DeliveryRecord0, 대기 version1/151행(PENDING·UNKNOWN/UNKNOWN·세 검증값 null), 공고1/첨부4/문서4, 판정/이력/초안0, Job·LLM 로그 보존. media4와 .env, 확인한 원본19개 SHA 동일.
- 단, 작업 중 별도 웹앱 클라이언트의 **20:34:28 정상 로그인, 20:35:33 PATCH /api/metadata-schemas/1**가 기존 서버 로그에 관찰됨. accounts_user·token_blacklist_outstandingtoken·documents_metadataschema 해시도 달라졌으므로 정책 외 모든 DB가 작업 내내 불변이었다고 주장하지 않는다. 이 수동/인증 변경은 **그대로 보존**, 복구/초기화하지 않음. 그 외34테이블 동일. B5A 자체 HTTP 검사는 기존 관리자 읽기와 메모리 내 단기 access JWT를 사용해 로그인/refresh/token 행을 추가하지 않음(토큰 저장/출력 없음).

## 서버 유지와 로컬 백업·복구

- 소스 기본 정책/근거 처리 반영을 위해 소유 프로세스·실행 경로를 확인한 뒤 **Django만 한 차례** 교체. 기존 localhost:8000/--noreload/같은 venv·cwd·.env 유지. 현재 launcher **28904**, listener **11636**, PostgreSQL **21016/5432**와 P: 매핑 유지. DB 재시작·migrate·워커 없음. 실제 상태 API200(llm_configured=true), 설정 API의 저장값=소스 기본값·활성 v2, 관리자 버전/행 조회200·PENDING151, 공고 목록200/count1. 반복 GET도 수행 후 Job/LLM/업무 데이터 동일.
- 로그/로컬 증거: `backend/.venv/b5a/`의 `regressions-verified.log`(339), `check.log`, `migration-check.log`, `runtime-request-verification.json`, `http-verification.json`, `db-before.json`, `db-after-final.json`, `preservation-verification-final.json`, `server-before.json`, `server-start.json`, `server.stdout.log`, `server.stderr.log`. 기존 runtime-resume 로그/DB 백업은 보존. 원문/백업/키/토큰은 Git에 포함하지 않음.
- 변경 전 관련 설정/프롬프트 백업: **`.venv/b5a/policy-before-apply.json`**, SHA256 **c4b81b4b857f8c195c48a7daeed060356d7daad49684c25794a7e530e033850a**. 한 설정 원행, 기존 활성9개 원행, 변경 계획만 포함하며 API/복호화 키·provider·model 비밀 필드는 없음. 최초 읽기 백업 `policy-before.json`도 보존. 일반 DB 전체 복원은 필요하지 않음.
- **복구가 필요할 때만** 백업 SHA와 대상 key/id를 먼저 확인하고 Django transaction.atomic에서 해당 AppSetting/프롬프트 행을 select_for_update로 잠근다. 현재 설정이 B5A 정책이고 각 활성 key가 백업 plan의 to(v2)이며 v2 내용이 B5A와 같은지 확인한다. 이후 `set_setting("evaluation.verdict_definitions", backup["setting"]["value"])` 및 백업 prompts 각 id의 `PromptTemplate.objects.get(pk=id).activate()`로 이전 버전을 재활성화한다. v1/v2 내용을 수정·삭제하지 않는다. 다른 수동 개정이 생겼으면 복구를 중단하고 개별 검토한다. 재조회/허용 범위 밖 해시 대조를 다시 수행한다. **B5A에서 복구를 실행한 것은 아님**. 코드도 예전 정책으로 맞춰야 한다면 별도 변경으로 검토하며 과거 커밋 reset/DB dump 복원은 하지 않는다.

## 시연 후보·최소 자료·다음 시작점

- 선정 후보 **20210829431-00 / [울산발전]GT #7,8 입구 공기필터(Pulse Filter)구매**. 공고 본문=폴더/파일명 번호, 구매결의번호=파일명, 사유서 건명과 규격서/품목명세서의 두 자재번호·형식·수량 대응 확인. HWP2/XLSX1 읽기 성공, 사유서 PDF1은 스캔으로 직접 판독만 완료하여 OCR/명시적 PDF 입력 필요. 원격 정정·첨부 완전성, HWP 물리 페이지, 단위 결손/순유효면적·고습 조건까지 검증 완료로 보고하지 않음. 새 공고 DB 등록/업무 추출 없음. 기존 공고1의 **20230342721 ↔ 20230323830-00 불일치는 미해결·보존**.
- 준비 기록: `backend/docs/analysis-readiness-b5a.md`. 기업 원문/모델·성적서번호/수치·실제 인용과 좌표는 Git 제외 **`.venv/b5a/pilot-readiness-private.json`**. 카탈로그 p3왼쪽·소개서 p9의 페어 후보, 직접생산p2/중소기업p1 원본, 별도 공급/정비 자격 원본, 소개서p23 실적 주장, 관리대장 **성능10·55행만** 최소 대상으로 재사용. 원본 성적서 미발견은 미보유가 아님. 대기 행·카탈로그·소개서는 정식 직접 근거로 승격하지 않음. 전체151행 검토/분류/정식 전환·모델 유사성 연결 없음.
- **사용자/기업 확인 최소 묶음:** 시연할 원통+원추 페어 확정 모델/도면과 시험 시료 대응, 해당 성적서 원본 위치(관리대장 성능10·55 중 관련 행), 순유효면적·고습 차압변동 근거, 단일 계약 실적증명 한 건. 2021 당시 재현이 목적이면 당시 자료가 별도 필요하며, 현재 설정 AUTO의 오늘 기준 재입찰 시뮬레이션과 구분한다. 사용자가 이미 연결한 키 재요청/151행 전수 분류 요구 없음.
- **다음 바로 할 수 있는 일:** 위 최소 모델/원본 대응 확인 후 해당 공고와 필요한 원본만 사람 대조/OCR 준비. 후속 승인 범위에서 최소 정식 반영/공고 등록과 실제 분석을 따로 실행한다. 현재 자동 추출후 판정=true이므로 등록·추출 경로의 자동 연쇄를 먼저 확인하고 명시적 실행 범위를 정해야 하며, 이번 단계가 후속 유료 작업 승인을 뜻하지 않는다. GET/새로고침에 유료 실행을 추가하지 않음.
- **최신 회사자료 경로:** `EvaluationContext.for_bid`는 매 실행 시 Company.load/활성 Product/정식 TestReport/Certificate/DeliveryRecord를 재조회하며 대기 행을 읽지 않는다. matching.match_items/update_fit도 새 컨텍스트/승인 입력으로 다시 확인해야 한다. 이전 ctx 재사용·새 사양 옆에 옛 판정/초안을 섞어 최신처럼 표시하면 안 된다. 실행 중 입력 변경을 막는 불변 스냅샷/전체 트랜잭션 보장은 아직 없음.
- **기존 결과의 오래됨/수동 보존:** `backend/docs/company-data-revision-plan.md`의 자료 개정·입력 스냅샷·stale 표시·파생 결과 개정 일치는 **미구현**. 현재 UI/DB가 자동으로 최신/오래됨을 구분한다고 보고하지 않는다. 다음 실제 분석 전후에는 공고/첨부·정식 회사자료·제품 선택·기준일·규칙 소스 SHA·설정/활성 프롬프트 해시/버전과 실행시각을 비밀값 없는 로컬 실행 목록으로 고정·대조하고, 일치 여부 불명인 기존 결과는 재확인 필요로 취급한다. `evaluate_bid(keep_modified=True)`의 수동 행/이력 보존은 합성 재실행으로 확인했으며 다음 실제 단계에서는 수동 제품 선택·판정/답변/근거·초안의 ID/해시를 별도 저장해 전후 동일·자동 결과 분리·실패 시 기존 결과 보존을 검증한다. 전체 개정 시스템은 이번에 구현하지 않았다.

---

# 이전 B4B 인수인계 (당시 관찰 기록)

- 상태: **B4B 완료, 추가 요청에 따라 기존 개발 DB/서버 재개 완료** (2026-10-22, Asia/Seoul). 새 기능 작업은 중단하고 서버는 유지. 실제 공고 판정·정답셋/정확도 검증·DB 적재/설정 변경·제품 연결·LLM 호출 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B4A `4399dd3` 이후 깨끗한 상태에서 시작. **B4B 완료 커밋 `5156670`** — `fix(backend): distinguish missing evidence from confirmed shortfalls` 보존. 재개 요청 시 미커밋 파일 없음. 아래 재개 기록은 이 인수인계 파일에만 추가하며 B4B 소스를 되돌리거나 변경하지 않음.
- 변경: `backend/apps/evaluation/rules.py`, `tests/{test_missing_evidence_rules.py,test_rules.py,test_qualification_rules.py}`(evaluation 아래), `backend/docs/{evaluation-rule-policy.md,company-data-revision-plan.md}`, 이 파일. 모델·마이그레이션·매핑·API/권한·프런트·루트 공통 문서·다른 worktree·원본 변경 없음.

## 추가 요청 — 기존 개발 실행 재개 (2026-10-22)

- `backend-runtime-resume.md`에 따라 꺼져 있던 기존 실행 환경만 재개. 복구 직전 5432/8000 리스너와 PostgreSQL 프로세스가 없음을 재확인. **P:가 비어 있을 때만** Unicode 경로 대조 후 이 backend의 `.venv`로 매핑. 다른 매핑 덮어쓰기 없음. 기존 `.venv/pgdata`와 `.venv/postgresql-runtime/pgsql` 재사용, initdb·재설치·DB 생성/삭제/복원·flush·migrate·자료 적재 없음.
- PostgreSQL은 기존 비정상 종료에 대한 자체 WAL 복구 후 정상 기동. 현재 **127.0.0.1:5432, PID21016**, 명령의 데이터 경로 **P:/pgdata** 확인. 실제 접속은 기존 **filtech DB/filtech 역할**, PostgreSQL18.6. 읽기 전용으로 확인한 적용 migration44개·미적용 계획0·이력 일관성 정상. 클러스터 초기화/수동 복구/권한 부여 없음.
- Django는 이 backend 실제 작업 경로에서 기존 `.venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload`로 **숨김 백그라운드** 기동. 시작 PID **16476**, 8000 리스너 **29588**, 두 프로세스의 실제 cwd·실행 파일/명령 확인. 기존 .env·키·관리자 계정 유지. **새 기동 프로세스에는 B4B `5156670` 코드가 반영됨**(소스 SHA 동일); 실제 판정 실행으로 동작을 재검증한 것은 아님. 기존 저장 결과는 재계산/갱신하지 않음.
- 실제 HTTP: **GET /api/system/status 200**, llm_configured=false/active_provider=null. 기존 관리자 정상 로그인/내정보200, 익명 대기 API401, 인증된 버전 목록/상세·행 목록/상세200. 버전 **1개/id1**, **151행(성능127·재질24), PENDING151**, 기본 페이지20행. 한 행 상세 payload와 DB 저장 원문 일치, 관계형 원본 대조 null 유지. 원문·토큰·암호/키 출력 없음. 공고 목록200/count1.
- 정상 로그인 전 public **39개 테이블의 건수·전체 내용 해시는 B4A 최종 대조와 모두 동일**. 조회/로그인 이후 변화는 `accounts_user.last_login`과 `token_blacklist_outstandingtoken` 인증 기록뿐. 회사/제품/정식 자료·대기 payload/검토 상태/updated_at·공고1·첨부4·문서4 보존. media4개·.env·B4B 소스 SHA 동일, LLM 로그0. 공고번호 불일치·첨부 조합 수정, 워커/판정/LLM/초안 실행 없음.
- 현재 로그/검증 자료는 Git 제외 **`backend/.venv/runtime-resume-20261022/`**: `postgres.log`, `pg-start.stdout.log`, `pg-start.stderr.log`, `server.stdout.log`, `server.stderr.log`, `before-start.json`, `database-verification.json`, `db-before-http.json`, `db-after-http.json`, `http-verification.json`, `processes.json`, `django-working-directories.json` 및 로컬 읽기 전용 검증 도구. 기존 로그/백업 덮어쓰기 없음.
- 재개 명령은 backend에서 P: 대상/포트/프로세스를 확인하고 꺼져 있을 때만 `P:/postgresql-runtime/pgsql/bin/pg_ctl.exe -D P:/pgdata -l P:/<새 Git 제외 로그> -w start`, `.venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload`. 백그라운드는 `Start-Process -WindowStyle Hidden`, WorkingDirectory는 이 backend. **이미 정상 실행 중이면 재시작/중복 실행하지 않는다. P:와 현재 서버를 유지한다.**
- B4B 검증 당시의 개발 DB/저장 설정 미조회 기록은 아래에 당시 사실로 보존. 이번 재개에서는 연결·migration 계획·상태/관리대장 조회만 확인했으며 저장 정책/활성 프롬프트의 정의 조정이나 실제 재분석으로 범위를 확대하지 않음.

## 변경한 의미와 보존한 분기

- 인증 종류가 미등록이면 회사 미보유/신규 취득을 단정하지 않고 **NEEDS_CONFIRMATION + 원본/내부 등록 확인**. SME null과 true+유효기간 미상도 확인 필요이며 필수 자료 HIGH 위험 유지. SME false·실제 인증 만료는 NEEDS_SUPPLEMENT, 알려진 유효 인증의 MET 유지.
- 시험규격은 품목이 있으면 선택 제품의 성적서만 사용. 미매칭이면 확인 필요이며 회사 전체/타 제품 자료를 빌리지 않음. 회사 공통 요구는 회사 범위 조회 유지. 같은 family 미등록도 원본/등록 확인부터 안내하며 시험 의뢰를 확정하지 않음.
- 발행일 미상은 연령 제한 유무와 무관하게 확인 필요. 알려진 모든 자료가 제한을 초과하면 보완 필요 유지. 날짜 미상 후보를 오래된 것으로 삭제하지 않음. 날짜/기관 조건을 통과하는 후보가 있으면 그 후보만 근거로 선택.
- 명시 기관 정보의 빈값/미확인/지원하지 않는 조건과 명시적 비공인·미인정을 구분. KOLAS 요구에 일반 공인 표기만 있으면 미확인. 실제 기관 부정은 보완 필요 유지. 제한된 문자열 구분이며 기관의 인정서/시험 범위 전체 체계는 아님.
- 제출 성적서/실적이 없으면 미보유를 단정하지 않음. 일부 후보가 있어도 품목·기간·원본·금액·시점 전체의 제출 적합성은 확인 필요로 남기고 후보 근거를 제공. 품목별 제출 후보도 선택 제품으로 제한. 인증서와 회사 작성 서류의 기존 충족 분기는 유지. 실적 수치 규칙 전체를 재작성하지 않음.
- 난연 자료 미등록/제품 미매칭은 확인 필요와 원본 등록 확인. 공식 Listing 요구에 명시적 비공식 자료만 있는 보완 필요, 기존 공식/허용된 준용 시험의 충족 분기 유지. 모든 결과를 확인 필요로 바꾸지 않음.
- RuleResult/API verdict 문자열·기존 권한·수동 수정/복원 계약 유지. 공식인증 Boolean 기본 true/준용 문구 추론, 인증 시작일/복수 기간/예외, 시험 판본·여재/완제품·고정 page=1 및 나머지 치수/등급/효율/차압/실적 규칙은 남은 범위. 이번에 업무 숫자·허용오차를 새로 하드코딩하거나 기존 값을 임의 변경하지 않음.

## 자동 검사와 실행 환경

- 신규 검사부터 작성: 수정 전 **29 failed / 16 passed**, 수정 후 최초 45 passed. 추가 경계(설정 연령 제한·다른 규격·폐지규격 날짜·제품별 실적 후보)를 포함한 **최종 신규 50 passed**. 합성 unsaved 객체를 사용하며 DB 접근 허용 표식 없음, Company.load/컨텍스트 DB 로드 금지, 설정은 명시적 테스트 대체. 기업 원문/가상 문서 fixture 사용 없음.
- 관련 B3A/B2B/B2A/B1·단위·등급·accounts·설정·기존 회사자료 API/적재 차단 회귀 묶음 **230 passed (9.37s, 당시 신규45 포함)**. 이후 추가한 5경계를 포함해 신규50 재확인(0.21s). 중복 제외 검사 항목은 235개이며 전체 pytest 통과라는 뜻이 아님. 변경된 옛 fixture 기반 규칙 검사 두 파일의 기대 의미는 갱신했지만 해당 가상 문서 경로는 실행/복원하지 않음. 기존 원본 누락 실패 8개·WeasyPrint 문제 미해결, 일괄 skip/삭제 없음.
- 시작 시 개발 **5432/8000 리스너 없음**, 개발 DB 읽기 전용 접속은 시간 초과. 기존 개발 DB/서버를 기동·재시작하지 않음. 별도 테스트는 기존 PostgreSQL 18.6 바이너리로 **`backend/.venv/b4b/pg-test` / 127.0.0.1:15432 / test_filtech_b4b**만 사용. 실제 .env는 바꾸지 않고 로컬 테스트 설정에서 endpoint를 고정·검사. pytest가 test_ DB를 제거한 뒤 잔존 테스트 DB 없음 확인, 임시 서버 PID13800만 경로/포트 확인 후 종료.
- 외부 Python socket 접속 시도 0회(격리된 로컬 PostgreSQL libpq 제외). `check` 문제0, `makemigrations --check --dry-run` 변경 없음은 기존 dummy DB/접속 차단 runner로 검증. 변경 Python4개 ruff·format, `git diff --check` 통과.
- 명령/로그: `backend/.venv/b4b/run_tests.py`로 신규 규칙/등급 및 B3A/B2/B1·accounts·core 설정·선택 회사 API/초기 적재 차단 테스트 실행. `tests-before.log`, `tests-after.log`, `regressions.log`, `tests-final-unit.log`, `check.log`, `migration-check.log`를 Git 제외 보관. 기존 개발 DB를 test DB로 재사용/flush하지 않았고 회사자료 fixture 19개를 복원·적재하지 않음.

## 실제 자료·정책 차이와 다음 필수 작업

- 기존 개발 DB가 꺼져 있어 행 건수/논리 내용 해시의 최신 SQL 대조와 현재 저장 AppSetting/활성 PromptTemplate 조회는 **미확인**. 이를 테스트 DB 결과로 대신하지 않음. 개발 pgdata **1,564개 파일**, media **4개**, .env, B4A 공고번호 불일치 기록의 SHA는 작업 전후 동일(`offline-preservation.json`). 기존 검토 대기/공고/첨부 대상에 쓰기·제품 연결·판정 저장·재분석을 하지 않음.
- **B4B 자동 검사 종료 당시에는 새 규칙이 테스트/별도 프로세스에만 반영된 상태였음.** 이후 위 추가 요청으로 기존 서버를 재개하여 B4B 소스가 반영됨. 기존 저장 판정은 여전히 갱신되지 않았고 최신 결과로 간주하면 안 됨. 테스트용 Q: 매핑은 Unicode 대상 경로 대조 후 해제 완료. 개발용 경로/.env는 유지.
- `apps/core/defaults.py`와 `apps/llm/prompt_defaults.py`의 옛 판정 정의는 서로 같지만 증빙/시험규격 부족을 넓게 보완 필요로 설명하여 이번 개인 정의와 차이가 있음. 현재 저장값/프롬프트는 개발 DB 접속 불가로 확인하지 못함. 운영 seed/프롬프트/설정을 덮어쓰지 않음. 실제 LLM 검증 전 규칙·저장 판정 정의·활성 프롬프트를 개정/보존 절차와 함께 맞춰야 함.
- `backend/docs/evaluation-rule-policy.md`: 변경 전후 분기, 실제 미달/정보 미상, 기존 정책값(설정과 고정값)·근거 미확인 범위, 남은 제약, 검사/서버 미반영 기록. 설정화와 업무적 타당성 검증을 구분함.
- **다음 필수 단계 설계**는 `backend/docs/company-data-revision-plan.md`: 정식 자료 개정 식별자/분석 입력 스냅샷, 자료·코드/정책 변경 후 재분석 필요, 매칭/후보·적합도·판정·파생 초안의 재계산 범위, 수동 선택/판정/초안 보존·재확인, 검토 대기와 정식 반영 구분, GET/새로고침의 유료 분석 금지. 이번 모델/마이그레이션/API 구현은 하지 않음.
- 공고 폴더/파일명 **20230342721**과 본문 **20230323830-00** 관계는 여전히 미확인. 번호·파일명·DB/첨부 조합을 수정하지 않음. B4A 최종 상세는 `.venv/b4a/review-v2/`이며 초기 초안과 구분. 별도 범위 지정 전 실제 공고 분석/정답셋·자료 적재·제품 연결·LLM·다음 개정 추적 구현을 자동 진행하지 않고 중단.

---

# 이전 B4A 인수인계 (당시 관찰 기록)

- 상태: **B4A 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 실제 과거 공고 한 건의 근거 대조·자료 공백·필텍/멘토 질문·판정 코드 점검 후보만 정리. 판정/정답셋/정확도 검증 완료가 아님.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B3A `e8947be`의 깨끗한 작업본에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `docs(backend): review evidence and gaps for one real bid pilot` (`git log -1 --oneline`).
- 커밋 변경은 **`backend/docs/analysis-pilot-plan.md`와 이 파일만**. 기능/API/모델/마이그레이션/파서/판정 코드·프런트·루트 공통 문서·다른 worktree 수정 없음. 상세 기업 원문·모델/개별 성적서번호·성능 수치·파일 원본은 커밋하지 않음.

## 검토 범위·확인된 사실과 미확인

- 대상: 지정 폴더 **20230342721**의 공고문·규격서·품목명세서·사유서와 개발 DB **bid=1**의 첨부 네 개. **최우선 공백: 공고문 파일명 번호와 달리 본문의 입찰공고번호는 20230323830-00**(추출 L34-35, S-identity). 정정공고/오분류를 추정하지 않고 공고·첨부 조합 확정을 보류. 이하 10묶음은 지정 첨부에 대한 후보이며 특정 공고의 확정 요구조건/적격성이 아님. DB notice_no/source_ref/마감도 비어 있고 title은 첫 첨부명, DRAFT. DB sha256 공란도 보정하지 않음. 지정 원본과 업로드 media 네 개의 바이트 SHA는 동일하지만 번호 상충을 해결하지는 않음.
- 기업 루트 **117개 파일**을 목록으로 구분한 뒤 관련 소개서·카탈로그·직접생산/중소기업/공급·정비 자격 자료와 기존 관리대장 미리보기만 사용. 관련 원본 파일 **11개**. 개찰이력·다른 공고·가상 회사자료·fixture를 실제 기술 근거로 쓰지 않음.
- 요구조건 **10개 묶음의 부분집합**: 페어 형식/치수/여재, 순유효면적, 등급/규격, 평균효율/중량법, 초기차압/풍량, 고습 차압변동, 공인기관/원본·시험대상별 제출, 물품 제조 등록/직접생산, 중소기업/예외, 단일 계약 실적/제출. 수치·연산자·규격/판본·조건·예외 및 선택하지 않은 범위를 상세 JSON에 보존. 전체 요구사항 추출/적격성 확인으로 보고하지 않음.
- 관련 제품 설명과 관리대장 후보를 찾았으나 시험 판본·시험풍량·평균/초기/MPPS 항목·페어/단품·여재/완제품·소유 관계는 미확인. 소개서/카탈로그 주장을 원본 시험 결과로 보지 않으며 모델명으로 연결하지 않음. 사용 습도와 차압변동 시험, 최소 보증과 실제 측정값을 구분함.
- 제품코드 문자 일치만으로 후보를 정하지 않고 외형/구조와 조건으로 범위를 좁힘. 관련 관리대장 **네 행**의 전체 payload를 B1 보존 미리보기와 정확히 대조. 원본 관리대장 바이트 SHA도 B1과 일치. 모든 151행을 사람이 검토/분류한 것은 아님. 나머지 행은 다음 작업의 선행 검토 조건이 아님.
- 후보 개별 성적서 원본은 제공 파일명 목록·후보 번호 검색·선택 문서 검토 **확인 범위에서 파일 미발견**. 회사가 원본을 보유하지 않는다고 단정하지 않음. 관리대장 좌표는 성적서 PDF 페이지가 아니며 원본 대조 완료/당사 완제품/공인시험·공식인증 상태를 저장하지 않음.
- 현재 검토일과 과거 입찰 마감·실적 공고일 기준을 구분. 제공 소개서는 현재 연도의 자료이며 과거 소개서 변경 이력은 재현하지 않음. 별도 최신 자격 문서의 범위·기관·기간은 소개서 요약과 별개로 확인. 직접생산 문서의 현재/과거 기간 행도 분리했으며 당시 정보망 상태·유지를 재현했다고 하지 않음.
- 먼저 확인할 질문: **폴더·파일명/본문 공고번호 불일치 원인과 올바른 첨부 조합**. 이후 관련 두 후보의 원본 성적서/시료·제품 대응, 제안 페어 도면·순유효면적/고습 시험, 병기 시험표준·판본의 인정 기준, 단일 계약 한 건의 실적증명·금액·완료일, 현재/당시 자격 유지·신청 자료. 질문은 작성만 했으며 외부 발송 없음.

## 코드 점검·상세 산출물

- 우선 수정/실험 후보 **5개**: ① 미등록/미확인과 실제 부족·근거 사용 자격 구분(모델명 연결/공식인증 추론 포함), ② 표준 판본·시험대상·효율 항목의 비교 가능성, ③ 차압/풍량/습도 조건 및 실제 비교값과 인용 근거 일치, ④ 인증 시작/종료·품목 특이사항·실적 공고일 기준, ⑤ 고정 page=1 대신 실제 위치/미상 보존.
- `evaluation/{rules.py,grades.py,evidence.py,context.py}`, `company/{mapping.py,models.py}`, 관련 추출/단위 코드의 **정적 관찰**만 수행. 다른 등급 체계 비교 차단·정규화된 필수특이사항 검사는 이미 있는 보호장치로 구분. 실제 함수 호출/동작 실패 재현/수정은 하지 않음. 정확한 코드 위치·현재 구현·다음 합성 사례·기업 확인 필요 항목은 `backend/docs/analysis-pilot-plan.md`에 기록.
- Git 제외 **최종 상세는 `backend/.venv/b4a/review-v2/analysis-pilot-detail.md`**, 같은 폴더의 `review-notes.json`(10묶음 사실·공백·질문·추론, verdict 모두 null), `evidence-index.json`(**34개** 인용/셀 근거의 경로·SHA·위치), `identity-discrepancy.json`, `original-report-search.json`. 상세 실제 값·개별 성적서번호·모델 후보는 이 로컬 자료에만 보존. 기업 파일 목록은 상위 `b4a/corporate-inventory.json`.
- 보조 자료: 상위 b4a의 `selected-pdf-text.json`, 원본 HWP 저장 텍스트/추출 표, 품목 셀 JSON, 선택 PDF 페이지 PNG 및 최종 review-v2의 `verified-notice-db-correspondence.json`, `review-validation.json`, `static-code-observations.json`, `preservation-verification.json`. 기존 출력은 덮어쓰지 않음. 상위 b4a의 초안 상세는 식별 상충 반영 전 기록으로 보존했으며 최종 참조는 review-v2만 사용. .venv 전체 Git 제외 확인.

## 검증·보존과 다음 시작점

- HWP 두 개는 기존 파서 재추출과 DB 텍스트 일치. 위치는 추출 구획/행/표로 기록하고 HWP의 PAGE를 물리 페이지로 대응하지 않음. 텍스트 인용은 정확 일치 검사, 스캔 사유서·공급 등록증은 OCR 없이 렌더링 직접 판독으로 명시. 관련 PDF 페이지/표를 육안 대조하고 카탈로그 좌우 표 혼합을 피함. 원본에서 단위가 불명확한 정보는 null로 남김.
- 원본 **11개 SHA**와 기존 media **4개 SHA** 종료 대조 동일. DB 시작/종료는 각각 `default_transaction_read_only=on` + `REPEATABLE READ, READ ONLY`로 확인. **public 39개 테이블의 건수·전체 내용/시각 해시 모두 동일**. 인증/토큰 테이블도 변화 없음. `db-before.json`/`db-after.json`에는 테이블 건수·해시만 보존.
- 버전1개/대기151행·payload·검토/미확인 상태·updated_at 보존. Company1, Product/TestReport/Certificate/DeliveryRecord0, 공고1·첨부4·문서4, LLM 로그0 보존. 정식 자료 0을 회사의 실제 제품/성적서 미보유로 해석하지 않음.
- 기존 8000 리스너 **5048**, PostgreSQL 5432 **5332** 시작/종료 동일. 서버/DB 재시작·워커·로그인/토큰 발급·API 분석 호출 없음. Company.load/평가 컨텍스트·매핑/적재·초안/LLM 서비스는 호출하지 않음. DB 쓰기·제품 연결·분류/검토 저장·원본 파일 수정 없음.
- 문서 검토 단계이므로 pytest·의미 없는 단위 테스트·기존 전체 테스트를 반복하지 않음. 원문 인용·위치·후보 payload·해시/보존 및 코드 관찰 anchor를 확인하고 `git diff --check` 통과. 기존 B3A 테스트 결과는 아래 당시 기록이며 B4A 판정 정확도 측정으로 사용하지 않음.
- 다음은 **공고번호·첨부 조합부터 확인하고 별도 범위 지정 후** 위 코드 우선순위와 최소 자료로 수정/합성 사례 설계 또는 관리자 검토 화면 연계를 진행. 이후 두 후보의 원본/제품 대응과 핵심 조건을 확인하며 전체 151행 검토·자동 연결·판정 실행을 자동 진행하지 않는다. 현재 상세 대조는 사람 검토 전 후보 상태로 보존하고 중단.

---

# 이전 B3A 인수인계 (당시 관찰 기록)

- 상태: **B3A 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 관리자 전용 검토 대기 조회 API만 구현·검증. 제품 연결·정식 전환·검토 수정·판정·LLM 호출·프런트 수정 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B2B `6b73be5`의 깨끗한 작업본에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `feat(backend): add admin-only report register read APIs` (`git log -1 --oneline`).
- 변경: `backend/apps/company/report_register_api.py`, `backend/apps/company/urls.py`, `backend/apps/company/tests/test_report_register_api.py`, `backend/docs/report-register-api.md`, 이 파일만. 모델·마이그레이션·기존 API 구현·파서·적재/매핑/평가 서비스·환경 설정 변경 없음.

## 실제 경로와 UI 연결 계약

- `GET /api/report-register-versions`, `GET /api/report-register-versions/{id}`: 파일 버전과 현재 DB 행 수, 상세의 시트별/검토상태별 집계. 저장 당시 metadata 집계와 구분하며 source_metadata/서버 경로/백업 위치를 응답하지 않음.
- `GET /api/report-register-rows`, `GET /api/report-register-rows/{id}`: 출처·6개 실제 value 요약·관계형 review·경고 수/코드·시각. 전체 원본 payload는 상세에만 변형 없이 반환. 최상위 미확인 Boolean null과 payload.review의 false를 별개로 보존.
- 기존 `IsAdminRole`, GET/HEAD/OPTIONS만 허용. 익명 401, 담당자 403, 관리자 쓰기 405. 기존 인증·LLM 게이트는 변경하지 않음.
- 행 필터: file_version/sheet_name/review_status/ownership/test_target. q는 번호/모델/시료명/규격/기관의 `fields.*.value`만 부분 검색. 없는 키·null 안전, 셀/수식/경고/원문 전체 검색 없음. 잘못된 필터 400, 없는 상세/페이지 404, 빈 결과 200/count=0.
- 기존 count/next/previous/results 페이지네이션, 기본 20·최대 200. 버전 id순, 행 file_version_id/sheet_name/row_number/id순. DB JSON 투영·count/limit/offset 사용, 전체 payload 목록 로딩·N+1·새 인덱스/캐시 없음.
- 응답 필드/타입·합성 예시·빈값·오류·PDF와 관리대장 셀 출처의 차이는 **`backend/docs/report-register-api.md`** 참조. 다음 별도 범위는 관리자 검토 대기 화면을 이 네 경로에 연결하는 것. 화면 구현/연결은 아직 하지 않음. 다른 worktree/채팅 수정·메시지 없음.

## 검사 결과와 실행 방법

- 신규 API 테스트 **33개**, B1/B2A/B2B·단위·accounts 권한·기존 회사자료 API/초기 적재 차단 회귀 포함 **164 passed (4.51s)**. 별도 `test_filtech_b2a` PostgreSQL에서 최소 합성 자료로 실행 후 테스트 DB 제거. 실제 개발 DB에 테스트 입력/계정 생성·flush 없음. Python 외부 socket 시도 0회(로컬 PostgreSQL libpq 제외).
- 익명/담당자/관리자 권한, 네 경로의 HEAD/OPTIONS·쓰기 거절, 집계·20/7 페이지·최대 크기·고정 순서, 중복 번호 유지, null/없는 모델, 실제 value만 검색, 필터/400/404, payload.review와 관계형 값의 분리 확인. 목록 SQL은 count+페이지 **2쿼리**, full payload 미선택. 조회 전후 대기/정식/판정 자료 불변과 기존 정식 API의 대기 자료 미노출 검증.
- 명령은 기존 `.venv/b2a/run_tests.py`에 `apps/company/tests/test_report_register_api.py`, `test_report_staging_service.py`, `test_report_register_staging.py`, `test_report_preview.py`, `apps/core/tests/test_units.py`, `apps/accounts` 및 선택한 기존 회사자료/적재 차단 테스트를 전달. 전체 출력: `backend/.venv/b3a/tests.log`.
- `check` 문제 0개, `makemigrations --check --dry-run` 변경 없음(기존 접속 차단 runner). 변경 Python 3개 ruff/format 및 `git diff --check` 통과. 기존 자료 누락 실패 8개·WeasyPrint DLL 문제는 해결/전체 테스트 통과로 처리하지 않음.

## 서버 반영·실제 조회·자료 보존

- 기존 --noreload 서버의 포트·실행 명령·부모 실행 파일·두 프로세스의 실제 작업 경로를 대조한 뒤 **현재 backend Django만 한 번 재시작**. 이전 시작 PID 13608/리스너 24964 → 현재 시작 **24552**/8000 리스너 **5048**. PostgreSQL **5332**(5432)는 그대로이며 UI/워커/다른 프로세스 종료·시작 없음.
- 기동 명령: backend 작업 경로에서 `.venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload`. 기존 .env·DB·인증 키·옵션 유지, `Start-Process -WindowStyle Hidden` 사용. 새 stdout/stderr: `backend/.venv/b3a/server.stdout.log`, `server.stderr.log`. 중복 서버 없음.
- 실제 HTTP: 상태 200(llm_configured=false), 관리자 로그인/내 정보 200, 네 조회 경로 200. 버전 **id=1/151행**, **성능127·재질24**, PENDING151 확인. 첫/다음 각20행·페이지 재조회 일치/중복 없음, 상세 payload와 DB 원문 일치, 모델 없는 재질 상세 null·시트 필터24행, 잘못된 필터400·없는 상세404·빈 결과200 확인. 원문/번호 목록·토큰은 출력/커밋하지 않음.
- 실제 담당자 계정은 없어 임의 생성하지 않음. 담당자 거절은 격리 테스트 검증 결과임. 새 경로 익명401도 실제 HTTP로 확인.
- 조회 전후 public **39개 테이블**의 건수/전체 내용 해시를 대조. 정상 로그인으로 `accounts_user.last_login` 및 `token_blacklist_outstandingtoken`만 변화. 나머지 37개 테이블의 payload·검토 상태·updated_at 포함 내용 해시 동일. 버전1개/대기151행의 PENDING/UNKNOWN/UNKNOWN·미확인 플래그 null 유지.
- 기존 Company1, Product/TestReport/Certificate/DeliveryRecord0, 공고1·첨부4·문서4·LLM 로그0 보존. 기존 공고 목록과 정식 자료 네 목록도 HTTP200 확인. 기존 media **4개 파일 해시 동일**. 자료 재적재·migration 적용·원본 엑셀 재파싱·Company.load/get_or_create·평가/LLM 실행 없음.
- Git 제외 검증 자료: `backend/.venv/b3a/` 아래 테스트 로그, `before-http.json`/`after-http.json`(테이블 건수/해시만), `media-before.json`, `live-verification.json`, `restart.json`, 재기동 전후 작업 경로 확인 자료와 로컬 검증 도구. 기존 B2B 백업은 보존. 루트 공통 문서 동기화가 필요하면 후속 조정하며 이번 수정 범위 밖 파일은 손대지 않음.
- 소유/여재·완제품 분류 확정, 검토 수정/이력, 제품 연결, 정식 전환, 원본 PDF 검증, LLM 및 다음 단계 자동 진행은 하지 않음. 다음 요청을 기다림.

---

# 이전 B2B 인수인계 (당시 관찰 기록)

- 상태: **B2B 완료, 여기서 중단** (2026-10-22, Asia/Seoul). 개발 DB 백업·B2A migration 적용·실제 관리대장 한 버전의 검토 대기 적재/재실행 검증 완료. 제품 연결·정식 성적서 전환·판정·LLM·새 API·프런트 수정 없음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B2A `ba437ef` 이후 깨끗한 상태에서 시작. 완료 커밋은 이 기록을 포함한 `HEAD` — `feat(backend): stage report register rows with atomic idempotent import` (`git log -1 --oneline`).
- 변경: `backend/apps/company/{report_preview.py,report_staging.py,management/commands/stage_filtech_reports.py,tests/test_report_staging_service.py}`, `backend/docs/report-register-staging.md`, 이 파일. 기존 모델/마이그레이션 파일·API/평가/매핑 코드는 변경하지 않음.

## 실제 DB와 저장 결과

- 대상 확인: **127.0.0.1:5432/filtech**, 역할 filtech, PostgreSQL 18.6. 적용 전 이력 43개·테이블 37개. 미적용 계획은 `company.0002_report_register_staging`의 CreateModel 두 개뿐임을 코드/`migrate --plan`으로 확인.
- 복구용 custom-format pg_dump: `backend/.venv/b2b/filtech-before-b2b-20261022-075035-194448.dump` (**190,674바이트**). SHA256 `02f4b109ce1a03b1fcd26f912cc7e0c05b424f18e29e16e7c0e9153bef4a65fb`. 자격 증명은 기존 설정→자식 프로세스 환경으로만 전달. 기존 백업 덮어쓰기 없음.
- `pg_restore --list` 성공 및 공고 TABLE DATA 목록 확인. 같은 이름의 `.list`, `backup-manifest.json` 보관. **실제 복원 시험은 하지 않음**. DB 삭제/복원/재초기화/flush 없음.
- 백업 검증 후 `manage.py migrate company 0002_report_register_staging --noinput` 적용 성공. 이후 `migrate --plan` 미적용 작업 없음. 기존 테이블에서 변경된 것은 migration 이력/content type/permission 등록 3종뿐이며 데이터 테이블 해시는 유지됨. 현재 public 테이블 39개.
- 실제 파일 SHA256: `0257bb970c4198796baae08fa6b2b6dc4bdc5750e530096e7d9a728443009afe`. B1 값과 실행 전후 동일. 실제 입력 경로는 아래 B1 기록 참조. 원본 파일 수정 없음.
- 실제 dry-run → 성능 **127행**, 재질 **24시료 행**, 총 **151행** 확인 후 apply. 저장된 **ReportRegisterVersion ID 1**, 파일 버전 1개·원본 행 151개. payload 151개 전체를 SHA/시트/행별 B1 객체와 대조해 일치 확인.
- 151개 모두 관계형 상태 **PENDING/UNKNOWN/UNKNOWN**, `is_lab_accredited`/`is_official_certification`/`original_report_verified` 모두 **null**. B1 payload.review의 false는 원문에 보존하며 관계형 false로 복사하지 않음. 이 수는 제품 수/원본 PDF 검증 수가 아님.
- 같은 명령 재실행 → **새 버전 0·새 행 0, 기존 버전 1·151행 재사용**. 대기 테이블의 전체 내용 해시(payload·검토 상태·metadata·updated_at 포함) 동일. 실제 DB에 고의 충돌/오류 자료를 만들지 않음.
- 백업 직전부터 최종 대조까지 Company **1**, Product/TestReport/Certificate/DeliveryRecord **0**, 공고 **1**, 첨부 **4**, 문서 **4**, LLM 호출 로그 **0**의 건수와 내용 해시 보존. 기존 media **4개**의 파일 해시 동일. 검증에서 Company.load()/평가 컨텍스트를 실제 DB에 호출하지 않음.
- 기존 PostgreSQL PID **5332**, Django 시작 PID **13608**/8000 리스너 **24964** 유지. 재시작·워커 시작 없음. `GET /api/system/status` **200**, llm_configured=false. `--noreload` 서버는 이전 코드 그대로이며 별도 CLI만 새 저장 코드를 사용한다. 대기 목록 HTTP API는 없음.

## 명령·파서·충돌 정책

- `stage_filtech_reports <xlsx>` 기본은 **dry-run**. 쓰기는 `--apply --expected-sha256 <확인한 소문자 SHA256>` 필수. force/update/replace 옵션 없음. 기존 `preview_filtech_reports`는 읽기 전용 유지.
- 고정 파서 상수: **`filtech-report-register/1`**. 리더 코드에 선언하며 현재 HEAD/시각/사용자 옵션으로 만들지 않음. metadata.parser에 `report_preview.py`·`core/units.py`의 LF 정규화 SHA256과 openpyxl **3.1.5** 버전 보존. B1 반환 payload 형식/해석은 변경하지 않음.
- 전체 JSON 저장 가능성, 비어 있지 않은 source/fields, 필수 구조·셀 근거·단위/수식 구조·SHA/시트/행·유일 좌표를 쓰기 전에 검증. 전체 원본 객체를 변형 없이 보존. metadata에는 file·시트별 집계/경고·파서 지문만 저장하고 원문 행/번호 목록을 중복 저장하지 않음.
- 한 파일 전체 `transaction.atomic`, 새 버전/각 행에 `full_clean()` 실행. SHA별 PostgreSQL transaction advisory lock과 기존 버전/행 잠금으로 동시 실행 직렬화. 중간 실패/DB 제약/원본 변경 시 전체 롤백.
- 동일 SHA·파서/지문·좌표 집합·payload면 기존 자료만 재사용. 이름 변경도 동일 버전이며 표시명/시각/수동 검토 플래그를 수정하지 않음. 파서/지문·payload·좌표 집합 불일치나 일부 행만 있는 버전은 충돌로 중단하고 보충/삭제하지 않음. 다른 SHA는 일반 정책상 새 버전 가능하나 이번 실제 실행은 위 한 버전만 수행.
- 실제 실행: `& .venv/Scripts/python.exe manage.py stage_filtech_reports '<B1 실제 원본 경로>' --apply --expected-sha256 0257bb970c4198796baae08fa6b2b6dc4bdc5750e530096e7d9a728443009afe`. 실제 apply/재실행은 `.venv/b2b/run_guarded_stage.py`로 외부 socket·LLM provider 호출을 차단한 상태에서 수행하여 두 실행 모두 시도 0회 확인.

## 검사·로컬 자료와 다음 범위

- 신규 적재 검사 **23개**, B1/B2A·단위·B0 차단 회귀 포함 **100 passed**. 별도 `test_filtech_b2a` PostgreSQL 테스트 DB에서만 오류/충돌/동시 실행/롤백 검증 후 자동 제거. 실제 개발 DB를 pytest 대상으로 사용하거나 flush하지 않음. 최소 합성 입력만 사용.
- 기본 dry-run 무변경, 최초 적재, 재실행/검토 상태/시각 유지, 이름 변경 멱등, 동일 번호 다중 행, 구조·SHA·좌표/JSON 오류, 파서/지문/payload/부분 집합 충돌, 중간 실패 롤백, 적재 중 원본 변경, B1 합성 workbook 왕복, 공식 자료/LLM 분리 및 동일 SHA 동시 실행을 확인.
- `check` 통과, `makemigrations --check --dry-run` 변경 없음(접속 차단 로컬 runner 사용), 적용 후 실제 `manage.py check`도 문제 0개. 변경 Python 4개 ruff·format 및 `git diff --check` 통과. 기존 자료 누락 실패 8개와 WeasyPrint 문제는 해결/전체 통과로 처리하지 않음.
- 로컬 Git 제외 자료는 `backend/.venv/b2b/`: `tests.log`, `check.log`, `migration-check.log`, `migrate-plan.log`, `migrate.log`, `migrate-plan-after.log`, `dry-run.json`, `apply.json`, `reapply.json`, `actual-verification.json`, `preservation-verification.json`, `http-status.json`, `guard-results.jsonl`, 백업/목록, 각 단계 테이블 건수/해시·media manifest. 원문 값/번호 목록·비밀값을 stdout/문서/커밋에 복사하지 않음. 백업과 상세 JSON의 Git 제외 확인.
- 다음은 별도 범위 지정 후 진행: 대기 목록 API/화면, 당사/타사·여재/완제품 검토, 동일 번호의 여러 시료 관계, 제품 연결 기준, 원본 성적서/단위/조건 확인 및 정식 성적서 구조 개편. 제품 연결·정식 전환·규격/등급 호환·고정 PDF page=1 우회 금지. 분석 정확도/원본 성적서 검증 완료로 보고하지 않음. 외부 질문 발송 없음.

---

# 이전 B2A 인수인계 (당시 관찰 기록)

- 상태: **B2A 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 저장 모델·마이그레이션 파일·테스트·설계 문서만 구현. 개발 DB 적용·실제 자료 적재·제품 연결·판정·LLM 호출·새 API 없음. B2B 자동 진행 금지.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. B1 `597ffb2` 이후 깨끗한 상태에서 시작. B0 환경·기존 데이터·서버 보존.
- 완료 커밋: `ba437ef` — `feat(backend): add isolated report register staging models`.
- 변경: `backend/apps/company/models.py`, `backend/apps/company/migrations/0002_report_register_staging.py`, `backend/apps/company/tests/test_report_register_staging.py`, `backend/docs/report-register-staging.md`, 이 파일만. 프런트·루트 공통 문서·기존 API/serializer·기존 평가/매핑 코드·B1 리더 변경 없음.

## 저장구조와 기존 엔진 분리

- `ReportRegisterVersion`: SHA256(unique, 소문자 64자리 검증/DB 제약), 최초 표시 파일명, 명시적 parser_version, source_metadata(JSON callable default=dict). 동일 SHA는 이름/경로/파서 변경만으로 두 버전이 될 수 없음. 다른 SHA의 개정본은 별도 버전으로 보존.
- `ReportRegisterRow`: 파일 버전 FK(PROTECT)·시트·행의 복합 고유키, B1 전체 payload(JSON default=dict), 검토 PENDING·소유 UNKNOWN·시험대상 UNKNOWN 기본값. 소유는 당사/타사/불명, 대상은 여재/완제품/기타/불명 구분 가능. 빈 시트와 Excel 행 범위 밖 좌표는 DB 제약으로 거절.
- 성적서번호·No.·모델명을 고유키로 사용하지 않음. 번호 공란/중복·다중 시료·병합 기준 셀·단위/변환식/조건/수식 캐시·매핑 밖 값·규격 원문은 payload에 그대로 보존. ISO 29463 자동 치환 없음.
- 공인시험(`is_lab_accredited`), 공식인증(`is_official_certification`), 원본 성적서 대조(`original_report_verified`)는 **서로 다른 nullable Boolean, 기본 null**. B1 payload의 원본 대조 false를 관계형 상태로 자동 복사하지 않음.
- Product/TestReport/Certificate FK·등록 시그널·적재/승인/승격 서비스·API·PDF 연결 없음. 기존 EvaluationContext 조회는 새 대기 모델을 읽지 않으며 분류/인증 플래그만 지정해도 승격되지 않음.
- `clean()`은 출처 SHA/시트/행 충돌과 잘못된 payload/source 객체를 거절하며 원문을 고치지 않음. 일반 ORM save/bulk_create는 full_clean을 자동 실행하지 않으므로 B2B는 별도 검증 필수. 무조건 append-only를 강제하는 이력 엔진은 만들지 않음.
- 같은 SHA를 새 파서로 재해석할 때 기존 parser_version/payload를 덮어쓰지 않고 별도 버전 표시의 Git 제외 미리보기로 남긴 뒤 DB 저장 보류. 다중 파서 실행의 동시 저장은 후속 설계. 자세한 필드·B1 대응·개정 정책은 `backend/docs/report-register-staging.md` 참조.

## 검사와 실제 DB 미적용 확인

- 새 migration `company.0002_report_register_staging`은 **CreateModel 두 개뿐**이며 기존 TestReport/규격군/Boolean 기본값/평가 규칙 변경이나 데이터 마이그레이션 없음.
- 생성 및 `check`, `makemigrations --check --dry-run`은 로컬 `.venv/b2a/offline_manage.py`로 실행. 해당 프로세스에만 dummy DB backend를 지정하고 DB 연결·Python socket 접속을 예외로 차단. 설정 파일/.env 변경 없이 실행했으며 접속 시도 **0회**. `check` 문제 0개, 마이그레이션 누락 검사 `No changes detected`.
- 신규 저장구조 **21개 테스트**: SHA/이름/파서 충돌, 좌표 중복/범위, 다른 행·시트의 동일 성적서번호, 공란 식별정보, 다른 SHA의 같은 좌표, JSON/병합/조건/단위/캐시 왕복, 독립적인 JSON 기본값, 미확인 null과 명시적 false, 보호 삭제, 잘못된 출처/FK, 평가 자료와의 분리.
- B1 미리보기·단위 유틸·B0 회사자료 차단 회귀 포함 **77 passed**. 실제 제품 fixture/기업 엑셀/상세 JSON 사용 없음. 기존 가상 회사자료 복원/적재 없음.
- 테스트는 전용 PostgreSQL **`test_filtech_b2a`**에서 새 migration과 저장을 검증한 뒤 pytest가 DB를 제거함. 모델 테스트는 접속 DB가 `test_` 이름이며 current_database()와 일치하는지도 확인. 개발 DB 재사용/flush 없음. Python 외부 socket 접속 시도 0회(로컬 PostgreSQL 테스트 연결은 libpq 사용).
- 명령: `& .venv/Scripts/python.exe .venv/b2a/run_tests.py apps/company/tests/test_report_register_staging.py apps/company/tests/test_report_preview.py apps/core/tests/test_units.py apps/documents/tests/test_documents_api.py::test_load_initial_data_endpoint apps/documents/tests/test_documents_api.py::test_company_seed_command_is_blocked --tb=short`.
- 기존 제품/정식 성적서/인증에 같은 모델명·번호가 있어도 대기 행 저장 전후 값 불변, 평가 컨텍스트에는 기존 정식 자료만 조회됨. 빈 평가 컨텍스트가 `Company.load()`로 만드는 회사 singleton은 테스트에서 구분하여 확인. 실제 판정 실행 없음.
- 개발 DB 스키마/마이그레이션 이력을 읽기 전용으로 대조: 시작/종료 모두 **43개 적용 이력·37개 public 테이블**, 새 migration 적용 이력/대기 테이블 **없음**. 개발 DB에는 `migrate`를 실행하지 않음. 병행 UI의 로그인·공고 데이터 변화는 전체 불변이라고 주장하지 않으며 손대지 않음.
- 변경 Python 3개 파일(모델/마이그레이션/테스트)의 ruff·format 검사와 `git diff --check` 통과. 기존 자료 누락 실패 8개와 WeasyPrint DLL 문제는 이번에 해결/전체 통과 처리하지 않음.
- 로컬 검사 도구/로그: `backend/.venv/b2a/{offline_manage.py,b2a_test_settings.py,run_tests.py,tests.log,check.log,migration-check.log,dev-schema-before.json,dev-schema-after.json}`. 스키마 대조 파일에는 테이블명/마이그레이션명만 저장. 전부 Git 제외이며 비밀값/기업 원문 커밋 없음.
- 기존 PostgreSQL PID **5332**(5432), Django 시작 PID **13608**/리스너 PID **24964**(8000) 유지, 재시작·워커 시작 없음. **실행 중인 --noreload 서버는 새 모델을 아직 반영하지 않음.** B2A 저장 기능이 실제 서버에서 사용 가능하다고 보고하지 않음.

## B2B 조건과 확인 질문

- **별도 요청 후** 개발 DB 적용 대상/보존 계획을 확인하고 migration 적용·서버 반영을 조정한다. 그다음 원본 SHA/파서 버전·행 건수·전체 payload/source 일치를 검증하고 멱등성/충돌 중단/transaction이 있는 전용 대기 적재 경로를 만든다. 아직 적재 명령이 없으며 기존 B1 명령은 읽기 전용 그대로임.
- 대기 자료 저장과 정식 성적서/제품 연결은 다른 단계다. 기존 TestReport 번호 고유 제약/단일 product, mapping.py의 모델명 자동 연결·공식인증 추론, evidence.py의 고정 page=1을 그대로 우회 사용하면 안 됨. 규격군/등급 호환성과 기존 Boolean 변경 영향도 후속 검토. 루트 specs/README 동기화 제안은 설계 문서에 남겼으며 이번 범위 밖 파일은 수정하지 않음.
- 필텍 확인 질문: 당사/타사·여재/완제품을 구분할 근거는 무엇인가? 같은 번호의 여러 시료는 어떤 관계인가? 모델 연결 기준은 무엇인가? 원본 성적서와 단위/시험조건을 확인할 자료는 무엇인가? 추정 답변이나 외부 질문 발송 없음.

---

# 이전 B1 인수인계 (당시 관찰 기록)

- 상태: **B1 완료, 여기서 중단** (2026-10-21, Asia/Seoul). 읽기 전용 관리대장 미리보기만 구현. B2·DB 적재·제품 연결·판정·LLM 호출은 진행하지 않음.
- 작업폴더/브랜치: `filtech-backend`, `feature/backend-foundation`. 시작 시 깨끗함. B0 `43a85d3`을 보존하고 환경 재설치·초기화 없이 진행.
- 완료 커밋: `597ffb2` — `feat(backend): add read-only Filtech report register preview`.
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
