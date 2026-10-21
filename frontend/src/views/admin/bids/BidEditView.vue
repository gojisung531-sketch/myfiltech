<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { deleteBid, extractBid, getBid, updateBid } from '@/api/bids'
import ConfirmModal from '@/components/ConfirmModal.vue'
import EntityForm from '@/components/EntityForm.vue'
import JobProgress from '@/components/JobProgress.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { PROCESSING_STATUS_VARIANT, toLocalInput } from '@/utils/format'
import { BID_OUTCOMES } from '@/utils/options'

import BidAttachmentsTab from './BidAttachmentsTab.vue'
import BidDeleteModal from './BidDeleteModal.vue'
import BidFitCard from './BidFitCard.vue'
import BidItemsTab from './BidItemsTab.vue'
import BidRequirementsTab from './BidRequirementsTab.vue'

const TABS = [
  { key: 'meta', label: '메타데이터' },
  { key: 'attachments', label: '첨부' },
  { key: 'items', label: '품목' },
  { key: 'requirements', label: '요구사항' },
]
const DATETIME_FIELDS = ['bid_open_at', 'bid_close_at', 'opening_at', 'qualification_deadline_at']
const FIELDS = [
  { key: 'title', label: '공고명', required: true, col: 'col-12' },
  { key: 'notice_no', label: '공고번호', col: 'col-md-4' },
  { key: 'buyer_org', label: '수요기관', col: 'col-md-4' },
  { key: 'contracting_org', label: '계약기관', col: 'col-md-4' },
  { key: 'plant_name', label: '발전소/사업장', col: 'col-md-4' },
  { key: 'bid_method', label: '입찰방식', col: 'col-md-4' },
  { key: 'procurement_type', label: '조달 구분', col: 'col-md-4' },
  { key: 'item_category_code', label: '물품분류번호', col: 'col-md-4' },
  { key: 'item_category_name', label: '물품분류명', col: 'col-md-4' },
  {
    key: 'is_power_plant',
    label: '발전소 공고',
    type: 'select',
    col: 'col-md-4',
    options: [
      { value: true, label: '예' },
      { value: false, label: '아니오' },
    ],
  },
  { key: 'budget_krw', label: '배정예산', type: 'number', unit: '원', col: 'col-md-6' },
  { key: 'estimated_price_krw', label: '추정가격', type: 'number', unit: '원', col: 'col-md-6' },
  { key: 'bid_open_at', label: '입찰 개시', type: 'datetime', col: 'col-md-3' },
  { key: 'bid_close_at', label: '입찰 마감', type: 'datetime', col: 'col-md-3' },
  { key: 'opening_at', label: '개찰', type: 'datetime', col: 'col-md-3' },
  { key: 'qualification_deadline_at', label: '자격 등록 마감', type: 'datetime', col: 'col-md-3' },
  { key: 'delivery_terms', label: '납품기한', col: 'col-md-4' },
  { key: 'delivery_place', label: '납품장소', col: 'col-md-4' },
  { key: 'warranty_terms', label: '하자보증', col: 'col-md-4' },
  { key: 'buyer_contact', label: '수요기관 담당자', type: 'json', rows: 3, empty: {} },
  { key: 'contract_contact', label: '계약 담당자', type: 'json', rows: 3, empty: {} },
  { key: 'summary', label: '요약', type: 'textarea', col: 'col-12', rows: 3 },
  {
    key: 'outcome',
    label: '낙찰 결과',
    type: 'select',
    required: true,
    col: 'col-md-4',
    options: BID_OUTCOMES,
  },
]

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const bid = ref(null)
const form = ref(null)
const formRef = ref(null)
const saving = ref(false)
const jobId = ref(null)
const deleting = ref(null)
const tab = computed(() => route.query.tab || 'meta')
const bidId = computed(() => Number(route.params.id))

function toForm(data) {
  const values = Object.fromEntries(FIELDS.map((f) => [f.key, data[f.key]]))
  for (const key of DATETIME_FIELDS) values[key] = toLocalInput(data[key])
  return values
}

async function load() {
  try {
    bid.value = await getBid(bidId.value)
    form.value = toForm(bid.value)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)
watch(bidId, load)

function setTab(key) {
  router.replace({ query: { ...route.query, tab: key } })
}

async function save() {
  let payload
  try {
    payload = formRef.value.collect()
  } catch (err) {
    toast.error(err.message)
    return
  }
  saving.value = true
  try {
    bid.value = await updateBid(bidId.value, payload)
    form.value = toForm(bid.value)
    toast.success('저장했습니다. 수정한 항목은 다시 추출해도 유지됩니다.')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    saving.value = false
  }
}

async function unlock(field) {
  try {
    bid.value = await updateBid(bidId.value, { unlock_fields: [field] })
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

const confirmExtract = ref(false)

function askExtract() {
  // Re-extraction replaces unlocked requirements and their verdicts (specs/08 §2).
  if (bid.value.modified_evaluation_count) confirmExtract.value = true
  else runExtract()
}

async function runExtract() {
  confirmExtract.value = false
  try {
    const res = await extractBid(bidId.value)
    jobId.value = res.job_id
    bid.value.processing_status = 'EXTRACTING'
    bid.value.processing_status_label = '추출 중'
  } catch (err) {
    if (err.response?.data?.code !== 'llm_not_configured') toast.error(errorMessage(err))
  }
}

async function onExtractDone(job) {
  jobId.value = null
  if (job.status === 'SUCCEEDED') {
    const r = job.result
    toast.success(`추출 완료: 품목 ${r.items}개, 요구사항 ${r.requirements}건`)
  } else if (job.status === 'FAILED') {
    toast.error(job.error || '추출에 실패했습니다.')
  }
  await load()
}

async function doDelete() {
  try {
    await deleteBid(bidId.value)
    toast.success('공고를 삭제했습니다.')
    router.push('/admin/bids')
  } catch (err) {
    toast.error(errorMessage(err))
    deleting.value = null
  }
}

const fieldLabel = (key) => FIELDS.find((f) => f.key === key)?.label || key
</script>

<template>
  <div>
    <div v-if="!bid" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <router-link to="/admin/bids" class="btn btn-sm btn-outline-secondary">
          <i class="bi bi-arrow-left"></i>
        </router-link>
        <h1 class="h5 mb-0 me-auto">{{ bid.title }}</h1>
        <span :class="['badge', `bg-${PROCESSING_STATUS_VARIANT[bid.processing_status]}`]">{{
          bid.processing_status_label
        }}</span>
        <router-link :to="`/bids/${bid.id}`" class="btn btn-sm btn-outline-secondary">
          담당자 화면
        </router-link>
        <button
          class="btn btn-sm btn-primary"
          :disabled="!!jobId || ['EXTRACTING', 'EVALUATING'].includes(bid.processing_status)"
          @click="askExtract"
        >
          <i class="bi bi-magic me-1"></i>추출 실행
        </button>
        <button class="btn btn-sm btn-outline-danger" @click="deleting = bid">삭제</button>
      </div>
      <p class="small text-muted mb-3">
        {{ bid.notice_no || '공고번호 미확인' }} · 첨부 {{ bid.attachment_count }}개 · 품목
        {{ bid.item_count }}개 · 요구사항 {{ bid.requirement_count }}건
      </p>

      <div v-if="jobId" class="card mb-3">
        <div class="card-body">
          <JobProgress :job-id="jobId" label="공고 추출" @done="onExtractDone" />
        </div>
      </div>
      <div v-else-if="bid.processing_status === 'FAILED'" class="alert alert-danger small">
        <strong>추출 실패:</strong> {{ bid.processing_error || '원인을 확인할 수 없습니다.' }}
      </div>
      <div v-else-if="bid.processing_status === 'DRAFT'" class="alert alert-info small">
        첨부를 확인한 뒤 <strong>추출 실행</strong>을 누르면 LLM이 공고 메타데이터·품목·핵심
        요구사항을 추출하고 적합도를 계산합니다.
      </div>

      <ul class="nav nav-tabs mb-3">
        <li v-for="t in TABS" :key="t.key" class="nav-item">
          <a
            class="nav-link"
            :class="{ active: tab === t.key }"
            href="#"
            @click.prevent="setTab(t.key)"
            >{{ t.label }}</a
          >
        </li>
      </ul>

      <div v-if="tab === 'meta'" class="row g-4">
        <div class="col-xl-8">
          <form class="card" @submit.prevent="save">
            <div class="card-body">
              <div v-if="bid.locked_fields.length" class="small mb-3">
                <i class="bi bi-lock me-1"></i>수정해서 잠긴 항목(다시 추출해도 유지):
                <span
                  v-for="key in bid.locked_fields"
                  :key="key"
                  class="badge bg-light text-dark border me-1"
                >
                  {{ fieldLabel(key) }}
                  <a
                    href="#"
                    class="ms-1 text-decoration-none"
                    :aria-label="`${fieldLabel(key)} 잠금 해제`"
                    title="잠금 해제"
                    @click.prevent="unlock(key)"
                    ><i class="bi bi-x"></i
                  ></a>
                </span>
              </div>
              <EntityForm ref="formRef" :fields="FIELDS" :model-value="form" id-prefix="bid" />
            </div>
            <div class="card-footer text-end">
              <button class="btn btn-primary" :disabled="saving">저장</button>
            </div>
          </form>
        </div>
        <div class="col-xl-4">
          <BidFitCard :bid="bid" />
        </div>
      </div>
      <BidAttachmentsTab v-else-if="tab === 'attachments'" :bid="bid" @changed="load" />
      <BidItemsTab v-else-if="tab === 'items'" :bid="bid" @changed="load" />
      <BidRequirementsTab v-else-if="tab === 'requirements'" :bid="bid" @changed="load" />
    </template>

    <BidDeleteModal :bid="deleting" @confirm="doDelete" @cancel="deleting = null" />
    <ConfirmModal
      :show="confirmExtract"
      title="다시 추출"
      :message="`담당자가 수정한 판정 ${bid?.modified_evaluation_count || 0}건이 있습니다.\n잠기지 않은 요구사항은 새로 추출되며, 그 판정도 함께 삭제됩니다. 계속할까요?`"
      confirm-text="추출 실행"
      variant="warning"
      @confirm="runExtract"
      @cancel="confirmExtract = false"
    />
  </div>
</template>
