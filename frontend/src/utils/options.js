// Choice labels mirroring backend TextChoices (specs/02 §4).
const opts = (map) => Object.entries(map).map(([value, label]) => ({ value, label }))

export const FILTER_TYPES = opts({
  PANEL: '패널형',
  POCKET_BAG: '포켓/백필터',
  V_BANK: 'V-bank',
  MINI_PLEAT_HEPA: '미니플리트/HEPA',
  CARTRIDGE_PULSE: '펄스 카트리지',
  DEMISTER: '데미스터',
  CARBON: '카본(활성탄)',
  OTHER: '기타',
})

export const STANDARD_FAMILIES = opts({
  ISO16890: 'ISO 16890',
  ISO29461: 'ISO 29461-1',
  EN1822: 'EN 1822',
  EN779: 'EN 779',
  ASHRAE52_1: 'ASHRAE 52.1',
  ASHRAE52_2: 'ASHRAE 52.2',
  UL900: 'UL 900',
  KS: 'KS',
  OTHER: '기타',
})

export const CERT_TYPES = opts({
  ISO9001: 'ISO 9001',
  ISO14001: 'ISO 14001',
  ISO45001: 'ISO 45001',
  DIRECT_PRODUCTION: '직접생산확인',
  SME: '중소기업확인',
  KS: 'KS',
  PATENT: '특허',
  OTHER: '기타',
})

export const CERT_STATUSES = opts({
  VALID: '유효',
  EXPIRING: '만료 임박',
  EXPIRED: '만료',
  UNKNOWN: '확인 필요',
})

export const PLANT_TYPES = opts({
  CCPP: '복합화력',
  THERMAL: '화력',
  CHP: '열병합/지역난방',
  OTHER: '기타',
})

export const YES_NO = [
  { value: 'true', label: '예' },
  { value: 'false', label: '아니오' },
]

export const OWNER_TYPES = opts({ COMPANY: '회사 자료', BID: '입찰 첨부' })

export const FIELD_TYPES = opts({
  str: '문자',
  int: '정수',
  float: '실수',
  date: '날짜',
  bool: '예/아니오',
  list: '목록',
  dimension: '치수',
  grade: '등급',
  json: 'JSON',
})

export const BID_OUTCOMES = opts({
  PENDING: '진행 중',
  WON: '낙찰',
  LOST: '미낙찰',
  NOT_BID: '불참',
})

export const PROCESSING_STATUSES = opts({
  DRAFT: '등록됨',
  EXTRACTING: '추출 중',
  EXTRACTED: '추출 완료',
  EVALUATING: '판정 중',
  EVALUATED: '판정 완료',
  FAILED: '실패',
})

export const REQUIREMENT_CATEGORIES = opts({
  DIMENSION: '제품 치수',
  FILTER_TYPE: '필터 형식',
  FILTER_GRADE: '필터 등급',
  EFFICIENCY: '효율',
  PRESSURE_DROP: '차압',
  AIRFLOW: '풍량',
  MATERIAL: '재질',
  ENVIRONMENT: '사용 환경',
  FIRE_RATING: '난연',
  TEST_STANDARD: '시험 규격',
  CERTIFICATION: '인증·자격',
  TRACK_RECORD: '납품실적',
  DELIVERY: '납기',
  SUBMISSION_DOC: '제출서류',
  WARRANTY: '하자보증',
  INSPECTION: '시험·검사',
  OTHER: '기타',
})

export const BID_ATTACHMENT_FORMATS = [
  '.txt',
  '.docx',
  '.doc',
  '.hwp',
  '.hwpx',
  '.pdf',
  '.xls',
  '.xlsx',
]

export const VERDICTS = opts({
  MET: '충족',
  NEEDS_SUPPLEMENT: '보완 필요',
  NEEDS_CONFIRMATION: '확인 필요',
})

export const RISK_LEVELS = opts({ LOW: '낮음', MEDIUM: '보통', HIGH: '높음' })
