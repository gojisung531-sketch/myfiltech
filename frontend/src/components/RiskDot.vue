<script setup>
defineProps({ risk: { type: String, default: '' } })
const COLORS = { HIGH: 'text-danger', MEDIUM: 'text-warning', LOW: 'text-success' }
const LABELS = { HIGH: '위험 높음', MEDIUM: '위험 보통', LOW: '위험 낮음' }
</script>

<template>
  <span v-if="risk" :title="LABELS[risk]" class="text-nowrap small">
    <i class="bi bi-circle-fill" :class="COLORS[risk]" style="font-size: 0.6rem"></i>
    <span class="visually-hidden">{{ LABELS[risk] }}</span>
    <span v-if="risk === 'HIGH'" class="text-danger ms-1">HIGH</span>
  </span>
</template>
