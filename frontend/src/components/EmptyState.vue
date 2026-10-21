<script setup>
defineProps({
  icon: { type: String, default: 'bi-inbox' },
  message: { type: String, default: '표시할 항목이 없습니다.' },
})
</script>

<template>
  <div class="text-center text-muted py-5">
    <i :class="['bi', icon, 'fs-1', 'd-block', 'mb-2']"></i>
    {{ message }}
    <div v-if="$slots.default" class="mt-3"><slot /></div>
  </div>
</template>
