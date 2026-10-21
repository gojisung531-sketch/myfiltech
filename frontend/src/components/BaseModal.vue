<script setup>
// Bootstrap modal markup driven by Vue state (no Bootstrap JS needed).
defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  size: { type: String, default: '' },
})
const emit = defineEmits(['close'])
</script>

<template>
  <template v-if="show">
    <div class="modal d-block" tabindex="-1" role="dialog" @click.self="emit('close')">
      <div class="modal-dialog modal-dialog-scrollable" :class="size ? `modal-${size}` : ''">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ title }}</h5>
            <button type="button" class="btn-close" aria-label="닫기" @click="emit('close')" />
          </div>
          <div class="modal-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop show"></div>
  </template>
</template>
