<script setup>
// Renders form inputs from a field config. JSON/tag fields are edited as text and
// converted by collect(); call it via a template ref before saving.
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  fields: { type: Array, required: true },
  modelValue: { type: Object, required: true },
  idPrefix: { type: String, default: 'f' },
})

const INPUT_TYPES = { number: 'number', date: 'date', datetime: 'datetime-local' }
const texts = reactive({})
// The parent owns the object; fields are edited in place (the parent passes a fresh copy).
const model = computed(() => props.modelValue)

function toText(field, value) {
  if (field.type === 'json') return value == null ? '' : JSON.stringify(value, null, 2)
  if (field.type === 'tags') return (value || []).join(', ')
  return value
}

watch(
  () => props.modelValue,
  (model) => {
    for (const field of props.fields) {
      if (['json', 'tags'].includes(field.type)) texts[field.key] = toText(field, model[field.key])
    }
  },
  { immediate: true },
)

function collect() {
  const payload = {}
  for (const field of props.fields) {
    if (field.readonly) continue
    let value = props.modelValue[field.key]
    if (field.type === 'json') {
      const text = (texts[field.key] || '').trim()
      try {
        value = text ? JSON.parse(text) : (field.empty ?? null)
      } catch {
        throw new Error(`'${field.label}' 항목이 올바른 JSON이 아닙니다.`)
      }
    } else if (field.type === 'tags') {
      value = (texts[field.key] || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    } else if (field.type === 'number') {
      value = value === '' || value === null || value === undefined ? null : Number(value)
    } else if (['date', 'datetime'].includes(field.type) && !value) {
      value = null
    }
    payload[field.key] = value
  }
  return payload
}

defineExpose({ collect })
</script>

<template>
  <div class="row g-3">
    <div v-for="field in fields" :key="field.key" :class="field.col || 'col-md-6'">
      <template v-if="field.type === 'checkbox'">
        <div class="form-check mt-md-4">
          <input
            :id="`${idPrefix}-${field.key}`"
            v-model="model[field.key]"
            class="form-check-input"
            type="checkbox"
            :disabled="field.readonly"
          />
          <label class="form-check-label" :for="`${idPrefix}-${field.key}`">
            {{ field.label }}
          </label>
        </div>
      </template>
      <template v-else>
        <label class="form-label small mb-1" :for="`${idPrefix}-${field.key}`">
          {{ field.label }}<span v-if="field.required" class="text-danger"> *</span>
          <span v-if="field.unit" class="text-muted"> ({{ field.unit }})</span>
        </label>
        <select
          v-if="field.type === 'select'"
          :id="`${idPrefix}-${field.key}`"
          v-model="model[field.key]"
          class="form-select form-select-sm"
          :required="field.required"
          :disabled="field.readonly"
        >
          <option v-if="!field.required" :value="null">-</option>
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <select
          v-else-if="field.type === 'multiselect'"
          :id="`${idPrefix}-${field.key}`"
          v-model="model[field.key]"
          class="form-select form-select-sm"
          multiple
          size="4"
        >
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <textarea
          v-else-if="field.type === 'textarea'"
          :id="`${idPrefix}-${field.key}`"
          v-model="model[field.key]"
          class="form-control form-control-sm"
          :rows="field.rows || 3"
          :readonly="field.readonly"
        ></textarea>
        <textarea
          v-else-if="field.type === 'json'"
          :id="`${idPrefix}-${field.key}`"
          v-model="texts[field.key]"
          class="form-control form-control-sm font-monospace"
          :rows="field.rows || 4"
          spellcheck="false"
        ></textarea>
        <input
          v-else-if="field.type === 'tags'"
          :id="`${idPrefix}-${field.key}`"
          v-model="texts[field.key]"
          class="form-control form-control-sm"
          placeholder="쉼표로 구분"
        />
        <input
          v-else
          :id="`${idPrefix}-${field.key}`"
          v-model="model[field.key]"
          class="form-control form-control-sm"
          :type="INPUT_TYPES[field.type] || 'text'"
          :step="field.type === 'number' ? 'any' : undefined"
          :required="field.required"
          :readonly="field.readonly"
        />
        <div v-if="field.help" class="form-text">{{ field.help }}</div>
      </template>
    </div>
  </div>
</template>
