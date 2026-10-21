// Quick-form keys for BidRequirement.normalized per category (mirrors the bid.extract prompt
// guide). Anything else is edited in the JSON box.
import { CERT_TYPES, FILTER_TYPES } from '@/utils/options'

const GRADE_STANDARDS = ['EN1822', 'ISO16890', 'ISO29461', 'EN779', 'ASHRAE52_2'].map((v) => ({
  value: v,
  label: v,
}))
const OPERATORS = ['>=', '<=', '=', '>', '<'].map((v) => ({ value: v, label: v }))

const num = (key, label, unit) => ({ key, label, type: 'number', unit })
const text = (key, label) => ({ key, label })
const select = (key, label, options) => ({ key, label, type: 'select', options })
const bool = (key, label) => ({ key, label, type: 'bool' })

export const NORMALIZED_FIELDS = {
  DIMENSION: [
    num('w', '폭', 'mm'),
    num('h', '높이', 'mm'),
    num('d', '깊이', 'mm'),
    num('d_max', '깊이 상한', 'mm'),
    num('dia', '외경', 'mm'),
    num('dia2', '외경2', 'mm'),
    num('len', '길이', 'mm'),
  ],
  FILTER_TYPE: [select('type', '형식', FILTER_TYPES)],
  FILTER_GRADE: [
    select('standard', '규격', GRADE_STANDARDS),
    text('class', '등급'),
    select('operator', '조건', OPERATORS),
  ],
  EFFICIENCY: [
    text('metric', '지표'),
    select('operator', '조건', OPERATORS),
    num('value', '값', '%'),
    text('test_standard', '시험규격'),
  ],
  PRESSURE_DROP: [
    select('metric', '구분', [
      { value: 'initial_dp', label: '초기 차압' },
      { value: 'final_dp', label: '최종 차압' },
    ]),
    select('operator', '조건', OPERATORS),
    num('value', '값', 'Pa'),
    num('at_airflow_m3h', '기준 풍량', 'm³/h'),
  ],
  AIRFLOW: [num('value', '풍량', 'm³/h')],
  ENVIRONMENT: [num('max_temp_c', '최고 온도', '℃'), num('max_rh', '최고 습도', '%')],
  FIRE_RATING: [text('standard', '규격'), text('class', '등급')],
  TEST_STANDARD: [text('standard', '규격'), text('lab_requirement', '시험기관 조건')],
  CERTIFICATION: [
    select('cert_type', '인증 종류', [
      ...CERT_TYPES,
      { value: 'G2B_ITEM', label: '나라장터 물품 등록' },
    ]),
    text('product_code', '세부품명번호'),
    text('required_note', '필수 특이사항'),
  ],
  TRACK_RECORD: [
    num('period_years', '기간', '년'),
    num('min_amount_krw', '최소 금액', '원'),
    bool('single_contract', '단일 계약'),
    bool('power_plant_only', '발전소 실적만'),
    text('spec_condition', '조건 원문'),
  ],
  DELIVERY: [num('days_after_contract', '계약 후', '일'), bool('partial_allowed', '분할 납품')],
  SUBMISSION_DOC: [
    text('doc', '서류'),
    select(
      'timing',
      '제출 시점',
      ['입찰 시', '계약 시', '납품 시'].map((v) => ({ value: v, label: v })),
    ),
  ],
  WARRANTY: [num('months', '기간', '개월')],
  INSPECTION: [text('type', '검사 종류'), text('standard', '규격'), num('samples', '시료 수')],
}
