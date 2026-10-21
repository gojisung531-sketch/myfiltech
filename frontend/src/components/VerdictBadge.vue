<script setup>
// 충족=녹색, 보완 필요=주황, 확인 필요=파랑 (specs/05 §3 ③)
defineProps({
  verdict: { type: String, default: '' },
  small: { type: Boolean, default: false },
})
const STYLES = {
  MET: ['bg-success', '충족'],
  NEEDS_SUPPLEMENT: ['bg-warning text-dark', '보완 필요'],
  NEEDS_CONFIRMATION: ['bg-info text-dark', '확인 필요'],
}
</script>

<template>
  <span v-if="STYLES[verdict]" class="badge" :class="[STYLES[verdict][0], { 'fw-normal': small }]">
    {{ STYLES[verdict][1] }}
  </span>
  <span v-else class="badge bg-light text-muted border">미판정</span>
</template>
