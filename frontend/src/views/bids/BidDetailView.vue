<script setup>
// Bid detail for bid managers: header + 5 step tabs (specs/05 §3, specs/11 BidDetailView).
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { evaluateBid, getBid, reviewBid } from '@/api/bids'
import { downloadReportPdf } from '@/api/drafts'
import BaseModal from '@/components/BaseModal.vue'
import FitScoreBar from '@/components/FitScoreBar.vue'
import JobProgress from '@/components/JobProgress.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { saveResponse } from '@/utils/download'
import { dDay, formatDateTime, formatKrw, PROCESSING_STATUS_VARIANT } from '@/utils/format'

import BidComparisonTab from './BidComparisonTab.vue'
import BidDraftsTab from './BidDraftsTab.vue'
import BidEvaluationTab from './BidEvaluationTab.vue'
import BidOverviewTab from './BidOverviewTab.vue'
import BidReviewTab from './BidReviewTab.vue'

const TABS = [
  { key: 'requirements', label: '① 핵심 요구사항' },
  { key: 'comparison', label: '② 회사 자료 비교' },
  { key: 'evaluation', label: '③ 판정 및 자동 답변' },
  { key: 'drafts', label: '④ 초안 생성' },
  { key: 'review', label: '⑤ 결과 확인' },
]

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const bid = ref(null)
const jobId = ref(null)
const refreshKey = ref(0)
const reviewing = ref(false)
const downloading = ref(false)
const rerun = reactive({ show: false, keepModified: true })

const bidId = computed(() => Number(route.params.id))
const tab = computed(() => route.query.tab || 'requirements')
const busy = computed(
  () => !!jobId.value || ['EXTRACTING', 'EVALUATING'].includes(bid.value?.processing_status),
)

async function load() {
  try {
    bid.value = await getBid(bidId.value)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
onMounted(load)
watch(bidId, load)

function setTab(key) {
  router.replace({ query: { ...route.query, tab: key } })
}

async function startEvaluation({ keepModified = true, requirementIds } = {}) {
  try {
    const res = await evaluateBid(bidId.value, { keepModified, requirementIds })
    jobId.value = res.job_id
    rerun.show = false
  } catch (err) {
    if (err.response?.data?.code !== 'llm_not_configured') toast.error(errorMessage(err))
  }
}

async function onJobDone(job) {
  jobId.value = null
  if (job.status === 'SUCCEEDED') {
    const c = job.result.counts
    toast.success(
      `판정 완료: 충족 ${c.MET} · 보완 필요 ${c.NEEDS_SUPPLEMENT} · 확인 필요 ${c.NEEDS_CONFIRMATION}` +
        (job.result.skipped_modified ? ` (수정된 ${job.result.skipped_modified}건 유지)` : ''),
    )
  } else if (job.status === 'FAILED') {
    toast.error(job.error || '판정에 실패했습니다.')
  }
  await load()
  refreshKey.value += 1
}

async function downloadReport() {
  downloading.value = true
  try {
    saveResponse(await downloadReportPdf(bidId.value), 'report.pdf')
  } catch (err) {
    toast.error(errorMessage(err, 'PDF를 만들지 못했습니다.'))
  } finally {
    downloading.value = false
  }
}

async function toggleReview() {
  reviewing.value = true
  try {
    const reviewed = bid.value.review_status !== 'REVIEWED'
    bid.value = await reviewBid(bidId.value, reviewed)
    toast.success(reviewed ? '확인 완료로 표시했습니다.' : '확인을 취소했습니다.')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    reviewing.value = false
  }
}

// A tab changed data itself (verdict edit, matched product): refresh the header only, so the
// tab keeps its state (expanded rows, filters). Other tabs reload when opened.
async function onChanged() {
  await load()
}
</script>

<template>
  <div>
    <div v-if="!bid" class="text-center py-5"><span class="spinner-border"></span></div>
    <template v-else>
      <div class="card mb-3">
        <div class="card-body">
          <div class="d-flex flex-wrap align-items-start gap-2">
            <div class="me-auto">
              <div class="small text-muted mb-1">
                <router-link to="/" class="text-decoration-none">
                  <i class="bi bi-arrow-left"></i> 목록
                </router-link>
                · {{ bid.notice_no || '공고번호 미확인' }} · {{ bid.buyer_org || '-' }}
              </div>
              <h1 class="h5 mb-1">{{ bid.title }}</h1>
              <div class="d-flex flex-wrap gap-1">
                <span v-if="bid.review_status === 'REVIEWED'" class="badge bg-success">
                  확인 완료 ({{ bid.reviewed_by_name }})
                </span>
                <span v-else class="badge bg-light text-dark border">미확인</span>
                <span
                  :class="['badge', `bg-${PROCESSING_STATUS_VARIANT[bid.processing_status]}`]"
                  >{{ bid.processing_status_label }}</span
                >
                <span v-if="bid.reference.is_simulation" class="badge bg-secondary">
                  과거 공고 — 오늘({{ bid.reference.date }}) 기준 판정
                </span>
                <span v-else class="badge bg-light text-dark border">
                  판정 기준일 {{ bid.reference.date }}
                </span>
                <span v-if="bid.outcome !== 'PENDING'" class="badge bg-light text-dark border">{{
                  bid.outcome_label
                }}</span>
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <button
                class="btn btn-sm"
                :class="bid.review_status === 'REVIEWED' ? 'btn-outline-secondary' : 'btn-success'"
                :disabled="reviewing"
                @click="toggleReview"
              >
                <i class="bi bi-check2-circle me-1"></i>
                {{ bid.review_status === 'REVIEWED' ? '확인 취소' : '확인 완료' }}
              </button>
              <button
                class="btn btn-sm btn-primary"
                :disabled="busy || !bid.requirement_count"
                @click="rerun.show = true"
              >
                <i class="bi bi-arrow-repeat me-1"></i>판정
                {{ bid.verdict_counts?.total ? '재실행' : '실행' }}
              </button>
              <button
                class="btn btn-sm btn-outline-secondary"
                :disabled="downloading"
                title="통합 보고서 PDF (표지·검토 보고서·판정·초안)"
                @click="downloadReport"
              >
                <span v-if="downloading" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="bi bi-file-earmark-pdf me-1"></i>PDF 다운로드
              </button>
            </div>
          </div>
          <dl class="row small mb-0 mt-3">
            <dt class="col-sm-2 col-lg-1">입찰 마감</dt>
            <dd class="col-sm-4 col-lg-3">
              {{ formatDateTime(bid.bid_close_at) }}
              <span v-if="bid.bid_close_at" class="text-muted">({{ dDay(bid.bid_close_at) }})</span>
            </dd>
            <dt class="col-sm-2 col-lg-1">사업금액</dt>
            <dd class="col-sm-4 col-lg-3">
              {{ formatKrw(bid.budget_krw) }}
              <span class="text-muted">/ 추정 {{ formatKrw(bid.estimated_price_krw) }}</span>
            </dd>
            <dt class="col-sm-2 col-lg-1">입찰방법</dt>
            <dd class="col-sm-4 col-lg-3">{{ bid.bid_method || '-' }}</dd>
            <dt class="col-sm-2 col-lg-1">적합도</dt>
            <dd class="col-sm-4 col-lg-3"><FitScoreBar :score="bid.fit_score" /></dd>
          </dl>
        </div>
      </div>

      <div v-if="jobId" class="card mb-3">
        <div class="card-body">
          <JobProgress :job-id="jobId" label="판정" @done="onJobDone" />
        </div>
      </div>
      <div
        v-else-if="bid.processing_status === 'FAILED' && bid.processing_error"
        class="alert alert-danger small"
      >
        {{ bid.processing_error }}
      </div>
      <div class="alert alert-light border small py-2">
        <i class="bi bi-info-circle me-1"></i>판정·답변·초안은 모두 자동 생성된
        <strong>초안</strong>입니다. 최종 제출 전 담당자가 검토해야 합니다.
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

      <BidOverviewTab v-if="tab === 'requirements'" :key="`r${refreshKey}`" :bid="bid" />
      <BidComparisonTab
        v-else-if="tab === 'comparison'"
        :key="`c${refreshKey}`"
        :bid="bid"
        :busy="busy"
        @evaluate="startEvaluation"
        @changed="onChanged"
      />
      <BidEvaluationTab
        v-else-if="tab === 'evaluation'"
        :key="`e${refreshKey}`"
        :bid="bid"
        :busy="busy"
        @evaluate="startEvaluation"
        @changed="onChanged"
      />
      <BidDraftsTab v-else-if="tab === 'drafts'" :key="`d${refreshKey}`" :bid="bid" />
      <BidReviewTab
        v-else-if="tab === 'review'"
        :bid="bid"
        :reviewing="reviewing"
        :downloading="downloading"
        @toggle="toggleReview"
        @download="downloadReport"
      />
    </template>

    <BaseModal :show="rerun.show" title="판정 실행" @close="rerun.show = false">
      <p class="small">
        요구사항마다 규칙 엔진으로 먼저 판정하고, LLM이 근거 서술과 자동 답변을 작성합니다. 규칙으로
        확정된 판정은 LLM이 바꾸지 않습니다.
      </p>
      <div class="form-check">
        <input
          id="keep-modified"
          v-model="rerun.keepModified"
          class="form-check-input"
          type="checkbox"
        />
        <label class="form-check-label small" for="keep-modified">
          담당자가 수정한 판정은 유지 ({{ bid?.modified_evaluation_count || 0 }}건)
        </label>
      </div>
      <template #footer>
        <button class="btn btn-secondary" @click="rerun.show = false">취소</button>
        <button
          class="btn btn-primary"
          @click="startEvaluation({ keepModified: rerun.keepModified })"
        >
          실행
        </button>
      </template>
    </BaseModal>
  </div>
</template>
