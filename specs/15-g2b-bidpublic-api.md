# 15. 나라장터 입찰공고정보서비스 (BidPublicInfoService) 활용 정리

> 출처: 조달청 OpenAPI 참고자료 「나라장터 입찰공고정보서비스」 v1.2.
> 용도: **신규 공고 탐색, 공고 메타데이터, 첨부파일(공고서·규격서) 확보, 품목·참가자격 정보**.
> 결과(순위·낙찰)는 14번 문서(낙찰정보서비스)에서 처리.

## 1. 공통

| 항목 | 값 |
|---|---|
| Base URL | `http://apis.data.go.kr/1230000/ad/BidPublicInfoService/{오퍼레이션}` (낙찰정보는 `/as/`, 여기는 **`/ad/`**) |
| 인증·형식 | `ServiceKey`(Decoding 키), `type=json`, `pageNo`, `numOfRows` |
| 조회 기간 | 기간 검색은 **최대 1개월 단위로 끊어서** 호출 (일부 오퍼레이션 문서에 명시, 전체에 동일 규칙 적용) |
| 대상 | 물품(`...Thng`)만 사용 |

## 2. 사용할 오퍼레이션

| 용도 | 오퍼레이션 | 주요 요청 파라미터 |
|---|---|---|
| ① 신규 공고 탐색 (매일) | `getBidPblancListInfoThngPPSSrch` | `inqryDiv=1`(공고게시일시), `inqryBgnDt`, `inqryEndDt`, `dtilPrdctClsfcNo`, `dminsttNm`(부분일치), `bidNtceNm`(부분일치) |
| ② 공고 상세 + **첨부파일 URL** | `getBidPblancListInfoThng` | `inqryDiv=2` + `bidNtceNo` |
| ③ 정정·변경 공고 감지 | `getBidPblancListInfoThng` (`inqryDiv=3` 변경일시), `getBidPblancListInfoChgHstryThng` | 기간 |
| ④ 구매대상 품목 | `getBidPblancListInfoThngPurchsObjPrdct` | `bidNtceNo` |
| ⑤ 참가가능지역 | `getBidPblancListInfoPrtcptPsblRgn` | `bidNtceNo` |
| ⑥ 면허·업종 제한 | `getBidPblancListInfoLicenseLimit` | `bidNtceNo` |
| ⑦ e발주 첨부파일 (②에 없을 때 보조) | `getBidPblancListInfoEorderAtchFileInfo` | `bidNtceNo` |

### ⚠️ `inqryDiv` 값이 오퍼레이션마다 다름
- `getBidPblancListInfoThng`: `1` 등록일시, **`2` 입찰공고번호**, `3` 변경일시
- `...PPSSrch`: `1` 공고게시일시, `2` 개찰일시 (공고번호 검색 없음)
- 14번 문서(낙찰정보)와도 다름 → **오퍼레이션별 상수로 관리**

## 3. 대상 공고 필터 (확정: 필텍 미팅)

API 파라미터로 1차 축소 → 코드에서 2차 필터.

| 조건 | 방법 |
|---|---|
| 세부품명번호 `40161505xx` (4016150501 공기여과기, 4016150500 등) | API `dtilPrdctClsfcNo`로 코드별 호출 + 코드에서 `startswith("40161505")` 확인 |
| 수요기관: 발전 5사(남동·중부·서부·남부·동서) + 한국지역난방공사 | 코드에서 `dminsttNm` 포함 여부 (지사명 포함되므로 부분일치) |
| 계약방법: **제한경쟁만** (수의계약 제외 — 필텍 확인) | 코드에서 `cntrctCnclsMthdNm == "제한경쟁"` |
| 가스터빈 관련 | `bidNtceNm`에 `가스터빈`, `GT`, `흡기`, `흡입`, `Air Intake`, `Inlet` → 미해당 시 제외하지 않고 **후순위 + "GT 여부 확인" 표시** |
| 공고 상태 | `ntceKindNm`: 등록공고 → 처리, 변경공고/재공고 → 재처리(최신 `bidNtceOrd`만 유지), 취소공고 → 취소 표시 |

## 4. 저장할 응답 필드 → `bid_notice`, `bid_attachment`, `bid_item`

**bid_notice**

| 필드 | 의미 |
|---|---|
| `bidNtceNo`, `bidNtceOrd`, `untyNtceNo` | 공고번호, 차수, 통합공고번호 |
| `bidNtceNm`, `ntceKindNm`, `reNtceYn`, `chgNtceRsn` | 공고명, 공고종류, 재공고 여부, 변경 사유 |
| `ntceInsttNm`, `dminsttCd`, `dminsttNm` | 공고기관, 수요기관 |
| `cntrctCnclsMthdNm`, `bidMethdNm`, `sucsfbidMthdNm` | 계약방법, 입찰방식, 낙찰방법 |
| `sucsfbidLwltRate` | 낙찰하한율 |
| `asignBdgtAmt`, `presmptPrce` | 배정예산, 추정가격 |
| `bidBeginDt`, `bidClseDt`, `opengDt` | 입찰 개시·마감·개찰 일시 |
| `dtilPrdctClsfcNo`, `dtilPrdctClsfcNoNm` | 세부품명번호·명 |
| `indstrytyLmtYn`, `prdctClsfcLmtYn`, `mnfctYn`, `rgnLmtBidLocplcJdgmBssNm` | 업종·품목 제한, 제조 여부, 지역제한 판단기준 |
| `dlvrTmlmtDt`, `dlvrDaynum`, `dlvryCndtnNm` | 납품기한·일수·인도조건 |
| `bidNtceDtlUrl` | 나라장터 공고 상세 링크 (화면에 "원문 보기") |

**bid_attachment** — `ntceSpecDocUrl1~10` + `ntceSpecFileNm1~10` (규격서 등), `stdNtceDocUrl` (표준 공고문). 없으면 ⑦ `eorderAtchFileNm`, `eorderAtchFileUrl`, `eorderDocDivNm`.
파일은 `data/` 하위(깃 제외)에 저장, DB에는 경로·해시·원본 URL만.

**bid_item** — ④의 물품순번, 품명, 세부품명번호, 수량, 단위, 납품기한.

**참가자격 보조** — ⑤ `prtcptPsblRgnNm`(참가가능지역 → 필텍 경기도 여부), ⑥ `lcnsLmtNm`, `permsnIndstrytyList`.

저장하지 않음: 담당자 이름·전화·이메일(`ntceInsttOfclNm`, `...TelNo`, `...EmailAdrs`).

## 5. 일일 수집 흐름
1. 매일 1회: ①을 전일~당일 범위, 세부품명번호별로 호출 (페이지 끝까지).
2. 코드 필터(3절) 통과 공고만 ②로 상세 조회 → 첨부 URL 수집 → 파일 다운로드.
3. ④⑤⑥ 호출해 품목·지역·면허 정보 저장.
4. ③으로 변경공고 확인 → 최신 차수로 재처리, 이전 차수는 보관만.
5. 이후 파이프라인: 파싱 → 요구사항 추출 → 검증 → 판정.

## 6. 확인 필요 (실제 호출로 검증)
- `dtilPrdctClsfcNo`가 10자리 완전일치인지, 앞자리 부분일치도 되는지.
- 차세대 나라장터(2025~) 공고에서 첨부가 ②와 ⑦ 중 어디에 오는지.
- 첨부 URL 다운로드 시 로그인·세션 필요 여부.
- 개발계정 일일 트래픽 한도(포털 마이페이지 확인).
