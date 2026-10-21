# 10. REST API

Prefix `/api`. 권한: 🅰 ADMIN, 🅱 BID_MANAGER 이상(= 로그인 사용자), 🌐 공개.

## 시스템 · 인증
| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/system/status` | 🌐 | `{llm_configured, active_provider, app_version, admin_must_change_password}` |
| POST | `/auth/login` | 🌐 | `{username, password}` → `{access, refresh, user}` |
| POST | `/auth/refresh` | 🌐 | `{refresh}` → `{access}` |
| POST | `/auth/logout` | 🅱 | refresh 블랙리스트 |
| GET | `/auth/me` | 🅱 | 현재 사용자 |
| POST | `/auth/change-password` | 🅱 | `{old_password, new_password}` |

## 사용자
| GET/POST | `/users` | 🅰 | 목록(필터 role, is_active)/생성 |
| GET/PATCH/DELETE | `/users/{id}` | 🅰 | 삭제는 비활성화. `?hard=true`는 로그인 이력 없는 사용자만 물리 삭제 |
| POST | `/users/{id}/reset-password` | 🅰 | `{new_password}` |

## 대시보드
| GET | `/dashboard/summary` | 🅱 | `{total, reviewed, unreviewed}` |

## 문서 · 메타데이터
| GET/POST | `/documents` | 🅰(쓰기) 🅱(읽기) | 업로드(multipart: `files[]`, `owner_type`, `category?`) 또는 JSON `{source_text, title, owner_type}` |
| GET/PATCH/DELETE | `/documents/{id}` | 🅱(읽기)/🅰 | GET 응답에 `low_confidence_threshold` 포함. PATCH: `{title?, category?, reextract?}` — 분류 변경 시 `category_source=MANUAL` |
| GET | `/documents/{id}/download` | 🅱 | 원본 파일 |
| GET | `/documents/{id}/text` | 🅱 | `{pages, page_count, tables}` 추출 텍스트(페이지별)와 표 |
| POST | `/documents/{id}/reprocess` | 🅰 | `{from_step: parse/classify/extract/map}` → `{job_id}` |
| GET | `/documents/{id}/mapping-preview` | 🅰 | 도메인 반영 diff |
| POST | `/documents/{id}/apply` | 🅰 | 도메인 반영 |
| GET/POST | `/documents/{id}/metadata` | 🅰 | 메타데이터 행 목록/추가 |
| PATCH/DELETE | `/documents/{id}/metadata/{mid}` | 🅰 | 수정(→ locked)/삭제 |
| GET/POST | `/metadata-schemas` | 🅰 | 분류 목록/생성 |
| GET/PATCH/DELETE | `/metadata-schemas/{id}` | 🅰 | |
| POST | `/metadata-schemas/{id}/reextract` | 🅰 | 해당 분류 문서 일괄 재추출 |

## 회사 자료
| GET/PUT | `/company` | 🅱/🅰 | 싱글턴 |
| CRUD | `/products`, `/test-reports`, `/certificates`, `/delivery-records` | 🅱 읽기 / 🅰 쓰기 | 목록 필터: `q`, `is_active`, `product`, `status`(인증) |

## 입찰 공고
| GET/POST | `/bids` | 🅱/🅰 | 목록 필터: `review_status, is_power_plant, fit_min, closing(before/after), outcome, q, ordering` / 생성(multipart `files[]` + `source_text?` + `title?`) |
| GET/PATCH/DELETE | `/bids/{id}` | 🅱/🅰 | 상세(헤더+요약+카운트) |
| POST | `/bids/{id}/attachments` | 🅰 | 첨부 추가 `files[]` |
| PATCH/DELETE | `/bids/{id}/attachments/{aid}` | 🅰 | 분류/is_primary/order 변경, 삭제 |
| POST | `/bids/{id}/extract` | 🅰 | → `{job_id}` |
| GET/POST | `/bids/{id}/items` | 🅱/🅰 | 품목 |
| PATCH/DELETE | `/bids/{id}/items/{iid}` | 🅰 (matched_product 변경은 🅱 허용) | |
| GET/POST | `/bids/{id}/requirements` | 🅱/🅰 | 요구사항(+ 판정 포함 `?include=evaluation`) |
| PATCH/DELETE | `/bids/{id}/requirements/{rid}` | 🅰 | |
| POST | `/bids/{id}/review` | 🅱 | `{reviewed: true/false}` 확인 완료/취소 |
| GET | `/bids/{id}/comparison` | 🅱 | ② 비교 표 데이터 |

## 판정
| POST | `/bids/{id}/evaluate` | 🅱 | `{keep_modified: true, requirement_ids?: []}` → `{job_id}` (LLM 미설정 시 409) |
| GET | `/bids/{id}/evaluations` | 🅱 | 전체 판정 + 요약 |
| PATCH | `/evaluations/{eid}` | 🅱 | 수정 |
| POST | `/evaluations/{eid}/revert` | 🅱 | AI 판정 복원 |
| GET | `/evaluations/{eid}/history` | 🅱 | 이력 |

## 초안 · PDF
| GET | `/bids/{id}/drafts` | 🅱 | 유형별 최신 버전 메타 |
| POST | `/bids/{id}/drafts/{type}/generate` | 🅱 | `{new_version: true}` → `{job_id}` |
| GET/PUT | `/bids/{id}/drafts/{type}` | 🅱 | 최신(또는 `?version=`) 조회 / 저장 |
| GET | `/bids/{id}/drafts/{type}/versions` | 🅱 | |
| GET | `/bids/{id}/drafts/{type}/pdf` | 🅱 | PDF |
| GET | `/bids/{id}/drafts/{type}/xlsx` | 🅱 | XLSX — `COMPLIANCE_MATRIX`, `BID_CHECKLIST`만 ([09](09-drafts-and-reports.md) §6) |
| GET | `/bids/{id}/report.pdf` | 🅱 | 통합 보고서 |

## LLM · 설정
| GET | `/settings/llm` | 🅰 | providers(키 마스킹), settings, model options |
| PUT | `/settings/llm` | 🅰 | `{active_provider, active_model_id, temperature, ...}` |
| PUT | `/settings/llm/providers/{provider}` | 🅰 | `{api_key?, base_url?, is_enabled}` (빈 api_key = 변경 없음) |
| POST | `/settings/llm/providers/{provider}/verify` | 🅰 | 연결 테스트 |
| CRUD | `/settings/llm/models` | 🅰 | 모델 옵션 |
| GET | `/settings/prompts` | 🅰 | 키별 활성 버전 |
| GET/POST | `/settings/prompts/{key}` | 🅰 | 버전 목록 / 새 버전 저장 |
| POST | `/settings/prompts/{key}/activate` | 🅰 | `{version}` 롤백 |
| POST | `/settings/prompts/{key}/reset` | 🅰 | seed 기본값 새 버전 |
| POST | `/settings/prompts/{key}/test` | 🅰 | `{variables | document_id, system_prompt?, user_prompt_template?, output_schema?}` — 편집 중(미저장) 내용으로 실행. `document_id`는 `document.*` 프롬프트만. → `{ok, system, user, raw_text, parsed, input_tokens, output_tokens, latency_ms}` 또는 `{ok: false, error, raw_text}`. LLM 미설정 시 409 |
| GET/PUT | `/settings/app` | 🅰 | GET `{groups: [{group, settings: [{key, value, value_type, description, default, is_default}]}]}` / PUT `{values: {key: value}}` — 하나라도 오류면 전체 롤백, 400 `errors`에 키별 사유 |
| POST | `/settings/app/{key}/reset` | 🅰 | |

## 작업 · 로그 · 적재
| GET | `/jobs/{id}` | 🅱(본인)/🅰 | 상태 폴링 |
| GET | `/jobs` | 🅰 | 목록 |
| POST | `/jobs/{id}/retry`, `/jobs/{id}/cancel` | 🅰 | |
| GET | `/llm-logs` | 🅰 | 필터 `task_key`(부분 일치), `status`, `provider`, `date_from`, `date_to`. 응답에 `summary: {today, month}` (호출 수·입력/출력 토큰 합계) |
| GET | `/llm-logs/{id}` | 🅰 | 요청 앞부분(`request_excerpt`)·응답 원문(`response_text`) 포함. 목록에는 두 필드를 넣지 않는다(응답 크기). |
| POST | `/admin/load-initial-data` | 🅰 | `{mode: skip|update}` → `{job_id}` |
