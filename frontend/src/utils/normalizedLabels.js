// 요구조건 정규화 값(normalized)의 표시명. 의미가 원문 표기(raw)나 키 이름으로 확인되는 항목만 매핑하고,
// 알 수 없는 키는 원본 키를 그대로 보여 준다(의미를 추측하지 않는다). 원본 키는 툴팁에 남긴다.
export const NORMALIZED_LABELS = {
  dia: { label: '외경(OD)', unit: 'mm' },
  dia2: { label: '보조 외경(OD)', unit: 'mm' },
  len: { label: '길이(L)', unit: 'mm' },
  raw: { label: '원문 표기' },
  value: { label: '기준값' },
  unit: { label: '단위' },
  operator: {
    label: '비교 방식',
    map: { '>=': '이상', '<=': '이하', '=': '같음', '>': '초과', '<': '미만' },
  },
  required_operator: {
    label: '필수 비교 방식',
    map: { '>=': '이상', '<=': '이하', '=': '같음', '>': '초과', '<': '미만' },
  },
  at_airflow_m3h: { label: '시험 풍량', unit: 'm³/h' },
  days_after_contract: { label: '계약 후 기한', unit: '일' },
  months: { label: '기간', unit: '개월' },
  period_years: { label: '기간', unit: '년' },
  min_amount_krw: { label: '최소 금액', unit: '원' },
  max_temp_c: { label: '최고 온도', unit: '℃' },
  min_temp_c: { label: '최저 온도', unit: '℃' },
  max_rh: { label: '최대 상대습도', unit: '%RH' },
  min_rh: { label: '최소 상대습도', unit: '%RH' },
  condition_rh_min: { label: '조건 최소 상대습도', unit: '%RH' },
  partial_allowed: { label: '분할 허용', bool: true },
  power_plant_only: { label: '발전소 실적만', bool: true },
  single_contract: { label: '단일 계약', bool: true },
  doc: { label: '문서' },
  timing: { label: '제출 시점' },
  deadline: { label: '기한', datetime: true },
  copies: { label: '부수' },
  delivery_copies: { label: '납품 부수', unit: '부' },
  note: { label: '비고' },
  standard: { label: '규격' },
  test_standard: { label: '시험 규격' },
  standards: { label: '규격' },
  required: { label: '필수 사양' },
  forbidden: { label: '금지 사양' },
  applicability: { label: '적용 조건' },
  product_code: { label: '품목 코드' },
}

export function describeNormalized(normalized) {
  return Object.entries(normalized || {})
    .filter(([k]) => k !== 'placeholder' && k !== 'interpretation_review')
    .map(([key, raw]) => {
      const def = NORMALIZED_LABELS[key]
      let value
      if (raw === null || raw === undefined) value = null
      else if (def?.map && def.map[raw]) value = def.map[raw]
      else if (def?.bool && typeof raw === 'boolean') value = raw ? '예' : '아니오'
      else if (Array.isArray(raw)) value = raw.length ? raw.join(', ') : '(없음)'
      else if (typeof raw === 'object') value = JSON.stringify(raw)
      else value = String(raw)
      return { key, known: !!def, label: def ? def.label : key, unit: def?.unit || '', value }
    })
}
