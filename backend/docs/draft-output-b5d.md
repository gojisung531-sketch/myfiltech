# 저장 결과에서 초안·XLSX·PDF 출력

B5D는 공고를 재추출하거나 판정을 다시 실행하지 않고, 기존 `apps/drafts` 생성기로 저장 초안 4종을 만들고 실제 다운로드 API에서 파일을 받았다. 실제 파일·검증 기록·회사 값은 Git 제외 `backend/.venv/b5d/`에 있으며 결과/버전/한계는 `BACKEND_PROGRESS.md`에 기록한다.

## 생성·수동 버전 보존

`generate_draft(..., allow_llm=False, new_version=True)`는 규칙 기반 생성과 저장을 사용한다. 전역 AI 설정·키·프롬프트를 바꾸지 않는다. API에서도 생성 요청의 Boolean `allow_llm:false`를 작업 payload로 전달할 수 있다. 생략하면 기존 기본 동작을 유지한다. 지정 공고/초안만 처리하며 워커 전체 실행은 필요하지 않다.

기존 정책은 수정되지 않은 최신 자동 초안이면 같은 버전을 갱신하고, `new_version=True` 또는 `is_modified=True`이면 새 버전을 생성한다. B5D 실제 실행은 새 버전 모드로 최초 4종만 저장했으며, 수동 수정 보존·자동 갱신 정책은 격리 테스트에서 검증했다. 기존 수동 판정은 생성 입력으로 읽기만 한다.

각 저장 초안에는 기존 판정 기준일·판정 건수·정규화/판정/trace의 입력 해시와 검토 고지가 들어간다. 생성일과 과거 저장 판정의 기준일을 혼동하지 않는다. 이 기록은 자료 개정·오래된 결과 자동 표시 시스템이 아니다.

## 내용·출처 범위

- 대응표는 최종 판정 행과 후보별 기재값 비교를 구분한다. 후보의 일치/차이는 확정 공고 충족/미달이나 검증된 시험 결과가 아니다. 원문 해석 제한과 제조사 원문 문서/확인 페이지를 표시하고 미확인 위치를 만들어내지 않는다.
- 체크리스트는 작성 완료를 추정하지 않고 미완료로 두며, 제작 전 승인과 계약/납품 시점을 구분한다. 조건부 적용과 후속 조치를 함께 읽는다.
- 기술질의서의 `questions`는 해소되지 않은 원문 부호·단위·적용 관계 등 발주처 확인 초안, `internal_questions`는 회사 자료/제안 모델·옵션/이행 준비의 내부 확인이다. 이미 기재된 치수·형식 자체를 다시 질문하지 않는다. 실제 발송은 하지 않는다.
- 검토보고서는 미확정 상태에서 입찰 가능/불가를 확정하지 않는다. 참고 점수·HIGH 표시만으로 최종 결정을 내리지 않으며, 미산정 점수는 미산정으로 표시한다. 비용 절감률·정확도·시험 결과를 추가 생성하지 않는다.
- 실제 등록 자료의 검토 고지를 사용하며, 기존 가상 자료용 문구를 해당 문서에 사실처럼 붙이지 않는다. 전역 `report.disclaimer`는 변경하지 않았다.

## 파일과 버전

개별 PDF/XLSX는 기존 `?version=`으로 지정한 저장 JSON을 출력한다. 통합 PDF는 한 조회에서 고른 각 유형의 최신 저장 JSON/버전을 사용하고 해당 버전을 절 제목에 표시한다. 없는 유형만 기존 규칙으로 임시 구성하며 저장/LLM 호출은 하지 않는다. B5D 실제 출력은 4종 모두 저장 v1을 사용했다.

대응표 XLSX는 최종 대응표 시트에 더해 후보 비교가 있을 때만 별도 `후보 비교` 시트를 제공한다. 체크리스트는 기존 단일 시트다. 문자열의 수식 시작 문자·선행 공백/탭/개행을 처리해 수식 주입을 막고, 숫자는 숫자로 유지한다. 한글·긴 텍스트의 줄바꿈/행 높이, 머리행 고정/필터를 유지한다. XLSX는 표 데이터 검증과 렌더링 검증을 구분하며, Excel 데스크톱에서 직접 조작한 검증은 아니다.

## Windows PDF 실행 환경

기존 `.venv`의 WeasyPrint 70은 GObject/Pango DLL이 없어 import에 실패했다. Python/DB/키를 재설치하지 않고, [공식 Windows 안내](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)와 [MSYS2 Pango 패키지](https://packages.msys2.org/packages/mingw-w64-x86_64-pango)를 기준으로 필요한 라이브러리를 준비했다.

이 작업의 DLL은 공식 MSYS2 저장소의 패키지 메타데이터와 SHA256을 대조한 뒤 `.venv/pdf-runtime/mingw64/bin`에 분리 추출했다. 시스템 설치/패키지 후처리 스크립트는 실행하지 않았다. 패키지 버전·URL·해시·라이선스는 `.venv/pdf-runtime/manifest.json` 및 해당 `share/licenses`에 남는다. 네트워크 의존성 내려받기는 준비 단계뿐이며 PDF 다운로드 시 회사 문서를 외부로 업로드하지 않는다.

실제 로컬 실행에서는 기존 P:가 이 worktree의 `.venv`를 가리키는 것을 확인한 뒤, 프로세스 환경에 `WEASYPRINT_DLL_DIRECTORIES=P:/pdf-runtime/mingw64/bin`, `FONTCONFIG_FILE=P:/pdf-runtime/fonts.conf`를 전달했다. Unicode 폴더 경로의 Fontconfig 설정/캐시 문제를 피하기 위한 기존 ASCII 별칭이며, 다른 P:를 덮어쓰지 않는다. Fontconfig 파일의 폰트/캐시도 같은 별칭을 사용한다. 기존 Noto Sans KR 두 파일과 OFL을 분리 런타임에 복사하고 SHA를 대조했다. `.env`나 시스템 전역 환경 변수는 변경하지 않았다.

앱은 Windows에 분리 런타임이 있으면 준비된 DLL 경로를 사용하며, 명시된 운영자 환경값을 우선한다. Linux에서는 이 Windows 경로를 적용하지 않는다. 실행 환경이 없을 때 다운로드 성공을 가장하는 빈 PDF/JSON 대체 파일을 만들지 않는다.

## 이후 Render 준비 조건 — 배포 미실행

[WeasyPrint의 Debian 계열 요구사항](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#debian-11)에 맞춰 런타임에 Pango/GObject·PangoFT2·HarfBuzz subset·Fontconfig가 있어야 한다. Debian 패키지 기준 `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`, `fontconfig`와 전이 의존성을 확인한다. 소스 빌드가 필요한 패키지는 개발 헤더가 추가로 필요할 수 있다.

Python 의존성 설치만 성공했다고 PDF 런타임이 준비됐다고 보지 않는다. 선택한 Render 실행 환경에서 DLL 대신 해당 Linux 공유 라이브러리의 로딩·실제 한글 PDF 생성/렌더링을 다시 확인해야 한다. `backend/fonts/NotoSansKR-Regular.otf`, `NotoSansKR-Bold.otf`, OFL이 배포 산출물에 포함되고 앱에서 읽을 수 있어야 한다. fallback 글리프와 쓰기 가능한 임시/캐시 경로도 확인한다. Windows DLL/P: 경로는 Render에 복사하지 않는다. 이번에는 배포 파일/원격 설정/서비스를 만들거나 변경하지 않았다.
