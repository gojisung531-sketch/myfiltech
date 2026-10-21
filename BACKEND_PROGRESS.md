# 백엔드 인수인계

- 상태: 대기. Backend B0 — 로컬 실행환경·DB 연결부터 시작.
- 작업폴더: `C:\Users\김가은\Documents\ChatGPT\it와비즈니스혁신\filtech-backend`
- 브랜치: `feature/backend-foundation`
- 담당 범위: backend/**, 이 파일.
- Phase 0: 의존성 설치와 weasyprint import 성공, 더미 DB 주소·키로 manage.py check 통과(기존 작업자 보고). 실제 migrate·서버·pytest·브라우저는 미확인.
- PostgreSQL: 현재 psql 명령·서비스·기본 설치경로에서 확인되지 않음. 실제 사용 가능한 로컬 서버 유무부터 확인.
- backend/.env·.venv는 새 작업폴더에 별도 준비 필요. 키를 로그·Git에 노출하지 않음.
- 테스트: 가상 회사자료 파일과 기존 적재 정책에 의존하는 테스트가 있음. 실패를 숨기거나 일괄 skip하지 말고 환경·제품 정책·픽스처 의존성을 구분해 기록. 테스트용 입력과 제품 데이터는 구분.
- 참고: 기존 specs/12는 입찰 8건을 실제 과거 공고로 명시. 가상 회사자료와 구분. 원문 파일은 코드 이력에서 제외되어 로컬 참조 경로가 필요할 수 있음.
- 다음: 병렬 백엔드 B0 지시서를 읽고 환경과 서버 동작 검증만 진행. API·분석 엔진 변경은 아직 하지 않음.
- 완료/중단 시 이 파일에 변경·검사·미확인·커밋·다음 위치를 기록. PERSONAL_PROGRESS.md는 수정하지 않음.
