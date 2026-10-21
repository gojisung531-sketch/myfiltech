<script setup>
// 작업(Job) 목록: 상태·진행률·오류, 재시도/취소 (specs/04 §6)
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { cancelJob, listJobs, retryJob } from '@/api/jobs'
import EmptyState from '@/components/EmptyState.vue'
import SettingsNav from '@/components/SettingsNav.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/format'

const TYPES = {
  EXTRACT_DOCUMENT: '문서 처리',
  LOAD_INITIAL_DATA: '초기 데이터 적재',
  EXTRACT_BID: '공고 추출',
  EVALUATE_BID: '판정',
  GENERATE_DRAFT: '초안 생성',
}
const STATUS_VARIANT = {
  PENDING: 'secondary',
  RUNNING: 'info',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  CANCELLED: 'light text-dark border',
}

const toast = useToastStore()
const jobs = ref([])
const count = ref(0)
const page = ref(1)
const loading = ref(false)
const filters = reactive({ status: '', type: '' })
const expanded = ref(null)
let timer = null

async function load(quiet = false) {
  if (!quiet) loading.value = true
  try {
    const params = { page: page.value }
    for (const [k, v] of Object.entries(filters)) if (v) params[k] = v
    const data = await listJobs(params)
    jobs.value = data.results
    count.value = data.count
  } catch (err) {
    if (!quiet) toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
  clearTimeout(timer)
  // keep progress fresh while something is running
  if (jobs.value.some((j) => ['PENDING', 'RUNNING'].includes(j.status))) {
    timer = setTimeout(() => load(true), 3000)
  }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))
watch(filters, () => {
  page.value = 1
  load()
})

async function act(fn, job, message) {
  try {
    await fn(job.id)
    toast.success(message)
    load()
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function goPage(delta) {
  page.value += delta
  load()
}
</script>

<template>
  <div>
    <SettingsNav />
    <div class="d-flex flex-wrap gap-2 mb-3">
      <select
        v-model="filters.type"
        class="form-select form-select-sm w-auto"
        aria-label="작업 유형"
      >
        <option value="">유형: 전체</option>
        <option v-for="(label, value) in TYPES" :key="value" :value="value">{{ label }}</option>
      </select>
      <select v-model="filters.status" class="form-select form-select-sm w-auto" aria-label="상태">
        <option value="">상태: 전체</option>
        <option value="PENDING">대기</option>
        <option value="RUNNING">실행 중</option>
        <option value="SUCCEEDED">완료</option>
        <option value="FAILED">실패</option>
        <option value="CANCELLED">취소</option>
      </select>
      <button class="btn btn-sm btn-outline-secondary ms-auto" @click="load()">
        <i class="bi bi-arrow-clockwise me-1"></i>새로고침
      </button>
    </div>
    <p class="small text-muted">
      작업은 <code>python manage.py run_jobs</code> 워커가 처리합니다. 대기 상태가 계속되면 워커가
      실행 중인지 확인하세요.
    </p>
    <div class="card">
      <div class="table-responsive">
        <table class="table table-sm table-hover align-middle mb-0 small">
          <thead class="table-light">
            <tr>
              <th>ID</th>
              <th>유형</th>
              <th>대상</th>
              <th>상태</th>
              <th style="width: 18%">진행</th>
              <th>등록</th>
              <th>종료</th>
              <th class="text-end">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="8" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!jobs.length">
              <td colspan="8"><EmptyState message="작업이 없습니다." /></td>
            </tr>
            <template v-for="job in jobs" v-else :key="job.id">
              <tr role="button" @click="expanded = expanded === job.id ? null : job.id">
                <td>{{ job.id }}</td>
                <td>{{ TYPES[job.type] || job.type }}</td>
                <td>
                  {{
                    job.target_type ? `${job.target_type.split('.').pop()} #${job.target_id}` : '-'
                  }}
                </td>
                <td>
                  <span class="badge" :class="`bg-${STATUS_VARIANT[job.status]}`">{{
                    job.status_label
                  }}</span>
                  <span v-if="job.attempts > 1" class="text-muted ms-1"
                    >({{ job.attempts }}회)</span
                  >
                </td>
                <td>
                  <div class="progress" style="height: 6px">
                    <div class="progress-bar" :style="{ width: `${job.progress}%` }"></div>
                  </div>
                  <div class="text-muted text-truncate" style="max-width: 16rem">
                    {{ job.message }}
                  </div>
                </td>
                <td class="text-nowrap">{{ formatDateTime(job.created_at) }}</td>
                <td class="text-nowrap">{{ formatDateTime(job.finished_at) }}</td>
                <td class="text-end text-nowrap" @click.stop>
                  <button
                    v-if="['FAILED', 'CANCELLED'].includes(job.status)"
                    class="btn btn-sm btn-outline-primary"
                    @click="act(retryJob, job, '다시 실행하도록 등록했습니다.')"
                  >
                    재시도
                  </button>
                  <button
                    v-if="job.status === 'PENDING'"
                    class="btn btn-sm btn-outline-danger"
                    @click="act(cancelJob, job, '작업을 취소했습니다.')"
                  >
                    취소
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === job.id">
                <td colspan="8" class="bg-light">
                  <div v-if="job.error" class="text-danger mb-2" style="white-space: pre-wrap">
                    {{ job.error }}
                  </div>
                  <div class="fw-semibold">payload</div>
                  <pre class="small mb-2">{{ JSON.stringify(job.payload, null, 2) }}</pre>
                  <div class="fw-semibold">result</div>
                  <pre class="small mb-0">{{ JSON.stringify(job.result, null, 2) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div v-if="count > 20" class="card-footer d-flex justify-content-end gap-2">
        <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="goPage(-1)">
          이전
        </button>
        <span class="small align-self-center">{{ page }} / {{ Math.ceil(count / 20) }}</span>
        <button
          class="btn btn-sm btn-outline-secondary"
          :disabled="page * 20 >= count"
          @click="goPage(1)"
        >
          다음
        </button>
      </div>
    </div>
  </div>
</template>
