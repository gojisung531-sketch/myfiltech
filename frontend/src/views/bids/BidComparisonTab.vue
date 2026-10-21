<script setup>
// ② 회사 자료 비교 (specs/05 §3 ②)
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
const viewer = ref(null)
const suggest = ref(null) // item whose product changed → offer re-evaluation

async function load() {
  try {
    data.value = await getComparison(props.bid.id)
  } catch (err) {
    toast.error(errorMessage(err))
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

function open(target) {
  if (target.document_id) viewer.value = target.document_id
  else toast.show('연결된 원본 문서가 없습니다.', 'warning')
}
</script>

<template>
  <div>
    <div v-if="!data" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div v-if="data.items.length" class="row g-3 mb-3">
        <div v-for="item in data.items" :key="item.id" class="col-lg-6">
          <div class="card h-100">
            <div class="card-body small">
              <div class="fw-semibold mb-1">{{ item.item_no || '-' }}. {{ item.name }}</div>
              <div class="text-muted mb-2">{{ item.spec_text }}</div>
              <label class="form-label mb-1" :for="`cmp-${item.id}`">매칭 제품</label>
              <select
                :id="`cmp-${item.id}`"
                class="form-select form-select-sm"
                :value="item.matched_product || ''"
                :disabled="busy"
                @change="changeProduct(item, Number($event.target.value) || null)"
              >
                <option value="">매칭 제품 없음</option>
                <option v-for="c in item.candidates" :key="c.product" :value="c.product">
                  {{ c.model_no }} — {{ c.name }} (점수 {{ Math.round(c.score * 100) }})
                </option>
              </select>
              <div v-if="item.candidates.length" class="text-muted mt-1">
                {{ item.candidates.find((c) => c.product === item.matched_product)?.reason }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <EmptyState v-if="!data.rows.length" message="비교할 요구사항이 없습니다." />
      <div v-for="section in sections" :key="section.key" class="card mb-3">
        <div class="card-header fw-semibold">{{ section.label }}</div>
        <div class="table-responsive">
          <table class="table table-sm align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th style="width: 22%">요구사항</th>
                <th style="width: 18%">요구값</th>
                <th>회사 제품 사양</th>
                <th>시험성적서</th>
                <th>인증</th>
                <th>납품실적</th>
                <th>판정</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in section.rows" :key="row.requirement_id">
                <td>
                  <span class="text-muted">{{ row.category_label }}</span>
                  <div class="fw-semibold">{{ row.title }}</div>
                </td>
                <td>{{ row.requirement_value }}</td>
                <td>
                  <template v-if="row.product">
                    <span class="fw-semibold">{{ row.product.model_no }}</span>
                    <div>{{ row.product_spec }}</div>
                  </template>
                  <span v-else class="text-muted">-</span>
                </td>
                <td>
                  <button
                    v-for="r in row.test_reports"
                    :key="r.id"
                    class="btn btn-link btn-sm p-0 d-block text-start small"
                    @click="open(r)"
                  >
                    {{ r.label }}
                  </button>
                  <span v-if="!row.test_reports.length" class="text-muted">-</span>
                </td>
                <td>
                  <button
                    v-for="c in row.certificates"
                    :key="c.id"
                    class="btn btn-link btn-sm p-0 d-block text-start small"
                    @click="open(c)"
                  >
                    {{ c.label }}
                    <span v-if="c.status === 'EXPIRED'" class="badge bg-danger">만료</span>
                    <span v-else-if="c.status === 'EXPIRING'" class="badge bg-warning text-dark"
                      >만료 임박</span
                    >
                  </button>
                  <span v-if="!row.certificates.length" class="text-muted">-</span>
                </td>
                <td>
                  <button
                    v-for="d in row.delivery_records"
                    :key="d.id"
                    class="btn btn-link btn-sm p-0 d-block text-start small"
                    @click="open(d)"
                  >
                    {{ d.label }}
                  </button>
                  <span v-if="!row.delivery_records.length" class="text-muted">-</span>
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
        '{{ suggest?.name }}' 품목의 매칭 제품이 바뀌었습니다. 이 품목의 요구사항을 다시 판정할까요?
        (담당자가 수정한 판정은 유지됩니다)
      </p>
      <template #footer>
        <button class="btn btn-secondary" @click="suggest = null">나중에</button>
        <button class="btn btn-primary" :disabled="busy" @click="reevaluateItem">재판정</button>
      </template>
    </BaseModal>

    <DocumentOffcanvas :document-id="viewer" @close="viewer = null" />
  </div>
</template>
