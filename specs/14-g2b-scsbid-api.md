# 14. 나라장터 낙찰정보서비스 (ScsbidInfoService) 활용 정리

> 출처: 조달청 OpenAPI 참고자료 「나라장터 낙찰정보서비스」 v1.2 (2026-10-01).
> 용도: **입찰 결과 이력 축적** (기술 판정과 분리 저장). 공고 탐색·첨부파일은 입찰공고정보서비스(별도 문서)에서 처리.

## 1. 공통

| 항목 | 값 |
|---|---|
| Base URL | `http://apis.data.go.kr/1230000/as/ScsbidInfoService/{오퍼레이션}` |
| 인증 | `ServiceKey` = 공공데이터포털 인증키 (Decoding 키를 `requests` params로 전달) |
| 응답 형식 | `type=json` (생략 시 XML) |
| 페이징 | `pageNo`, `numOfRows` / 응답 `totalCount` |
| 일시 형식 | 요청 `YYYYMMDDHHMM`, 응답 `YYYY-MM-DD HH:MM:SS` |
| 성능 | 평균 500 ms, 최대 30 tps. 개발계정 일일 트래픽 제한 있음(에러 22) |
| 대상 | 물품(`...Thng`) 오퍼레이션만 사용. 공사·용역·외자 제외 |

### 입찰공고번호 형식 (두 가지 모두 지원해야 함)
- 구 체계: `20230342721` (년4+월2+순번5, 11자리)
- 차세대 체계: `R26BK01289682` (R + 년2 + 단계구분2 + 순번8, 13자리. BK=입찰)
- `bidNtceOrd`(공고차수): 정정공고·재공고 시 증가 → **같은 공고번호는 가장 큰 차수만 사용**.

## 2. 사용할 오퍼레이션

| # | 오퍼레이션 | 용도 | 주요 요청 파라미터 |
|---|---|---|---|
| 13 | `getOpengResultListInfoOpengCompt` | **공고 1건의 전체 개찰순위** (필텍 순위·경쟁사·무효 사유) | `bidNtceNo`(필수), `bidNtceOrd`, `bidClsfcNo`, `rbidNo` |
| 9 | `getOpengResultListInfoThngPreparPcDetail` | 복수예비가격 15개·기초금액·예정가격·추첨 정보 (과거 기반 추정 범위용) | `inqryDiv`, 기간 또는 `bidNtceNo` |
| 16 | `getScsbidListSttusThngPPSSrch` | 조건 검색: 낙찰자 목록 (수요기관·세부품명번호·사업자번호) | `inqryDiv`, 기간, `dminsttNm`/`dminsttCd`, `dtilPrdctClsfcNo`, `bizno` |
| 20 | `getOpengResultListInfoThngPPSSrch` | 조건 검색: 개찰결과 목록 | `inqryDiv`, 기간, 수요기관, 세부품명번호 |
| 1 / 5 | `getScsbidListSttusThng` / `getOpengResultListInfoThng` | 기간 또는 공고번호 단순 조회 | `inqryDiv`, 기간 또는 `bidNtceNo` |

### ⚠️ `inqryDiv` 값이 오퍼레이션마다 다름
- 1·5번: `1` 등록일시, `2` 공고일시, `3` 개찰일시, **`4` 공고번호**
- 16·20번(PPSSrch): `1` 공고게시일시, `2` 개찰일시, **`3` 공고번호**

## 3. 저장할 응답 필드 → `bid_result` 테이블

| 필드 | 의미 | 출처 |
|---|---|---|
| `bidNtceNo`, `bidNtceOrd`, `bidClsfcNo`, `rbidNo` | 공고 식별자 | 공통 |
| `bidNtceNm` | 공고명 | 공통 |
| `opengRank` | 개찰순위 | 13 |
| `prcbdrBizno`, `prcbdrNm` | 투찰업체 사업자번호·업체명 (필텍 = 1288126350) | 13 |
| `bidprcAmt`, `bidprcrt` | 투찰금액, 투찰률(%) | 13 |
| `rmrk` | 비고 (무효·탈락 사유 확인용) | 13 |
| `opengRsltDivNm` | 개찰결과구분 (개찰완료/유찰/재입찰) | 13 |
| `prtcptCnum` | 참가업체수 | 1, 16 |
| `bidwinnrNm`, `bidwinnrBizno`, `sucsfbidAmt` | 최종낙찰업체·금액 | 1, 16 |
| `sucsfbidRate` | 최종낙찰률 = 낙찰금액 / **예정가격** × 100 | 1, 16 |
| `bssamt`, `plnprc` | 기초금액, 예정가격 | 9 |
| `compnoRsrvtnPrceSno`, `bsisPlnprc`, `drwtYn`, `drwtNum` | 복수예가 순번·금액·추첨여부·추첨횟수 | 9 |
| `dminsttCd`, `dminsttNm` | 수요기관 | 1, 16 |
| `rlOpengDt`, `fnlSucsfDate` | 실개찰일시, 최종낙찰일 | 1, 16 |

저장하지 않음: 낙찰업체 대표자·주소·전화·담당자 (개인정보, 불필요).

## 4. 처리 흐름
1. 입찰공고정보서비스로 수집한 대상 공고(가스터빈, 발전5사+한국지역난방공사, 40161505*, 제한경쟁)의 `bidNtceNo` 목록 확보.
2. 개찰일 이후 공고별로 13번 호출 → 전체 순위 저장, `prcbdrBizno == 1288126350` 행으로 필텍 결과 표시.
3. 9번 호출 → 복수예가·기초금액 저장 (추정 범위 기능용, 낙찰방법별로 분리 집계).
4. 결과는 `bid_result`에만 저장하고 판정(`evaluation`)과 섞지 않는다.

## 5. 에러 코드 대응

| 코드 | 의미 | 대응 |
|---|---|---|
| 03 | 데이터 없음 | 정상 처리(빈 결과) |
| 06 / 07 / 08 / 11 | 날짜 형식·범위·필수값 오류 | 파라미터 검증 후 재시도 안 함 |
| 20 | 활용 미승인 (승인까지 2~3일 가능) | 대기 |
| 22 | 일일 트래픽 초과 | 다음 날 재시도, 호출 수 로깅 |
| 30 | 등록되지 않은 키 / 키 인코딩 문제 | Decoding 키 사용 여부 확인 |
| 31 | 키 기간 만료 | 활용 연장 신청 |
| 01 / 02 / 04 / 05 | 제공기관 장애 | 지수 백오프 재시도 |
