// B6B 근거 위치 객체(서버 계산 결과)를 화면 용어로만 바꾼다. 위치·상태를 새로 만들거나 고치지 않는다.

export const ROLE_KIND = {
  REQUIREMENT_SOURCE: 'requirement_source',
  STORED_EVALUATION_EVIDENCE: 'stored_evidence',
  CURRENT_COMPANY_REFERENCE: 'current_reference',
}

// confirmed: 위치로 이동해도 되는 상태. tone: 배지 색.
export const STATUS_INFO = {
  EXACT_MATCH: { label: '인용 일치', tone: 'bg-success', confirmed: true },
  WHITESPACE_MATCH: {
    label: '공백·줄바꿈만 다름',
    tone: 'bg-success',
    confirmed: true,
    reason:
      '저장된 인용문과 공백·줄바꿈만 다릅니다. 강조는 저장된 인용이 아니라 실제로 일치한 글자 기준입니다.',
  },
  MULTIPLE_MATCHES: {
    label: '여러 위치에서 일치',
    tone: 'bg-info',
    confirmed: true,
    reason: '같은 인용이 여러 곳에 있습니다. 어느 위치가 맞는지 직접 선택하세요(자동 선택 안 함).',
  },
  MANUAL_REVIEWED_PAGE: {
    label: '수동 확인 페이지',
    tone: 'bg-info',
    confirmed: true,
    reason:
      '사람이 확인해 기록한 PDF 물리 페이지입니다. 인용 문자는 기계로 대조하지 않았으므로 글자 단위 강조는 하지 않습니다.',
  },
  PAGE_ONLY: {
    label: '페이지만 확인',
    tone: 'bg-info',
    confirmed: true,
    reason:
      'PDF 물리 페이지는 확인됐지만 저장된 텍스트가 없어 인용문 자동 대조는 하지 않았습니다(문자 대조 안 됨).',
  },
  QUOTE_NOT_FOUND: {
    label: '인용 불일치',
    tone: 'bg-warning',
    confirmed: false,
    reason:
      '저장된 인용문이 현재 추출 텍스트에서 발견되지 않았습니다(문장부호·따옴표 차이일 수 있음). 인용문은 고치지 않았고 비슷한 문장도 근거로 쓰지 않았습니다.',
  },
  NO_QUOTE: {
    label: '인용문 없음',
    tone: 'bg-secondary',
    confirmed: false,
    reason: '저장된 인용문이 없어 위치를 찾지 않았습니다.',
  },
  NO_VERIFIABLE_TEXT: {
    label: '대조할 텍스트 없음',
    tone: 'bg-secondary',
    confirmed: false,
    reason:
      'PDF 저장 텍스트가 없거나 실제 페이지 구조와 맞지 않아 자동으로 페이지를 연결할 수 없습니다.',
  },
  INVALID_PAGE: {
    label: '페이지 범위 밖',
    tone: 'bg-warning',
    confirmed: false,
    reason: '기록된 페이지가 제공된 원본 PDF의 페이지 범위를 벗어납니다.',
  },
  SOURCE_CHANGED: {
    label: '원본 변경',
    tone: 'bg-warning',
    confirmed: false,
    reason: '현재 원본 파일이 기록된 값과 달라 위치를 확정하지 않았습니다.',
  },
  SOURCE_UNAVAILABLE: {
    label: '원본 파일 없음',
    tone: 'bg-warning',
    confirmed: false,
    reason: '원본 파일을 찾을 수 없어 위치를 확인하지 못했습니다.',
  },
  SOURCE_UNREADABLE: {
    label: '원본 읽기 실패',
    tone: 'bg-warning',
    confirmed: false,
    reason: '원본 파일을 읽지 못해 위치를 확인하지 못했습니다.',
  },
  SOURCE_UNVERIFIED: {
    label: '원본 동일성 미확인',
    tone: 'bg-warning',
    confirmed: false,
    reason: '원본 파일의 해시 기록이 없어 같은 파일인지 확인하지 못했습니다.',
  },
  MISSING_DOCUMENT: {
    label: '연결 문서 없음',
    tone: 'bg-secondary',
    confirmed: false,
    reason: '연결된 문서가 없어 원문을 열 수 없습니다. 다른 문서로 추정해 연결하지 않았습니다.',
  },
  MISSING_SOURCE: {
    label: '원본 연결 없음',
    tone: 'bg-secondary',
    confirmed: false,
    reason: '수동 원본 연결이 없어 위치를 확인하지 못했습니다.',
  },
  AMBIGUOUS_SOURCE: {
    label: '원본 연결 중복',
    tone: 'bg-warning',
    confirmed: false,
    reason: '원본 연결이 둘 이상이라 어느 문서인지 정하지 않았습니다.',
  },
}

export const statusInfo = (loc) =>
  STATUS_INFO[loc?.status] || {
    label: loc?.status || '위치 정보 없음',
    tone: 'bg-secondary',
    confirmed: false,
    reason: '서버가 위치를 확정하지 않았습니다.',
  }

export const ROLE_NOTE = {
  REQUIREMENT_SOURCE: '공고 요구조건이 인용한 원문입니다.',
  STORED_EVALUATION_EVIDENCE:
    '저장된 판정이 기록한 근거입니다. 위치는 지금 원본과 다시 대조한 결과이며 판정을 바꾸지 않습니다.',
  CURRENT_COMPANY_REFERENCE:
    '현재 등록된 회사 참고자료의 위치입니다. 이미 저장된 판정에 반영된 근거가 아닙니다.',
}

// 위치 값의 종류를 사용자 언어로. HWP 등은 원본 페이지가 아니라 추출 텍스트 위치다.
export function kindLabel(kind, fileFormat) {
  if (kind === 'PDF_PAGE') return 'PDF 물리 페이지'
  if (kind === 'SPREADSHEET_CELL') return '엑셀 시트·셀'
  if (kind === 'EXTRACTED_TEXT_RANGE') {
    return fileFormat === 'HWP' ? '추출 텍스트 위치(원본 페이지 아님)' : '추출 텍스트 위치'
  }
  return '위치 미확정'
}

const FIELD_LABELS = {
  cert_no: '인증 번호',
  name: '명칭',
  cert_type: '종류',
  standard: '규격',
  holder: '인증 대상',
  scope: '인증 범위',
  product_codes: '세부품명번호',
  issuer: '발급 기관',
  issue_date: '인증일',
  valid_from: '유효 시작일',
  valid_until: '유효 종료일',
  business_no: '사업자등록번호',
  is_sme: '중소기업 여부',
  sme_cert_valid_until: '중소기업확인서 유효기간',
  ceo: '대표자',
  address: '주소',
  established_date: '설립일',
}
export const fieldLabel = (key) => FIELD_LABELS[key] || key
export const fieldsText = (loc) => (loc?.fields || []).map(fieldLabel).join(' · ')

// 호출부 공통: 위치 객체와 화면 설명으로 원문 패널 입력을 만든다.
export function viewerFromLocation(loc, extra = {}) {
  return {
    documentId: loc?.document_id ?? null,
    page: 0,
    quote: loc?.quote || '',
    kind: ROLE_KIND[loc?.role] || 'reference',
    location: loc,
    ...extra,
  }
}

// 위치 객체가 문서를 가리키는지(원문 패널을 열 수 있는지)
export const hasDocument = (loc) => Boolean(loc?.document_id)
