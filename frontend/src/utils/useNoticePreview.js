// 붙여 넣은 공고 본문에서 기본 정보를 읽어 편집 가능한 값으로 유지한다.
// - 입력할 때마다 요청하지 않고(대기 후 1회), 새 요청이 시작되면 이전 요청은 취소·무시한다.
// - 사용자가 직접 고친 값은 자동 응답이 덮어쓰지 않는다.
// - 등록에는 "지금 본문과 같은 본문으로 읽은 결과"만 보낸다.
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

import { previewNoticeMetadata } from '@/api/bids'
import { errorMessage } from '@/utils/errors'
import { toLocalInput } from '@/utils/format'

// 먼저 보여 줄 항목 / 접어 둘 항목. 서버가 준 값의 키는 기존 공고 필드명과 같다.
export const PRIMARY_FIELDS = [
  { key: 'title', label: '공고명', col: 'col-12' },
  { key: 'notice_no', label: '공고번호', col: 'col-md-6' },
  { key: 'buyer_org', label: '수요기관', col: 'col-md-6' },
  { key: 'contracting_org', label: '계약기관', col: 'col-md-6' },
  { key: 'budget_krw', label: '배정예산', type: 'number', unit: '원', col: 'col-md-6' },
  { key: 'estimated_price_krw', label: '추정가격', type: 'number', unit: '원', col: 'col-md-6' },
  { key: 'bid_open_at', label: '입찰 개시', type: 'datetime', col: 'col-md-6' },
  { key: 'bid_close_at', label: '입찰 마감', type: 'datetime', col: 'col-md-6' },
  { key: 'opening_at', label: '개찰', type: 'datetime', col: 'col-md-6' },
  { key: 'qualification_deadline_at', label: '자격 등록 마감', type: 'datetime', col: 'col-md-6' },
]
export const EXTRA_FIELDS = [
  { key: 'plant_name', label: '발전소/사업장', col: 'col-md-6' },
  { key: 'bid_method', label: '입찰방식', col: 'col-md-6' },
  { key: 'procurement_type', label: '조달 구분', col: 'col-md-6' },
  { key: 'item_category_code', label: '물품분류번호', col: 'col-md-6' },
  { key: 'item_category_name', label: '물품분류명', col: 'col-md-6' },
  { key: 'delivery_terms', label: '납품기한', col: 'col-md-6' },
  { key: 'delivery_place', label: '납품장소', col: 'col-md-6' },
  { key: 'warranty_terms', label: '하자보증', col: 'col-md-6' },
  { key: 'summary', label: '요약', type: 'textarea', col: 'col-12' },
]
export const FIELDS = [...PRIMARY_FIELDS, ...EXTRA_FIELDS]
const FIELD_BY_KEY = Object.fromEntries(FIELDS.map((f) => [f.key, f]))
export const fieldLabel = (key) => FIELD_BY_KEY[key]?.label || ''

const WAIT_MS = 700
const PASTE_WAIT_MS = 150
const MIN_CHARS = 10

const isBlank = (v) => v === null || v === undefined || String(v).trim() === ''

// 서버 값 → 입력칸 값
function toInput(field, value) {
  if (isBlank(value)) return ''
  if (field.type === 'datetime') return toLocalInput(value)
  return String(value)
}

// 입력칸 값 → API 값(고친 값만 변환한다. 고치지 않은 값은 서버 값을 그대로 돌려보낸다)
function fromInput(field, value) {
  if (isBlank(value)) return null
  if (field.type === 'number') {
    const n = Number(value)
    return Number.isFinite(n) && n >= 0 ? Math.round(n) : null
  }
  if (field.type === 'datetime') {
    const v = String(value)
    return v.length === 16 ? `${v}:00+09:00` : v
  }
  return String(value).trim()
}

export function useNoticePreview(sourceText) {
  // idle | waiting | loading | ready | error
  const status = ref('idle')
  const error = ref('')
  const shown = ref(null) // 마지막으로 성공한 응답 + 그때의 본문
  const vals = reactive({}) // 입력칸 값
  const edited = reactive({}) // key → true (사용자가 직접 고친 항목)
  const kept = ref([]) // 자동 응답 때문에 덮어쓰지 않고 유지한 항목 [{key, found}]

  let timer = null
  let seq = 0
  let controller = null

  const text = () => sourceText.value
  const canRead = () => text().trim().length >= MIN_CHARS

  function cancelPending() {
    clearTimeout(timer)
    timer = null
    if (controller) controller.abort()
    controller = null
    seq += 1 // 이미 나간 응답도 무시한다
  }

  function apply(res, readText) {
    const values = res?.values || {}
    const keptNow = []
    for (const f of FIELDS) {
      const serverValue = toInput(f, values[f.key])
      if (edited[f.key]) {
        if (serverValue && serverValue !== vals[f.key]) keptNow.push(f.key)
        continue
      }
      vals[f.key] = serverValue
    }
    kept.value = keptNow
    shown.value = {
      text: readText,
      sha: res?.source_sha256 || '',
      values,
      evidence: res?.evidence || {},
      warnings: Array.isArray(res?.warnings) ? res.warnings : [],
    }
  }

  async function run() {
    clearTimeout(timer)
    timer = null
    if (!canRead()) {
      status.value = 'idle'
      return
    }
    if (controller) controller.abort()
    const mine = ++seq
    const readText = text()
    controller = new AbortController()
    status.value = 'loading'
    error.value = ''
    try {
      const res = await previewNoticeMetadata(readText, { signal: controller.signal })
      if (mine !== seq) return // 더 새로운 요청이 있다
      apply(res, readText)
      status.value = 'ready'
    } catch (err) {
      if (mine !== seq || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return
      // 이전 결과는 현재 본문의 결과가 아니므로 등록에 쓰지 않는다. 입력값은 보존한다.
      // 이전 본문에서 자동으로 채운 값도 현재 본문의 값이 아니므로 비운다(직접 고친 값은 유지).
      shown.value = null
      kept.value = []
      for (const f of FIELDS) if (!edited[f.key]) vals[f.key] = ''
      error.value = errorMessage(err, '본문에서 기본 정보를 읽지 못했습니다.')
      status.value = 'error'
    }
  }

  function schedule(ms = WAIT_MS) {
    clearTimeout(timer)
    if (!canRead()) {
      cancelPending()
      shown.value = null
      kept.value = []
      for (const f of FIELDS) if (!edited[f.key]) vals[f.key] = ''
      status.value = 'idle'
      return
    }
    status.value = 'waiting'
    timer = setTimeout(run, ms)
  }

  watch(sourceText, () => schedule())
  onBeforeUnmount(cancelPending)

  const matchesText = computed(() => shown.value && shown.value.text === text())
  // 화면에 보이는 결과가 지금 본문 기준인가
  const current = computed(() => status.value === 'ready' && matchesText.value)

  function touch(key) {
    edited[key] = true
    kept.value = kept.value.filter((k) => k !== key)
  }
  function restore(key) {
    // 자동 값으로 되돌린다(현재 본문 기준 결과가 있을 때만)
    if (!shown.value) return
    delete edited[key]
    vals[key] = toInput(FIELD_BY_KEY[key], shown.value.values[key])
    kept.value = kept.value.filter((k) => k !== key)
  }
  function reset() {
    cancelPending()
    shown.value = null
    kept.value = []
    status.value = 'idle'
    error.value = ''
    for (const k of Object.keys(edited)) delete edited[k]
    for (const f of FIELDS) vals[f.key] = ''
  }

  // 등록 요청에 실을 notice_metadata. 현재 본문과 일치하는 읽기 결과가 없으면 null.
  function payload() {
    if (!current.value) return null
    const out = { ...shown.value.values }
    const editedKeys = []
    for (const f of FIELDS) {
      if (!edited[f.key]) continue
      const v = fromInput(f, vals[f.key])
      // 건명은 비울 수 없다 → 비우면 수정으로 보내지 않는다(자동값 또는 기존 입력 규칙 유지).
      if (f.key === 'title' && v === null) continue
      editedKeys.push(f.key)
      // 지우려면 값을 보내고 수정 항목에 표시해야 한다(텍스트 '', 금액·일시 null).
      out[f.key] = v === null ? (f.type === 'number' || f.type === 'datetime' ? null : '') : v
    }
    return { source_sha256: shown.value.sha, values: out, edited_fields: editedKeys }
  }

  return {
    status,
    error,
    shown,
    vals,
    edited,
    kept,
    current,
    touch,
    restore,
    reset,
    payload,
    retry: () => run(),
    onPaste: () => schedule(PASTE_WAIT_MS),
    canRead,
  }
}
