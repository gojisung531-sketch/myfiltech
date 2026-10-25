<script setup>
// 관리대장 한 행의 상세: 관계형 검토 상태 + 저장된 원본 payload(셀 근거). 읽기 전용.
// 위치는 관리대장의 시트/셀이며 원본 성적서 PDF의 위치가 아니다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getRegisterRow } from '@/api/reportRegister'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'
import {
  headerLabel,
  OWNERSHIP,
  REVIEW_STATUS,
  showValue,
  TEST_TARGET,
  triState,
} from '@/utils/reportRegister'

const props = defineProps({ rowId: { type: Number, required: true } })
const emit = defineEmits(['close'])

const row = ref(null)
const loading = ref(true)
const error = ref('')
let seq = 0 // 행을 바꿀 때 이전 행의 늦은 응답이 섞이지 않게 한다.

async function load() {
  const mine = ++seq
  row.value = null
  error.value = ''
  loading.value = true
  try {
    const result = await getRegisterRow(props.rowId)
    if (mine === seq) row.value = result
  } catch (err) {
    if (mine === seq) error.value = errorMessage(err, '행 상세를 불러오지 못했습니다.')
  } finally {
    if (mine === seq) loading.value = false
  }
}
watch(() => props.rowId, load, { immediate: true })
onBeforeUnmount(() => (seq += 1))

const payload = computed(() => row.value?.payload || {})
const fields = computed(() => Object.entries(payload.value.fields || {}))
const warnings = computed(() => payload.value.warnings || [])
const unmapped = computed(() => payload.value.unmapped_cells || [])
// 목록 요약 항목이 원본에서 어떤 상태인지: 저장된 필드 자체가 없으면 '열 없음', 키는 있고 값이 null이면 '칸 비어 있음'.
const SUMMARY_FIELDS = [
  ['report_no', '성적서번호'],
  ['model', '모델'],
  ['sample_name', '시료명'],
  ['test_standard', '시험규격'],
  ['lab_name', '시험기관'],
  ['issue_date', '발행일'],
]
const summaryStates = computed(() =>
  SUMMARY_FIELDS.map(([key, label]) => {
    const all = payload.value.fields || {}
    if (!(key in all)) return { key, label, state: '원본에 열 없음(저장된 필드 없음)', muted: true }
    const value = all[key]?.value
    if (value === null || value === undefined) {
      return { key, label, state: '원본 칸 비어 있음(값 없음)', muted: true }
    }
    if (value === '') return { key, label, state: '빈 문자열', muted: true }
    return { key, label, state: '값 있음', muted: false }
  }),
)
const KNOWN = ['fields', 'review', 'source', 'warnings', 'unmapped_cells']
const extra = computed(() =>
  Object.fromEntries(Object.entries(payload.value).filter(([k]) => !KNOWN.includes(k))),
)

function cellText(f) {
  if (!f.cell) return '-'
  return f.requested_cell && f.requested_cell !== f.cell
    ? `${f.cell} (요청 ${f.requested_cell})`
    : f.cell
}
function normalizedText(f) {
  const n = f.normalized
  if (!n) return null
  return `${n.value ?? '-'} ${n.unit ?? ''}`.trim()
}
</script>

<template>
  <div>
    <div v-if="loading" class="text-center py-5"><span class="spinner-border"></span></div>
    <div v-else-if="error" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
      <span class="flex-grow-1">{{ error }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
      <button class="btn btn-sm btn-outline-secondary" @click="emit('close')">목록으로</button>
    </div>
    <template v-else-if="row">
      <div class="small text-muted mb-3">
        관리대장 파일 버전 #{{ row.file_version }} · 시트 <strong>{{ row.source.sheet }}</strong> ·
        원본 {{ row.source.row }}행 · 행 ID {{ row.id }}
        <div>위치는 관리대장의 시트/셀입니다(원본 시험성적서 PDF 위치가 아님).</div>
      </div>

      <h3 class="h6">검토 상태 <span class="fw-normal text-muted">(관계형 기록)</span></h3>
      <dl class="row small mb-3">
        <dt class="col-sm-4 fw-normal text-muted">검토 상태</dt>
        <dd class="col-sm-8">
          {{ REVIEW_STATUS[row.review.review_status] || row.review.review_status }}
        </dd>
        <dt class="col-sm-4 fw-normal text-muted">소유 구분</dt>
        <dd class="col-sm-8">{{ OWNERSHIP[row.review.ownership] || row.review.ownership }}</dd>
        <dt class="col-sm-4 fw-normal text-muted">시험 대상</dt>
        <dd class="col-sm-8">
          {{ TEST_TARGET[row.review.test_target] || row.review.test_target }}
        </dd>
        <dt class="col-sm-4 fw-normal text-muted">시험기관 인정</dt>
        <dd class="col-sm-8">{{ triState(row.review.is_lab_accredited) }}</dd>
        <dt class="col-sm-4 fw-normal text-muted">공식 인증 시험</dt>
        <dd class="col-sm-8">{{ triState(row.review.is_official_certification) }}</dd>
        <dt class="col-sm-4 fw-normal text-muted">원본 성적서 대조</dt>
        <dd class="col-sm-8">{{ triState(row.review.original_report_verified) }}</dd>
      </dl>

      <h3 class="h6">
        경고 <span class="fw-normal text-muted">({{ row.warning_count }}건)</span>
      </h3>
      <div v-if="!warnings.length" class="small text-muted mb-3">저장된 경고가 없습니다.</div>
      <div v-else class="table-responsive mb-3">
        <table class="table table-sm small mb-0 w-auto warn-table">
          <thead>
            <tr>
              <th>코드</th>
              <th>필드</th>
              <th>셀</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(w, i) in warnings" :key="i">
              <td class="text-break">{{ w.code }}</td>
              <td class="text-break">{{ w.field || '-' }}</td>
              <td>{{ w.cell || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 class="h6">목록 요약 항목의 원본 상태</h3>
      <dl class="state-grid small mb-3">
        <div v-for="s in summaryStates" :key="s.key">
          <dt>{{ s.label }}</dt>
          <dd :class="{ 'text-muted': s.muted }">{{ s.state }}</dd>
        </div>
      </dl>

      <h3 class="h6">
        저장된 필드 값 <span class="fw-normal text-muted">({{ fields.length }}개)</span>
      </h3>
      <div class="table-responsive mb-3">
        <table class="table table-sm small align-top mb-0 fields-table">
          <thead>
            <tr>
              <th>항목 (원본 헤더 · 키)</th>
              <th>값</th>
              <th>단위</th>
              <th>정규화</th>
              <th>셀</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[key, f] in fields" :key="key">
              <td class="text-break">
                {{ headerLabel(f, key) }}
                <div class="text-muted key-code">{{ key }}</div>
              </td>
              <td class="text-break">
                <span :class="{ 'text-muted fst-italic': showValue(f.value).empty }">{{
                  showValue(f.value).text
                }}</span>
              </td>
              <td class="text-break">
                <template v-if="f.unit">{{ showValue(f.unit.value).text }}</template>
                <span v-else class="text-muted">-</span>
              </td>
              <td class="text-break">
                <template v-if="normalizedText(f)">{{ normalizedText(f) }}</template>
                <span v-else class="text-muted">없음</span>
              </td>
              <td class="text-nowrap">
                {{ cellText(f) }}
                <div v-if="f.merged_range" class="text-muted">병합 {{ f.merged_range }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <details class="ft-help mb-2">
        <summary>셀 근거 상세 (원값·수식·서식)</summary>
        <div class="table-responsive">
          <table class="table table-sm small align-top mb-0 detail-table">
            <thead>
              <tr>
                <th>키</th>
                <th>셀 / 요청 셀</th>
                <th>병합 범위</th>
                <th>원값</th>
                <th>XML 값</th>
                <th>수식 / 캐시값</th>
                <th>형식 / 서식</th>
                <th>헤더 셀</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="[key, f] in fields" :key="key">
                <td class="text-break">{{ key }}</td>
                <td class="text-nowrap">{{ f.cell || '-' }} / {{ f.requested_cell || '-' }}</td>
                <td>{{ f.merged_range || '-' }}</td>
                <td class="text-break">{{ showValue(f.raw_value).text }}</td>
                <td class="text-break">{{ showValue(f.xml_value).text }}</td>
                <td class="text-break">
                  {{ f.formula ? f.formula : '-' }}
                  <div
                    v-if="f.cached_value !== null && f.cached_value !== undefined"
                    class="text-muted"
                  >
                    캐시 {{ showValue(f.cached_value).text }}
                  </div>
                </td>
                <td class="text-break">{{ f.value_type || '-' }} / {{ f.number_format || '-' }}</td>
                <td class="text-break">
                  <div v-for="(h, i) in f.headers || []" :key="i">
                    {{ h.cell }}: {{ showValue(h.value).text
                    }}<span v-if="h.merged_range" class="text-muted">
                      (병합 {{ h.merged_range }})</span
                    >
                  </div>
                  <span v-if="!(f.headers || []).length" class="text-muted">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <details class="ft-help mb-2">
        <summary>매핑되지 않은 셀 ({{ unmapped.length }}개)</summary>
        <pre v-if="unmapped.length" class="small mb-0 raw">{{
          JSON.stringify(unmapped, null, 2)
        }}</pre>
        <p v-else>저장된 항목이 없습니다.</p>
      </details>

      <details class="ft-help mb-2">
        <summary>읽기 당시 스냅샷 (payload.review) · 출처 · SHA</summary>
        <p>
          아래는 파일을 읽을 당시 저장된 값이며 위의 관계형 검토 상태와 별개입니다.
          <code>original_report_verified=false</code>는 읽는 시점에 PDF 대조를 하지 않았다는
          표시이며 대조 실패가 아닙니다.
        </p>
        <pre class="small raw">{{ JSON.stringify(payload.review ?? null, null, 2) }}</pre>
        <p class="mb-0 text-break">
          출처: 시트 {{ payload.source?.sheet }} · {{ payload.source?.row }}행<br />
          파일 SHA-256: {{ payload.source?.file_sha256 }}
        </p>
        <p class="mb-0">
          저장 {{ formatDateTime(row.created_at) }} · 갱신 {{ formatDateTime(row.updated_at) }}
        </p>
      </details>

      <details v-if="Object.keys(extra).length" class="ft-help mb-2">
        <summary>기타 저장 항목 (알려진 구조 밖의 키)</summary>
        <pre class="small mb-0 raw">{{ JSON.stringify(extra, null, 2) }}</pre>
      </details>
    </template>
  </div>
</template>

<style scoped>
.state-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.3rem 1rem;
}
.state-grid dt {
  font-weight: 400;
  color: var(--ft-muted);
}
.state-grid dd {
  margin: 0;
}
.warn-table {
  min-width: 26rem;
}
.fields-table {
  min-width: 38rem;
}
.detail-table {
  min-width: 56rem;
}
.key-code {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.75rem;
}
.raw {
  white-space: pre-wrap;
  background: var(--ft-bg);
  border: 1px solid var(--ft-border);
  border-radius: 0.3rem;
  padding: 0.5rem;
  max-height: 18rem;
  overflow: auto;
}
</style>
