<script setup>
// ① 핵심 요구사항 (specs/05 §3 ①)
import { computed, onMounted, ref } from 'vue'

import { bidItems, bidRequirements } from '@/api/bids'
import { downloadDocument } from '@/api/documents'
import DocumentOffcanvas from '@/components/DocumentOffcanvas.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import {
  formatBytes,
  formatDateTime,
  formatKrw,
  formatNumber,
  productDimension,
} from '@/utils/format'
import { REQUIREMENT_CATEGORIES } from '@/utils/options'

const props = defineProps({ bid: { type: Object, required: true } })

// Minimum categories always shown, even when the notice has none (specs/05 §3 ①).
const MIN_CATEGORIES = [
  'DIMENSION',
  'FILTER_GRADE',
  'EFFICIENCY',
  'PRESSURE_DROP',
  'TEST_STANDARD',
  'CERTIFICATION',
  'DELIVERY',
  'SUBMISSION_DOC',
]

const toast = useToastStore()
const items = ref([])
const requirements = ref([])
const loading = ref(true)
const groupBy = ref('category')
const viewer = ref({ documentId: null, page: 0, quote: '' })

onMounted(async () => {
  try {
    ;[items.value, requirements.value] = await Promise.all([
      bidItems.list(props.bid.id),
      bidRequirements.list(props.bid.id),
    ])
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
})

const attachmentDocs = computed(() =>
  Object.fromEntries(props.bid.attachments.map((a) => [a.id, a.document_id])),
)

const groups = computed(() => {
  if (groupBy.value === 'item') {
    const keys = [null, ...items.value.map((i) => i.id)]
    return keys
      .map((id) => ({
        key: `i${id}`,
        label: id ? itemLabel(items.value.find((i) => i.id === id)) : '공고 공통',
        rows: requirements.value.filter((r) => r.item === id),
      }))
      .filter((g) => g.rows.length)
  }
  return REQUIREMENT_CATEGORIES.map((c) => ({
    key: c.value,
    label: c.label,
    rows: requirements.value.filter((r) => r.category === c.value),
  })).filter((g) => g.rows.length || MIN_CATEGORIES.includes(g.key))
})

const itemLabel = (item) => (item ? `${item.item_no || '-'}. ${item.name}` : '')

const overview = computed(() => {
  const b = props.bid
  return [
    ['입찰 개시', formatDateTime(b.bid_open_at)],
    ['입찰 마감', formatDateTime(b.bid_close_at)],
    ['개찰', formatDateTime(b.opening_at)],
    ['자격 등록 마감', formatDateTime(b.qualification_deadline_at)],
    ['배정예산', formatKrw(b.budget_krw)],
    ['추정가격', formatKrw(b.estimated_price_krw)],
    ['입찰방법', b.bid_method || '-'],
    ['물품분류', [b.item_category_code, b.item_category_name].filter(Boolean).join(' ') || '-'],
    ['납품기한', b.delivery_terms || '-'],
    ['납품장소', b.delivery_place || '-'],
    ['하자보증', b.warranty_terms || '-'],
    ['계약기관', b.contracting_org || '-'],
  ]
})

function openSource(r) {
  const documentId = attachmentDocs.value[r.source_attachment]
  if (documentId) viewer.value = { documentId, page: r.source_page || 0, quote: r.source_quote }
}

async function download(attachment) {
  try {
    const blob = await downloadDocument(attachment.document_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.display_name
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
</script>

<template>
  <div>
    <div class="row g-3 mb-3">
      <div class="col-lg-7">
        <div class="card h-100">
          <div class="card-header fw-semibold">공고 요약</div>
          <div class="card-body small">
            <p class="mb-3" style="white-space: pre-line">
              {{ bid.summary || '요약이 없습니다.' }}
            </p>
            <dl class="row mb-0">
              <template v-for="[label, value] in overview" :key="label">
                <dt class="col-sm-3 fw-normal text-muted">{{ label }}</dt>
                <dd class="col-sm-9 mb-1">{{ value }}</dd>
              </template>
            </dl>
          </div>
        </div>
      </div>
      <div class="col-lg-5">
        <div class="card h-100">
          <div class="card-header fw-semibold">첨부파일</div>
          <ul class="list-group list-group-flush small">
            <li
              v-for="a in bid.attachments"
              :key="a.id"
              class="list-group-item d-flex align-items-center"
            >
              <i class="bi bi-file-earmark me-2"></i>
              <span class="me-auto">
                {{ a.display_name }}
                <span v-if="a.is_primary" class="badge bg-primary ms-1">공고문</span>
                <span class="text-muted d-block"
                  >{{ a.category_name || '미분류' }} · {{ formatBytes(a.file_size) }}</span
                >
              </span>
              <button
                class="btn btn-sm btn-link"
                :aria-label="`${a.display_name} 보기`"
                @click="viewer = { documentId: a.document_id, page: 0, quote: '' }"
              >
                <i class="bi bi-eye"></i>
              </button>
              <button
                v-if="a.has_file"
                class="btn btn-sm btn-link"
                :aria-label="`${a.display_name} 다운로드`"
                @click="download(a)"
              >
                <i class="bi bi-download"></i>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card mb-3">
      <div class="card-header fw-semibold">품목</div>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0 small">
          <thead class="table-light">
            <tr>
              <th>품번</th>
              <th>품명</th>
              <th>규격</th>
              <th class="text-end">수량</th>
              <th>매칭 제품 후보</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!items.length && !loading">
              <td colspan="5" class="text-muted text-center py-3">품목이 없습니다.</td>
            </tr>
            <tr v-for="item in items" :key="item.id">
              <td>{{ item.item_no || '-' }}</td>
              <td>
                {{ item.name }}
                <div class="text-muted">{{ item.filter_type_label }}</div>
              </td>
              <td>
                {{ productDimension(item) }}
                <div class="text-muted" style="white-space: pre-line">{{ item.spec_text }}</div>
              </td>
              <td class="text-end text-nowrap">
                {{ formatNumber(item.quantity) }} {{ item.unit }}
              </td>
              <td>
                <div v-for="c in item.candidates" :key="c.product">
                  <span :class="{ 'fw-semibold': c.product === item.matched_product }">
                    {{ c.model_no }}
                  </span>
                  <span class="text-muted">({{ Math.round(c.score * 100) }})</span>
                </div>
                <span v-if="!item.candidates.length" class="text-muted">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-header d-flex align-items-center">
        <span class="fw-semibold me-auto">요구사항</span>
        <div class="btn-group btn-group-sm" role="group" aria-label="그룹 기준">
          <button
            class="btn"
            :class="groupBy === 'category' ? 'btn-secondary' : 'btn-outline-secondary'"
            @click="groupBy = 'category'"
          >
            카테고리별
          </button>
          <button
            class="btn"
            :class="groupBy === 'item' ? 'btn-secondary' : 'btn-outline-secondary'"
            @click="groupBy = 'item'"
          >
            품목별
          </button>
        </div>
      </div>
      <div v-if="loading" class="text-center py-4">
        <span class="spinner-border spinner-border-sm"></span>
      </div>
      <EmptyState v-else-if="!requirements.length" message="추출된 요구사항이 없습니다." />
      <table v-else class="table table-sm align-middle mb-0 small">
        <tbody v-for="group in groups" :key="group.key">
          <tr class="table-light">
            <th colspan="3">
              {{ group.label }} <span class="text-muted fw-normal">({{ group.rows.length }})</span>
            </th>
          </tr>
          <tr v-if="!group.rows.length">
            <td colspan="3" class="text-muted ps-4">공고에 명시된 요구사항 없음</td>
          </tr>
          <tr
            v-for="r in group.rows"
            :key="r.id"
            :class="{ 'table-warning': r.normalized?.placeholder }"
          >
            <td class="ps-4" style="width: 55%">
              <span class="fw-semibold">{{ r.title }}</span>
              <span v-if="r.is_mandatory" class="badge bg-danger ms-1">필수</span>
              <span v-if="groupBy === 'category' && r.item_label" class="text-muted ms-1"
                >· {{ r.item_label }}</span
              >
              <span v-if="groupBy === 'item'" class="text-muted ms-1"
                >· {{ r.category_label }}</span
              >
              <div class="text-muted">{{ r.requirement_text }}</div>
            </td>
            <td>
              <button
                v-if="r.source_attachment_name"
                class="btn btn-link btn-sm p-0 text-start small"
                :title="r.source_quote"
                @click="openSource(r)"
              >
                <i class="bi bi-quote me-1"></i>{{ r.source_attachment_name
                }}<span v-if="r.source_page"> p.{{ r.source_page }}</span>
              </button>
              <span v-else class="text-muted">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <DocumentOffcanvas
      :document-id="viewer.documentId"
      :page="viewer.page"
      :quote="viewer.quote"
      @close="viewer = { documentId: null, page: 0, quote: '' }"
    />
  </div>
</template>
