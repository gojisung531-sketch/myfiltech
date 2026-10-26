<script setup>
// 현재 공고의 대기·실행 중 작업을 서버에서 찾아 추적한다(새로고침·재진입 후에도 복구).
// localStorage의 작업 ID는 쓰지 않고, GET /api/jobs 목록을 target_type/target_id로 대조한다.
// 이 화면은 작업을 만들거나 취소·재시도하지 않는다.
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { findActiveBidJobs, getBidJob } from '@/api/jobs'
import JobProgress from '@/components/JobProgress.vue'

const props = defineProps({ bidId: { type: Number, required: true } })
// busy: 작업이 있거나 아직 확인하지 못함 → 실행 버튼을 막는다. unknown: 조회 실패.
const emit = defineEmits(['update:busy', 'update:unknown', 'done'])

const LABELS = { EXTRACT_BID: '공고 추출', EVALUATE_BID: '판정' }

const tracked = ref([]) // [{ id, type }]
const scanning = ref(true)
const scanError = ref(false)

let controller = null
let seq = 0

const busy = computed(() => scanning.value || scanError.value || tracked.value.length > 0)
watch(busy, (v) => emit('update:busy', v), { immediate: true })
watch(scanError, (v) => emit('update:unknown', v), { immediate: true })

function add(job) {
  if (!tracked.value.some((t) => t.id === job.id)) {
    tracked.value = [...tracked.value, { id: job.id, type: job.type }].sort((a, b) => a.id - b.id)
  }
}

async function scan() {
  if (controller) controller.abort()
  const mine = ++seq
  controller = new AbortController()
  scanning.value = true
  scanError.value = false
  try {
    const jobs = await findActiveBidJobs(props.bidId, { signal: controller.signal })
    if (mine !== seq) return // 다른 공고로 이동했거나 더 새로운 조회가 있다
    jobs.forEach(add)
    scanning.value = false
  } catch (err) {
    if (mine !== seq || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return
    // 조회 실패는 "작업 없음"이 아니다. 실행 버튼은 계속 막고 다시 확인하게 한다.
    scanError.value = true
    scanning.value = false
  }
}

// 부모가 방금 시작한 작업(추출 실행 응답의 job_id)을 바로 추적한다.
function track(jobId, type = 'EXTRACT_BID') {
  add({ id: jobId, type })
}

async function onJobDone(job) {
  tracked.value = tracked.value.filter((t) => t.id !== job.id)
  emit('done', job)
  // 추출 뒤 자동 판정이 이어지면 같은 공고의 후속 작업을 찾아 이어서 보여 준다.
  const followId = job.result?.evaluate_job_id
  if (followId) {
    try {
      const follow = await getBidJob(props.bidId, followId)
      if (follow && !['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(follow.status)) add(follow)
    } catch {
      // 아래 재조회에서 다시 확인한다.
    }
  }
  scan()
}

watch(
  () => props.bidId,
  () => {
    tracked.value = []
    scan()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  seq += 1
  if (controller) controller.abort()
})
defineExpose({ track, scan })
</script>

<template>
  <div>
    <div v-if="scanError" class="alert alert-warning small" role="alert">
      <i class="bi bi-wifi-off me-1"></i>이 공고의 진행 중 작업을 확인하지 못했습니다. 확인되기
      전에는 추출·판정을 새로 시작할 수 없습니다.
      <button type="button" class="btn btn-sm btn-outline-secondary ms-2" @click="scan">
        다시 확인
      </button>
    </div>
    <div v-else-if="scanning && !tracked.length" class="small text-muted mb-2" role="status">
      <span class="spinner-border spinner-border-sm me-1"></span>진행 중인 작업을 확인하는 중…
    </div>
    <div v-for="t in tracked" :key="t.id" class="card mb-2">
      <div class="card-body py-2">
        <JobProgress :job-id="t.id" :label="LABELS[t.type] || '작업'" @done="onJobDone" />
      </div>
    </div>
  </div>
</template>
