<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  accept: { type: Array, default: () => ['.txt', '.docx', '.doc', '.hwp', '.hwpx', '.pdf'] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['files'])

const dragging = ref(false)
const input = ref(null)
const rejected = ref([])
const acceptAttr = computed(() => props.accept.join(','))

function pick(fileList) {
  const files = Array.from(fileList || [])
  const ok = []
  rejected.value = []
  for (const file of files) {
    const ext = `.${file.name.split('.').pop().toLowerCase()}`
    if (file.name.endsWith(':Zone.Identifier') || file.name.startsWith('.')) continue
    if (props.accept.includes(ext)) ok.push(file)
    else rejected.value.push(file.name)
  }
  if (ok.length) emit('files', ok)
}

function onDrop(event) {
  dragging.value = false
  if (!props.disabled) pick(event.dataTransfer.files)
}

function onChange(event) {
  pick(event.target.files)
  event.target.value = ''
}
</script>

<template>
  <div>
    <div
      class="dropzone rounded border border-2 text-center p-4"
      :class="{ 'border-primary bg-light': dragging, 'opacity-50': disabled }"
      role="button"
      tabindex="0"
      @click="!disabled && input.click()"
      @keydown.enter="!disabled && input.click()"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <i class="bi bi-cloud-arrow-up fs-2 d-block text-secondary"></i>
      <div>파일을 끌어다 놓거나 클릭하여 선택하세요 (여러 개 가능)</div>
      <div class="small text-muted">{{ accept.join(', ') }}</div>
      <input
        ref="input"
        type="file"
        multiple
        class="d-none"
        :accept="acceptAttr"
        @change="onChange"
      />
    </div>
    <div v-if="rejected.length" class="text-danger small mt-1">
      지원하지 않는 형식이라 제외: {{ rejected.join(', ') }}
    </div>
  </div>
</template>

<style scoped>
.dropzone {
  border-style: dashed !important;
  cursor: pointer;
}
</style>
