<script setup>
// ② 회사 자료 비교 (specs/05 §3 ②)
// 이 화면의 시험성적서·인증·납품실적은 서버가 연결했거나 후보로 돌려준 참고 자료다.
// 목록에 있다는 사실만으로 해당 요구조건의 충족 근거로 읽지 않는다. 판정은 서버 값만 표시한다.
import { computed, onMounted, ref } from 'vue'

import { bidItems, getComparison } from '@/api/bids'
import BaseModal from '@/components/BaseModal.vue'
import DocumentOffcanvas from '@/components/DocumentOffcanvas.vue'
import EmptyState from '@/components/EmptyState.vue'
import RiskDot from '@/components/RiskDot.vue'
import VerdictBadge from '@/components/VerdictBadge.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'

const props = defineProps({
  bid: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['evaluate', 'changed'])

const toast = useToastStore()
const data = ref(null)
const loadError = ref('')
const viewer = ref(null) // { documentId, title, text }
const suggest = ref(null) // item whose product changed → offer re-evaluation

async function load() {
  loadError.value = ''
  try {
    data.value = await getComparison(props.bid.id)
  } catch (err) {
    if (data.value) toast.error(errorMessage(err))
    else loadError.value = errorMessage(err, '비교 자료를 불러오지 못했습니다.')
  }
}
onMounted(load)

const sections = computed(() => {
  if (!data.value) return []
  const groups = data.value.items.map((item) => ({
    key: `i${item.id}`,
    label: `${item.item_no || '-'}. ${item.name}`,
    rows: data.value.rows.filter((r) => r.item_id === item.id),
  }))
  groups.push({
    key: 'common',
    label: '공통 요구사항 (자격·서류·납기 등)',
    rows: data.value.rows.filter((r) => !r.item_id),
  })
  return groups.filter((g) => g.rows.length)
})

// 비어 있는 이유를 서버 상태로만 구분한다.
const emptyMessage = computed(() => {
  const status = props.bid.processing_status
  if (status === 'DRAFT') return '아직 요구조건 추출을 실행하지 않아 비교할 요구사항이 없습니다.'
  if (status === 'EXTRACTING') return '요구조건 추출이 진행 중입니다.'
  if (status === 'FAILED')
    return '처리에 실패해 비교할 요구사항이 없을 수 있습니다. 상세 오류를 확인하세요.'
  return '저장된 요구사항이 없습니다. 추출 누락 가능성이 있으니 원문을 확인하세요.'
})

const hasEvaluation = computed(() => data.value?.rows.some((r) => r.verdict))

async function changeProduct(item, productId) {
  try {
    await bidItems.update(props.bid.id, item.id, { matched_product: productId || null })
    toast.success('매칭 제품을 변경했습니다.')
    await load()
    emit('changed')
    if (data.value.rows.some((r) => r.item_id === item.id)) suggest.value = item
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function reevaluateItem() {
  const ids = data.value.rows
    .filter((r) => r.item_id === suggest.value.id)
    .map((r) => r.requirement_id)
  suggest.value = null
  emit('evaluate', { keepModified: true, requirementIds: ids })
}

function open(target, kind, row) {
  if (target.document_id) {
    viewer.value = {
      documentId: target.document_id,
      title: `${row.title} — ${kind}`,
      text: target.label,
    }
  } else {
    toast.show(
      `이 ${kind}에는 연결된 원본 문서가 없습니다(문서 ID가 저장되지 않음). 자료 목록에서 직접 확인하세요.`,
      'warning',
    )
  }
}

const hasRefs = (row) =>
  row.test_reports.length || row.certificates.length || row.delivery_records.length
</script>

<template>
  <div>
    <div v-if="loadError" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ loadError }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
    </div>
    <div v-else-if="!data" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="alert alert-secondary small py-2">
        <i class="bi bi-info-circle me-1"></i>회사 값·제품 사양·참고 자료는 서로 다른 출처입니다.
        참고 자료는 서버가 연결했거나 후보로 제시한 것으로, 목록에 있다고 해서 해당 요구조건의 충족
        근거가 되는 것은 아닙니다. 판정은 서버가 계산한 값 그대로 표시합니다.
        <span class="text-muted">
          (판정 기준일 {{ data.reference_date
          }}<template v-if="data.is_simulation"> · 과거 공고를 오늘 기준으로 판정</template>)
        </span>
      </div>

      <div v-if="data.items.length" class="row g-3 mb-3">
        <div v-for="item in data.items" :key="item.id" class="col-lg-6">
          <div class="card h-100">
            <div class="card-body small">
              <div class="fw-semibold mb-1 text-break">
                {{ item.item_no || '-' }}. {{ item.name }}
              </div>
              <div class="text-muted mb-2 text-break">{{ item.spec_text }}</div>
              <label class="form-label mb-1" :for="`cmp-${item.id}`">연결 제품</label>
              <select
                :id="`cmp-${item.id}`"
                class="form-select form-select-sm"
                :value="item.matched_product || ''"
                :disabled="busy"
                @change="changeProduct(item, Number($event.target.value) || null)"
              >
                <option value="">연결 제품 없음</option>
                <option v-for="c in item.candidates" :key="c.product" :value="c.product">
                  {{ c.model_no }} — {{ c.name }} (매칭 점수 {{ Math.round(c.score * 100) }})
                </option>
              </select>
              <div v-if="item.candidates.length" class="text-muted mt-1">
                <template v-if="item.candidates.find((c) => c.product === item.matched_product)">
                  선택 사유:
                  {{ item.candidates.find((c) => c.product === item.matched_product).reason }}
                </template>
                <div>매칭 점수는 품목과 제품의 유사도이며 기술 적합도·낙찰 확률이 아닙니다.</div>
              </div>
              <div v-else class="text-muted mt-1">
                매칭 후보가 없습니다. 등록된 제품 자료가 없거나 연결할 제품이 없는 상태입니다.
              </div>
            </div>
          </div>
        </div>
      </div>

      <EmptyState
        v-if="!data.rows.length"
        :icon="bid.processing_status === 'DRAFT' ? 'bi-hourglass' : 'bi-question-circle'"
        :message="emptyMessage"
      />
      <div v-else-if="!hasEvaluation" class="alert alert-info small py-2">
        아직 판정을 실행하지 않았습니다. 아래 판정 열은 '미판정'이며 '확인 필요'와 다릅니다.
      </div>

      <div v-for="section in sections" :key="section.key" class="card mb-3">
        <div class="card-header fw-semibold text-break">{{ section.label }}</div>
        <div class="table-responsive">
          <table class="table table-sm align-top mb-0 small compare-table">
            <thead class="table-light">
              <tr>
                <th>요구사항</th>
                <th>요구 내용 (공고 원문 기준)</th>
                <th>연결 제품 · 제품 사양</th>
                <th>회사 값 (판정 시 서버 기록)</th>
                <th>연결·참고 자료</th>
                <th>서버 판정</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in section.rows" :key="row.requirement_id">
                <td>
                  <span class="text-muted">{{ row.category_label }}</span>
                  <div class="fw-semibold text-break">{{ row.title }}</div>
                </td>
                <td class="text-break">
                  {{ row.requirement_value }}
                  <div class="text-muted">단위·시험표준·시험조건은 원문에서 확인</div>
                </td>
                <td class="text-break">
                  <template v-if="row.product">
                    <span class="fw-semibold">{{ row.product.model_no }}</span>
                    <div v-if="row.product_spec">{{ row.product_spec }}</div>
                    <div v-else class="text-muted">이 항목의 제품 사양 정보 미제공</div>
                  </template>
                  <span v-else class="text-muted">연결된 제품 없음</span>
                </td>
                <td class="text-break">
                  <template v-if="row.company_value">{{ row.company_value }}</template>
                  <span v-else class="text-muted">
                    {{ row.verdict ? '기록된 회사 값 없음' : '판정 전' }}
                  </span>
                </td>
                <td>
                  <div v-if="row.test_reports.length" class="mb-1">
                    <div class="text-muted">시험성적서</div>
                    <button
                      v-for="r in row.test_reports"
                      :key="r.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(r, '시험성적서', row)"
                    >
                      {{ r.label }}
                    </button>
                  </div>
                  <div v-if="row.certificates.length" class="mb-1">
                    <div class="text-muted">인증</div>
                    <button
                      v-for="c in row.certificates"
                      :key="c.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(c, '인증', row)"
                    >
                      {{ c.label }}
                      <span v-if="c.status === 'EXPIRED'" class="badge bg-danger">만료</span>
                      <span v-else-if="c.status === 'EXPIRING'" class="badge bg-warning"
                        >만료 임박</span
                      >
                    </button>
                  </div>
                  <div v-if="row.delivery_records.length">
                    <div class="text-muted">납품실적</div>
                    <button
                      v-for="d in row.delivery_records"
                      :key="d.id"
                      class="btn btn-link btn-sm p-0 d-block text-start small text-break"
                      @click="open(d, '납품실적', row)"
                    >
                      {{ d.label }}
                    </button>
                  </div>
                  <span v-if="!hasRefs(row)" class="text-muted">자료 미등록 또는 연결 없음</span>
                </td>
                <td class="text-nowrap">
                  <VerdictBadge :verdict="row.verdict" />
                  <RiskDot :risk="row.risk_level" class="ms-1" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <BaseModal :show="!!suggest" title="재판정 제안" @close="suggest = null">
      <p class="small mb-0">
        '{{ suggest?.name }}' 품목의 연결 제품이 바뀌었습니다. 이 품목의 요구사항을 다시 판정할까요?
        (담당자가 수정한 판정은 유지됩니다)
      </p>
      <template #footer>
        <button class="btn btn-secondary" @click="suggest = null">나중에</button>
        <button class="btn btn-primary" :disabled="busy" @click="reevaluateItem">재판정</button>
      </template>
    </BaseModal>

    <DocumentOffcanvas
      :document-id="viewer?.documentId ?? null"
      kind="reference"
      :context-title="viewer?.title || ''"
      :context-text="viewer?.text || ''"
      position-note="이 화면은 자료의 위치(페이지)를 받지 않아 문서의 처음부터 표시합니다."
      @close="viewer = null"
    />
  </div>
</template>

<style scoped>
.compare-table {
  min-width: 62rem;
}
.compare-table th {
  white-space: nowrap;
}
</style>
