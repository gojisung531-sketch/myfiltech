# 지정 공고 작업 복구와 개발 워커 재개

전제: API 서버는 요청/조회, 별도 워커는 대기 작업을 실행한다. `jobs.run_inline=false`에서 서버만 켜면 작업은 실행되지 않는다. 이 설정과 자동 판정 설정·키·전역 모델은 변경하지 않는다.

## 과거 대기열을 건드리지 않는 명령

backend 작업폴더에서 기존 `.venv`, `.env`, 로컬 PostgreSQL을 사용한다. **기존 `run_jobs`/`run_jobs --once`는 과거 대기열 전체를 처리하므로 이번 환경에서는 사용하지 않는다.**

```powershell
# 공고8의 이미 만들어진 Job3만 실행. 신규 추출 Job을 생성하지 않는다.
.venv/Scripts/python.exe manage.py run_bid_jobs --job-id 3 --bid-id 8 --follow --budget-ledger .venv/job3-recovery/budget-ledger.json --budget-usd 10 --prior-spend-usd 0.16715
```

위 명령은 완료/실행 중/실패 Job을 다시 실행하지 않는다. `--follow`는 root 결과에 기록된 evaluate_job_id, 같은 공고, EVALUATE_BID 유형, payload.parent_job_id가 모두 맞는 **직접 후속1건**만 실행한다. 무관한 Job, 다른 공고, 원래 대기 중이던 Job1/2를 따라가지 않는다. 실패 Job을 자동 retry하지 않는다.

원인을 확인한 첫 실패에 한해 `--job-id 4 --bid-id 8 --retry-failed`처럼 명시하면 **한 번만** 재시도한다(attempts1의 FAILED만 허용, attempts2 이후 거부). 이전 error/message·공고 오류·완료 시각을 payload.previous_attempts에 보존한다. 이번에는 응답 스트림 중단 뒤 Job4에만 사용했으며 Job3을 다시 실행하지 않았다. SDK 연결 재시도 최대2회와 JSON 복구 최대1회는 기존 설정이며 각각 HTTP 시도로 예산에 포함된다. 실패 요청을 무료로 가정하지 않는다.

향후 화면에서 새 작업을 요청할 때 사용할 워커:

```powershell
# N은 이미 확인한 작업의 최고 ID. 새 Job 중 ID>N인 공고 추출/판정만 처리.
# 이번 복구 완료 후의 실제 N/PID는 BACKEND_PROGRESS.md 상단 참조.
.venv/Scripts/python.exe manage.py run_bid_jobs --after-id N --budget-ledger .venv/job3-recovery/budget-ledger.json --budget-usd 10 --prior-spend-usd 0.16715
```

- `--after-id`는 **명시한 고정 경계**이며 시작할 때 임의로0으로 내리지 않는다. 기존 Job1/2는 계속 제외한다. 허용 유형은 EXTRACT_BID/EVALUATE_BID, target_type은 bids.BidNotice뿐이다. 필요하면 `--bid-id`를 더해 한 공고만 감시한다. `--once`를 더하면 범위 안 대기 작업만 처리하고 종료한다.
- 장기 워커는 단일 실행 스레드이며2초 간격으로 확인한다. 같은 비용 대장을 사용하는 두 프로세스는 PostgreSQL 세션 잠금으로 거부한다. `.env`의 jobs.concurrency를 바꾸지 않는다.
- PowerShell에서 백그라운드 실행할 때 `Start-Process ... -WindowStyle Hidden`과 별도 stdout/stderr 로그를 사용한다. 현재 정상 서버/워커를 먼저 확인하고 중복으로 띄우지 않는다. 재시작은 이전 정상 종료/프로세스 부재를 확인한 다음 수행한다.
- API 서버 재개는 같은 폴더에서 `.venv/Scripts/python.exe manage.py runserver localhost:8000 --noreload`. 기존 PDF 환경을 사용한다면 `WEASYPRINT_DLL_DIRECTORIES=P:/pdf-runtime/mingw64/bin`, `FONTCONFIG_FILE=P:/pdf-runtime/fonts.conf`와 P: 매핑의 가용성도 유지한다. API 서버를 재개해도 워커 프로세스는 별도로 재개해야 한다.
- Windows 로그아웃/재부팅 뒤 자동 시작하는 서비스는 추가하지 않았다. 새 Job이 PENDING에 머무르면 해당 워커 PID/명령행·오류 로그를 먼저 확인하고 같은 경계/대장으로 재개한다. 제외된 과거 Job1/2가 계속 PENDING인 것은 의도한 보존 상태다.

## 중복 실행/오류/진행 조회

동일 공고·유형·payload의 PENDING/RUNNING enqueue는 기존 Job을 반환한다. 명시 `execute`는 DB 원행을 잠가 상태를 재확인하고, PostgreSQL 작업별 advisory lock을 계산 완료까지 유지한다. 오래된 Python 객체/동시 호출/완료 Job의 재호출로 handler를 반복 실행하지 않는다. `claim_next`도 필터 범위를 받은 뒤 원자적으로 선점한다. 한 Job의 attempts는 실제 선점 시에만 증가한다.

`GET /api/jobs/{id}`의 status/progress/message/attempts/started_at/finished_at/error와 `GET /api/bids/{id}`의 processing_status/processing_error를 기존 화면 폴링에 사용한다. 첨부5~40, 통합 추출45, 정리80, 매칭/적합도90, 완료100을 보고한다. 자동 판정은 다른 Job이므로 root result.evaluate_job_id를 따라 표시한다. 실제 관찰한 상태/영수증은 로컬 progress-api-private.jsonl에 저장한다. 백엔드 API로 확인한 상태를 브라우저 렌더 검증으로 확대하지 않는다.

예산/LLM 사용자 오류는 Job.error와 message에 노출하고 내부 traceback은 서버 로그에만 남긴다. 알 수 없는 내부 오류는 기존 일반 메시지를 유지한다. 추출은 공고.processing_error도 저장한다. FAIL 상태를 자동으로 PENDING으로 되돌리지 않는다. 실패하면 API·로그·비용 대장·중간 저장 결과부터 확인하며 전체 재실행을 습관적으로 하지 않는다.

강제 종료/DB 재시작 중 RUNNING으로 남은 작업에는 자동 재실행을 하지 않는다. 기존 프로세스의 생존 여부와 provider 응답/사용량·부분 저장을 먼저 대조해야 한다. 세션이 바뀌면 비용 워커가 추가 전송을 차단한다. 이 단계는 강제 종료된 Job의 자동 복원/lease 만료를 구현하지 않는다.

## 승인 예산과 영수증

총한도$10, 이전 확인 사용액$0.16715. 같은 비용 대장을 계속 사용한다. 대장을 지우거나 이름을 바꾸어 예산을 초기화하지 않는다. 이력/원문/키는 Git에 넣지 않는다. 실제 계정 전체 잔액·다른 클라이언트 소비는 직접 확인하지 못하며, 앱 로그 및 이 워커의 추가 요청을 대조하는 한도다.

`WorkerBudget`는 매 HTTP 전송 **이전**에 최대액을 디스크에 fsync/원자 교체하여 예약한다. SDK 재시도와 JSON 복구도 새 전송마다 한도를 검사한다. 텍스트/JSON의 UTF-8 바이트+20,000 토큰 여유, 최대 출력, primary+Sonnet5 fallback의 보수 단가 합을 상한으로 쓴다. 미완료/실패/사용량 미상 요청은 전액 예약을 남긴다. 영수증으로 확인한 단일 primary의 실제 사용량만 정산하며, 단일 primary iterations를 top-level usage와 중복 합산하지 않는다. 이미 완료된 영수증은 재개 시 무료로 다시 정산할 수 있다.

단가는 [Anthropic 공식 가격표](https://platform.claude.com/docs/en/about-claude/pricing)와 [Sonnet5.5 발표](https://www.anthropic.com/claude-sonnet-5-5)를 2026-10-26 확인: Sonnet5.5 입력$2/출력$10·캐시읽기$0.10/백만, fallback Sonnet5 입력$2/출력$10·캐시읽기$0.20/백만. 출력 사용량에 포함된 thinking을 별도로 더하지 않는다. 캐시쓰기에는 보수 상한$4/백만을 적용한다. receipt에 모델/usage/stop_reason을 남기고 HTTP attempt에 Job ID·SDK retry count·상태·예약액을 연결한다. 프롬프트·Authorization·API 키는 비용 대장에 기록하지 않는다.

현재 비용 검증은 공식 Anthropic Sonnet5.5의 텍스트 입력/표준 모드에 제한한다. 다른 모델·별도 base_url·도구/fast/priority·원본 PDF/이미지 전송은 **지출 전에 차단**한다. 이번 공고8의 첨부는 이미 텍스트가 있어 이 범위에 해당한다. 모델/요금/새 입력 방식이 바뀌면 상한 검증을 별도로 갱신해야 한다. 한도 부족 시 새 Job은 실패 사유를 노출하며 무기한 PENDING으로 두거나 무제한 유료 재시도하지 않는다.

실제 실행 결과·비용·보존·검사·정상 서버/워커 PID는 BACKEND_PROGRESS.md 상단에 기록한다. 이 문서는 프런트/계약/인증 권한을 변경하지 않는다.

## 2026-10-26 실제 복구 결과와 남은 문제

- 기존 Job3→공고8 추출 **SUCCEEDED/attempts1**, 품목1·요구54·placeholder0. 자동 Job4는 공고8/parent_job_id3만 실행했다. 첫 판정 스트림이 `incomplete chunked read`로 끊겨 FAILED, 판정 결과는 원자적으로 롤백됐다. 첫 실패 실행9와 오류 스냅샷을 보존하고 Job4만 한 번 재시도해 **SUCCEEDED/attempts2**, 실행10에 판정54 저장·CURRENT54를 확인했다. Job3 중복 생성/재실행0, 초안 생성0.
- 조회 API에서 실제 첨부 진행22/37→통합45→Job3 완료100, 공고 EVALUATING→FAILED→EVALUATING→EVALUATED와 Job4 실패/재시도/완료를 관찰했다. 첫 실패의 Job.error는 일반 메시지였고 공고.processing_error에는 실제 스트림 오류가 있었다. raw httpx2 전송 오류를 LLMError로 변환해 후속 동일 장애가 화면 오류 필드에도 구체적으로 나타나도록 보완했다(격리 중단 스트림 검사). 실제 브라우저 렌더를 검증했다고 보고하지 않는다.
- 원문 인용 대조는 EXACT_TEXT45/WHITESPACE_MATCH9. 저장 호환 판정은 MET3/NEEDS_SUPPLEMENT7/NEEDS_CONFIRMATION44/HIGH15이며 업무11개 등을 포함한다. 이것을 회사의 최종 참가 자격/제안 적합성 충족으로 보고하지 않는다.
- **남은 정합성 문제:** 기존 LLM 추출 적용 경로가 합계금액214,500,000을 budget_krw로, 공고시각2026-10-16 09:43을 bid_open_at으로 저장했다. 원문/붙여넣기 미리보기의 필드 의미와 다르다. 등록 당시 스냅샷·원문·수동 건명 잠금은 보존했다. 실제 추출·판정 당시 값을 감추거나 조회에서 조용히 보정하지 않았다. 다음 단계는 LLM 추출 적용에도 기본 정보 원문 의미 검증을 연결하고 수정 시 freshness를 반영하는 것이다.
- 기존 자동 매칭은 새 품목3→GTCO-445-F9, score0.35/fit0으로 저장했다. 가스 공급설비와 등록 카트리지 제품의 실제 제안 대응은 검토가 필요하다. 공통 안내 일부가 가스터빈/F7 표현을 재사용하는 점도 후속 적정성 검토 대상이다. 이번 단계에서 수동 제안으로 확정하거나 판정 문구/기준을 바꾸지 않았다. 기존 공고2 수동 선택은 그대로다.
- 실제 HTTP **25시도**, SDK 연결 재시도2/JSON 복구0. 완료 영수증22개와 앱 신규 OK 로그22개 대조: 입력204,482/출력60,381(생각14,535 포함), 캐시0. 확인 추가 사용액 **$1.012774**. 영수증 없는 요청18(끊긴 스트림)·20/21(연결 재시도)은 합계 **최대$2.827828**로 예약을 유지한다. 이전$0.16715 포함 확인 누적 **$1.179924**, 실패 미상액 포함 보수 누적상한 **$4.007752**, 보수 잔여 **$5.992248**. 실제 청구/계정 잔액 미확인. 미상 요청의 토큰/정확한 청구액을 만들지 않았다.
- 격리50 passed(범위/중복/예산/전송33+추출 경계17), 외부 Python socket0. 최종 실제 GET15건200·전후40테이블 변경0, 기존 미디어38/기업117/.env의156파일 SHA 동일. 기존 공고2 판정CURRENT37·초안8·수동 선택·Job1/2 PENDING/attempts0 전체 원행 동일.
- **정상 유지:** API launcher25464/listener25244. 새 작업 감시 워커 launcher22952/child13376, `run_bid_jobs --after-id 4`로 실행 중(동일 비용 대장 사용). ID1/2/3/4를 처리하지 않고 화면에서 이후 새로 만들어진 공고 추출/판정만 처리한다. 로그 `.venv/job3-recovery/watch.*.log`; Windows venv의 launcher/child 한 쌍을 두 독립 워커로 오인하지 않는다.
- 복구본 `.venv/job3-recovery/before-job3.dump` 1,695,735bytes, SHA `82bcf6af3a23b48e20f462d28f07aa8a982a1aeb444727c73f01b90d123760cb`. TOC 확인/실제 복원 미실행. 기존 자료를 현재 DB에 덮어쓰지 않는다. 비공개 전후 원행/진행 API/실패 보존/비용 영수증은 같은 로컬 폴더에 있다.
