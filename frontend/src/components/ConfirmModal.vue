<script setup>
import BaseModal from './BaseModal.vue'

defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '확인' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '확인' },
  variant: { type: String, default: 'danger' },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <BaseModal :show="show" :title="title" @close="emit('cancel')">
    <p class="mb-0" style="white-space: pre-line">{{ message }}</p>
    <template #footer>
      <button class="btn btn-secondary" :disabled="loading" @click="emit('cancel')">취소</button>
      <button :class="`btn btn-${variant}`" :disabled="loading" @click="emit('confirm')">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>{{ confirmText }}
      </button>
    </template>
  </BaseModal>
</template>
