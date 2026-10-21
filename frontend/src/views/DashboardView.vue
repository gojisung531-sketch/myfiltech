<script setup>
// Dashboard cards + bid list (specs/05 §2).
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { dashboardSummary, listBids } from '@/api/bids'
import EmptyState from '@/components/EmptyState.vue'
import FitScoreBar from '@/components/FitScoreBar.vue'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/utils/errors'
import { dDay, formatDateTime, isPast, PROCESSING_STATUS_VARIANT } from '@/utils/format'
import { BID_OUTCOMES } from '@/utils/options'

const PAGE_SIZE = 20
const router = useRouter()
const auth = useAuthStore()
// null = 아직 불러오지 못함(실패 시 0건으로 표시하지 않는다)
const summary = ref(null)
const error = ref('')
const bids = ref([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const filters = reactive({
  review_status: '',
  is_power_plant: '',
  fit_min: '',
  closing: '',
  outcome: '',
  q: '',
  ordering: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value }
    for (const [key, value] of Object.entries(filters)) if (value !== '') params[key] = value
    const [data, counts] = await Promise.all([listBids(params), dashboardSummary()])
    bids.value = data.results
    count.value = data.count
    summary.value = counts
  } catch (err) {
    bids.value = []
    count.value = 0
    summary.value = null
    error.value = errorMessage(err, '입찰 공고를 불러오지 못했습니다.')
  } finally {
    loading.value = false
  }
}

let timer = null
watch(filters, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})
onMounted(load)

function setReview(status) {
  filters.review_status = status
}

const hasFilters = computed(() => Object.values(filters).some((v) => v !== ''))
function resetFilters() {
  for (const key of Object.keys(filters)) filters[key] = ''
}

function goPage(delta) {
  page.value += delta
  load()
}

const CARDS = [
  { key: 'total', label: '총 입찰 건수', status: '', icon: 'bi-collection', color: 'brand' },
  {
    key: 'reviewed',
    label: '확인 건수',
    status: 'REVIEWED',
    icon: 'bi-check2-circle',
    color: 'ok',
  },
  {
    key: 'unreviewed',
    label: '미확인 건수',
    status: 'UNREVIEWED',
    icon: 'bi-hourglass-split',
    color: 'warn',
  },
]
</script>

<template>
  <div>
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-3">
      <div>
        <h2 class="h4 mb-0">입찰 공고 현황</h2>
        <div class="small text-muted">
          공고를 선택하면 요구사항 비교와 판정 근거를 확인할 수 있습니다.
        </div>
      </div>
      <router-link v-if="auth.isAdmin" to="/admin/bids/new" class="btn btn-sm btn-primary">
        <i class="bi bi-plus-lg me-1"></i>공고 등록
      </router-link>
    </div>

    <div v-if="error" class="alert alert-danger d-flex align-items-center gap-2" role="alert">
      <i class="bi bi-exclamation-octagon"></i>
      <span class="flex-grow-1">{{ error }}</span>
      <button class="btn btn-sm btn-outline-secondary" @click="load">다시 시도</button>
    </div>

    <div class="row g-3 mb-4">
      <div v-for="card in CARDS" :key="card.key" class="col-12 col-sm-4">
        <button
          type="button"
          class="card stat-card w-100 text-start h-100"
          :class="[`stat-${card.color}`, { active: filters.review_status === card.status }]"
          :aria-pressed="filters.review_status === card.status"
          @click="setReview(card.status)"
        >
          <div class="card-body d-flex align-items-center">
            <i class="bi fs-2 me-3 stat-icon" :class="card.icon"></i>
            <div>
              <div class="small text-muted">{{ card.label }}</div>
              <div class="fs-3 fw-semibold">{{ summary ? summary[card.key] : '-' }}</div>
            </div>
          </div>
        </button>
      </div>
    </div>

    <div class="row g-2 mb-3">
      <div class="col-12 col-sm-6 col-lg-3">
        <input
          v-model="filters.q"
          class="form-control form-control-sm"
          placeholder="공고명, 수요기관, 공고번호"
          aria-label="검색"
        />
      </div>
      <div class="col-6 col-sm-auto">
        <select
          v-model="filters.review_status"
          class="form-select form-select-sm"
          aria-label="확인 상태"
        >
          <option value="">확인 상태: 전체</option>
          <option value="UNREVIEWED">미확인</option>
          <option value="REVIEWED">확인</option>
        </select>
      </div>
      <div class="col-6 col-sm-auto">
        <select v-model="filters.closing" class="form-select form-select-sm" aria-label="마감">
          <option value="">마감: 전체</option>
          <option value="before">마감 전</option>
          <option value="after">마감 후</option>
        </select>
      </div>
      <div class="col-6 col-sm-auto">
        <select v-model="filters.fit_min" class="form-select form-select-sm" aria-label="적합도">
          <option value="">적합도: 전체</option>
          <option value="70">70 이상</option>
          <option value="40">40 이상</option>
        </select>
      </div>
      <div class="col-6 col-sm-auto">
        <select v-model="filters.outcome" class="form-select form-select-sm" aria-label="낙찰 결과">
          <option value="">낙찰 결과: 전체</option>
          <option v-for="o in BID_OUTCOMES" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="col-auto">
        <div class="form-check mt-1">
          <input
            id="pp-only"
            class="form-check-input"
            type="checkbox"
            :checked="filters.is_power_plant === 'true'"
            @change="filters.is_power_plant = $event.target.checked ? 'true' : ''"
          />
          <label class="form-check-label small" for="pp-only">발전소 공고만</label>
        </div>
      </div>
      <div class="col-6 col-sm-auto ms-sm-auto">
        <select v-model="filters.ordering" class="form-select form-select-sm" aria-label="정렬">
          <option value="">미확인 우선 · 마감 임박순</option>
          <option value="fit">적합도 높은순</option>
          <option value="created">최근 등록순</option>
        </select>
      </div>
      <div v-if="hasFilters" class="col-auto">
        <button class="btn btn-sm btn-outline-secondary" @click="resetFilters">
          <i class="bi bi-arrow-counterclockwise me-1"></i>초기화
        </button>
      </div>
    </div>

    <div class="card">
      <div class="card-header small text-muted">
        <span v-if="!error">조건에 맞는 공고 {{ count }}건</span>
        <span v-else>목록을 불러오지 못했습니다.</span>
      </div>
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0 bid-table">
          <thead>
            <tr>
              <th>확인</th>
              <th>공고번호</th>
              <th>공고명 · 수요기관</th>
              <th>입찰 마감</th>
              <th
                title="공고 요구사항과 회사 자료를 비교해 계산한 기술 적합도입니다. 낙찰 확률이 아닙니다."
              >
                기술 적합도
              </th>
              <th>판정 요약</th>
              <th>매칭 제품</th>
              <th>처리 상태</th>
              <th>결과</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="9" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!bids.length">
              <td colspan="9">
                <EmptyState
                  v-if="error"
                  icon="bi-exclamation-triangle"
                  message="서버에서 목록을 받지 못했습니다."
                />
                <EmptyState
                  v-else-if="hasFilters"
                  message="조건에 맞는 입찰 공고가 없습니다. 검색어나 필터를 바꿔 보세요."
                />
                <EmptyState v-else message="등록된 입찰 공고가 없습니다.">
                  <router-link
                    v-if="auth.isAdmin"
                    to="/admin/bids/new"
                    class="btn btn-sm btn-primary"
                  >
                    공고 등록
                  </router-link>
                </EmptyState>
              </td>
            </tr>
            <tr
              v-for="bid in bids"
              v-else
              :key="bid.id"
              role="button"
              :class="{ 'past-bid': isPast(bid.bid_close_at) }"
              @click="router.push(`/bids/${bid.id}`)"
            >
              <td>
                <span v-if="bid.review_status === 'REVIEWED'" class="badge bg-success">확인</span>
                <span v-else class="badge bg-secondary">미확인</span>
              </td>
              <td class="small text-nowrap">{{ bid.notice_no || '-' }}</td>
              <td>
                <router-link :to="`/bids/${bid.id}`" class="fw-semibold text-break" @click.stop>{{
                  bid.title
                }}</router-link>
                <div class="small text-muted text-break">{{ bid.buyer_org || '-' }}</div>
              </td>
              <td class="small text-nowrap">
                {{ formatDateTime(bid.bid_close_at) }}
                <div v-if="bid.bid_close_at" class="text-muted">{{ dDay(bid.bid_close_at) }}</div>
              </td>
              <td><FitScoreBar :score="bid.fit_score" /></td>
              <td class="text-nowrap">
                <template v-if="bid.verdict_counts?.total">
                  <span class="badge bg-success me-1" title="충족">{{
                    bid.verdict_counts.MET
                  }}</span>
                  <span class="badge bg-warning text-dark me-1" title="보완 필요">{{
                    bid.verdict_counts.NEEDS_SUPPLEMENT
                  }}</span>
                  <span class="badge bg-info text-dark" title="확인 필요">{{
                    bid.verdict_counts.NEEDS_CONFIRMATION
                  }}</span>
                </template>
                <span v-else class="text-muted small">-</span>
              </td>
              <td class="small text-break">{{ bid.matched_models.join(', ') || '-' }}</td>
              <td>
                <span
                  :class="['badge', `bg-${PROCESSING_STATUS_VARIANT[bid.processing_status]}`]"
                  >{{ bid.processing_status_label }}</span
                >
              </td>
              <td class="small">{{ bid.outcome_label }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="count > PAGE_SIZE" class="card-footer d-flex justify-content-end gap-2">
        <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="goPage(-1)">
          이전
        </button>
        <span class="small align-self-center">{{ page }} / {{ Math.ceil(count / PAGE_SIZE) }}</span>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="page * PAGE_SIZE >= count"
          @click="goPage(1)"
        >
          다음
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.past-bid td {
  color: var(--ft-muted);
  background-color: var(--ft-bg);
}
.bid-table {
  min-width: 56rem;
}
.bid-table thead th {
  background-color: var(--ft-primary-soft);
  color: var(--ft-text);
  white-space: nowrap;
  font-size: 0.85rem;
}
.bid-table td:nth-child(3) {
  min-width: 16rem;
  max-width: 28rem;
}
.stat-card {
  cursor: pointer;
}
.stat-card.active {
  border-color: var(--ft-primary);
  box-shadow: 0 0 0 1px var(--ft-primary);
}
.stat-brand .stat-icon {
  color: var(--ft-primary);
}
.stat-ok .stat-icon {
  color: var(--ft-ok-fg);
}
.stat-warn .stat-icon {
  color: var(--ft-warn-fg);
}
</style>
