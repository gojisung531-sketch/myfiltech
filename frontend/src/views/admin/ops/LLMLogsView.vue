<script setup>
// LLM 호출 로그: 작업·모델·토큰·지연·상태 필터, 응답 원문 보기 (specs/04 §6, specs/07 §5)
import { onMounted, reactive, ref, watch } from 'vue'

import { getLLMLog, listLLMLogs } from '@/api/jobs'
import BaseModal from '@/components/BaseModal.vue'
import EmptyState from '@/components/EmptyState.vue'
import SettingsNav from '@/components/SettingsNav.vue'
import { useToastStore } from '@/stores/toast'
import { errorMessage } from '@/utils/errors'
import { formatDateTime, formatNumber } from '@/utils/format'

const toast = useToastStore()
const logs = ref([])
const count = ref(0)
const summary = ref(null)
const page = ref(1)
const loading = ref(false)
const filters = reactive({ task_key: '', status: '', provider: '', date_from: '', date_to: '' })
const detail = ref(null)

async function load() {
  loading.value = true
  try {
    const params = { page: page.value }
    for (const [k, v] of Object.entries(filters)) if (v) params[k] = v
    const data = await listLLMLogs(params)
    logs.value = data.results
    count.value = data.count
    summary.value = data.summary
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    loading.value = false
  }
}
onMounted(load)
let timer = null
watch(filters, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

async function open(row) {
  try {
    detail.value = await getLLMLog(row.id)
  } catch (err) {
    toast.error(errorMessage(err))
  }
}

function goPage(delta) {
  page.value += delta
  load()
}

const STATUS_VARIANT = { OK: 'success', ERROR: 'danger', INVALID_JSON: 'warning text-dark' }
</script>

<template>
  <div>
    <SettingsNav />
    <div v-if="summary" class="row g-3 mb-3">
      <div
        v-for="[key, label] in [
          ['today', '오늘'],
          ['month', '이번 달'],
        ]"
        :key="key"
        class="col-md-6"
      >
        <div class="card">
          <div class="card-body small">
            <div class="text-muted">{{ label }}</div>
            <span class="fs-5 fw-semibold me-3">{{ formatNumber(summary[key].calls) }}회</span>
            입력 {{ formatNumber(summary[key].input_tokens) }} · 출력
            {{ formatNumber(summary[key].output_tokens) }} 토큰
          </div>
        </div>
      </div>
    </div>
    <div class="row g-2 mb-3">
      <div class="col-sm-3">
        <input
          v-model="filters.task_key"
          class="form-control form-control-sm"
          placeholder="작업 키 (예: bid.extract)"
          aria-label="작업 키"
        />
      </div>
      <div class="col-auto">
        <select v-model="filters.status" class="form-select form-select-sm" aria-label="상태">
          <option value="">상태: 전체</option>
          <option value="OK">성공</option>
          <option value="ERROR">오류</option>
          <option value="INVALID_JSON">응답 형식 오류</option>
        </select>
      </div>
      <div class="col-auto">
        <select v-model="filters.provider" class="form-select form-select-sm" aria-label="제공자">
          <option value="">제공자: 전체</option>
          <option value="ANTHROPIC">Claude</option>
          <option value="OPENAI">ChatGPT</option>
          <option value="GEMINI">Gemini</option>
        </select>
      </div>
      <div class="col-auto">
        <input
          v-model="filters.date_from"
          type="date"
          class="form-control form-control-sm"
          aria-label="시작일"
        />
      </div>
      <div class="col-auto">
        <input
          v-model="filters.date_to"
          type="date"
          class="form-control form-control-sm"
          aria-label="종료일"
        />
      </div>
    </div>
    <div class="card">
      <div class="table-responsive">
        <table class="table table-sm table-hover align-middle mb-0 small">
          <thead class="table-light">
            <tr>
              <th>일시</th>
              <th>작업</th>
              <th>모델</th>
              <th class="text-end">입력</th>
              <th class="text-end">출력</th>
              <th class="text-end">지연</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="7" class="text-center py-4">
                <span class="spinner-border spinner-border-sm"></span>
              </td>
            </tr>
            <tr v-else-if="!logs.length">
              <td colspan="7"><EmptyState message="호출 기록이 없습니다." /></td>
            </tr>
            <tr v-for="log in logs" v-else :key="log.id" role="button" @click="open(log)">
              <td class="text-nowrap">{{ formatDateTime(log.created_at) }}</td>
              <td>
                {{ log.task_key }}
                <span v-if="log.prompt_version" class="text-muted">v{{ log.prompt_version }}</span>
              </td>
              <td>{{ log.model_id }}</td>
              <td class="text-end">{{ formatNumber(log.request_tokens) }}</td>
              <td class="text-end">{{ formatNumber(log.response_tokens) }}</td>
              <td class="text-end text-nowrap">{{ (log.latency_ms / 1000).toFixed(1) }}s</td>
              <td>
                <span class="badge" :class="`bg-${STATUS_VARIANT[log.status] || 'secondary'}`">{{
                  log.status_label
                }}</span>
                <div v-if="log.error" class="text-danger text-truncate" style="max-width: 18rem">
                  {{ log.error }}
                </div>
              </td>
            </tr>
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

    <BaseModal :show="!!detail" :title="`LLM 호출 #${detail?.id}`" size="xl" @close="detail = null">
      <template v-if="detail">
        <p class="small text-muted">
          {{ detail.task_key }} · {{ detail.provider }} {{ detail.model_id }} ·
          {{ formatDateTime(detail.created_at)
          }}<span v-if="detail.job"> · 작업 #{{ detail.job }}</span>
        </p>
        <div v-if="detail.error" class="alert alert-danger small">{{ detail.error }}</div>
        <div class="fw-semibold small">요청 (앞부분)</div>
        <pre class="log-text">{{ detail.request_excerpt }}</pre>
        <div class="fw-semibold small">응답 원문</div>
        <pre class="log-text">{{ detail.response_text || '(없음)' }}</pre>
      </template>
    </BaseModal>
  </div>
</template>

<style scoped>
.log-text {
  max-height: 22rem;
  overflow: auto;
  white-space: pre-wrap;
  background: var(--bs-light);
  padding: 0.5rem;
  font-size: 0.75rem;
}
</style>
