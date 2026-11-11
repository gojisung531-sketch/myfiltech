<script setup>
// 기본 정보 한 항목: 자동 입력된 값을 고칠 수 있고, 원문 근거와 안내를 접어서 보여 준다.
defineProps({
  field: { type: Object, required: true },
  modelValue: { type: String, default: '' },
  edited: { type: Boolean, default: false },
  quote: { type: String, default: '' },
  warnings: { type: Array, default: () => [] },
  kept: { type: Boolean, default: false },
  auto: { type: Boolean, default: false }, // 자동으로 채워진 값인가
  disabled: { type: Boolean, default: false },
  canRestore: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'edit', 'restore'])

function onInput(e) {
  emit('update:modelValue', e.target.value)
  emit('edit')
}
</script>

<template>
  <div :class="field.col">
    <label class="form-label small mb-1" :for="`nf-${field.key}`">
      {{ field.label }}
      <span v-if="edited" class="badge bg-secondary ms-1">직접 수정</span>
      <span v-else-if="auto" class="badge bg-info ms-1">자동 입력</span>
    </label>
    <div class="input-group input-group-sm">
      <textarea
        v-if="field.type === 'textarea'"
        :id="`nf-${field.key}`"
        :value="modelValue"
        class="form-control form-control-sm"
        rows="3"
        :disabled="disabled"
        @input="onInput"
      ></textarea>
      <input
        v-else
        :id="`nf-${field.key}`"
        :value="modelValue"
        class="form-control form-control-sm"
        :type="
          field.type === 'datetime' ? 'datetime-local' : field.type === 'number' ? 'number' : 'text'
        "
        :min="field.type === 'number' ? 0 : undefined"
        :disabled="disabled"
        @input="onInput"
      />
      <span v-if="field.unit" class="input-group-text">{{ field.unit }}</span>
    </div>
    <div v-if="kept" class="small text-warning-emphasis mt-1">
      새로 읽은 값이 다르지만, 직접 수정한 값을 그대로 두었습니다.
      <button
        v-if="canRestore"
        type="button"
        class="btn btn-link btn-sm p-0 align-baseline"
        @click="$emit('restore')"
      >
        읽은 값으로 바꾸기
      </button>
    </div>
    <div v-for="(w, i) in warnings" :key="i" class="small text-warning-emphasis mt-1">
      <i class="bi bi-exclamation-triangle me-1"></i>{{ w.message }}
    </div>
    <details v-if="quote" class="ft-help mt-1">
      <summary>원문 근거</summary>
      <p class="mb-0 text-break nf-quote">{{ quote }}</p>
    </details>
  </div>
</template>

<style scoped>
.nf-quote {
  white-space: pre-wrap;
  border-left: 3px solid var(--ft-border);
  padding-left: 0.5rem;
}
</style>
