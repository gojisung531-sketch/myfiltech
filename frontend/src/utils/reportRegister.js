// 관리대장 조회 화면 공통 표기. 서버가 준 값의 종류(null·0·false·빈 문자열)를 구분해 보여 준다.
export const REVIEW_STATUS = { PENDING: '검토 대기', NEEDS_CONFIRMATION: '확인 필요' }
export const OWNERSHIP = { UNKNOWN: '미확인', FILTECH: '필텍', THIRD_PARTY: '타사' }
export const TEST_TARGET = {
  UNKNOWN: '미확인',
  MEDIA: '여재',
  FINISHED_PRODUCT: '완제품',
  OTHER: '기타',
}

export const options = (map) => Object.entries(map).map(([value, label]) => ({ value, label }))

// 관계형 review의 Boolean: null은 '미확인', 명시적 true/false만 '예/아니오'
export function triState(value) {
  if (value === true) return '예'
  if (value === false) return '아니오'
  return '미확인'
}

// 값 표기: { text, empty }. empty=true면 흐리게 보여 주는 '값 없음' 계열 표기.
export function showValue(value) {
  if (value === null || value === undefined) return { text: '(없음)', empty: true }
  if (value === '') return { text: '(빈 문자열)', empty: true }
  if (typeof value === 'boolean') return { text: value ? 'true' : 'false', empty: false }
  if (typeof value === 'object') return { text: JSON.stringify(value), empty: false }
  return { text: String(value), empty: false }
}

// 목록 칸: null(키 없음/값 없음)은 '미기재', 빈 문자열은 '(빈 칸)'
export function listText(value) {
  if (value === null || value === undefined) return { text: '미기재', empty: true }
  if (value === '') return { text: '(빈 칸)', empty: true }
  return { text: String(value), empty: false }
}

// 필드의 헤더 라벨: 원본 헤더 셀 값을 이어 붙이고, 없으면 키를 그대로 쓴다.
export function headerLabel(field, key) {
  const parts = (field?.headers || [])
    .map((h) => (h && h.value !== null && h.value !== undefined ? String(h.value) : ''))
    .filter(Boolean)
  return parts.length ? parts.join(' / ') : key
}
