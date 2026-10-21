<script setup>
// Polls GET /api/jobs/{id} every 2s and shows progress (specs/01 §5, specs/11 §1).
import { onBeforeUnmount, ref, watch } from 'vue'

import { getJob } from '@/api/jobs'

const props = defineProps({
  jobId: { type: Number, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['done'])

const job = ref(null)
let timer = null
const FINISHED = ['SUCCEEDED', 'FAILED', 'CANCELLED']

async function poll() {
  try {
    job.value = await getJob(props.jobId)
  } catch {
    job.value = { status: 'FAILED', error: '작업 상태를 불러오지 못했습니다.', progress: 0 }
  }
  if (FINISHED.includes(job.value.status)) {
    emit('done', job.value)
    return
  }
  timer = setTimeout(poll, 2000)
}

watch(
  () => props.jobId,
  () => {
    clearTimeout(timer)
    job.value = null
    poll()
  },
  { immediate: true },
)
onBeforeUnmount(() => clearTimeout(timer))

const variant = (status) =>
  ({ SUCCEEDED: 'bg-success', FAILED: 'bg-danger', CANCELLED: 'bg-secondary' })[status] ||
  'progress-bar-striped progress-bar-animated'
</script>

<template>
  <div class="small">
    <div class="d-flex justify-content-between mb-1">
      <span>{{ label }} {{ job?.message || job?.status_label || '대기 중' }}</span>
      <span>{{ job?.progress ?? 0 }}%</span>
    </div>
    <div class="progress" style="height: 6px">
      <div
        class="progress-bar"
        :class="variant(job?.status)"
        :style="{ width: `${job?.status === 'FAILED' ? 100 : job?.progress || 5}%` }"
      ></div>
    </div>
    <div v-if="job?.status === 'FAILED'" class="text-danger mt-1">{{ job.error }}</div>
  </div>
</template>
