<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  accept: { type: Array, default: () => ['.txt', '.docx', '.doc', '.hwp', '.hwpx', '.pdf'] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['files'])

const dragging = ref(false)
const input = ref(null)
const rejected = ref([]) // [{ name, reason }]
const acceptAttr = computed(() => props.accept.join(','))

function pick(fileList) {
  const files = Array.from(fileList || [])
  const ok = []
  rejected.value = []
  for (const file of files) {
    const ext = `.${file.name.split('.').pop().toLowerCase()}`
    if (file.name.endsWith(':Zone.Identifier') || file.name.startsWith('.')) continue
    if (!props.accept.includes(ext)) {
      rejected.value.push({ name: file.name, reason: '지원하지 않는 형식' })
    } else if (file.size === 0) {
      rejected.value.push({ name: file.name, reason: '빈 파일' })
    } else {
      ok.push(file)
    }
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

function open() {
  if (!props.disabled) input.value.click()
}
</script>

<template>
  <div>
    <div
      class="dropzone rounded text-center p-4"
      :class="{ dragging, disabled }"
      role="button"
      tabindex="0"
      :aria-disabled="disabled"
      @click="open"
      @keydown.enter.prevent="open"
      @keydown.space.prevent="open"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <i class="bi bi-cloud-arrow-up fs-2 d-block dropzone-icon"></i>
      <div>파일을 끌어다 놓거나 클릭하여 선택하세요 (여러 개 가능)</div>
      <div class="small text-muted text-break">{{ accept.join(', ') }}</div>
      <input
        ref="input"
        type="file"
        multiple
        class="d-none"
        :accept="acceptAttr"
        @change="onChange"
      />
    </div>
    <div v-if="rejected.length" class="alert alert-danger py-2 small mt-2 mb-0" role="alert">
      선택에서 제외된 파일 {{ rejected.length }}개
      <ul class="mb-0 ps-3">
        <li v-for="(r, i) in rejected" :key="i" class="text-break">
          {{ r.name }} — {{ r.reason }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.dropzone {
  border: 2px dashed var(--ft-border);
  background: var(--ft-surface);
  cursor: pointer;
}
.dropzone:hover,
.dropzone:focus-visible,
.dropzone.dragging {
  border-color: var(--ft-primary);
  background: var(--ft-primary-soft);
  outline: none;
}
.dropzone.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.dropzone-icon {
  color: var(--ft-primary);
}
</style>
