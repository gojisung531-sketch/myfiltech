<script setup>
// ≥70 높음(녹), 40–69 보통(황), <40 낮음(회) — specs/08 §6.2
import { computed } from 'vue'

const props = defineProps({ score: { type: Number, default: null } })
const variant = computed(() =>
  props.score >= 70 ? 'bg-success' : props.score >= 40 ? 'bg-warning' : 'bg-secondary',
)
</script>

<template>
  <div v-if="score !== null" class="d-flex align-items-center gap-2" style="min-width: 7rem">
    <div class="progress flex-grow-1" style="height: 6px">
      <div class="progress-bar" :class="variant" :style="{ width: `${score}%` }"></div>
    </div>
    <span class="small fw-semibold" style="width: 1.8rem">{{ score }}</span>
  </div>
  <span v-else class="text-muted small">-</span>
</template>
