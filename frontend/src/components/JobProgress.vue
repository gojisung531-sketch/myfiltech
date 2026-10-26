<script setup>
// GET /api/jobs/{id}를 2초마다 조회해 서버가 알려 준 상태만 보여 준다(specs/01 §5, specs/11 §1).
// - 통신 오류는 작업 실패가 아니다: 마지막으로 확인한 상태를 유지하고 다시 확인 버튼을 제공한다.
// - done은 서버가 종료 상태(SUCCEEDED/FAILED/CANCELLED)를 돌려줬을 때만, 작업당 한 번 발생한다.
// - 대기(PENDING)에서는 진행 막대·예상 시간을 만들지 않는다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getJob } from '@/api/jobs'

const props = defineProps({
  jobId: { type: Number, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['done'])

const FINISHED = ['SUCCEEDED', 'FAILED', 'CANCELLED']
const POLL_MS = 2000
const SLOW_WAIT_MS = 2 * 60 * 1000

const job = ref(null) // 마지막으로 서버에서 받은 상태
const lastChecked = ref(null)
const failed = ref(false) // 마지막 조회가 통신 오류
const checking = ref(false)
const now = ref(Date.now())

let timer = null
let ticker = null
let controller = null
let seq = 0
let doneSent = false

function stop() {
  clearTimeout(timer)
  timer = null
  if (controller) controller.abort()
  controller = null
  seq += 1 // 이미 나간 응답은 무시한다
}

async function poll() {
  clearTimeout(timer)
  if (controller) controller.abort()
  const mine = ++seq
  const id = props.jobId
  controller = new AbortController()
  checking.value = true
  try {
    const data = await getJob(id, { signal: controller.signal })
    if (mine !== seq || data?.id !== id) return // 이전 작업·오래된 응답
    job.value = data
    lastChecked.value = new Date()
    failed.value = false
    checking.value = false
    if (FINISHED.includes(data.status)) {
      if (!doneSent) {
        doneSent = true
        emit('done', data)
      }
      return
    }
    timer = setTimeout(poll, POLL_MS)
  } catch (err) {
    if (mine !== seq || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return
    // 통신 오류: 작업 상태를 바꾸지 않고, 자동 반복도 멈춘 뒤 사용자가 다시 확인하게 한다.
    failed.value = true
    checking.value = false
  }
}

watch(
  () => props.jobId,
  () => {
    stop()
    job.value = null
    lastChecked.value = null
    failed.value = false
    doneSent = false
    poll()
  },
  { immediate: true },
)
ticker = setInterval(() => (now.value = Date.now()), 15000)
onBeforeUnmount(() => {
  stop()
  clearInterval(ticker)
})

const status = computed(() => job.value?.status || '')
const waitedMs = computed(() => {
  if (status.value !== 'PENDING' || !job.value?.created_at) return 0
  return now.value - new Date(job.value.created_at).getTime()
})
const slowWait = computed(() => waitedMs.value > SLOW_WAIT_MS)
const progress = computed(() => Math.max(0, Math.min(100, Number(job.value?.progress) || 0)))
const checkedText = computed(() =>
  lastChecked.value ? lastChecked.value.toLocaleTimeString('ko-KR', { hour12: false }) : '',
)
const barClass = computed(
  () =>
    ({ SUCCEEDED: 'bg-success', CANCELLED: 'bg-secondary' })[status.value] ||
    'progress-bar-striped progress-bar-animated',
)
</script>

<template>
  <div class="small">
    <div v-if="!job && !failed" class="text-muted">
      <span class="spinner-border spinner-border-sm me-1"></span>{{ label }} 상태를 확인하는 중…
    </div>
    <div v-else-if="!job" class="text-muted">{{ label }} 작업 상태를 아직 확인하지 못했습니다.</div>

    <template v-else-if="status === 'PENDING'">
      <div>
        <span class="badge bg-secondary me-1">대기</span>{{ label }} <strong>실행 대기</strong> —
        아직 분석을 시작하지 않았습니다.
      </div>
      <div v-if="slowWait" class="text-muted mt-1">
        대기가 길어지고 있습니다. 작업 처리 프로그램(<code>run_jobs</code>)이 실행 중인지 서버
        환경을 확인하세요. 화면에서는 작업 처리 프로그램의 상태를 알 수 없습니다.
      </div>
    </template>

    <template v-else-if="status === 'RUNNING'">
      <div class="d-flex justify-content-between mb-1">
        <span
          ><span class="badge bg-primary me-1">실행 중</span>{{ label }}
          {{ job.message || '' }}</span
        >
        <span>{{ progress }}%</span>
      </div>
      <div class="progress" style="height: 6px">
        <div class="progress-bar" :class="barClass" :style="{ width: `${progress}%` }"></div>
      </div>
    </template>

    <template v-else>
      <div>
        <span
          class="badge me-1"
          :class="
            { SUCCEEDED: 'bg-success', FAILED: 'bg-danger', CANCELLED: 'bg-secondary' }[status] ||
            'bg-secondary'
          "
          >{{ job.status_label || status }}</span
        >{{ label }} {{ job.message || '' }}
      </div>
      <div v-if="status === 'FAILED' && job.error" class="text-danger mt-1 text-break">
        {{ job.error }}
      </div>
    </template>

    <div v-if="failed" class="alert alert-warning py-1 px-2 mt-2 mb-0" role="alert">
      <i class="bi bi-wifi-off me-1"></i>상태를 확인하지 못했습니다.
      <span v-if="job">마지막으로 확인한 상태({{ checkedText }})를 그대로 표시합니다.</span>
      <button
        type="button"
        class="btn btn-sm btn-outline-secondary ms-2"
        :disabled="checking"
        @click="poll"
      >
        다시 확인
      </button>
    </div>
  </div>
</template>
