<script setup>
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
</script>

<template>
  <div class="toast-container position-fixed bottom-0 end-0 p-3">
    <div
      v-for="item in toast.items"
      :key="item.id"
      class="toast show align-items-center border-0"
      :class="`text-white bg-${item.variant}`"
      role="alert"
    >
      <div class="d-flex">
        <div class="toast-body">{{ item.message }}</div>
        <button
          type="button"
          class="btn-close btn-close-white me-2 m-auto"
          aria-label="닫기"
          @click="toast.dismiss(item.id)"
        ></button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toast-container {
  z-index: 1100;
}
</style>
