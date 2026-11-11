<script setup>
import { onMounted, reactive, ref, watch } from 'vue'

import { deleteBid, listBids } from '@/api/bids'
import EmptyState from '@/components/EmptyState.vue'
import BidDeleteModal from '@/views/admin/bids/BidDeleteModal.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatDateTime, formatKrw, PROCESSING_STATUS_VARIANT } from '@/utils/format'
import { BID_OUTCOMES, PROCESSING_STATUSES } from '@/utils/options'

const PAGE_SIZE = 20
const toast = useToastStore()
const bids = ref([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const filters = reactive({ q: '', processing_status: '', outcome: '', ordering: 'created' })
const removing = ref(null)

async function load() {
  loading.value = true
  try {
    const params = { page: page.value }
    for (const [key, value] of Object.entries(filters)) if (value) params[key] = value
    const data = await listBids(params)
    bids.value = data.results
    count.value = data.count
  } catch (err) {
    toast.error(errorMessage(err))
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

function goPage(delta) {
  page.value += delta
  load()
}

async function doDelete(bid) {
  try {
    await deleteBid(bid.id)
    toast.success('공고를 삭제했습니다.')
    removing.value = null
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}
</script>

<template>
  <div>
    <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
      <h1 class="h4 mb-0 me-auto">입찰 공고 관리</h1>
      <router-link to="/admin/bids/new" class="btn btn-sm btn-primary">
        <i class="bi bi-plus-lg me-1"></i>공고 등록
      </router-link>
    </div>

    <div class="row g-2 mb-3">
      <div class="col-sm-4 col-lg-3">
        <input
          v-model="filters.q"
          class="form-control form-control-sm"
          placeholder="공고명, 공고번호, 수요기관"
          aria-label="검색"
        />
      </div>
      <div class="col-auto">
        <select
          v-model="filters.processing_status"
          class="form-select form-select-sm"
          aria-label="처리 상태"
        >
          <option value="">처리 상태: 전체</option>
          <option v-for="o in PROCESSING_STATUSES" :key="o.value" :value="o.value">
            {{ o.label }}
          </option>
        </select>
      </div>
      <div class="col-auto">
        <select v-model="filters.outcome" class="form-select form-select-sm" aria-label="낙찰 결과">
          <option value="">낙찰 결과: 전체</option>
          <option v-for="o in BID_OUTCOMES" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="col-auto">
        <select v-model="filters.ordering" class="form-select form-select-sm" aria-label="정렬">
          <option value="created">최근 등록순</option>
          <option value="fit">적합도 높은순</option>
          <option value="-closing">마감 최근순</option>
        </select>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover table-sm align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th>공고</th>
              <th>수요기관</th>
              <th>입찰 마감</th>
              <th class="text-end">예산</th>
              <th class="text-end">적합도</th>
              <th>처리 상태</th>
              <th>결과</th>
              <th class="text-end">첨부/요구</th>
              <th class="text-end">작업</th>
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
                  message="등록된 입찰 공고가 없습니다. 공고 등록으로 공고 파일을 올려 주세요."
                >
                  <router-link to="/admin/bids/new" class="btn btn-sm btn-primary"
                    >공고 등록</router-link
                  >
                </EmptyState>
              </td>
            </tr>
            <tr v-for="bid in bids" v-else :key="bid.id">
              <td>
                <router-link :to="`/admin/bids/${bid.id}/edit`" class="fw-semibold">{{
                  bid.title
                }}</router-link>
                <div class="small text-muted">
                  {{ bid.notice_no || '공고번호 미확인' }}
                  <span v-if="bid.source_ref && bid.source_ref !== bid.notice_no">
                    · 폴더 {{ bid.source_ref }}</span
                  >
                </div>
              </td>
              <td class="small">{{ bid.buyer_org || '-' }}</td>
              <td class="small text-nowrap">{{ formatDateTime(bid.bid_close_at) }}</td>
              <td class="small text-end text-nowrap">{{ formatKrw(bid.budget_krw) }}</td>
              <td class="text-end">
                <span v-if="bid.fit_score !== null" class="fw-semibold">{{ bid.fit_score }}</span>
                <span v-else class="text-muted">-</span>
              </td>
              <td>
                <router-link
                  :to="`/bids/${bid.id}`"
                  class="status-link"
                  :title="`${bid.title} — 담당자용 상세 화면 열기`"
                  :aria-label="`${bid.title}: ${bid.processing_status_label}, 담당자용 상세 화면 열기`"
                >
                  <span
                    :class="['badge', `bg-${PROCESSING_STATUS_VARIANT[bid.processing_status]}`]"
                    >{{ bid.processing_status_label }}</span
                  >
                </router-link>
              </td>
              <td class="small">{{ bid.outcome_label }}</td>
              <td class="small text-end">
                {{ bid.attachment_count }} / {{ bid.requirement_count }}
              </td>
              <td class="text-end text-nowrap">
                <router-link
                  :to="`/admin/bids/${bid.id}/edit`"
                  class="btn btn-sm btn-outline-primary me-1"
                  >편집</router-link
                >
                <button class="btn btn-sm btn-outline-danger" @click="removing = bid">삭제</button>
              </td>
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

    <BidDeleteModal :bid="removing" @confirm="doDelete" @cancel="removing = null" />
  </div>
</template>

<style scoped>
.status-link {
  text-decoration: none;
}
.status-link:hover .badge {
  text-decoration: underline;
}
</style>
